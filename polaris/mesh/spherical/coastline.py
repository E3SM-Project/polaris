from typing import Any

import netCDF4
import numpy as np
import xarray as xr
from scipy import ndimage
from scipy.spatial import cKDTree

from polaris.constants import get_constant
from polaris.mesh.spherical.critical_transects import CriticalTransects

CONVENTIONS = ('calving_front', 'grounding_line', 'bedrock_zero')
EARTH_RADIUS = get_constant('mean_radius')


def build_coastline_datasets(
    ds_topo,
    resolution,
    mask_threshold=0.5,
    sea_level_elevation=0.0,
    distance_chunk_size=64,
    workers=1,
    critical_transects=None,
):
    """
    Build coastline datasets from combined topography.

    Parameters
    ----------
    ds_topo : xr.Dataset
        Combined topography on a lat-lon grid

    resolution : float
        The target lat-lon resolution in degrees

    mask_threshold : float, optional
        Threshold for converting remapped mask fields to binary masks

    sea_level_elevation : float, optional
        Elevation threshold used to classify below-sea-level cells

    distance_chunk_size : int, optional
        Number of latitude rows per signed-distance query chunk

    workers : int, optional
        Number of workers to use in KD-tree queries

    critical_transects : CriticalTransects, optional
        Critical land blockages and passages to rasterize before flood fill

    Returns
    -------
    ds_coastlines : dict[str, xr.Dataset]
        Coastline datasets keyed by coastline convention
    """
    lon = ds_topo.lon.values
    lat = ds_topo.lat.values

    base_elevation = ds_topo.base_elevation.transpose('lat', 'lon').values
    ice_mask = (
        ds_topo.ice_mask.transpose('lat', 'lon').values >= mask_threshold
    )
    grounded_mask = (
        ds_topo.grounded_mask.transpose('lat', 'lon').values >= mask_threshold
    )
    below_sea_level = np.isfinite(base_elevation) & (
        base_elevation < sea_level_elevation
    )

    candidate_masks = {
        'calving_front': below_sea_level & np.logical_not(ice_mask),
        'grounding_line': below_sea_level & np.logical_not(grounded_mask),
        'bedrock_zero': below_sea_level,
    }

    land_blockages, passages = _rasterize_critical_transects(
        critical_transects=critical_transects,
        lon=lon,
        lat=lat,
    )

    ds_coastlines: dict[str, xr.Dataset] = {}

    for convention in CONVENTIONS:
        candidate_ocean = candidate_masks[convention]
        candidate_ocean = np.logical_and(
            candidate_ocean, np.logical_not(land_blockages)
        )
        candidate_ocean = np.logical_or(candidate_ocean, passages)

        ocean_mask = _flood_fill_ocean(candidate_ocean, lat)
        edge_east, edge_north = _coastline_edges(ocean_mask)
        signed_distance = _signed_distance_from_mask(
            ocean_mask=ocean_mask,
            edge_east=edge_east,
            edge_north=edge_north,
            lon=lon,
            lat=lat,
            chunk_size=distance_chunk_size,
            workers=workers,
        )

        ds_coastlines[convention] = _build_single_coastline_dataset(
            convention=convention,
            ds_topo=ds_topo,
            resolution=resolution,
            mask_threshold=mask_threshold,
            sea_level_elevation=sea_level_elevation,
            ocean_mask=ocean_mask.astype(np.int8),
            signed_distance=signed_distance.astype(np.float32),
        )

    return ds_coastlines


def build_coastline_dataset(
    ds_topo,
    resolution,
    convention,
    mask_threshold=0.5,
    sea_level_elevation=0.0,
    distance_chunk_size=64,
    workers=1,
    critical_transects=None,
):
    """
    Build a coastline dataset for one coastline convention.
    """
    ds_coastlines = build_coastline_datasets(
        ds_topo=ds_topo,
        resolution=resolution,
        mask_threshold=mask_threshold,
        sea_level_elevation=sea_level_elevation,
        distance_chunk_size=distance_chunk_size,
        workers=workers,
        critical_transects=critical_transects,
    )
    return ds_coastlines[convention]


