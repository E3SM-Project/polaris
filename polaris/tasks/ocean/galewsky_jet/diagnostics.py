"""
Diagnostics computed from the normal velocity and height for comparison with
Galewsky, Scott & Polvani (2004) and its corrigendum (2006)
"""

import numpy as np
from matplotlib.tri import Triangulation

from polaris.mpas import time_since_start


def relative_vorticity(ds_mesh, normal_velocity):
    """
    Compute the relative vorticity at vertices as the circulation around each
    dual triangle divided by its area

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS spherical mesh

    normal_velocity : numpy.ndarray
        The normal velocity in m/s with ``nEdges`` as its last dimension

    Returns
    -------
    vorticity : numpy.ndarray
        The relative vorticity in 1/s with ``nVertices`` as its last
        dimension
    """
    edges_on_vertex = ds_mesh.edgesOnVertex.values - 1
    valid = edges_on_vertex >= 0
    edges = np.where(valid, edges_on_vertex, 0)

    x_vertex = _positions(ds_mesh, 'Vertex')
    x_edge = _positions(ds_mesh, 'Edge')
    normal = _edge_normals(ds_mesh)

    k_hat = x_vertex / np.linalg.norm(x_vertex, axis=1, keepdims=True)
    outward = x_edge[edges] - x_vertex[:, np.newaxis, :]
    # counterclockwise around the vertex is k x (outward from the vertex)
    counterclockwise = np.cross(k_hat[:, np.newaxis, :], outward)
    sign = np.sign(np.sum(counterclockwise * normal[edges], axis=2))
    sign = np.where(valid, sign, 0.0)

    weights = sign * ds_mesh.dcEdge.values[edges]
    circulation = np.sum(weights * normal_velocity[..., edges], axis=-1)
    return circulation / ds_mesh.areaTriangle.values


def divergence(ds_mesh, normal_velocity):
    """
    Compute the divergence at cells as the net outward flux through each
    cell's edges divided by its area

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS spherical mesh

    normal_velocity : numpy.ndarray
        The normal velocity in m/s with ``nEdges`` as its last dimension

    Returns
    -------
    div : numpy.ndarray
        The divergence in 1/s with ``nCells`` as its last dimension
    """
    n_cells = ds_mesh.sizes['nCells']
    edges_on_cell = ds_mesh.edgesOnCell.values - 1
    n_edges_on_cell = ds_mesh.nEdgesOnCell.values
    max_edges = edges_on_cell.shape[1]
    valid = np.arange(max_edges)[np.newaxis, :] < n_edges_on_cell[:, None]
    edges = np.where(valid, edges_on_cell, 0)

    # positive normal velocity points from the first cell on an edge to the
    # second, so it is an outward flux from the first cell
    first_cell = ds_mesh.cellsOnEdge.values[edges, 0] - 1
    cells = np.arange(n_cells)[:, np.newaxis]
    sign = np.where(first_cell == cells, 1.0, -1.0)
    sign = np.where(valid, sign, 0.0)

    weights = sign * ds_mesh.dvEdge.values[edges]
    flux = np.sum(weights * normal_velocity[..., edges], axis=-1)
    return flux / ds_mesh.areaCell.values


def global_l2(field, area):
    """
    The l2 norm of GSP04 eq. 6: the square root of the area-weighted global
    mean of the field squared

    Parameters
    ----------
    field : numpy.ndarray
        The field on cells or vertices

    area : numpy.ndarray
        The area of each cell or dual triangle

    Returns
    -------
    l2 : float
        The l2 norm
    """
    return np.sqrt(np.sum(area * field**2) / np.sum(area))


def get_output_times(ds, model):
    """
    Get the time of each output record in seconds since the start of the
    simulation

    Parameters
    ----------
    ds : xarray.Dataset
        Model output, opened with ``decode_times=False``

    model : str
        The ocean model, ``mpas-ocean`` or ``omega``

    Returns
    -------
    times : numpy.ndarray
        Seconds since the start of the simulation
    """
    if model == 'mpas-ocean':
        return time_since_start(ds.xtime.values)
    # Omega writes time as seconds since the start of the simulation
    return np.asarray(ds.Time.values, dtype=float)


def contour_levels(interval, values):
    """
    Contour levels at odd multiples of half the interval, as in GSP06:
    ..., -3/2, -1/2, +1/2, +3/2, ... times the interval, covering the range
    of the values

    Parameters
    ----------
    interval : float
        The contour interval

    values : numpy.ndarray
        The values to contour

    Returns
    -------
    levels : numpy.ndarray
        The contour levels, or an empty array if no level falls within the
        range of the values
    """
    max_abs = np.nanmax(np.abs(values))
    count = int(np.floor(max_abs / interval + 0.5))
    if count == 0:
        return np.array([])
    positive = interval * (np.arange(count) + 0.5)
    return np.concatenate([-positive[::-1], positive])


def contour_lon_lat(ax, lon, lat, values, interval, lon_min, lat_bounds):
    """
    Draw black contour lines, with negative contours dashed, of an
    unstructured field on a longitude-latitude rectangle that spans 360
    degrees of longitude

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to draw on

    lon : numpy.ndarray
        Longitude in degrees

    lat : numpy.ndarray
        Latitude in degrees

    values : numpy.ndarray
        The field

    interval : float
        The contour interval

    lon_min : float
        The western edge of the plot in degrees.  The plot spans
        ``lon_min`` to ``lon_min + 360``.

    lat_bounds : tuple of float
        The southern and northern edges of the plot in degrees
    """
    lat_min, lat_max = lat_bounds
    pad = 5.0
    lon = np.mod(lon - lon_min, 360.0) + lon_min
    mask = (lat >= lat_min - pad) & (lat <= lat_max + pad)
    lon = lon[mask]
    lat = lat[mask]
    values = values[mask]

    # copy points across the seam so contours are continuous at the edges
    west = lon < lon_min + pad
    east = lon > lon_min + 360.0 - pad
    lon = np.concatenate([lon, lon[west] + 360.0, lon[east] - 360.0])
    lat = np.concatenate([lat, lat[west], lat[east]])
    values = np.concatenate([values, values[west], values[east]])

    levels = contour_levels(interval, values)
    if len(levels) > 0:
        triangulation = Triangulation(lon, lat)
        ax.tricontour(
            triangulation,
            values,
            levels=levels,
            colors='k',
            linewidths=0.5,
            negative_linestyles='dashed',
        )
    ax.set_xlim(lon_min, lon_min + 360.0)
    ax.set_ylim(lat_min, lat_max)


def _edge_normals(ds_mesh):
    """
    Unit vectors in the direction of positive normal velocity, from the first
    cell on each edge to the second
    """
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    x_cell = _positions(ds_mesh, 'Cell')
    normal = x_cell[cells_on_edge[:, 1]] - x_cell[cells_on_edge[:, 0]]
    return normal / np.linalg.norm(normal, axis=1, keepdims=True)


def _positions(ds_mesh, location):
    """
    Cartesian positions of cells, edges or vertices as an (n, 3) array
    """
    return np.stack(
        [
            ds_mesh[f'x{location}'].values,
            ds_mesh[f'y{location}'].values,
            ds_mesh[f'z{location}'].values,
        ],
        axis=1,
    )
