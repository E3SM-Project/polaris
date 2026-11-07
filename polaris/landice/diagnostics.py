"""
Diagnostics of MALI's ice, computed from the flotation criterion, for any
dataset with MALI's thickness, bed and mesh variables
"""

import numpy as np
import xarray as xr


def thickness_above_flotation(thickness, bed, ice_density, ocean_density):
    """
    Compute the thickness above flotation

    Parameters
    ----------
    thickness : xarray.DataArray
        The ice thickness in m

    bed : xarray.DataArray
        The bed elevation in m, relative to sea level

    ice_density : float
        The density of ice in kg m^-3

    ocean_density : float
        The density of seawater in kg m^-3

    Returns
    -------
    haf : xarray.DataArray
        The thickness above flotation in m, positive where ice is grounded
    """
    return thickness + (ocean_density / ice_density) * np.minimum(bed, 0.0)


def compute_volume_and_area(
    thickness, bed, area_cell, ice_density, ocean_density
):
    """
    Compute the ice volume, volume above flotation and grounded area

    Parameters
    ----------
    thickness : xarray.DataArray
        The ice thickness in m, with an ``nCells`` dimension and with or
        without a ``Time`` dimension

    bed : xarray.DataArray
        The bed elevation in m, relative to sea level

    area_cell : xarray.DataArray
        The area of each cell in m^2

    ice_density : float
        The density of ice in kg m^-3

    ocean_density : float
        The density of seawater in kg m^-3

    Returns
    -------
    ds : xarray.Dataset
        ``iceVolume`` (m^3), ``iceVAF`` (m^3) and ``groundedArea`` (m^2),
        with the ``Time`` dimension of ``thickness``, if any
    """
    haf = thickness_above_flotation(thickness, bed, ice_density, ocean_density)
    grounded = np.logical_and(thickness > 0.0, haf > 0.0)

    ds = xr.Dataset()
    ds['iceVolume'] = (thickness * area_cell).sum(dim='nCells')
    ds['iceVAF'] = (haf.clip(min=0.0) * area_cell).sum(dim='nCells')
    ds['groundedArea'] = area_cell.where(grounded, 0.0).sum(dim='nCells')
    for var, units in [
        ('iceVolume', 'm^3'),
        ('iceVAF', 'm^3'),
        ('groundedArea', 'm^2'),
    ]:
        ds[var].attrs['units'] = units
    return ds


def grounding_line_points(haf, ds_mesh):
    """
    Find where the grounding line crosses the edges of the mesh at one time:
    on each edge between a cell with positive thickness above flotation and
    one with negative thickness above flotation, interpolated linearly
    between the cell centers.  Edges where grounded ice meets ice-free ocean
    are included.  The mesh must not be periodic.

    Parameters
    ----------
    haf : xarray.DataArray
        The thickness above flotation in m, with only an ``nCells``
        dimension

    ds_mesh : xarray.Dataset
        A dataset with ``cellsOnEdge``, ``xCell`` and ``yCell``

    Returns
    -------
    x : numpy.ndarray
        The x coordinates of the grounding-line points in m

    y : numpy.ndarray
        The y coordinates of the grounding-line points in m
    """
    if haf.dims != ('nCells',):
        raise ValueError(
            f'Expected thickness above flotation with only an nCells '
            f'dimension, not {haf.dims}'
        )
    haf_cell = haf.values
    cells = ds_mesh.cellsOnEdge.values - 1
    cells = cells[np.all(cells >= 0, axis=1)]
    haf0 = haf_cell[cells[:, 0]]
    haf1 = haf_cell[cells[:, 1]]
    crossing = haf0 * haf1 < 0.0
    cells = cells[crossing]
    haf0 = haf0[crossing]
    haf1 = haf1[crossing]
    frac = haf0 / (haf0 - haf1)

    x_cell = ds_mesh.xCell.values
    y_cell = ds_mesh.yCell.values
    x0 = x_cell[cells[:, 0]]
    y0 = y_cell[cells[:, 0]]
    x = x0 + frac * (x_cell[cells[:, 1]] - x0)
    y = y0 + frac * (y_cell[cells[:, 1]] - y0)
    return x, y


def grounding_line_on_row(haf, ds_mesh, y):
    """
    Find where the grounding line crosses a row of cell centers at a given
    y, such as a flowline down the middle of a channel.  Along the row,
    in increasing x, the position is interpolated linearly between the
    centers of the last grounded cell and the first cell where the thickness
    above flotation is not positive.

    Parameters
    ----------
    haf : xarray.DataArray
        The thickness above flotation in m, with an ``nCells`` dimension and
        with or without a ``Time`` dimension

    ds_mesh : xarray.Dataset
        A dataset with ``xCell``, ``yCell`` and ``dcEdge`` on a planar
        hexagonal mesh with a row of cell centers at ``y``

    y : float
        The y coordinate of the row in m

    Returns
    -------
    x_gl : xarray.DataArray
        The x coordinate of the grounding line in m, with the ``Time``
        dimension of ``haf``, if any, and NaN where the row has no grounding
        line
    """
    x_cell = ds_mesh.xCell.values
    y_cell = ds_mesh.yCell.values
    dc = float(ds_mesh.dcEdge.values[0])
    dy = 0.5 * np.sqrt(3.0) * dc
    row = np.nonzero(np.isclose(y_cell, y, atol=0.05 * dy, rtol=0.0))[0]
    if len(row) == 0:
        raise ValueError(f'The mesh has no row of cells at y = {y} m')
    row = row[np.argsort(x_cell[row])]
    x_row = x_cell[row]

    has_time = 'Time' in haf.dims
    if has_time:
        haf_row = haf.isel(nCells=row).transpose('Time', 'nCells').values
    else:
        haf_row = haf.isel(nCells=row).values[np.newaxis, :]

    x_gl = np.nan * np.ones(haf_row.shape[0])
    for t_index in range(haf_row.shape[0]):
        floating = np.nonzero(haf_row[t_index, :] <= 0.0)[0]
        if len(floating) == 0 or floating[0] == 0:
            # no grounding line along the row
            continue
        i1 = floating[0]
        i0 = i1 - 1
        haf0 = haf_row[t_index, i0]
        haf1 = haf_row[t_index, i1]
        x_gl[t_index] = x_row[i0] + haf0 / (haf0 - haf1) * (
            x_row[i1] - x_row[i0]
        )

    if has_time:
        return xr.DataArray(x_gl, dims=('Time',))
    return xr.DataArray(x_gl[0])
