import os

import numpy as np
import xarray as xr
from scipy.spatial import cKDTree
from shapely.geometry import Point, mapping, shape

from polaris.mesh.spherical.unified.river.distance import (
    haversine_distance,
)
from polaris.mesh.spherical.unified.river.geojson import (
    read_geojson,
    write_geojson,
)
from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.river.simplify import (
    EARTH_RADIUS,
    read_river_segments_from_feature_collection,
)


class RasterizeRiverLatLonStep(Step):
    """
    Rasterize a simplified river network onto a shared lat-lon target grid.
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
            name='river_rasterize',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.simplify_step = simplify_step
        self.coastline_step = coastline_step
        self.masks_filename = 'river_network.nc'
        self.outlets_filename = 'river_outlets.geojson'

    def setup(self):
        """
        Link shared source and coastline inputs and declare outputs.
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
            filename='retained_outlets.geojson',
            work_dir_target=os.path.join(
                self.simplify_step.path, self.simplify_step.outlets_filename
            ),
        )
        self.add_input_file(
            filename='coastline.nc',
            work_dir_target=os.path.join(
                self.coastline_step.path,
                self.coastline_step.output_filenames[convention],
            ),
        )
        self.add_output_file(filename=self.masks_filename)
        self.add_output_file(filename=self.outlets_filename)

    def run(self):
        """
        Build target-grid river masks and snapped outlet diagnostics.
        """
        section = self.config['river_rasterize']
        river_fc = read_geojson('simplified_river_network.geojson')
        outlet_fc = read_geojson('retained_outlets.geojson')
        ds_coastline = xr.open_dataset('coastline.nc')
        ds_river, snapped_outlets = build_river_network_dataset(
            river_feature_collection=river_fc,
            outlet_feature_collection=outlet_fc,
            ds_coastline=ds_coastline,
            resolution=self.config.getfloat(
                'unified_mesh', 'resolution_latlon'
            ),
            outlet_match_tolerance=section.getfloat('outlet_match_tolerance'),
            channel_subsegment_fraction=section.getfloat(
                'channel_subsegment_fraction'
            ),
            channel_buffer_km=section.getfloat('channel_buffer_km'),
        )
        ds_river.attrs['source_river_step'] = self.simplify_step.subdir
        ds_river.attrs['source_coastline_step'] = self.coastline_step.subdir
        ds_river.attrs['mesh_name'] = self.config.get(
            'unified_mesh', 'mesh_name'
        )
        ds_river.attrs['antarctic_boundary_convention'] = self.config.get(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        ds_river.to_netcdf(self.masks_filename)
        write_geojson(snapped_outlets, self.outlets_filename)


def build_river_network_dataset(
    river_feature_collection,
    outlet_feature_collection,
    ds_coastline,
    resolution,
    outlet_match_tolerance,
    channel_subsegment_fraction=0.5,
    channel_buffer_km=0.0,
):
    """
    Rasterize a simplified river network onto a regular lat-lon grid.

    Parameters
    ----------
    river_feature_collection : dict
        A GeoJSON feature collection of simplified river line segments

    outlet_feature_collection : dict
        A GeoJSON feature collection of outlet points

    ds_coastline : xarray.Dataset
        Coastline dataset with ``lat``, ``lon``, and ``ocean_mask``
        variables

    resolution : float
        The target grid resolution in degrees

    outlet_match_tolerance : float
        Maximum distance in meters within which an ocean outlet is
        snapped to the nearest ocean cell; outlets beyond this distance
        fall back to the nearest grid cell

    channel_subsegment_fraction : float, optional
        Fraction of the target resolution used as the maximum
        inter-sample spacing when densifying river channels for
        rasterization

    channel_buffer_km : float, optional
        Physical buffer radius in kilometres around each sampled channel
        point within which additional grid cells are marked

    Returns
    -------
    ds_river : xarray.Dataset
        Dataset with ``river_channel_mask``, ``river_outlet_mask``,
        ``river_ocean_outlet_mask``, and ``river_inland_sink_mask``
        on the target lat-lon grid

    snapped_outlets : dict
        A GeoJSON feature collection of snapped outlet points with
        diagnostic snapping properties
    """
    river_segments = read_river_segments_from_feature_collection(
        river_feature_collection
    )
    lat = ds_coastline.lat.values
    lon = ds_coastline.lon.values
    shape_2d = (lat.size, lon.size)

    river_channel_mask = np.zeros(shape_2d, dtype=np.int8)
    river_outlet_mask = np.zeros(shape_2d, dtype=np.int8)
    river_ocean_outlet_mask = np.zeros(shape_2d, dtype=np.int8)
    river_inland_sink_mask = np.zeros(shape_2d, dtype=np.int8)
    channel_buffer_m = channel_buffer_km * 1.0e3

    for segment in river_segments:
        sample_points = _sample_line(
            segment.geometry,
            resolution=resolution,
            subsegment_fraction=channel_subsegment_fraction,
        )
        for sample_lon, sample_lat in sample_points:
            _mark_channel_sample(
                mask=river_channel_mask,
                sample_lon=sample_lon,
                sample_lat=sample_lat,
                lon=lon,
                lat=lat,
                buffer_m=channel_buffer_m,
            )

    snapped_features = []
    ocean_outlets = 0
    unmatched_ocean_outlets = 0
    ocean_mask = _mask_from_dataset(ds_coastline, 'ocean_mask')
    land_mask = _get_land_mask(ds_coastline)
    ocean_kdtree, ocean_indices_arr = _build_cell_kdtree(ocean_mask, lon, lat)
    land_kdtree, land_indices_arr = _build_cell_kdtree(land_mask, lon, lat)
    for feature in outlet_feature_collection['features']:
        properties = dict(feature['properties'])
        source_point = shape(feature['geometry'])
        source_lon = float(source_point.x)
        source_lat = float(source_point.y)
        outlet_type = properties['outlet_type']
        if outlet_type == 'ocean':
            ocean_outlets += 1
            (
                lat_index,
                lon_index,
                snapped_lon,
                snapped_lat,
                matched_to_ocean,
                snapping_distance,
            ) = _match_ocean_outlet(
                source_lon=source_lon,
                source_lat=source_lat,
                lon=lon,
                lat=lat,
                ocean_kdtree=ocean_kdtree,
                ocean_indices_arr=ocean_indices_arr,
                outlet_match_tolerance=outlet_match_tolerance,
            )
            if not matched_to_ocean:
                unmatched_ocean_outlets += 1
            river_ocean_outlet_mask[lat_index, lon_index] = 1
        else:
            (
                lat_index,
                lon_index,
                snapped_lon,
                snapped_lat,
                snapping_distance,
            ) = _match_land_point(
                source_lon=source_lon,
                source_lat=source_lat,
                lon=lon,
                lat=lat,
                land_kdtree=land_kdtree,
                land_indices_arr=land_indices_arr,
            )
            matched_to_ocean = False
            river_inland_sink_mask[lat_index, lon_index] = 1

        river_outlet_mask[lat_index, lon_index] = 1
        properties.update(
            source_lon=source_lon,
            source_lat=source_lat,
            snapped_lon=snapped_lon,
            snapped_lat=snapped_lat,
            snapped_lat_index=int(lat_index),
            snapped_lon_index=int(lon_index),
            snapping_distance_m=snapping_distance,
            matched_to_ocean=matched_to_ocean,
        )
        snapped_features.append(
            dict(
                type='Feature',
                properties=properties,
                geometry=mapping(Point(snapped_lon, snapped_lat)),
            )
        )

    ds_river = xr.Dataset(
        coords=dict(lat=ds_coastline.lat, lon=ds_coastline.lon)
    )
    dims = ('lat', 'lon')
    ds_river['river_channel_mask'] = xr.DataArray(
        river_channel_mask, dims=dims
    )
    ds_river['river_outlet_mask'] = xr.DataArray(river_outlet_mask, dims=dims)
    ds_river['river_ocean_outlet_mask'] = xr.DataArray(
        river_ocean_outlet_mask, dims=dims
    )
    ds_river['river_inland_sink_mask'] = xr.DataArray(
        river_inland_sink_mask, dims=dims
    )
    ds_river.attrs.update(
        dict(
            target_grid='lat_lon',
            target_grid_resolution_degrees=resolution,
            outlet_match_tolerance_m=outlet_match_tolerance,
            channel_buffer_m=channel_buffer_m,
            unmatched_ocean_outlets=unmatched_ocean_outlets,
            matched_ocean_outlets=ocean_outlets - unmatched_ocean_outlets,
        )
    )
    ds_river['river_channel_mask'].attrs['long_name'] = (
        'Lat-lon mask for retained river channels'
    )
    ds_river['river_outlet_mask'].attrs['long_name'] = (
        'Lat-lon mask for all retained river outlets and inland sinks'
    )
    ds_river['river_ocean_outlet_mask'].attrs['long_name'] = (
        'Lat-lon mask for retained ocean-draining river outlets'
    )
    ds_river['river_inland_sink_mask'].attrs['long_name'] = (
        'Lat-lon mask for retained inland sinks'
    )

    snapped_outlets = dict(
        type='FeatureCollection',
        features=snapped_features,
        metadata=dict(
            mesh_name=ds_river.attrs.get('mesh_name'),
            target_grid='lat_lon',
            target_grid_resolution_degrees=resolution,
            outlet_match_tolerance_m=outlet_match_tolerance,
            channel_buffer_m=channel_buffer_m,
            unmatched_ocean_outlets=unmatched_ocean_outlets,
        ),
    )
    return ds_river, snapped_outlets


def _mask_from_dataset(ds_coastline, variable_name):
    """
    Read an integer mask from a coastline dataset if available.
    """
    if variable_name not in ds_coastline:
        return None
    return ds_coastline[variable_name].values.astype(bool)


def _get_land_mask(ds_coastline):
    """
    Derive the land mask from ocean_mask.
    """
    return np.logical_not(ds_coastline.ocean_mask.values.astype(bool))


def _build_cell_kdtree(mask, lon, lat):
    """
    Build a 3-D spherical KD-tree from grid cells where mask is True.

    Converts lon/lat to unit-sphere Cartesian coordinates so that the
    nearest neighbour in Euclidean 3-D space equals the nearest neighbour
    by great-circle distance.  Returns (None, None) when the mask is empty.
    """
    if mask is None or not np.any(mask):
        return None, None
    indices = np.argwhere(mask)
    cell_lon_rad = np.deg2rad(lon[indices[:, 1]])
    cell_lat_rad = np.deg2rad(lat[indices[:, 0]])
    xyz = np.column_stack(
        [
            np.cos(cell_lat_rad) * np.cos(cell_lon_rad),
            np.cos(cell_lat_rad) * np.sin(cell_lon_rad),
            np.sin(cell_lat_rad),
        ]
    )
    return cKDTree(xyz), indices


def _sample_line(geometry, resolution, subsegment_fraction):
    """
    Sample a line densely enough to rasterize it onto a regular grid.
    """
    coords = np.asarray(geometry.coords)
    sample_points = [tuple(coords[0])]
    max_step = resolution * subsegment_fraction
    for start, end in zip(coords[:-1], coords[1:], strict=True):
        lon0, lat0 = start
        lon1, lat1 = end
        delta_lon = _wrapped_longitude_difference(lon1 - lon0)
        delta_lat = lat1 - lat0
        segment_extent = max(abs(delta_lon), abs(delta_lat))
        n_steps = max(1, int(np.ceil(segment_extent / max_step)))
        for index in range(1, n_steps + 1):
            fraction = index / n_steps
            sample_points.append(
                (
                    _wrap_longitude(lon0 + fraction * delta_lon),
                    lat0 + fraction * delta_lat,
                )
            )
    return sample_points


def _nearest_grid_index(sample_lon, sample_lat, lon, lat):
    """
    Find the nearest lat-lon grid-cell center.
    """
    lon_index = _nearest_periodic_index(sample_lon, lon)
    lat_index = _nearest_bounded_index(sample_lat, lat)
    return lat_index, lon_index


def _mark_channel_sample(mask, sample_lon, sample_lat, lon, lat, buffer_m):
    """
    Mark grid cells within a physical buffer of a sampled river point.
    """
    lat_index, lon_index = _nearest_grid_index(
        sample_lon=sample_lon,
        sample_lat=sample_lat,
        lon=lon,
        lat=lat,
    )
    mask[lat_index, lon_index] = 1
    if buffer_m <= 0.0:
        return

    angular_buffer = buffer_m / EARTH_RADIUS
    lat_delta = np.rad2deg(angular_buffer)
    cos_lat = max(np.cos(np.deg2rad(sample_lat)), 1.0e-6)
    lon_delta = min(180.0, np.rad2deg(angular_buffer / cos_lat))
    lat_indices = _coordinate_window(sample_lat, lat, lat_delta)
    lon_indices = _coordinate_window(sample_lon, lon, lon_delta, periodic=True)

    candidate_lat = lat[lat_indices][:, np.newaxis]
    candidate_lon = lon[lon_indices][np.newaxis, :]
    distances = haversine_distance(
        sample_lon, sample_lat, candidate_lon, candidate_lat
    )
    buffered_mask = distances <= buffer_m
    mask[np.ix_(lat_indices, lon_indices)] |= buffered_mask.astype(np.int8)


def _nearest_bounded_index(value, coord):
    """
    Find the nearest index in a regular coordinate array.
    """
    if coord.size == 1:
        return 0

    step = coord[1] - coord[0]
    raw_index = int(np.rint((value - coord[0]) / step))
    return int(np.clip(raw_index, 0, coord.size - 1))


def _nearest_periodic_index(value, coord):
    """
    Find the nearest index in a regular periodic coordinate array.
    """
    if coord.size == 1:
        return 0

    step = coord[1] - coord[0]
    raw_index = int(np.rint((value - coord[0]) / step))
    return raw_index % coord.size


def _coordinate_window(value, coord, delta, periodic=False):
    """
    Find candidate coordinate indices within one regular-grid window.
    """
    if coord.size == 1:
        return np.array([0], dtype=int)

    spacing = abs(coord[1] - coord[0])
    half_width = int(np.ceil(delta / spacing)) + 1
    if periodic:
        center = _nearest_periodic_index(value, coord)
        indices = np.arange(
            center - half_width, center + half_width + 1, dtype=int
        )
        return np.unique(indices % coord.size)

    center = _nearest_bounded_index(value, coord)
    start = max(0, center - half_width)
    stop = min(coord.size, center + half_width + 1)
    return np.arange(start, stop, dtype=int)


def _match_ocean_outlet(
    source_lon,
    source_lat,
    lon,
    lat,
    ocean_kdtree,
    ocean_indices_arr,
    outlet_match_tolerance,
):
    """
    Match an ocean outlet to the nearest ocean cell.
    """
    if ocean_kdtree is not None:
        lon_rad = np.deg2rad(source_lon)
        lat_rad = np.deg2rad(source_lat)
        source_xyz = [
            np.cos(lat_rad) * np.cos(lon_rad),
            np.cos(lat_rad) * np.sin(lon_rad),
            np.sin(lat_rad),
        ]
        _, tree_idx = ocean_kdtree.query(source_xyz)
        lat_index = int(ocean_indices_arr[tree_idx, 0])
        lon_index = int(ocean_indices_arr[tree_idx, 1])
        snapped_lon = float(lon[lon_index])
        snapped_lat = float(lat[lat_index])
        snapping_distance = float(
            haversine_distance(
                source_lon, source_lat, snapped_lon, snapped_lat
            )
        )
        matched_to_ocean = snapping_distance <= outlet_match_tolerance
        if matched_to_ocean:
            return (
                lat_index,
                lon_index,
                snapped_lon,
                snapped_lat,
                True,
                snapping_distance,
            )

    lat_index, lon_index = _nearest_grid_index(
        sample_lon=source_lon,
        sample_lat=source_lat,
        lon=lon,
        lat=lat,
    )
    snapped_lon = float(lon[lon_index])
    snapped_lat = float(lat[lat_index])
    snapping_distance = float(
        haversine_distance(source_lon, source_lat, snapped_lon, snapped_lat)
    )
    return (
        lat_index,
        lon_index,
        snapped_lon,
        snapped_lat,
        False,
        snapping_distance,
    )


def _match_land_point(
    source_lon,
    source_lat,
    lon,
    lat,
    land_kdtree,
    land_indices_arr,
):
    """
    Match an inland sink to the nearest land cell.
    """
    if land_kdtree is not None:
        lon_rad = np.deg2rad(source_lon)
        lat_rad = np.deg2rad(source_lat)
        source_xyz = [
            np.cos(lat_rad) * np.cos(lon_rad),
            np.cos(lat_rad) * np.sin(lon_rad),
            np.sin(lat_rad),
        ]
        _, tree_idx = land_kdtree.query(source_xyz)
        lat_index = int(land_indices_arr[tree_idx, 0])
        lon_index = int(land_indices_arr[tree_idx, 1])
        snapped_lon = float(lon[lon_index])
        snapped_lat = float(lat[lat_index])
        snapping_distance = float(
            haversine_distance(
                source_lon, source_lat, snapped_lon, snapped_lat
            )
        )
        return (
            lat_index,
            lon_index,
            snapped_lon,
            snapped_lat,
            snapping_distance,
        )

    lat_index, lon_index = _nearest_grid_index(
        sample_lon=source_lon,
        sample_lat=source_lat,
        lon=lon,
        lat=lat,
    )
    snapped_lon = float(lon[lon_index])
    snapped_lat = float(lat[lat_index])
    snapping_distance = float(
        haversine_distance(source_lon, source_lat, snapped_lon, snapped_lat)
    )
    return lat_index, lon_index, snapped_lon, snapped_lat, snapping_distance


def _wrapped_longitude_difference(delta_lon):
    """
    Wrap a longitude difference into the [-180, 180) interval.
    """
    return (delta_lon + 180.0) % 360.0 - 180.0


def _wrap_longitude(lon):
    """
    Wrap a longitude into the [-180, 180) interval.
    """
    return _wrapped_longitude_difference(lon)
