import json
import os
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np
import shapefile
from shapely import line_merge, unary_union
from shapely.geometry import LineString, Point, mapping, shape

from polaris.archive import extract_zip_subdir
from polaris.constants import get_constant
from polaris.step import Step

EARTH_RADIUS = get_constant('mean_radius')
KM2_TO_M2 = 1.0e6


@dataclass(frozen=True)
class RiverSegment:
    """
    Canonical representation of one river-network segment.
    """

    geometry: LineString
    hyriv_id: int
    main_riv: int
    ord_stra: int
    drainage_area: float
    next_down: int
    endorheic: int
    river_name: str | None = None
    outlet_type: str | None = None
    outlet_hyriv_id: int | None = None

    @property
    def endpoint(self) -> tuple[float, float]:
        """
        Return the downstream endpoint of the segment.
        """
        lon, lat = self.geometry.coords[-1]
        return float(lon), float(lat)


class PrepareRiverSourceStep(Step):
    """
    Prepare a simplified, source-grid-independent river network.
    """

    def __init__(self, component, subdir):
        super().__init__(
            component=component,
            name='river_source',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.raw_source_filename = 'source_river_network.geojson'
        self.simplified_filename = 'simplified_river_network.geojson'
        self.outlets_filename = 'retained_outlets.geojson'

    def setup(self):
        """
        Add the HydroRIVERS shapefile archive input and declare outputs.
        """
        section = self.config['river_network']
        archive_filename = section.get('hydrorivers_archive_filename')
        source_url = section.get('hydrorivers_url')
        self.add_input_file(
            filename=archive_filename,
            target=archive_filename,
            url=source_url,
            database='river_network',
        )
        self.add_output_file(filename=self.raw_source_filename)
        self.add_output_file(filename=self.simplified_filename)
        self.add_output_file(filename=self.outlets_filename)

    def run(self):
        """
        Download, unpack, convert, and simplify HydroRIVERS source data.
        """
        section = self.config['river_network']
        archive_filename = section.get('hydrorivers_archive_filename')
        shp_directory = section.get('hydrorivers_shp_directory')
        shp_filename = section.get('hydrorivers_shp_filename')
        _unpack_hydrorivers_archive(archive_filename, shp_directory)
        _convert_hydrorivers_shapefile_to_geojson(
            shp_filename=os.path.join(shp_directory, shp_filename),
            output_filename=self.raw_source_filename,
        )

        feature_collection = _read_geojson(self.raw_source_filename)
        simplified_fc, outlets_fc = simplify_river_network_feature_collection(
            feature_collection=feature_collection,
            drainage_area_threshold=section.getfloat(
                'drainage_area_threshold'
            ),
            outlet_distance_tolerance=section.getfloat(
                'outlet_distance_tolerance'
            ),
            tributary_area_ratio=section.getfloat('tributary_area_ratio'),
        )
        simplified_fc['metadata'] = dict(
            mesh_name=self.config.get('unified_mesh', 'mesh_name'),
            resolution_latlon=self.config.getfloat(
                'unified_mesh', 'resolution_latlon'
            ),
            hydrorivers_url=section.get('hydrorivers_url'),
            hydrorivers_archive_filename=archive_filename,
            hydrorivers_shp_directory=shp_directory,
            hydrorivers_shp_filename=shp_filename,
            drainage_area_threshold=section.getfloat(
                'drainage_area_threshold'
            ),
            outlet_distance_tolerance=section.getfloat(
                'outlet_distance_tolerance'
            ),
            tributary_area_ratio=section.getfloat('tributary_area_ratio'),
        )
        outlets_fc['metadata'] = dict(simplified_fc['metadata'])
        _write_geojson(simplified_fc, self.simplified_filename)
        _write_geojson(outlets_fc, self.outlets_filename)


def _unpack_hydrorivers_archive(archive_filename, data_directory):
    """
    Unpack the HydroRIVERS archive if needed.
    """
    if os.path.isdir(data_directory):
        return

    extract_zip_subdir(archive_filename, data_directory)

    if not os.path.isdir(data_directory):
        raise OSError(
            'Unpacked HydroRIVERS archive but did not find the expected '
            f'data directory {data_directory!r}.'
        )


def _convert_hydrorivers_shapefile_to_geojson(shp_filename, output_filename):
    """
    Convert the HydroRIVERS shapefile to GeoJSON.
    """
    reader = shapefile.Reader(shp_filename)
    features = []
    for shape_record in reader.iterShapeRecords():
        features.append(
            dict(
                type='Feature',
                properties=shape_record.record.as_dict(),
                geometry=shape_record.shape.__geo_interface__,
            )
        )
    _write_geojson(
        dict(type='FeatureCollection', features=features), output_filename
    )


def simplify_river_network_feature_collection(
    feature_collection,
    drainage_area_threshold,
    outlet_distance_tolerance,
    tributary_area_ratio=0.05,
):
    """
    Simplify a HydroRIVERS-style feature collection.

    Parameters
    ----------
    feature_collection : dict
        A GeoJSON feature collection

    drainage_area_threshold : float
        Minimum retained drainage area in square meters

    outlet_distance_tolerance : float
        Minimum retained spacing between non-endorheic outlets in meters

    tributary_area_ratio : float, optional
        The minimum tributary-to-main-stem drainage-area ratio for retaining
        a nearby tributary at a confluence

    Returns
    -------
    simplified_fc : dict
        A GeoJSON feature collection for the simplified river network

    outlets_fc : dict
        A GeoJSON feature collection for retained outlet points
    """
    segments = read_river_segments_from_feature_collection(feature_collection)
    segments = [
        segment
        for segment in segments
        if segment.drainage_area >= drainage_area_threshold
    ]
    if len(segments) == 0:
        raise ValueError(
            'No river-network segments remain after applying the drainage '
            'area threshold.'
        )

    segment_by_id = {segment.hyriv_id: segment for segment in segments}
    _validate_acyclic_downstream_graph(segment_by_id)

    upstream_map: dict[int, list[RiverSegment]] = defaultdict(list)
    for segment in segments:
        if segment.next_down != 0:
            upstream_map[segment.next_down].append(segment)

    outlet_candidates = [
        segment for segment in segments if segment.next_down == 0
    ]
    retained_outlets = _filter_outlets(
        outlet_candidates, outlet_distance_tolerance
    )

    retained_segments: dict[int, RiverSegment] = {}
    for outlet in retained_outlets:
        if outlet.endorheic == 1:
            outlet_type = 'inland_sink'
        else:
            outlet_type = 'ocean'
        _retain_basin_segments(
            segment=replace(
                outlet,
                outlet_type=outlet_type,
                outlet_hyriv_id=outlet.hyriv_id,
            ),
            upstream_map=upstream_map,
            segment_by_id=segment_by_id,
            retained_segments=retained_segments,
            basin_segments=[],
            distance_tolerance=outlet_distance_tolerance,
            tributary_area_ratio=tributary_area_ratio,
        )

    simplified_segments = sorted(
        retained_segments.values(),
        key=lambda segment: (
            segment.outlet_hyriv_id or -1,
            -segment.drainage_area,
            segment.hyriv_id,
        ),
    )
    outlet_segments = sorted(
        [segment for segment in retained_outlets],
        key=lambda segment: (-segment.drainage_area, segment.hyriv_id),
    )

    return (
        river_segments_to_feature_collection(simplified_segments),
        outlet_segments_to_feature_collection(outlet_segments),
    )


def read_river_segments_from_feature_collection(
    feature_collection,
) -> list[RiverSegment]:
    """
    Convert a GeoJSON feature collection to canonical river segments.
    """
    merged_segments: dict[int, RiverSegment] = {}
    for feature in feature_collection['features']:
        segment = _segment_from_feature(feature)
        existing = merged_segments.get(segment.hyriv_id)
        if existing is None:
            merged_segments[segment.hyriv_id] = segment
            continue

        merged_geometry = line_merge(
            unary_union([existing.geometry, segment.geometry])
        )
        if not isinstance(merged_geometry, LineString):
            merged_geometry = LineString(
                np.vstack(
                    [
                        np.asarray(existing.geometry.coords),
                        np.asarray(segment.geometry.coords),
                    ]
                )
            )
        merged_segments[segment.hyriv_id] = replace(
            existing, geometry=merged_geometry
        )

    return list(merged_segments.values())


def river_segments_to_feature_collection(segments):
    """
    Convert canonical river segments to a GeoJSON feature collection.
    """
    features = []
    for segment in segments:
        properties = dict(
            hyriv_id=segment.hyriv_id,
            main_riv=segment.main_riv,
            ord_stra=segment.ord_stra,
            drainage_area=segment.drainage_area,
            upland_skm=segment.drainage_area / KM2_TO_M2,
            next_down=segment.next_down,
            endorheic=segment.endorheic,
            outlet_type=segment.outlet_type,
            outlet_hyriv_id=segment.outlet_hyriv_id,
        )
        if segment.river_name is not None:
            properties['river_name'] = segment.river_name
        features.append(
            dict(
                type='Feature',
                properties=properties,
                geometry=mapping(segment.geometry),
            )
        )
    return dict(type='FeatureCollection', features=features)


def outlet_segments_to_feature_collection(segments):
    """
    Convert retained outlet segments to a GeoJSON feature collection.
    """
    features = []
    for segment in segments:
        lon, lat = segment.endpoint
        if segment.endorheic == 1:
            outlet_type = 'inland_sink'
        else:
            outlet_type = 'ocean'
        features.append(
            dict(
                type='Feature',
                properties=dict(
                    hyriv_id=segment.hyriv_id,
                    main_riv=segment.main_riv,
                    drainage_area=segment.drainage_area,
                    upland_skm=segment.drainage_area / KM2_TO_M2,
                    endorheic=segment.endorheic,
                    outlet_type=outlet_type,
                ),
                geometry=mapping(Point(lon, lat)),
            )
        )
    return dict(type='FeatureCollection', features=features)


def _retain_basin_segments(
    segment,
    upstream_map,
    segment_by_id,
    retained_segments,
    basin_segments,
    distance_tolerance,
    tributary_area_ratio,
):
    """
    Iteratively retain a main stem and major tributaries for one basin.
    """
    basin_visited: set[int] = set()
    stack = [segment]

    while len(stack) > 0:
        current = stack.pop()
        if current.hyriv_id not in segment_by_id:
            continue
        if current.hyriv_id in basin_visited:
            continue

        basin_visited.add(current.hyriv_id)
        retained_segments[current.hyriv_id] = current
        basin_segments.append(current)

        keep_segments = _select_upstream_segments(
            segment=current,
            upstream_map=upstream_map,
            basin_segments=basin_segments,
            distance_tolerance=distance_tolerance,
            tributary_area_ratio=tributary_area_ratio,
        )

        for upstream in reversed(keep_segments):
            annotated = replace(
                upstream,
                outlet_type=current.outlet_type,
                outlet_hyriv_id=current.outlet_hyriv_id,
            )
            stack.append(annotated)


def _select_upstream_segments(
    segment,
    upstream_map,
    basin_segments,
    distance_tolerance,
    tributary_area_ratio,
):
    """
    Select retained upstream segments for one confluence.
    """
    upstream_segments = sorted(
        upstream_map.get(segment.hyriv_id, []),
        key=lambda upstream: (
            upstream.drainage_area,
            upstream.ord_stra,
            upstream.hyriv_id,
        ),
        reverse=True,
    )
    if len(upstream_segments) == 0:
        return []

    keep_segments = [upstream_segments[0]]
    primary = upstream_segments[0]
    for upstream in upstream_segments[1:]:
        keep = upstream.drainage_area >= (
            tributary_area_ratio * primary.drainage_area
        )
        if not keep:
            keep = _distance_to_basin(upstream, basin_segments) >= (
                distance_tolerance
            )
        if keep:
            keep_segments.append(upstream)

    return keep_segments


def _validate_acyclic_downstream_graph(segment_by_id):
    """
    Validate that retained segments do not contain NEXT_DOWN cycles.
    """
    checked: set[int] = set()

    for hyriv_id in segment_by_id:
        if hyriv_id in checked:
            continue

        path: list[int] = []
        path_index: dict[int, int] = {}
        current_id = hyriv_id

        while current_id in segment_by_id:
            if current_id in checked:
                break
            if current_id in path_index:
                cycle = path[path_index[current_id] :] + [current_id]
                cycle_text = ' -> '.join(str(item) for item in cycle)
                raise ValueError(
                    'Cycle detected in retained river-network NEXT_DOWN '
                    f'chain: {cycle_text}'
                )

            path_index[current_id] = len(path)
            path.append(current_id)

            next_down = segment_by_id[current_id].next_down
            if next_down == 0:
                break
            current_id = next_down

        checked.update(path)


def _distance_to_basin(segment, basin_segments):
    """
    Compute the minimum distance from a segment to already retained segments.
    """
    if len(basin_segments) == 0:
        return np.inf
    return min(
        _minimum_line_distance(segment.geometry, other.geometry)
        for other in basin_segments
    )


def _minimum_line_distance(line_a, line_b):
    """
    Approximate the minimum distance between two lines on the sphere.
    """
    coords_a = np.asarray(line_a.coords)
    coords_b = np.asarray(line_b.coords)
    min_distance = np.inf
    for lon_a, lat_a in coords_a:
        distances = _haversine_distance(
            lon_a,
            lat_a,
            coords_b[:, 0],
            coords_b[:, 1],
        )
        min_distance = min(min_distance, float(np.min(distances)))
    for lon_b, lat_b in coords_b:
        distances = _haversine_distance(
            lon_b,
            lat_b,
            coords_a[:, 0],
            coords_a[:, 1],
        )
        min_distance = min(min_distance, float(np.min(distances)))
    return min_distance


def _filter_outlets(outlet_candidates, outlet_distance_tolerance):
    """
    Retain large, well-separated outlets while preserving inland sinks.
    """
    retained_outlets: list[RiverSegment] = []
    for candidate in sorted(
        outlet_candidates,
        key=lambda outlet: (
            outlet.drainage_area,
            outlet.ord_stra,
            outlet.hyriv_id,
        ),
        reverse=True,
    ):
        keep = True
        lon, lat = candidate.endpoint
        for retained in retained_outlets:
            if candidate.endorheic == 1 and retained.endorheic == 1:
                continue
            retained_lon, retained_lat = retained.endpoint
            distance = _haversine_distance(
                lon, lat, retained_lon, retained_lat
            )
            if float(distance) < outlet_distance_tolerance:
                keep = False
                break
        if keep:
            retained_outlets.append(candidate)

    return retained_outlets


def _segment_from_feature(feature):
    """
    Parse one GeoJSON feature into a canonical river segment.
    """
    properties = feature['properties']
    geometry = _line_string_from_geojson(feature['geometry'])
    hyriv_id = _get_int_property(properties, ('hyriv_id', 'HYRIV_ID'))
    main_riv = _get_int_property(properties, ('main_riv', 'MAIN_RIV'))
    ord_stra = _get_int_property(properties, ('ord_stra', 'ORD_STRA'))
    next_down = _get_int_property(properties, ('next_down', 'NEXT_DOWN'))
    endorheic = _get_int_property(properties, ('endorheic', 'ENDORHEIC'))
    drainage_area = _get_float_property(
        properties,
        ('drainage_area',),
        default=None,
    )
    if drainage_area is None:
        drainage_area = _get_float_property(
            properties, ('upland_skm', 'UPLAND_SKM')
        )
        drainage_area *= KM2_TO_M2
    river_name = _get_str_property(
        properties, ('river_name', 'RIVER_NAME', 'RIV_NAME', 'NAME')
    )

    return RiverSegment(
        geometry=geometry,
        hyriv_id=hyriv_id,
        main_riv=main_riv,
        ord_stra=ord_stra,
        drainage_area=drainage_area,
        next_down=next_down,
        endorheic=endorheic,
        river_name=river_name,
    )


def _line_string_from_geojson(geometry):
    """
    Convert a GeoJSON line geometry to a single LineString.
    """
    geom = shape(geometry)
    if isinstance(geom, LineString):
        return geom

    merged = line_merge(geom)
    if isinstance(merged, LineString):
        return merged

    raise ValueError(
        f'Unsupported river geometry type {geom.geom_type!r}; expected a '
        'LineString-compatible geometry.'
    )


def _get_int_property(properties, keys):
    """
    Read an integer property using one of several candidate keys.
    """
    value = _get_property(properties, keys)
    return int(value)


def _get_float_property(properties, keys, default=np.nan):
    """
    Read a float property using one of several candidate keys.
    """
    value = _get_property(properties, keys, default=default)
    if value is None:
        return None
    return float(value)


def _get_str_property(properties, keys):
    """
    Read a string property if available.
    """
    value = _get_property(properties, keys, default=None)
    if value in (None, ''):
        return None
    return str(value)


def _get_property(properties, keys, default=np.nan):
    """
    Read one of several candidate properties from a mapping.
    """
    for key in keys:
        if key in properties:
            return properties[key]
    if default is np.nan:
        raise ValueError(
            f'Could not find any of the required properties {keys!r}.'
        )
    return default


def _haversine_distance(lon_a, lat_a, lon_b, lat_b):
    """
    Compute great-circle distance in meters.
    """
    lon_a = np.deg2rad(lon_a)
    lat_a = np.deg2rad(lat_a)
    lon_b = np.deg2rad(lon_b)
    lat_b = np.deg2rad(lat_b)
    delta_lon = lon_b - lon_a
    delta_lat = lat_b - lat_a
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat_a) * np.cos(lat_b) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS * np.arcsin(np.sqrt(haversine))


def _read_geojson(filename):
    """
    Read a GeoJSON file into a dictionary.
    """
    with open(filename, 'r', encoding='utf-8') as infile:
        return json.load(infile)


def _write_geojson(feature_collection, filename):
    """
    Write a GeoJSON feature collection.
    """
    with open(filename, 'w', encoding='utf-8') as outfile:
        json.dump(feature_collection, outfile, indent=2, sort_keys=True)
