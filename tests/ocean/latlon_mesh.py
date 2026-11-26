"""
A small spherical mesh of latitude-longitude cells, for tests of lines of
latitude.

The cells are the boxes of a regular latitude-longitude grid, joined by an
edge to their neighbors to the north, south, east and west.  That is not an
MPAS mesh, but it has every field a line of latitude is found from:
``cellsOnEdge``, the cell coordinates, ``dvEdge`` and ``dcEdge``.
"""

import numpy as np
import xarray as xr

EARTH_RADIUS = 6.371e6


def latlon_mesh(dlat=10.0, dlon=10.0, radius=EARTH_RADIUS):
    """
    Make the mesh

    Parameters
    ----------
    dlat, dlon : float, optional
        The size of each cell in degrees

    radius : float, optional
        The radius of the sphere (m)

    Returns
    -------
    ds_mesh : xarray.Dataset
        The mesh, with ``cellsOnEdge`` one-based and coordinates in radians
    """
    lat_centers = np.arange(-90.0 + 0.5 * dlat, 90.0, dlat)
    lon_centers = np.arange(0.5 * dlon, 360.0, dlon)
    n_lat = len(lat_centers)
    n_lon = len(lon_centers)
    lat_cell, lon_cell = np.meshgrid(lat_centers, lon_centers, indexing='ij')
    index = np.arange(n_lat * n_lon).reshape(n_lat, n_lon)

    # edges to the north of each cell but the northernmost row, and to the
    # east of each cell, across the 0/360 seam too
    north = np.stack([index[:-1, :].ravel(), index[1:, :].ravel()], axis=1)
    east = np.stack(
        [index.ravel(), np.roll(index, -1, axis=1).ravel()], axis=1
    )
    cells_on_edge = np.concatenate([north, east])

    lat_rad = np.deg2rad(lat_cell.ravel())
    lon_rad = np.deg2rad(lon_cell.ravel())
    lat1 = lat_rad[cells_on_edge[:, 0]]
    lat2 = lat_rad[cells_on_edge[:, 1]]
    lon1 = lon_rad[cells_on_edge[:, 0]]
    lon2 = lon_rad[cells_on_edge[:, 1]]
    a = (
        np.sin(0.5 * (lat2 - lat1)) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(0.5 * (lon2 - lon1)) ** 2
    )
    dc_edge = 2.0 * radius * np.arcsin(np.sqrt(a))

    # a north edge is the boundary between two rows, a parallel; an east
    # edge is a meridian a cell high
    boundary_lat = 0.5 * (lat1 + lat2)
    n_north = len(north)
    dv_edge = np.empty(len(cells_on_edge))
    dv_edge[:n_north] = (
        radius * np.cos(boundary_lat[:n_north]) * np.deg2rad(dlon)
    )
    dv_edge[n_north:] = radius * np.deg2rad(dlat)

    return xr.Dataset(
        data_vars=dict(
            cellsOnEdge=(('nEdges', 'TWO'), cells_on_edge + 1),
            latCell=(('nCells',), lat_rad),
            lonCell=(('nCells',), lon_rad),
            dvEdge=(('nEdges',), dv_edge),
            dcEdge=(('nEdges',), dc_edge),
        )
    )
