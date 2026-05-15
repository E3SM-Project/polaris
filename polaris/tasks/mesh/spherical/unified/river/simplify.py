import multiprocessing
import os
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np
import shapefile
from shapely import line_merge, unary_union
from shapely.geometry import LineString, box, mapping, shape
from shapely.strtree import STRtree

from polaris.archive import extract_zip_subdir
from polaris.constants import get_constant
from polaris.mesh.spherical.unified.river.distance import (
    haversine_distance,
)
from polaris.mesh.spherical.unified.river.geojson import (
    write_geojson,
)
from polaris.step import Step

EARTH_RADIUS = get_constant('mean_radius')
KM2_TO_M2 = 1.0e6
_METERS_PER_DEGREE = np.pi / 180.0 * EARTH_RADIUS

# Module-level state shared with fork-based parallel workers.
# Set by simplify_river_network_feature_collection before Pool creation.
_WORKER_UPSTREAM_MAP = None
_WORKER_SEGMENT_BY_ID = None
_WORKER_DISTANCE_TOLERANCE = None
_WORKER_TRIBUTARY_AREA_RATIO = None
_WORKER_SEG_TREE = None
_WORKER_SEG_LIST = None


@dataclass(frozen=True)
class RiverSegment:
    """
    Canonical representation of one river-network segment.

    Attributes
    ----------
    geometry : shapely.geometry.LineString
        The segment geometry in longitude-latitude coordinates

    hyriv_id : int
        The HydroRIVERS unique segment identifier

    main_riv : int
        The HydroRIVERS main-river identifier

    ord_stra : int
        The Strahler stream order

    drainage_area : float
        The upstream drainage area in square meters

    next_down : int
        The HydroRIVERS identifier of the next downstream segment
        (0 for outlets)

    endorheic : int
        1 if the segment drains to an inland sink, 0 otherwise

    river_name : str or None, optional
        The river name, if available

    outlet_hyriv_id : int or None, optional
        The HydroRIVERS identifier of the outlet for the basin this
        segment belongs to

    outlet_drainage_area : float or None, optional
        The upstream drainage area of the outlet for the basin this segment
        belongs to, in square meters

    river_network_rank : int or None, optional
        The 1-based size rank of this segment's basin, with 1 denoting the
        largest retained outlet drainage area
    """

    geometry: LineString
    hyriv_id: int
    main_riv: int
    ord_stra: int
    drainage_area: float
    next_down: int
    endorheic: int
    river_name: str | None = None
    outlet_hyriv_id: int | None = None
    outlet_drainage_area: float | None = None
    river_network_rank: int | None = None

    @property
    def endpoint(self) -> tuple[float, float]:
        """
        Return the downstream endpoint of the segment.
        """
        lon, lat = self.geometry.coords[-1]
        return float(lon), float(lat)


