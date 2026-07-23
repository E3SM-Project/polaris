"""
Helpers for converting a converged p-star initial state (from
:py:class:`polaris.ocean.vertical.pstar_init.PStarInitStep`) into the
fields that the ocean models read.
"""

import numpy as np
import xarray as xr


def layer_thickness_from_geom_interfaces(ds):
    """
    Compute ``restingThickness`` and ``layerThickness`` from the converged
    geometric interface heights in ``ds``.

    Both fields equal the converged geometric layer thickness (appropriate
    for a quiescent initialisation).  Layers below the seafloor are zeroed
    out using ``cellMask``.

    Parameters
    ----------
    ds : xarray.Dataset
        P-star init dataset containing ``GeomZInterface`` and ``cellMask``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``restingThickness`` and ``layerThickness`` added.
    """
    geom_z_inter = ds['GeomZInterface']  # (Time, nCells, nVertLevelsP1)
    layer_thick = (
        geom_z_inter.isel(nVertLevelsP1=slice(None, -1))
        - geom_z_inter.isel(nVertLevelsP1=slice(1, None))
    ).rename({'nVertLevelsP1': 'nVertLevels'})

    cell_mask = ds['cellMask'].astype(bool)
    layer_thick = layer_thick.where(cell_mask, other=0.0)
    layer_thick.attrs['long_name'] = 'layer thickness'
    layer_thick.attrs['units'] = 'm'

    ds['restingThickness'] = layer_thick
    ds.restingThickness.attrs['long_name'] = 'resting layer thickness'
    ds.restingThickness.attrs['units'] = 'm'

    ds['layerThickness'] = layer_thick
    return ds


def add_quiescent_normal_velocity(ds, ds_mesh):
    """
    Add a quiescent ``normalVelocity`` field (all zeros) to ``ds``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset to add the field to, with an ``nVertLevels`` dimension.

    ds_mesh : xarray.Dataset
        Horizontal mesh dataset, used to determine ``nEdges``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``normalVelocity`` added.
    """
    nedges = ds_mesh.sizes['nEdges']
    nlevels = ds.sizes['nVertLevels']
    ds['normalVelocity'] = xr.DataArray(
        data=np.zeros((1, nedges, nlevels), dtype=float),
        dims=['Time', 'nEdges', 'nVertLevels'],
        attrs={'long_name': 'normal velocity', 'units': 'm s-1'},
    )
    return ds


def add_density_from_specvol(ds):
    """
    Add an in-situ ``Density`` field computed from ``SpecVol`` to ``ds``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing ``SpecVol``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``Density`` added.
    """
    ds['Density'] = 1.0 / ds['SpecVol']
    ds.Density.attrs['long_name'] = 'in-situ density'
    ds.Density.attrs['units'] = 'kg m-3'
    return ds
