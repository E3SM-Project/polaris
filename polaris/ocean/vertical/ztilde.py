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
from mpas_tools.cime.constants import constants

from polaris.config import PolarisConfigParser
from polaris.ocean.eos import compute_specvol

__all__ = [
    'z_tilde_from_pressure',
    'pressure_from_z_tilde',
    'pressure_and_spec_vol_from_state_at_geom_height',
    'pressure_from_geom_thickness',
    'geom_z_from_z_tilde',
]


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

    g = constants['SHR_CONST_G']

    z = -(p) / (rho0 * g)
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

    g = constants['SHR_CONST_G']

    p = -(z_tilde) * (rho0 * g)
    return p.assign_attrs(
        {
            'long_name': 'sea pressure',
            'units': 'Pa',
            'note': 'p = -z_tilde * (rho0 * g)',
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
        The geometric thickness of each layer.

    spec_vol : xarray.DataArray
        The specific volume at each layer.

    Returns
    -------
    p_interface : xarray.DataArray
        The pressure at layer interfaces.

    p_mid : xarray.DataArray
        The pressure at layer midpoints.
    """

    n_vert_levels = geom_layer_thickness.sizes['nVertLevels']
    g = constants['SHR_CONST_G']

    p_top = surf_pressure
    p_interface_list = [p_top]
    p_mid_list = []

    for k in range(n_vert_levels):
        dp = (
            g
            / spec_vol.isel(nVertLevels=k)
            * geom_layer_thickness.isel(nVertLevels=k)
        )
        p_bot = p_top + dp
        p_interface_list.append(p_bot)
        p_mid_list.append(p_top + 0.5 * dp)
        p_top = p_bot

    dims = list(geom_layer_thickness.dims)
    interface_dims = list(dims) + ['nVertLevelsP1']
    interface_dims.remove('nVertLevels')

    p_interface = xr.concat(p_interface_list, dim='nVertLevelsP1').transpose(
        *interface_dims
    )
    p_mid = xr.concat(p_mid_list, dim='nVertLevels').transpose(*dims)

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


def geom_z_from_z_tilde(
    pseudo_thickness: xr.DataArray,
    bottom_depth: xr.DataArray,
    spec_vol: xr.DataArray,
    rho0: float,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute geometric height z at layer interfaces and midpoints given
    pseudo-layer thicknesses, bottom depth, specific volume and reference
    density. This calculation assumes a constant specific volume within each
    layer.

    Parameters
    ----------
    pseudo_thickness : xarray.DataArray
        The pseudo thickness of each layer.

    spec_vol : xarray.DataArray
        The specific volume at each layer.

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor.

    rho0 : float
        Reference density in kg m^-3.

    Returns
    -------
    z_interface : xarray.DataArray
        The elevation of layer interfaces.

    z_mid : xarray.DataArray
        The elevation of layer midpoints.
    """

    n_vert_levels = pseudo_thickness.sizes['nVertLevels']

    z_bot = -bottom_depth
    z_interface_list = [z_bot]
    z_mid_list = []

    for k in range(n_vert_levels - 1, -1, -1):
        dz = (
            rho0
            * spec_vol.isel(nVertLevels=k)
            * pseudo_thickness.isel(nVertLevels=k)
        )
        z_top = z_bot + dz
        z_interface_list.append(z_top)
        z_mid_list.append(z_bot + 0.5 * dz)
        z_bot = z_top

    dims = list(pseudo_thickness.dims)
    interface_dims = list(dims) + ['nVertLevelsP1']
    interface_dims.remove('nVertLevels')

    z_interface = xr.concat(
        reversed(z_interface_list), dim='nVertLevelsP1'
    ).transpose(*interface_dims)
    z_mid = xr.concat(reversed(z_mid_list), dim='nVertLevels').transpose(*dims)

    return z_interface, z_mid