class SimplifyRiverNetworkStep(Step):
    """
    Prepare a simplified, source-grid-independent river network.
    """

    def __init__(self, component, subdir):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory within the component's work directory
        """
        super().__init__(
            component=component,
            name='river_simplify',
            subdir=subdir,
            cpus_per_task=128,
            min_cpus_per_task=1,
        )
        self.simplified_filename = 'simplified_river_network.geojson'

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
        self.add_output_file(filename=self.simplified_filename)

    def run(self):
        """
        Download, unpack, convert, and simplify HydroRIVERS source data.
        """
        import time

        print(f'cpus_per_task = {self.cpus_per_task}', flush=True)

        section = self.config['river_network']
        archive_filename = section.get('hydrorivers_archive_filename')
        shp_directory = section.get('hydrorivers_shp_directory')
        shp_filename = section.get('hydrorivers_shp_filename')
        _unpack_hydrorivers_archive(archive_filename, shp_directory)

        drainage_area_threshold = section.getfloat('drainage_area_threshold')
        if drainage_area_threshold < 0:
            land_background_km = self.config.getfloat(
                'sizing_field', 'land_background_km'
            )
            drainage_area_multiplier = section.getfloat(
                'drainage_area_multiplier'
            )
            drainage_area_threshold = (
                land_background_km**2 * drainage_area_multiplier * KM2_TO_M2
            )

        branch_distance_tolerance = section.getfloat(
            'branch_distance_tolerance'
        )
        if branch_distance_tolerance < 0:
            river_channel_km = self.config.getfloat(
                'sizing_field', 'river_channel_km'
            )
            branch_distance_tolerance = river_channel_km * 1000.0

        t0 = time.time()
        feature_collection = _read_filtered_shapefile_feature_collection(
            shp_filename=os.path.join(shp_directory, shp_filename),
            drainage_area_threshold=drainage_area_threshold,
        )
        print(
            f'read shapefile (filtered): {time.time() - t0:.1f} s',
            flush=True,
        )

        t0 = time.time()
        simplified_fc = simplify_river_network_feature_collection(
            feature_collection=feature_collection,
            drainage_area_threshold=drainage_area_threshold,
            branch_distance_tolerance=branch_distance_tolerance,
            tributary_area_ratio=section.getfloat('tributary_area_ratio'),
            n_cpus=self.cpus_per_task,
        )
        print(f'simplify: {time.time() - t0:.1f} s', flush=True)
        simplified_fc['metadata'] = dict(
            mesh_name=self.config.get('unified_mesh', 'mesh_name'),
            resolution_latlon=self.config.getfloat(
                'unified_mesh', 'resolution_latlon'
            ),
            hydrorivers_url=section.get('hydrorivers_url'),
            hydrorivers_archive_filename=archive_filename,
            hydrorivers_shp_directory=shp_directory,
            hydrorivers_shp_filename=shp_filename,
            drainage_area_threshold=drainage_area_threshold,
            branch_distance_tolerance=branch_distance_tolerance,
            tributary_area_ratio=section.getfloat('tributary_area_ratio'),
        )
        t0 = time.time()
        write_geojson(simplified_fc, self.simplified_filename)
        print(f'write outputs: {time.time() - t0:.1f} s', flush=True)


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


def _read_filtered_shapefile_feature_collection(
    shp_filename, drainage_area_threshold
):
    """
    Read a HydroRIVERS shapefile, skipping segments below the drainage area
    threshold before constructing geometry to avoid processing the ~97% of
    records that would be discarded immediately afterward.
    """
    reader = shapefile.Reader(shp_filename)
    features = []
    for shape_record in reader.iterShapeRecords():
        props = shape_record.record.as_dict()
        upland_skm = props.get('UPLAND_SKM')
        if upland_skm is None:
            upland_skm = props.get('upland_skm', 0.0)
        if float(upland_skm) * KM2_TO_M2 < drainage_area_threshold:
            continue
        features.append(
            dict(
                type='Feature',
                properties=props,
                geometry=shape_record.shape.__geo_interface__,
            )
        )
    return dict(type='FeatureCollection', features=features)


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
    write_geojson(
        dict(type='FeatureCollection', features=features), output_filename
    )


def simplify_river_network_feature_collection(
    feature_collection,
    drainage_area_threshold,
    branch_distance_tolerance,
    tributary_area_ratio=0.05,
    n_cpus=1,
):
    """
    Simplify a HydroRIVERS-style feature collection.

    Parameters
    ----------
    feature_collection : dict
        A GeoJSON feature collection

    drainage_area_threshold : float
        Minimum retained drainage area in square meters

    branch_distance_tolerance : float
        Minimum retained spacing between nearby upstream branches in meters

    tributary_area_ratio : float, optional
        The minimum tributary-to-main-stem drainage-area ratio for retaining
        a nearby tributary at a confluence

    n_cpus : int, optional
        Number of parallel worker processes for basin traversal.
        Defaults to 1 (single-process).

    Returns
    -------
    simplified_fc : dict
        A GeoJSON feature collection for the simplified river network

    """
    import time

    t0 = time.time()
    segments = read_river_segments_from_feature_collection(feature_collection)
    n_raw = len(segments)
    segments = [
        segment
        for segment in segments
        if segment.drainage_area >= drainage_area_threshold
    ]
    print(
        f'  read segments: {n_raw} raw, {len(segments)} after area filter, '
        f'{time.time() - t0:.1f} s',
        flush=True,
    )
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

    terminal_segments = [
        segment for segment in segments if segment.next_down == 0
    ]
    print(
        f'  terminal basin roots: {len(terminal_segments)}',
        flush=True,
    )

    t0 = time.time()
    seg_list = list(segments)
    seg_tree = STRtree([seg.geometry for seg in seg_list])
    print(
        f'  build STRtree ({len(seg_list)} geoms): {time.time() - t0:.1f} s',
        flush=True,
    )

    retained_segments: dict[int, RiverSegment] = {}
    n_workers = min(n_cpus, len(terminal_segments))
    print(f'  basin traversal: n_workers={n_workers}', flush=True)
    t0 = time.time()
    if n_workers > 1:
        global _WORKER_UPSTREAM_MAP, _WORKER_SEGMENT_BY_ID
        global _WORKER_DISTANCE_TOLERANCE, _WORKER_TRIBUTARY_AREA_RATIO
        global _WORKER_SEG_TREE, _WORKER_SEG_LIST
        _WORKER_UPSTREAM_MAP = upstream_map
        _WORKER_SEGMENT_BY_ID = segment_by_id
        _WORKER_DISTANCE_TOLERANCE = branch_distance_tolerance
        _WORKER_TRIBUTARY_AREA_RATIO = tributary_area_ratio
        _WORKER_SEG_TREE = seg_tree
        _WORKER_SEG_LIST = seg_list
        ctx = multiprocessing.get_context('fork')
        with ctx.Pool(processes=n_workers) as pool:
            results = pool.map(_process_basin_root, terminal_segments)
        _WORKER_UPSTREAM_MAP = None
        _WORKER_SEGMENT_BY_ID = None
        _WORKER_DISTANCE_TOLERANCE = None
        _WORKER_TRIBUTARY_AREA_RATIO = None
        _WORKER_SEG_TREE = None
        _WORKER_SEG_LIST = None
        for result in results:
            retained_segments.update(result)
    else:
        for root in terminal_segments:
            _retain_basin_segments(
                segment=replace(
                    root,
                    outlet_hyriv_id=root.hyriv_id,
                ),
                upstream_map=upstream_map,
                segment_by_id=segment_by_id,
                retained_segments=retained_segments,
                distance_tolerance=branch_distance_tolerance,
                tributary_area_ratio=tributary_area_ratio,
                seg_tree=seg_tree,
                seg_list=seg_list,
            )

    print(f'  basin traversal: {time.time() - t0:.1f} s', flush=True)

    annotated_segments = _annotate_river_networks(
        segments=retained_segments.values(),
        terminal_segments=terminal_segments,
    )
    simplified_segments = sorted(
        annotated_segments,
        key=lambda segment: (
            -_get_outlet_drainage_area(segment),
            -segment.drainage_area,
            segment.hyriv_id,
        ),
    )

    return river_segments_to_feature_collection(simplified_segments)


def read_river_segments_from_feature_collection(
    feature_collection,
) -> list[RiverSegment]:
    """
    Convert a GeoJSON feature collection to canonical river segments.

    Parameters
    ----------
    feature_collection : dict
        A GeoJSON feature collection with HydroRIVERS-style properties

    Returns
    -------
    list of RiverSegment
        Canonical river segments; geometries with duplicate HydroRIVERS
        identifiers are merged into a single segment
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

    Parameters
    ----------
    segments : list of RiverSegment
        Canonical river segments

    Returns
    -------
    dict
        A GeoJSON feature collection with one feature per segment,
        preserving all HydroRIVERS properties
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
            outlet_hyriv_id=segment.outlet_hyriv_id,
        )
        if segment.outlet_drainage_area is not None:
            properties['outlet_drainage_area'] = segment.outlet_drainage_area
        if segment.river_network_rank is not None:
            properties['river_network_rank'] = segment.river_network_rank
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


