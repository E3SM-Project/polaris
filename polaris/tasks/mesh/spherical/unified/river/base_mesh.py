import os

import numpy as np
import xarray as xr
from mpas_tools.mesh.interpolation import interp_bilin
from shapely.geometry import LineString

from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.river.lat_lon import (
    build_river_network_dataset,
)
from polaris.tasks.mesh.spherical.unified.river.source import (
    RiverSegment,
    _haversine_distance,
    _read_geojson,
    _write_geojson,
    read_river_segments_from_feature_collection,
    river_segments_to_feature_collection,
)


class PrepareRiverForBaseMeshStep(Step):
    """
    Prepare clipped river products for base-mesh consumers.
    """

    def __init__(self, component, prepare_step, coastline_step, subdir):
        super().__init__(
            component=component,
            name='river_base_mesh',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.prepare_step = prepare_step
        self.coastline_step = coastline_step
        self.clipped_filename = 'clipped_river_network.geojson'
        self.clipped_outlets_filename = 'clipped_outlets.geojson'
        self.masks_filename = 'clipped_river_network.nc'

    def setup(self):
        """
        Link simplified river and coastline products and declare outputs.
        """
        convention = self.config.get(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        self.add_input_file(
            filename='simplified_river_network.geojson',
            work_dir_target=os.path.join(
                self.prepare_step.path, self.prepare_step.simplified_filename
            ),
        )
        self.add_input_file(
            filename='retained_outlets.geojson',
            work_dir_target=os.path.join(
                self.prepare_step.path, self.prepare_step.outlets_filename
            ),
        )
        self.add_input_file(
            filename='coastline.nc',
            work_dir_target=os.path.join(
                self.coastline_step.path,
                self.coastline_step.output_filenames[convention],
            ),
        )
        self.add_output_file(filename=self.clipped_filename)
        self.add_output_file(filename=self.clipped_outlets_filename)
        self.add_output_file(filename=self.masks_filename)

    def run(self):
        """
        Clip and simplify the retained river network for base-mesh use.
        """
        section = self.config['river_network']
        river_fc = _read_geojson('simplified_river_network.geojson')
        outlet_fc = _read_geojson('retained_outlets.geojson')
        with xr.open_dataset('coastline.nc') as ds_coastline:
            segments = read_river_segments_from_feature_collection(river_fc)
            clipped_segments = condition_base_mesh_river_segments(
                segments=segments,
                ds_coastline=ds_coastline,
                clip_distance_m=1.0e3
                * section.getfloat('base_mesh_clip_distance_km'),
                simplify_tolerance_deg=_km_to_equatorial_degrees(
                    section.getfloat('base_mesh_simplify_tolerance_km')
                ),
                min_segment_length_m=1.0e3
                * section.getfloat('base_mesh_min_segment_length_km'),
                preserve_outlet_stub_m=1.0e3
                * section.getfloat('base_mesh_preserve_outlet_stub_km'),
            )
            clipped_fc = river_segments_to_feature_collection(clipped_segments)
            clipped_outlets_fc = clip_outlet_feature_collection(
                outlet_feature_collection=outlet_fc,
                ds_coastline=ds_coastline,
                clip_distance_m=1.0e3
                * section.getfloat('base_mesh_clip_distance_km'),
            )
            ds_river, _ = build_river_network_dataset(
                river_feature_collection=clipped_fc,
                outlet_feature_collection=clipped_outlets_fc,
                ds_coastline=ds_coastline,
                resolution=self.config.getfloat(
                    'unified_mesh', 'resolution_latlon'
                ),
                outlet_match_tolerance=self.config['river_lat_lon'].getfloat(
                    'outlet_match_tolerance'
                ),
                channel_subsegment_fraction=self.config[
                    'river_lat_lon'
                ].getfloat('channel_subsegment_fraction'),
                channel_buffer_km=self.config['river_lat_lon'].getfloat(
                    'channel_buffer_km'
                ),
            )

        metadata = dict(
            mesh_name=self.config.get('unified_mesh', 'mesh_name'),
            resolution_latlon=self.config.getfloat(
                'unified_mesh', 'resolution_latlon'
            ),
            source_river_step=self.prepare_step.subdir,
            source_coastline_step=self.coastline_step.subdir,
            clip_distance_m=1.0e3
            * section.getfloat('base_mesh_clip_distance_km'),
            simplify_tolerance_km=section.getfloat(
                'base_mesh_simplify_tolerance_km'
            ),
            min_segment_length_km=section.getfloat(
                'base_mesh_min_segment_length_km'
            ),
            preserve_outlet_stub_km=section.getfloat(
                'base_mesh_preserve_outlet_stub_km'
            ),
        )
        clipped_fc['metadata'] = metadata
        clipped_outlets_fc['metadata'] = dict(metadata)
        ds_river.attrs.update(metadata)
        _write_geojson(clipped_fc, self.clipped_filename)
        _write_geojson(clipped_outlets_fc, self.clipped_outlets_filename)
        ds_river.to_netcdf(self.masks_filename)


def condition_base_mesh_river_segments(
    segments,
    ds_coastline,
    clip_distance_m,
    simplify_tolerance_deg,
    min_segment_length_m,
    preserve_outlet_stub_m=0.0,
):
    """
    Clip, simplify, and clean river segments for base-mesh use.
    """
    clipped_segments: list[RiverSegment] = []
    lon = ds_coastline.lon.values.astype(float)
    lat = ds_coastline.lat.values.astype(float)
    signed_distance = ds_coastline.signed_distance.values.astype(float)
    threshold_m = -float(clip_distance_m)

    for segment in segments:
        clipped_geometries = _clip_line_string_by_signed_distance(
            geometry=segment.geometry,
            lon=lon,
            lat=lat,
            signed_distance=signed_distance,
            threshold_m=threshold_m,
            preserve_outlet_stub_m=preserve_outlet_stub_m,
        )
        for geometry in clipped_geometries:
            simplified = geometry.simplify(
                simplify_tolerance_deg, preserve_topology=False
            )
            cleaned = _clean_conditioned_geometry(
                simplified, min_segment_length_m
            )
            if cleaned is None:
                continue
            clipped_segments.append(
                _conditioned_segment_from_geometry(segment, cleaned)
            )

    return sorted(
        clipped_segments,
        key=lambda segment: (
            segment.outlet_hyriv_id or -1,
            -segment.drainage_area,
            segment.hyriv_id,
            tuple(segment.geometry.coords[-1]),
        ),
    )


def clip_outlet_feature_collection(
    outlet_feature_collection,
    ds_coastline,
    clip_distance_m,
):
    """
    Retain only outlets that remain inland after base-mesh clipping.
    """
    lon = ds_coastline.lon.values.astype(float)
    lat = ds_coastline.lat.values.astype(float)
    signed_distance = ds_coastline.signed_distance.values.astype(float)
    threshold_m = -float(clip_distance_m)
    features = []

    for feature in outlet_feature_collection['features']:
        point_lon, point_lat = feature['geometry']['coordinates']
        point_distance = float(
            _interpolate_signed_distance(
                coords=np.array([[point_lon, point_lat]], dtype=float),
                lon=lon,
                lat=lat,
                signed_distance=signed_distance,
            )[0]
        )
        if point_distance <= threshold_m:
            features.append(feature)

    return dict(type='FeatureCollection', features=features)


def _conditioned_segment_from_geometry(segment, geometry):
    outlet_type = segment.outlet_type
    outlet_hyriv_id = segment.outlet_hyriv_id
    if geometry.coords[-1] != segment.geometry.coords[-1]:
        outlet_type = None
        outlet_hyriv_id = None

    return RiverSegment(
        geometry=geometry,
        hyriv_id=segment.hyriv_id,
        main_riv=segment.main_riv,
        ord_stra=segment.ord_stra,
        drainage_area=segment.drainage_area,
        next_down=segment.next_down,
        endorheic=segment.endorheic,
        river_name=segment.river_name,
        outlet_type=outlet_type,
        outlet_hyriv_id=outlet_hyriv_id,
    )


def _clean_conditioned_geometry(geometry, min_segment_length_m):
    """
    Drop degenerate or too-short conditioned geometries.
    """
    if not isinstance(geometry, LineString):
        return None

    coords = np.asarray(geometry.coords, dtype=float)
    if coords.shape[0] < 2:
        return None

    deduped = [coords[0]]
    for point in coords[1:]:
        if not np.allclose(deduped[-1], point):
            deduped.append(point)

    if len(deduped) < 2:
        return None

    cleaned = LineString(np.asarray(deduped))
    if _line_string_length_m(cleaned) < min_segment_length_m:
        return None

    return cleaned


def _clip_line_string_by_signed_distance(
    geometry,
    lon,
    lat,
    signed_distance,
    threshold_m,
    preserve_outlet_stub_m,
):
    coords = np.asarray(geometry.coords, dtype=float)
    point_signed_distance = _interpolate_signed_distance(
        coords=coords,
        lon=lon,
        lat=lat,
        signed_distance=signed_distance,
    )
    clipped_coords = _clip_coords_by_threshold(
        coords=coords,
        point_signed_distance=point_signed_distance,
        threshold_m=threshold_m,
    )
    if len(clipped_coords) == 0 and preserve_outlet_stub_m > 0.0:
        stub = _build_outlet_stub(
            coords=coords,
            point_signed_distance=point_signed_distance,
            threshold_m=threshold_m,
            preserve_outlet_stub_m=preserve_outlet_stub_m,
        )
        if stub is not None:
            clipped_coords = [stub]

    return [LineString(line) for line in clipped_coords if len(line) >= 2]


def _build_outlet_stub(
    coords,
    point_signed_distance,
    threshold_m,
    preserve_outlet_stub_m,
):
    for start_index in range(coords.shape[0] - 1, 0, -1):
        start_point = coords[start_index - 1]
        end_point = coords[start_index]
        start_distance = float(point_signed_distance[start_index - 1])
        end_distance = float(point_signed_distance[start_index])
        if start_distance <= threshold_m or end_distance <= threshold_m:
            continue

        crossing = _interpolate_threshold_crossing(
            start_point=start_point,
            end_point=end_point,
            start_distance=start_distance,
            end_distance=end_distance,
            threshold_m=threshold_m,
        )
        stub = LineString([crossing, end_point])
        if _line_string_length_m(stub) >= preserve_outlet_stub_m:
            return np.vstack([crossing, end_point])

    return None


def _clip_coords_by_threshold(coords, point_signed_distance, threshold_m):
    clipped_lines: list[np.ndarray] = []
    current_points: list[np.ndarray] = []

    for start_index in range(coords.shape[0] - 1):
        start_point = coords[start_index]
        end_point = coords[start_index + 1]
        start_distance = float(point_signed_distance[start_index])
        end_distance = float(point_signed_distance[start_index + 1])
        start_valid = start_distance <= threshold_m
        end_valid = end_distance <= threshold_m

        if start_valid and not current_points:
            _append_point_if_distinct(current_points, start_point)

        if start_valid and end_valid:
            _append_point_if_distinct(current_points, end_point)
            continue

        if start_valid and not end_valid:
            _append_point_if_distinct(
                current_points,
                _interpolate_threshold_crossing(
                    start_point=start_point,
                    end_point=end_point,
                    start_distance=start_distance,
                    end_distance=end_distance,
                    threshold_m=threshold_m,
                ),
            )
            if len(current_points) >= 2:
                clipped_lines.append(np.vstack(current_points))
            current_points = []
            continue

        if not start_valid and end_valid:
            _append_point_if_distinct(
                current_points,
                _interpolate_threshold_crossing(
                    start_point=start_point,
                    end_point=end_point,
                    start_distance=start_distance,
                    end_distance=end_distance,
                    threshold_m=threshold_m,
                ),
            )
            _append_point_if_distinct(current_points, end_point)

    if len(current_points) >= 2:
        clipped_lines.append(np.vstack(current_points))

    return clipped_lines


def _line_string_length_m(geometry):
    coords = np.asarray(geometry.coords, dtype=float)
    if coords.shape[0] < 2:
        return 0.0

    segment_lengths = _haversine_distance(
        coords[:-1, 0],
        coords[:-1, 1],
        coords[1:, 0],
        coords[1:, 1],
    )
    return float(np.sum(segment_lengths))


def _km_to_equatorial_degrees(distance_km):
    return float(distance_km) / 111.0


def _interpolate_signed_distance(coords, lon, lat, signed_distance):
    sample_lon = np.asarray(coords[:, 0], dtype=float)
    interp_lon, interp_field, sample_lon = (
        _prepare_periodic_longitude_interpolation(
            lon=lon,
            field=signed_distance,
            sample_lon=sample_lon,
        )
    )
    sample_lat = np.asarray(coords[:, 1], dtype=float)
    return interp_bilin(
        x=interp_lon,
        y=lat,
        field=interp_field,
        xCell=sample_lon,
        yCell=sample_lat,
    )


def _prepare_periodic_longitude_interpolation(lon, field, sample_lon):
    lon = np.asarray(lon, dtype=float)
    field = np.asarray(field)
    sample_lon = np.asarray(sample_lon, dtype=float)

    if lon.ndim != 1 or lon.size < 2:
        return lon, field, sample_lon

    lon_spacing = np.diff(lon)
    if not np.all(lon_spacing > 0.0):
        return lon, field, sample_lon

    spacing = float(np.median(lon_spacing))
    includes_periodic_endpoint = np.isclose(
        lon[-1] - lon[0], 360.0, atol=spacing * 0.5
    )
    omits_periodic_endpoint = np.isclose(
        lon[-1] - lon[0] + spacing, 360.0, atol=spacing * 0.5
    )

    if not includes_periodic_endpoint and not omits_periodic_endpoint:
        return lon, field, sample_lon

    original_sample_lon = sample_lon.copy()
    sample_lon = lon[0] + np.mod(sample_lon - lon[0], 360.0)

    if includes_periodic_endpoint:
        wrap_mask = np.isclose(sample_lon, lon[0]) & (
            original_sample_lon > lon[-1]
        )
        sample_lon[wrap_mask] = lon[-1]
        return lon, field, sample_lon

    lon = np.append(lon, lon[0] + 360.0)
    field = np.concatenate([field, field[:, :1]], axis=1)
    return lon, field, sample_lon


def _interpolate_threshold_crossing(
    start_point,
    end_point,
    start_distance,
    end_distance,
    threshold_m,
):
    if np.isclose(end_distance, start_distance):
        fraction = 0.5
    else:
        fraction = (threshold_m - start_distance) / (
            end_distance - start_distance
        )

    fraction = float(np.clip(fraction, 0.0, 1.0))
    return start_point + fraction * (end_point - start_point)


def _append_point_if_distinct(points, point):
    point = np.asarray(point, dtype=np.float64)
    if len(points) == 0 or not np.allclose(points[-1], point):
        points.append(point)
