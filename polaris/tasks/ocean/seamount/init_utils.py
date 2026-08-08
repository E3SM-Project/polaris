"""
Shared helpers for the seamount init step: the Beckmann and Haidvogel
density profile and the tracers that reproduce it under either equation of
state.

Kept free of ``mpas_tools`` and of the step framework so the unit tests can
import it directly.
"""

import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.eos import ct_from_potential_density


def compute_target_density(
    config: PolarisConfigParser, z_mid: xr.DataArray
) -> xr.DataArray:
    """
    Compute the target Beckmann and Haidvogel stratification, either the
    linear profile of their eqn 15 or the exponential profile of their
    eqn 16.

    The profile is a potential density referenced to the surface.  Under the
    linear equation of state, which has no pressure dependence, that is the
    same thing as the density; under a nonlinear equation of state it is
    not, and reading it as in-situ density would be unphysical -- TEOS-10
    in-situ density at 5000 m is near 1050 kg m-3 from compression alone,
    well outside the range this profile spans.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[seamount]`` stratification options.

    z_mid : xarray.DataArray
        The geometric height (m, negative down) of the layer midpoints.

    Returns
    -------
    xarray.DataArray
        The target potential density (kg m-3) at the layer midpoints.
    """
    section = config['seamount']
    stratification_type = section.get('seamount_stratification_type')

    if stratification_type == 'linear':
        coef = section.getfloat('seamount_density_coef_linear')
        gradient = section.getfloat('seamount_density_gradient_linear')
        depth = section.getfloat('seamount_density_depth_linear')
        density = coef - gradient * z_mid / depth
    elif stratification_type == 'exponential':
        coef = section.getfloat('seamount_density_coef_exp')
        gradient = section.getfloat('seamount_density_gradient_exp')
        depth = section.getfloat('seamount_density_depth_exp')
        density = coef - gradient * np.exp(z_mid / depth)
    else:
        raise ValueError(
            f'Unsupported seamount_stratification_type: {stratification_type}'
        )

    density.attrs['long_name'] = 'target potential density'
    density.attrs['units'] = 'kg m-3'
    return density


def compute_tracers(
    config: PolarisConfigParser, z_mid: xr.DataArray
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the temperature and salinity that reproduce the Beckmann and
    Haidvogel stratification under the configured equation of state.

    Salinity is constant, so all of the stratification is carried by
    temperature.  For ``eos_type = linear`` the linear equation of state is
    inverted algebraically; for ``eos_type = teos-10`` the tracers are
    conservative temperature and absolute salinity, and the inversion is
    through :py:func:`polaris.ocean.eos.ct_from_potential_density`.

    Both branches reproduce the same potential density, so the two
    equations of state give the same buoyancy stratification and differ
    only in how density depends on pressure.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[seamount]`` and ``[ocean]`` equation of
        state options.

    z_mid : xarray.DataArray
        The geometric height (m, negative down) of the layer midpoints.

    Returns
    -------
    temperature : xarray.DataArray
        Potential temperature for a linear equation of state, conservative
        temperature for TEOS-10 (degC).

    salinity : xarray.DataArray
        Practical salinity for a linear equation of state, absolute
        salinity for TEOS-10.
    """
    density = compute_target_density(config, z_mid)

    constant_salinity = config.getfloat('seamount', 'constant_salinity')
    salinity = constant_salinity * xr.ones_like(density)

    eos_type = config.get('ocean', 'eos_type').strip()

    if eos_type == 'linear':
        section = config['ocean']
        rhoref = section.getfloat('eos_linear_rhoref')
        tref = section.getfloat('eos_linear_Tref')
        sref = section.getfloat('eos_linear_Sref')
        alpha = section.getfloat('eos_linear_alpha')
        beta = section.getfloat('eos_linear_beta')

        # Back-solve the linear EOS that both Polaris and the ocean model
        # apply, rho = rho_ref - alpha * (T - T_ref) + beta * (S - S_ref),
        # for the temperature that reproduces the target density.  The
        # salinity term matters: dropping it leaves the model's density
        # offset from the Beckmann and Haidvogel profile by beta * S.
        temperature = (
            tref + (rhoref + beta * (salinity - sref) - density) / alpha
        )
        temperature.attrs['long_name'] = 'potential temperature'
        salinity.attrs['long_name'] = 'practical salinity'
        salinity.attrs['units'] = 'PSU'
    elif eos_type == 'teos-10':
        temperature = ct_from_potential_density(density, salinity)
        salinity.attrs['long_name'] = 'absolute salinity'
        salinity.attrs['units'] = 'g kg-1'
    else:
        raise ValueError(
            f'The seamount task does not support eos_type: {eos_type}'
        )

    temperature.attrs['units'] = 'degC'
    return temperature, salinity
