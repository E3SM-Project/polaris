import os

import numpy as np
import xarray as xr
from mpas_tools.mesh.interpolation import interp_bilin
from shapely.geometry import LineString

from polaris.mesh.spherical.unified.river.distance import (
    haversine_distance,
)
from polaris.mesh.spherical.unified.river.geojson import (
    read_geojson,
    write_geojson,
)
from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.river.rasterize import (
    build_river_network_dataset,
)
from polaris.tasks.mesh.spherical.unified.river.simplify import (
    RiverSegment,
    read_river_segments_from_feature_collection,
    river_segments_to_feature_collection,
)


class ClipRiverNetworkStep(Step):
    """
    Prepare clipped river products for base-mesh consumers.
    """

    def __init__(self, component, simplify_step, coastline_step, subdir):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        simplify_step : polaris.tasks.mesh.spherical.unified.river.simplify.SimplifyRiverNetworkStep
            The shared simplify river network step

        coastline_step : polaris.Step
            The shared coastline step

        subdir : str
            The subdirectory within the component's work directory
        """  # noqa: E501
        super().__init__(
            component=component,
            name='river_clip',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.simplify_step = simplify_step
        self.coastline_step = coastline_step
        self.clipped_filename = 'clipped_river_network.geojson'
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
                self.simplify_step.path, self.simplify_step.simplified_filename
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
        self.add_output_file(filename=self.masks_filename)

    def run(self):
        """
        Clip and simplify the retained river network for base-mesh use.
        """
        section = self.config['river_network']
        river_fc = read_geojson('simplified_river_network.geojson')
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
            )
            clipped_fc = river_segments_to_feature_collection(clipped_segments)
            ds_river = build_river_network_dataset(
                river_feature_collection=clipped_fc,
                ds_coastline=ds_coastline,
                resolution=self.config.getfloat(
                    'unified_mesh', 'resolution_latlon'
                ),
                channel_subsegment_fraction=self.config[
                    'river_rasterize'
                ].getfloat('channel_subsegment_fraction'),
                channel_buffer_km=self.config['river_rasterize'].getfloat(
                    'channel_buffer_km'
                ),
            )

        metadata = dict(
            mesh_name=self.config.get('unified_mesh', 'mesh_name'),
            resolution_latlon=self.config.getfloat(
                'unified_mesh', 'resolution_latlon'
            ),
            source_river_step=self.simplify_step.subdir,
            source_coastline_step=self.coastline_step.subdir,
            clip_distance_m=1.0e3
            * section.getfloat('base_mesh_clip_distance_km'),
            simplify_tolerance_km=section.getfloat(
                'base_mesh_simplify_tolerance_km'
            ),
            min_segment_length_km=section.getfloat(
                'base_mesh_min_segment_length_km'
            ),
        )
        clipped_fc['metadata'] = metadata
        ds_river.attrs.update(metadata)
        write_geojson(clipped_fc, self.clipped_filename)
        ds_river.to_netcdf(self.masks_filename)


def condition_base_mesh_river_segments(
    segments,
    ds_coastline,
    clip_distance_m,
    simplify_tolerance_deg,
    min_segment_length_m,
):
    """
    Clip, simplify, and clean river segments for base-mesh use.

    Parameters
    ----------
    segments : list of RiverSegment
        River segments to condition

    ds_coastline : xarray.Dataset
        Coastline dataset with ``signed_distance``, ``lon``, and ``lat``
        variables

    clip_distance_m : float
        Distance inland from the coastline at which segments are clipped,
        in meters; segment portions seaward of this boundary are removed

    simplify_tolerance_deg : float
        Douglas-Peucker simplification tolerance applied after clipping,
        in degrees

    min_segment_length_m : float
        Minimum retained segment length after simplification, in meters

    Returns
    -------
    list of RiverSegment
        Conditioned segments sorted by network size (outlet drainage area,
        largest first), then by segment drainage area and HydroRIVERS
        identifier within each network
    """
    clipped_segments: list[RiverSegment] = []
    lon = ds_coastline.lon.values.astype(float)
    lat = ds_coastline.lat.values.astype(float)
    signed_distance = ds_coastline.signed_distance.values.astype(float)
    threshold_m = -float(clip_distance_m)

    all_coords = [
        np.asarray(seg.geometry.coords, dtype=float) for seg in segments
    ]
    seg_sizes = [len(c) for c in all_coords]
    if seg_sizes:
        all_distances = _interpolate_signed_distance(
            coords=np.vstack(all_coords),
            lon=lon,
            lat=lat,
            signed_distance=signed_distance,
        )
        per_segment_distances = np.split(
            all_distances, np.cumsum(seg_sizes)[:-1]
        )
    else:
        per_segment_distances = []

    for segment, coords, point_signed_distance in zip(
        segments, all_coords, per_segment_distances, strict=True
    ):
        clipped_geometries = _clip_line_string_with_distances(
            coords=coords,
            point_signed_distance=point_signed_distance,
            threshold_m=threshold_m,
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

    outlet_area_by_id = {
        s.outlet_hyriv_id: s.drainage_area
        for s in segments
        if s.outlet_hyriv_id is not None and s.hyriv_id == s.outlet_hyriv_id
    }
    return sorted(
        clipped_segments,
        key=lambda segment: (
            -outlet_area_by_id.get(_get_outlet_hyriv_id(segment), 0.0),
            -segment.drainage_area,
            segment.hyriv_id,
            tuple(segment.geometry.coords[-1]),
        ),
    )


def _conditioned_segment_from_geometry(segment, geometry):
    return RiverSegment(
        geometry=geometry,
        hyriv_id=segment.hyriv_id,
        main_riv=segment.main_riv,
        ord_stra=segment.ord_stra,
        drainage_area=segment.drainage_area,
        next_down=segment.next_down,
        endorheic=segment.endorheic,
        river_name=segment.river_name,
        outlet_hyriv_id=segment.outlet_hyriv_id,
    )


def _get_outlet_hyriv_id(segment):
    """
    Get a sortable basin-root identifier for a river segment.
    """
    if segment.outlet_hyriv_id is None:
        return 0
    return segment.outlet_hyriv_id


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


def _clip_line_string_with_distances(
    coords,
    point_signed_distance,
    threshold_m,
):
    clipped_coords = _clip_coords_by_threshold(
        coords=coords,
        point_signed_distance=point_signed_distance,
        threshold_m=threshold_m,
    )

    return [LineString(line) for line in clipped_coords if len(line) >= 2]


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

    segment_lengths = haversine_distance(
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
