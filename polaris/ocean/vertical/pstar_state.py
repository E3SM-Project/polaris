"""
Helpers for converting a converged p-star initial state (from
:py:class:`polaris.ocean.vertical.pstar_init.PStarInitStep`) into the
fields that the ocean models read.
"""

import gsw
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


def convert_tracers_to_mpas_ocean(ds, lon, lat):
    """
    Convert conservative temperature and absolute salinity in ``ds`` to the
    MPAS-Ocean tracer conventions (potential temperature and practical
    salinity) using GSW.

    Parameters
    ----------
    ds : xarray.Dataset
        P-star init dataset with ``temperature`` (conservative temperature,
        degC), ``salinity`` (absolute salinity, g/kg), and ``pressure``
        (Pa), each with dimensions ``(Time, nCells, nVertLevels)``.

    lon : float or numpy.ndarray
        Longitude(s) in degrees used in the practical-salinity conversion,
        either a nominal scalar value (e.g. on a planar mesh) or an array
        with dimension ``nCells``.

    lat : float or numpy.ndarray
        Latitude(s) in degrees, a scalar or an array with dimension
        ``nCells``, as for ``lon``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``temperature`` as potential temperature (degC) and
        ``salinity`` as practical salinity (PSU).
    """
    ct = ds['temperature'].values  # (Time, nCells, nVertLevels)
    sa = ds['salinity'].values
    p_pa = ds['pressure'].values  # Pa
    p_dbar = p_pa / 1e4  # Pa -> dbar  (1 dbar = 1e4 Pa)

    lon_arr = np.asarray(lon, dtype=float)
    lat_arr = np.asarray(lat, dtype=float)
    if lon_arr.ndim == 1:
        # (nCells,) -> (Time, nCells, nVertLevels) broadcast shape
        lon_arr = lon_arr[np.newaxis, :, np.newaxis]
        lat_arr = lat_arr[np.newaxis, :, np.newaxis]
    lon_3d = np.broadcast_to(lon_arr, ct.shape)
    lat_3d = np.broadcast_to(lat_arr, ct.shape)

    valid = np.isfinite(ct) & np.isfinite(sa)
    pot_temp = np.full_like(ct, np.nan)
    prac_sal = np.full_like(sa, np.nan)

    pot_temp[valid] = gsw.pt_from_CT(sa[valid], ct[valid])
    prac_sal[valid] = gsw.SP_from_SA(
        sa[valid], p_dbar[valid], lon_3d[valid], lat_3d[valid]
    )

    ds['temperature'] = xr.DataArray(
        data=pot_temp,
        dims=ds['temperature'].dims,
        attrs={
            'long_name': 'potential temperature',
            'units': 'degC',
        },
    )
    ds['salinity'] = xr.DataArray(
        data=prac_sal,
        dims=ds['salinity'].dims,
        attrs={
            'long_name': 'practical salinity',
            'units': 'PSU',
        },
    )
    return ds
