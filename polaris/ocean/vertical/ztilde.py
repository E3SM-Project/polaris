"""
Conversions between Omega pseudo-height and pressure.

Omega's vertical coordinate is pseudo-height
    z_tilde = -p / (rho0 * g)
with z_tilde positive upward. Here, ``p`` is sea pressure in Pascals (Pa),
``rho0`` is a reference density (kg m^-3) supplied by the caller, and
``g`` is gravitational acceleration obtained from
``mpas_tools.cime.constants``.
"""

import logging

import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.eos import compute_specvol

__all__ = [
    'z_tilde_from_pressure',
    'pressure_from_z_tilde',
    'pressure_and_spec_vol_from_state_at_geom_height',
    'pressure_from_geom_thickness',
]

# TODO: replace with value looked up in GCD YAML file when possible
# Temporarily hard-coded with the GCD/Omega value
Gravity = 9.80665


def z_tilde_from_pressure(p: xr.DataArray, rho0: float) -> xr.DataArray:
    """
    Convert sea pressure to pseudo-height.

    z_tilde = -p / (rho0 * g)

    Parameters
    ----------
    p : xarray.DataArray
        Sea pressure in Pascals (Pa).

    rho0 : float
        Reference density in kg m^-3.

    Returns
    -------
    xarray.DataArray
        Pseudo-height with the same shape and coords as ``p`` (units: m).
    """

    z = -(p) / (rho0 * Gravity)
    return z.assign_attrs(
        {
            'long_name': 'pseudo-height',
            'units': 'm',
            'note': 'z_tilde = -p / (rho0 * g)',
        }
    )


def pressure_from_z_tilde(z_tilde: xr.DataArray, rho0: float) -> xr.DataArray:
    """
    Convert pseudo-height to sea pressure.

    p = -z_tilde * (rho0 * g)

    Parameters
    ----------
    z_tilde : xarray.DataArray
        Pseudo-height in meters (m), positive upward.

    rho0 : float
        Reference density in kg m^-3.

    Returns
    -------
    xarray.DataArray
        Sea pressure with the same shape and coords as ``z_tilde`` (Pa).
    """

    p = -(z_tilde) * (rho0 * Gravity)
    return p.assign_attrs(
        {
            'long_name': 'sea pressure',
            'units': 'Pa',
            'note': 'p = -rho0 * g * z_tilde',
        }
    )