def _build_single_coastline_dataset(
    convention,
    ds_topo,
    resolution,
    mask_threshold,
    sea_level_elevation,
    ocean_mask,
    signed_distance,
):
    """
    Build one convention-specific coastline dataset.
    """
    ds_coastline = xr.Dataset(
        coords=dict(
            lat=ds_topo.lat,
            lon=ds_topo.lon,
        )
    )

    dims = ('lat', 'lon')
    data_vars: dict[str, np.ndarray[Any, Any]] = {
        'ocean_mask': ocean_mask,
        'signed_distance': signed_distance,
    }
    for var_name, values in data_vars.items():
        ds_coastline[var_name] = xr.DataArray(values, dims=dims)

    ds_coastline.attrs.update(
        dict(
            coastline_convention=convention,
            target_grid='lat_lon',
            target_grid_resolution_degrees=resolution,
            coastline_source='combined_topography',
            mask_threshold=mask_threshold,
            sea_level_elevation=sea_level_elevation,
            flood_fill_seed_strategy='candidate_ocean_on_northernmost_row',
            sign_convention='negative_over_land_positive_over_ocean',
            coastline_edge_definition=(
                'east and north cell-edge transitions on the target grid'
            ),
            coastline_distance_definition=(
                'spherical nearest-sample distance from raster coastline'
            ),
        )
    )

    ds_coastline['ocean_mask'].attrs['long_name'] = (
        'Exclusive ocean mask after flood fill'
    )
    ds_coastline['signed_distance'].attrs['long_name'] = (
        'Signed distance to the nearest coastline sample'
    )
    ds_coastline['signed_distance'].attrs['units'] = 'm'

    return ds_coastline


def _flood_fill_ocean(candidate_ocean, lat):
    """
    Flood fill candidate ocean regions from the northernmost latitude row.

    Periodicity is enforced in longitude by merging labels on the eastern and
    western boundaries before selecting connected components.
    """
    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8)
    labels, label_count = ndimage.label(candidate_ocean, structure=structure)
    if label_count == 0:
        return np.zeros_like(candidate_ocean, dtype=bool)

    seed_row = int(np.argmax(lat))

    parent = np.arange(label_count + 1, dtype=np.int64)

    def find(label):
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    wrap_rows = np.nonzero(candidate_ocean[:, 0] & candidate_ocean[:, -1])[0]
    for row in wrap_rows:
        union(labels[row, 0], labels[row, -1])

    seed_labels = np.unique(labels[seed_row, candidate_ocean[seed_row, :]])
    seed_roots = {find(label) for label in seed_labels if label != 0}
    if not seed_roots:
        return np.zeros_like(candidate_ocean, dtype=bool)

    ocean_mask = np.zeros_like(candidate_ocean, dtype=bool)
    for label in range(1, label_count + 1):
        if find(label) in seed_roots:
            ocean_mask |= labels == label

    return ocean_mask


def _coastline_edges(ocean_mask):
    """
    Build east and north coastline edge diagnostics from an ocean mask.
    """
    edge_east = ocean_mask != np.roll(ocean_mask, -1, axis=1)
    edge_north = np.zeros_like(ocean_mask, dtype=bool)
    edge_north[:-1, :] = ocean_mask[:-1, :] != ocean_mask[1:, :]
    return edge_east, edge_north


def _signed_distance_from_mask(
    ocean_mask,
    edge_east,
    edge_north,
    lon,
    lat,
    chunk_size,
    workers,
):
    """
    Compute signed distance to the nearest raster coastline sample.
    """
    sample_points = _coastline_sample_xyz(
        edge_east=edge_east, edge_north=edge_north, lon=lon, lat=lat
    )
    if sample_points.shape[0] == 0:
        return np.where(ocean_mask, np.inf, -np.inf)

    tree = cKDTree(sample_points)
    lon_rad = np.deg2rad(lon)
    cos_lon = np.cos(lon_rad)
    sin_lon = np.sin(lon_rad)

    distance = np.empty(ocean_mask.shape, dtype=np.float64)
    for start in range(0, lat.size, chunk_size):
        stop = min(start + chunk_size, lat.size)
        lat_rad = np.deg2rad(lat[start:stop])
        cos_lat = np.cos(lat_rad)[:, np.newaxis]
        sin_lat = np.sin(lat_rad)[:, np.newaxis]
        xyz = np.empty((stop - start, lon.size, 3), dtype=np.float64)
        xyz[:, :, 0] = cos_lat * cos_lon[np.newaxis, :]
        xyz[:, :, 1] = cos_lat * sin_lon[np.newaxis, :]
        xyz[:, :, 2] = sin_lat
        points = xyz.reshape((-1, 3))
        chord_distance, _ = _tree_query(tree, points, workers)
        chord_distance = np.clip(chord_distance, 0.0, 2.0)
        angle = 2.0 * np.arcsin(0.5 * chord_distance)
        distance[start:stop, :] = angle.reshape((stop - start, lon.size))

    signed_distance = EARTH_RADIUS * distance
    return np.where(ocean_mask, signed_distance, -signed_distance)


