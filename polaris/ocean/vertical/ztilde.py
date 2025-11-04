"""
Conversions between Omega pseudo-height and pressure.

Omega's vertical coordinate is pseudo-height
    z_tilde = -p / (rho0 * g)
with z_tilde positive upward. Here, ``p`` is sea pressure in Pascals (Pa),
``rho0`` is a reference density (kg m^-3) supplied by the caller, and
``g`` is gravitational acceleration obtained from
``mpas_tools.cime.constants``.
"""

from typing import Union

import xarray as xr
from mpas_tools.cime.constants import constants

ArrayLike = Union[xr.DataArray]

__all__ = [
    'z_tilde_from_pressure',
    'pressure_from_z_tilde',
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