def pressure_from_geom_thickness(
    surf_pressure: xr.DataArray,
    geom_layer_thickness: xr.DataArray,
    spec_vol: xr.DataArray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the pressure at layer interfaces and midpoints given surface
    pressure, geometric layer thicknesses, and specific volume. This
    calculation assumes a constant specific volume within each layer.

    Parameters
    ----------
    surf_pressure : xarray.DataArray
        The surface pressure at the top of the water column.

    geom_layer_thickness : xarray.DataArray
        The geometric thickness of each layer, set to zero for invalid layers.

    spec_vol : xarray.DataArray
        The specific volume at each layer.

    Returns
    -------
    p_interface : xarray.DataArray
        The pressure at layer interfaces.

    p_mid : xarray.DataArray
        The pressure at layer midpoints.
    """

    dp = Gravity / spec_vol * geom_layer_thickness

    p_interface = dp.cumsum(dim='nVertLevels').pad(
        nVertLevels=(1, 0), mode='constant', constant_values=0.0
    )
    p_interface = surf_pressure + p_interface
    p_interface = p_interface.rename({'nVertLevels': 'nVertLevelsP1'})

    p_interface_top = p_interface.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    p_mid = p_interface_top + 0.5 * dp

    dims = list(geom_layer_thickness.dims)
    interface_dims = [dim for dim in dims if dim != 'nVertLevels']
    interface_dims.append('nVertLevelsP1')

    p_interface = p_interface.transpose(*interface_dims)
    p_mid = p_mid.transpose(*dims)

    return p_interface, p_mid


def pressure_and_spec_vol_from_state_at_geom_height(
    config: PolarisConfigParser,
    geom_layer_thickness: xr.DataArray,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    surf_pressure: xr.DataArray,
    iter_count: int,
    logger: logging.Logger | None = None,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Compute the pressure at layer interfaces and midpoints, as well as the
    specific volume at midpoints given geometric layer thicknesses,
    temperature and salinity at layer midpoints (i.e. constant in geometric
    height, not pseudo-height), and surface pressure. The solution is found
    iteratively starting from a specific volume calculated from the reference
    density.

    Requires config option ``[vertical_grid] rho0`` and those required
    for {py:func}`polaris.ocean.eos.compute_specvol()`.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters defining the equation of state
        and ``rho0`` for the pseudo-height.

    geom_layer_thickness : xarray.DataArray
        The geometric thickness of each layer.

    temperature : xarray.DataArray
        The temperature at layer midpoints.

    salinity : xarray.DataArray
        The salinity at layer midpoints.

    surf_pressure : xarray.DataArray
        The surface pressure at the top of the water column.

    iter_count : int
        The number of iterations to perform.

    logger : logging.Logger, optional
        A logger for logging iteration information.

    Returns
    -------
    p_interface : xarray.DataArray
        The pressure at layer interfaces.

    p_mid : xarray.DataArray
        The pressure at layer midpoints.

    spec_vol : xarray.DataArray
        The specific volume at layer midpoints.
    """

    rho0 = config.getfloat('vertical_grid', 'rho0')
    if rho0 is None:
        raise ValueError(
            'Config option [vertical_grid] rho0 must be set to use '
            'pressure_and_spec_vol_from_state_at_geom_height().'
        )

    spec_vol = 1.0 / rho0 * xr.ones_like(geom_layer_thickness)

    p_interface, p_mid = pressure_from_geom_thickness(
        surf_pressure=surf_pressure,
        geom_layer_thickness=geom_layer_thickness,
        spec_vol=spec_vol,
    )

    prev_spec_vol = spec_vol

    for iter in range(iter_count):
        spec_vol = compute_specvol(
            config=config,
            temperature=temperature,
            salinity=salinity,
            pressure=p_mid,
        )

        if logger is not None:
            delta_spec_vol = spec_vol - prev_spec_vol
            max_delta = np.abs(delta_spec_vol).max().item()
            prev_spec_vol = spec_vol
            logger.info(
                f'Max change in specific volume during EOS iteration {iter}: '
                f'{max_delta:.3e} m3 kg-1'
            )

        p_interface, p_mid = pressure_from_geom_thickness(
            surf_pressure=surf_pressure,
            geom_layer_thickness=geom_layer_thickness,
            spec_vol=spec_vol,
        )

    return p_interface, p_mid, spec_vol


def geom_height_from_pseudo_height(
    geom_z_bot: xr.DataArray,
    h_tilde: xr.DataArray,
    spec_vol: xr.DataArray,
    min_level_cell: np.ndarray,
    max_level_cell: np.ndarray,
    rho0: float,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Sum geometric heights from pseudo-heights and specific volume.

    Parameters
    ----------
    geom_z_bot : xarray.DataArray
        Geometric height at the bathymetry for each water column.

    h_tilde : xarray.DataArray
        Pseudo-thickness of vertical layers, set to zero for invalid layers.

    spec_vol : xarray.DataArray
        Specific volume at midpoints of vertical layers.

    min_level_cell : xarray.DataArray
        Minimum valid zero-based level index for each cell.

    max_level_cell : xarray.DataArray
        Maximum valid zero-based level index for each cell.

    rho0 : float
        Reference density in kg m^-3.

    Returns
    -------
    geom_z_inter : xarray.DataArray
        Geometric height at layer interfaces.

    geom_z_mid : xarray.DataArray
        Geometric height at layer midpoints.
    """
    # geometric height starts with geom_z_bot at the bottom
    # and adds up the contributions from each layer above

    n_vert_levels = spec_vol.sizes['nVertLevels']

    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mid_mask = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    )

    geom_thickness = (spec_vol * h_tilde * rho0).where(mid_mask, 0.0)

    dz_rev = geom_thickness.isel(nVertLevels=slice(None, None, -1))
    sum_from_level = dz_rev.cumsum(dim='nVertLevels').isel(
        nVertLevels=slice(None, None, -1)
    )

    geom_z_inter_top = geom_z_bot + sum_from_level
    geom_z_inter = geom_z_inter_top.pad(
        nVertLevels=(0, 1), mode='constant', constant_values=0.0
    )
    geom_z_inter[dict(nVertLevels=n_vert_levels)] = geom_z_bot
    geom_z_inter = geom_z_inter.rename({'nVertLevels': 'nVertLevelsP1'})

    z_index_p1 = xr.DataArray(
        np.arange(n_vert_levels + 1), dims=['nVertLevelsP1']
    )
    inter_mask = np.logical_and(
        z_index_p1 >= min_level_cell,
        z_index_p1 <= max_level_cell + 1,
    )
    geom_z_inter = geom_z_inter.where(inter_mask)

    geom_z_inter_lower = geom_z_inter.isel(
        nVertLevelsP1=slice(1, None)
    ).rename({'nVertLevelsP1': 'nVertLevels'})
    geom_z_mid = (geom_z_inter_lower + 0.5 * geom_thickness).where(mid_mask)

    # transpose to match h_tilde.  For geom_z_inter, replace nVertLevels with
    # nVertLevelsP1 at the same index in the list of dimensions
    z_mid_dims = list(h_tilde.dims)
    z_inter_dims = z_mid_dims.copy()
    z_inter_dims[z_mid_dims.index('nVertLevels')] = 'nVertLevelsP1'
    geom_z_inter = geom_z_inter.transpose(*z_inter_dims)
    geom_z_mid = geom_z_mid.transpose(*z_mid_dims)

    return geom_z_inter, geom_z_mid