def _process_basin_root(root):
    """
    Process one terminal-root basin in a fork-based worker process.
    """
    retained: dict[int, RiverSegment] = {}
    _retain_basin_segments(
        segment=replace(
            root,
            outlet_hyriv_id=root.hyriv_id,
        ),
        upstream_map=_WORKER_UPSTREAM_MAP,
        segment_by_id=_WORKER_SEGMENT_BY_ID,
        retained_segments=retained,
        distance_tolerance=_WORKER_DISTANCE_TOLERANCE,
        tributary_area_ratio=_WORKER_TRIBUTARY_AREA_RATIO,
        seg_tree=_WORKER_SEG_TREE,
        seg_list=_WORKER_SEG_LIST,
    )
    return retained


def _get_outlet_drainage_area(segment):
    """
    Get a sortable outlet drainage area for a river segment.
    """
    if segment.outlet_drainage_area is None:
        return 0.0
    return segment.outlet_drainage_area


def _annotate_river_networks(segments, terminal_segments):
    """
    Add size-rank metadata to retained river-network segments.
    """
    roots = sorted(
        terminal_segments,
        key=lambda root: (-root.drainage_area, root.hyriv_id),
    )
    outlet_area_by_id = {
        root.hyriv_id: root.drainage_area for root in terminal_segments
    }
    rank_by_outlet_id = {
        root.hyriv_id: index + 1 for index, root in enumerate(roots)
    }

    annotated_segments = []
    for segment in segments:
        outlet_hyriv_id = segment.outlet_hyriv_id
        annotated_segments.append(
            replace(
                segment,
                outlet_drainage_area=outlet_area_by_id.get(outlet_hyriv_id),
                river_network_rank=rank_by_outlet_id.get(outlet_hyriv_id),
            )
        )
    return annotated_segments


