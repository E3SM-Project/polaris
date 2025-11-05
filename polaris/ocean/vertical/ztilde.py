"""
Conversions between Omega pseudo-height and pressure.

Omega's vertical coordinate is pseudo-height
    z_tilde = -p / (rho0 * g)
with z_tilde positive upward. Here, ``p`` is sea pressure in Pascals (Pa),
``rho0`` is a reference density (kg m^-3) supplied by the caller, and
``g`` is gravitational acceleration obtained from
``mpas_tools.cime.constants``.
"""

import xarray as xr
from mpas_tools.cime.constants import constants

__all__ = [
    'z_tilde_from_pressure',
    'pressure_from_z_tilde',
    'z_from_z_tilde',
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


def z_from_z_tilde(
    layer_thickness: xr.DataArray,
    bottom_depth: xr.DataArray,
    spec_vol: xr.DataArray,
    rho0: float,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute geometric height z at layer interfaces and midpoints given the
    layer thicknesses, bottom depth, specific volume and reference density.
    This calculation assumes a constant specific volume within each layer.

    Parameters
    ----------
    layer_thickness : xarray.DataArray
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
        The elevation of layer centers.
    """

    n_vert_levels = layer_thickness.sizes['nVertLevels']

    z_bot = -bottom_depth
    z_interface_list = [z_bot]
    z_mid_list = []

    for k in range(n_vert_levels - 1, -1, -1):
        dz = (
            rho0
            * spec_vol.isel(nVertLevels=k)
            * layer_thickness.isel(nVertLevels=k)
        )
        z_top = z_bot + dz
        z_interface_list.append(z_top)
        z_mid_list.append(z_bot + 0.5 * dz)
        z_bot = z_top

    dims = list(layer_thickness.dims)
    interface_dims = list(dims) + ['nVertLevelsP1']
    interface_dims.remove('nVertLevels')

    z_interface = xr.concat(
        reversed(z_interface_list), dim='nVertLevelsP1'
    ).transpose(*interface_dims)
    z_mid = xr.concat(reversed(z_mid_list), dim='nVertLevels').transpose(*dims)

    return z_interface, z_mid
