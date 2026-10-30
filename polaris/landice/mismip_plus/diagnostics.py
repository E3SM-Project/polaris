"""
The MISMIP+ diagnostics, computed from the flotation criterion
"""

import numpy as np
import xarray as xr

from polaris.landice.mismip_plus.geometry import (
    DOMAIN_WIDTH,
    ICE_DENSITY,
    OCEAN_DENSITY,
)


def thickness_above_flotation(thickness, bed):
    """
    Compute the thickness above flotation

    Parameters
    ----------
    thickness : xarray.DataArray
        The ice thickness in m

    bed : xarray.DataArray
        The bed elevation in m, relative to sea level

    Returns
    -------
    haf : xarray.DataArray
        The thickness above flotation in m, positive where ice is grounded
    """
    return thickness + (OCEAN_DENSITY / ICE_DENSITY) * np.minimum(bed, 0.0)


def compute_diagnostics(ds, ds_mesh=None):
    """
    Compute the ice volume, volume above flotation, grounded area and
    centerline grounding line of MISMIP+

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``thickness`` and ``bedTopography``, with or without a
        ``Time`` dimension

    ds_mesh : xarray.Dataset, optional
        A dataset with ``areaCell``, ``xCell`` and ``yCell``, by default
        ``ds``

    Returns
    -------
    ds_diag : xarray.Dataset
        The diagnostics ``iceVolume`` (m^3), ``iceVAF`` (m^3),
        ``groundedArea`` (m^2) and ``xGL`` (m), the position at which the
        grounding line crosses the centerline, with the same ``Time``
        dimension as ``ds``
    """
    if ds_mesh is None:
        ds_mesh = ds
    area = ds_mesh.areaCell
    thickness = ds.thickness
    haf = thickness_above_flotation(thickness, ds.bedTopography)
    grounded = np.logical_and(thickness > 0.0, haf > 0.0)

    ds_diag = xr.Dataset()
    ds_diag['iceVolume'] = (thickness * area).sum(dim='nCells')
    ds_diag['iceVAF'] = (haf.clip(min=0.0) * area).sum(dim='nCells')
    ds_diag['groundedArea'] = area.where(grounded, 0.0).sum(dim='nCells')
    ds_diag['xGL'] = _centerline_grounding_line(haf, ds_mesh)

    for var, units in [
        ('iceVolume', 'm^3'),
        ('iceVAF', 'm^3'),
        ('groundedArea', 'm^2'),
        ('xGL', 'm'),
    ]:
        ds_diag[var].attrs['units'] = units
    return ds_diag


def _centerline_grounding_line(haf, ds_mesh):
    """
    Interpolate linearly between cell centers along the centerline to where
    the grounded ice next to the ice divide ends
    """
    x_cell = ds_mesh.xCell.values
    y_cell = ds_mesh.yCell.values
    dc = float(ds_mesh.dcEdge.values[0])
    dy = 0.5 * np.sqrt(3.0) * dc
    row = np.nonzero(
        np.isclose(y_cell, 0.5 * DOMAIN_WIDTH, atol=0.05 * dy, rtol=0.0)
    )[0]
    if len(row) == 0:
        raise ValueError('The mesh has no row of cells on the centerline')
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
            # no grounding line along the centerline
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
