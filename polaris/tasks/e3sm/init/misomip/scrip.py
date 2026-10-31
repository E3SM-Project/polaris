import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.tasks.e3sm.init.misomip.projection import (
    SPHERE_RADIUS,
    get_lat_lon,
)


def write_scrip(ds_mesh, filename, y_min=None, y_max=None):
    """
    Write a SCRIP file for a planar MISOMIP mesh, with the projection's
    latitude and longitude

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh, in the protocols' planar coordinates

    filename : str
        The SCRIP file to write

    y_min : float, optional
        A wall in m below which cell polygons are trimmed

    y_max : float, optional
        A wall in m above which cell polygons are trimmed
    """
    x_vertex = ds_mesh.xVertex.values
    y_vertex = ds_mesh.yVertex.values
    vertices_on_cell = ds_mesh.verticesOnCell.values - 1
    n_edges_on_cell = ds_mesh.nEdgesOnCell.values

    polygons = []
    for i_cell in range(ds_mesh.sizes['nCells']):
        vertices = vertices_on_cell[i_cell, : n_edges_on_cell[i_cell]]
        x = x_vertex[vertices]
        y = y_vertex[vertices]
        if (y_min is not None and np.any(y < y_min)) or (
            y_max is not None and np.any(y > y_max)
        ):
            x, y = clip_polygon_to_y_band(x, y, y_min, y_max)
        polygons.append((x, y))

    n_corners = max(len(x) for x, _ in polygons)
    corner_x = np.zeros((len(polygons), n_corners))
    corner_y = np.zeros((len(polygons), n_corners))
    for i_cell, (x, y) in enumerate(polygons):
        # SCRIP pads a polygon by repeating its last corner
        corner_x[i_cell, :] = x[-1]
        corner_y[i_cell, :] = y[-1]
        corner_x[i_cell, : len(x)] = x
        corner_y[i_cell, : len(y)] = y

    corner_lat, corner_lon = get_lat_lon(corner_x, corner_y)
    center_lat, center_lon = get_lat_lon(
        ds_mesh.xCell.values, ds_mesh.yCell.values
    )

    ds = xr.Dataset()
    ds['grid_dims'] = ('grid_rank', np.array([len(polygons)], dtype=np.int32))
    ds['grid_center_lat'] = ('grid_size', center_lat)
    ds['grid_center_lon'] = ('grid_size', center_lon)
    ds['grid_corner_lat'] = (('grid_size', 'grid_corners'), corner_lat)
    ds['grid_corner_lon'] = (('grid_size', 'grid_corners'), corner_lon)
    for var in [
        'grid_center_lat',
        'grid_center_lon',
        'grid_corner_lat',
        'grid_corner_lon',
    ]:
        ds[var].attrs['units'] = 'radians'
    ds['grid_area'] = (
        'grid_size',
        ds_mesh.areaCell.values / SPHERE_RADIUS**2,
    )
    ds.grid_area.attrs['units'] = 'radians^2'
    ds['grid_imask'] = (
        'grid_size',
        np.ones(len(polygons), dtype=np.int32),
    )
    ds.grid_imask.attrs['units'] = 'unitless'
    write_netcdf(ds, filename)


def clip_polygon_to_y_band(x, y, y_min=None, y_max=None):
    """
    Clip a convex polygon to the band between two lines of constant y

    Parameters
    ----------
    x : numpy.ndarray
        The x coordinates of the polygon's vertices, in order

    y : numpy.ndarray
        The y coordinates of the polygon's vertices

    y_min : float, optional
        The lower bound of the band

    y_max : float, optional
        The upper bound of the band

    Returns
    -------
    x : numpy.ndarray
        The x coordinates of the clipped polygon's vertices

    y : numpy.ndarray
        The y coordinates of the clipped polygon's vertices
    """
    points = list(zip(x, y, strict=True))
    for bound, sign in [(y_min, 1.0), (y_max, -1.0)]:
        if bound is None:
            continue
        clipped = []
        for index, current in enumerate(points):
            previous = points[index - 1]
            current_inside = sign * (current[1] - bound) >= 0.0
            previous_inside = sign * (previous[1] - bound) >= 0.0
            if current_inside != previous_inside:
                x0, y0 = previous
                x1, y1 = current
                crossing_x = x0 + (bound - y0) / (y1 - y0) * (x1 - x0)
                clipped.append((crossing_x, bound))
            if current_inside:
                clipped.append(current)
        points = clipped
    x_clipped = np.array([point[0] for point in points])
    y_clipped = np.array([point[1] for point in points])
    return x_clipped, y_clipped