def _retain_basin_segments(
    segment,
    upstream_map,
    segment_by_id,
    retained_segments,
    distance_tolerance,
    tributary_area_ratio,
    seg_tree,
    seg_list,
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

        keep_segments = _select_upstream_segments(
            segment=current,
            upstream_map=upstream_map,
            basin_id_set=basin_visited,
            distance_tolerance=distance_tolerance,
            tributary_area_ratio=tributary_area_ratio,
            seg_tree=seg_tree,
            seg_list=seg_list,
        )

        for upstream in reversed(keep_segments):
            annotated = replace(
                upstream,
                outlet_hyriv_id=current.outlet_hyriv_id,
            )
            stack.append(annotated)


def _select_upstream_segments(
    segment,
    upstream_map,
    basin_id_set,
    distance_tolerance,
    tributary_area_ratio,
    seg_tree,
    seg_list,
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
            keep = (
                _distance_to_basin(
                    upstream,
                    basin_id_set,
                    seg_tree,
                    seg_list,
                    distance_tolerance,
                )
                >= distance_tolerance
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


def _distance_to_basin(
    segment,
    basin_id_set,
    seg_tree,
    seg_list,
    distance_tolerance,
):
    """
    Compute the minimum distance from a segment to already retained segments.

    Uses a spatial index to limit exact distance computations to nearby
    candidates, and returns early once a distance below distance_tolerance
    is found.
    """
    if len(basin_id_set) == 0:
        return np.inf
    bounds = segment.geometry.bounds
    max_abs_lat = max(abs(bounds[1]), abs(bounds[3]))
    cos_lat = np.cos(np.deg2rad(min(max_abs_lat, 89.0)))
    lat_exp = distance_tolerance / _METERS_PER_DEGREE
    lon_exp = distance_tolerance / (_METERS_PER_DEGREE * cos_lat)
    query_box = box(
        bounds[0] - lon_exp,
        bounds[1] - lat_exp,
        bounds[2] + lon_exp,
        bounds[3] + lat_exp,
    )
    min_dist = np.inf
    for idx in seg_tree.query(query_box):
        other = seg_list[idx]
        if other.hyriv_id not in basin_id_set:
            continue
        dist = _minimum_line_distance(segment.geometry, other.geometry)
        if dist < min_dist:
            min_dist = dist
        if min_dist < distance_tolerance:
            return min_dist
    return min_dist


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
    outlet_hyriv_id = _get_optional_int_property(
        properties, ('outlet_hyriv_id', 'OUTLET_HYRIV_ID')
    )
    outlet_drainage_area = _get_float_property(
        properties,
        ('outlet_drainage_area', 'OUTLET_DRAINAGE_AREA'),
        default=None,
    )
    river_network_rank = _get_optional_int_property(
        properties, ('river_network_rank', 'RIVER_NETWORK_RANK')
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
        outlet_hyriv_id=outlet_hyriv_id,
        outlet_drainage_area=outlet_drainage_area,
        river_network_rank=river_network_rank,
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


def _get_optional_int_property(properties, keys):
    """
    Read an optional integer property using one of several candidate keys.
    """
    value = _get_property(properties, keys, default=None)
    if value is None:
        return None
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


def _minimum_line_distance(line_a, line_b):
    """
    Approximate the minimum distance between two lines on the sphere.
    """
    coords_a = np.asarray(line_a.coords)
    coords_b = np.asarray(line_b.coords)
    distances = haversine_distance(
        coords_a[:, 0:1],
        coords_a[:, 1:2],
        coords_b[np.newaxis, :, 0],
        coords_b[np.newaxis, :, 1],
    )
    return float(np.min(distances))