def _coastline_sample_xyz(edge_east, edge_north, lon, lat):
    """
    Convert coastline edge midpoints into Cartesian coordinates.
    """
    east_rows, east_cols = np.nonzero(edge_east)
    north_rows, north_cols = np.nonzero(edge_north)

    sample_xyz = []

    if east_rows.size > 0:
        east_lon = _angular_midpoint(
            lon[east_cols], lon[(east_cols + 1) % lon.size]
        )
        east_lat = lat[east_rows]
        sample_xyz.append(_lon_lat_to_xyz(east_lon, east_lat))

    if north_rows.size > 0:
        north_lon = lon[north_cols]
        north_lat = 0.5 * (lat[north_rows] + lat[north_rows + 1])
        sample_xyz.append(_lon_lat_to_xyz(north_lon, north_lat))

    if not sample_xyz:
        return np.empty((0, 3), dtype=np.float64)

    return np.vstack(sample_xyz)


def _angular_midpoint(lon_a, lon_b):
    """
    Compute the midpoint between longitudes, respecting antimeridian wrap.
    """
    lon_a_rad = np.deg2rad(lon_a)
    lon_b_rad = np.deg2rad(lon_b)
    x = np.cos(lon_a_rad) + np.cos(lon_b_rad)
    y = np.sin(lon_a_rad) + np.sin(lon_b_rad)
    return np.rad2deg(np.arctan2(y, x))


def _lon_lat_to_xyz(lon, lat):
    """
    Convert lon/lat coordinates in degrees to Cartesian coordinates.
    """
    lon_rad = np.deg2rad(lon)
    lat_rad = np.deg2rad(lat)
    cos_lat = np.cos(lat_rad)
    xyz = np.empty((lon_rad.size, 3), dtype=np.float64)
    xyz[:, 0] = cos_lat * np.cos(lon_rad)
    xyz[:, 1] = cos_lat * np.sin(lon_rad)
    xyz[:, 2] = np.sin(lat_rad)
    return xyz


def _tree_query(tree, points, workers):
    """
    Query a KD-tree with SciPy-version-compatible worker support.
    """
    try:
        return tree.query(points, workers=workers)
    except TypeError:
        return tree.query(points)


def _write_netcdf_with_fill_values(ds, filename, format='NETCDF4'):
    """
    Write an xarray Dataset with NetCDF4 fill values where needed.
    """
    ds = ds.copy()
    fill_values = netCDF4.default_fillvals
    encoding = {}
    vars_and_coords = list(ds.data_vars.keys()) + list(ds.coords.keys())
    for var_name in vars_and_coords:
        ds[var_name].attrs.pop('_FillValue', None)
        is_numeric = np.issubdtype(ds[var_name].dtype, np.number)
        if is_numeric:
            dtype = ds[var_name].dtype
            for fill_type, fill_value in fill_values.items():
                if dtype == np.dtype(fill_type):
                    encoding[var_name] = {'_FillValue': fill_value}
                    break
        else:
            encoding[var_name] = {'_FillValue': None}
    ds.to_netcdf(filename, encoding=encoding, format=format)


def _rasterize_critical_transects(
    critical_transects: CriticalTransects | None,
    lon,
    lat,
):
    """
    Rasterize critical land blockages and passages onto a lat-lon grid.
    """
    shape = (lat.size, lon.size)
    if critical_transects is None:
        return (
            np.zeros(shape, dtype=bool),
            np.zeros(shape, dtype=bool),
        )

    land_blockages = _rasterize_feature_collection(
        feature_collection=critical_transects.land_blockages,
        lon=lon,
        lat=lat,
    )
    passages = _rasterize_feature_collection(
        feature_collection=critical_transects.passages,
        lon=lon,
        lat=lat,
    )
    return land_blockages, passages


def _rasterize_feature_collection(feature_collection, lon, lat):
    """
    Rasterize a transect feature collection to a 4-connected cell mask.
    """
    mask = np.zeros((lat.size, lon.size), dtype=bool)
    if feature_collection is None:
        return mask

    lon_spacing = _representative_spacing(lon)
    lat_spacing = _representative_spacing(lat)

    for coordinates in _iter_feature_coordinates(feature_collection):
        _rasterize_linestring(
            mask=mask,
            coordinates=coordinates,
            lon=lon,
            lat=lat,
            lon_spacing=lon_spacing,
            lat_spacing=lat_spacing,
        )

    return mask


def _iter_feature_coordinates(feature_collection):
    """
    Yield the coordinates for each line geometry in a feature collection.
    """
    if isinstance(feature_collection, dict):
        features = feature_collection.get('features', [])
    else:
        features = getattr(feature_collection, 'features', [])

    for feature in features:
        geometry = feature.get('geometry')
        if geometry is None:
            continue

        geometry_type = geometry.get('type')
        if geometry_type == 'LineString':
            yield np.asarray(geometry['coordinates'], dtype=np.float64)
        elif geometry_type == 'MultiLineString':
            for coordinates in geometry['coordinates']:
                yield np.asarray(coordinates, dtype=np.float64)
        else:
            raise ValueError(
                f'Unsupported critical transect geometry type: {geometry_type}'
            )


def _rasterize_linestring(
    mask,
    coordinates,
    lon,
    lat,
    lon_spacing,
    lat_spacing,
):
    """
    Rasterize one line string by densifying and connecting nearest cells.
    """
    if coordinates.shape[0] == 0:
        return

    grid_path: list[tuple[int, int]] = []
    for index in range(coordinates.shape[0] - 1):
        start = coordinates[index, :2]
        stop = coordinates[index + 1, :2]
        dense_points = _densify_segment(
            start=start,
            stop=stop,
            lon_spacing=lon_spacing,
            lat_spacing=lat_spacing,
        )
        for point in dense_points:
            row = _nearest_lat_index(point[1], lat)
            col = _nearest_lon_index(point[0], lon)
            cell = (row, col)
            if not grid_path or grid_path[-1] != cell:
                grid_path.append(cell)

    if not grid_path:
        point = coordinates[0, :2]
        grid_path.append(
            (
                _nearest_lat_index(point[1], lat),
                _nearest_lon_index(point[0], lon),
            )
        )

    start_row, start_col = grid_path[0]
    mask[start_row, start_col] = True
    for previous, current in zip(grid_path[:-1], grid_path[1:], strict=False):
        _mark_grid_connection(mask, previous, current)


def _densify_segment(start, stop, lon_spacing, lat_spacing):
    """
    Densify a segment enough to avoid gaps when mapping to cell centers.
    """
    delta_lon = _wrap_longitude_delta(stop[0] - start[0])
    delta_lat = stop[1] - start[1]
    n_lon = 0.0 if lon_spacing == 0.0 else abs(delta_lon) / lon_spacing
    n_lat = 0.0 if lat_spacing == 0.0 else abs(delta_lat) / lat_spacing
    segments = max(1, int(np.ceil(2.0 * max(n_lon, n_lat))))
    fractions = np.linspace(0.0, 1.0, segments + 1)
    dense = np.empty((segments + 1, 2), dtype=np.float64)
    dense[:, 0] = start[0] + fractions * delta_lon
    dense[:, 1] = start[1] + fractions * delta_lat
    return dense


def _representative_spacing(values):
    """
    Estimate a typical grid spacing from a one-dimensional coordinate.
    """
    if values.size < 2:
        return 1.0

    spacing = np.abs(np.diff(values))
    spacing = spacing[spacing > 0.0]
    if spacing.size == 0:
        return 1.0
    return float(np.median(spacing))


def _nearest_lat_index(value, lat):
    """
    Find the nearest latitude index for a point.
    """
    return int(np.argmin(np.abs(lat - value)))


def _nearest_lon_index(value, lon):
    """
    Find the nearest longitude index for a point with periodic wrap.
    """
    delta = _wrap_longitude_delta(lon - value)
    return int(np.argmin(np.abs(delta)))


def _wrap_longitude_delta(delta):
    """
    Wrap longitude differences to the shortest path on the sphere.
    """
    return np.mod(delta + 180.0, 360.0) - 180.0


def _mark_grid_connection(mask, previous, current):
    """
    Mark a 4-connected path between two raster cells.
    """
    row, col = previous
    stop_row, stop_col = current
    n_lon = mask.shape[1]

    while row != stop_row or col != stop_col:
        lon_delta = _periodic_index_delta(stop_col - col, n_lon)
        if lon_delta != 0:
            col = (col + int(np.sign(lon_delta))) % n_lon
            mask[row, col] = True

        lat_delta = stop_row - row
        if lat_delta != 0:
            row += int(np.sign(lat_delta))
            mask[row, col] = True


def _periodic_index_delta(delta, size):
    """
    Compute the shortest signed periodic index delta.
    """
    half_size = size / 2.0
    if delta > half_size:
        delta -= size
    elif delta < -half_size:
        delta += size
    return delta
