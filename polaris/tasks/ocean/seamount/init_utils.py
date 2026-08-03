"""
Shared helpers for the seamount init step: the Beckmann and Haidvogel
density profile and the tracers that reproduce it under either equation of
state, plus the profile that is linear in pressure.

Kept free of ``mpas_tools`` and of the step framework so the unit tests can
import it directly.
"""

import logging

import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.eos import compute_specvol, ct_from_potential_density
from polaris.ocean.vertical.ztilde import pressure_from_geom_thickness

RhoSw = get_constant('seawater_density_reference')

# Pascals per decibar, the unit the linear-in-pressure profile is configured
# in
DBAR_TO_PA = 1.0e4

# The linear-in-pressure profile is a fixed point rather than a formula: the
# tracers are prescribed as a function of pressure, and pressure follows from
# the tracers through the specific volume.  The iteration contracts by roughly
# the fractional density range of the column per pass, so it reaches round-off
# in well under ten; the cap is a guard, not a working limit.
MAX_PRESSURE_ITERATIONS = 100

# Convergence tolerance on the layer-mean temperature (degC).  The whole point
# of this profile is that the reconstruction the finite-volume pressure
# gradient performs is exact on it, so the fixed point has to be converged to
# round-off rather than to something merely small.
PRESSURE_ITERATION_TOLERANCE = 1.0e-12


def compute_target_density(
    config: PolarisConfigParser, z_mid: xr.DataArray
) -> xr.DataArray:
    """
    Compute the target Beckmann and Haidvogel stratification, either the
    linear profile of their eqn 15 or the exponential profile of their
    eqn 16.

    These are the two stratifications that are prescribed as a density.  The
    ``linear_pressure`` stratification prescribes temperature directly and so
    has no target density to compute; see
    :py:func:`compute_tracers_linear_in_pressure`.

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
    elif stratification_type == 'linear_pressure':
        raise ValueError(
            'The linear_pressure stratification prescribes temperature as a '
            'function of pressure, not a target density.  Call '
            'compute_tracers_linear_in_pressure() instead.'
        )
    else:
        raise ValueError(
            f'Unsupported seamount_stratification_type: {stratification_type}'
        )

    density.attrs['long_name'] = 'target potential density'
    density.attrs['units'] = 'kg m-3'
    return density


def compute_tracers(
    config: PolarisConfigParser,
    z_mid: xr.DataArray,
    layer_thickness: xr.DataArray | None = None,
    surf_pressure: xr.DataArray | float | None = None,
    logger: logging.Logger | None = None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the temperature and salinity for the configured stratification
    under the configured equation of state.

    Salinity is constant, so all of the stratification is carried by
    temperature.

    The ``linear`` and ``exponential`` stratifications prescribe a Beckmann
    and Haidvogel potential density, which has to be inverted for the
    tracers.  For ``eos_type = linear`` the linear equation of state is
    inverted algebraically; for ``eos_type = teos-10`` the tracers are
    conservative temperature and absolute salinity, and the inversion is
    through :py:func:`polaris.ocean.eos.ct_from_potential_density`.  Both
    branches reproduce the same potential density, so the two equations of
    state give the same buoyancy stratification and differ only in how
    density depends on pressure.

    The ``linear_pressure`` stratification prescribes temperature as a
    function of pressure instead and is handled by
    :py:func:`compute_tracers_linear_in_pressure`, which needs the column
    geometry rather than the layer midpoints.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[seamount]`` and ``[ocean]`` equation of
        state options.

    z_mid : xarray.DataArray
        The geometric height (m, negative down) of the layer midpoints.
        Unused by the ``linear_pressure`` stratification.

    layer_thickness : xarray.DataArray, optional
        The geometric thickness (m) of each layer.  Required by the
        ``linear_pressure`` stratification and unused by the others.

    surf_pressure : xarray.DataArray or float, optional
        The sea-surface gauge pressure (Pa), zero if not given.

    logger : logging.Logger, optional
        A logger for the ``linear_pressure`` fixed-point iteration.

    Returns
    -------
    temperature : xarray.DataArray
        Potential temperature for a linear equation of state, conservative
        temperature for TEOS-10 (degC).

    salinity : xarray.DataArray
        Practical salinity for a linear equation of state, absolute
        salinity for TEOS-10.
    """
    stratification_type = config.get(
        'seamount', 'seamount_stratification_type'
    )
    if stratification_type == 'linear_pressure':
        if layer_thickness is None:
            raise ValueError(
                'The linear_pressure stratification is prescribed as a '
                'function of pressure, so compute_tracers() needs '
                'layer_thickness to integrate the hydrostatic balance.'
            )
        return compute_tracers_linear_in_pressure(
            config,
            layer_thickness=layer_thickness,
            surf_pressure=surf_pressure,
            logger=logger,
        )

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


def compute_tracers_linear_in_pressure(
    config: PolarisConfigParser,
    layer_thickness: xr.DataArray,
    surf_pressure: xr.DataArray | float | None = None,
    logger: logging.Logger | None = None,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute exact layer means of a temperature profile that is linear in
    pressure, with constant salinity.

    The finite-volume horizontal pressure gradient reconstructs the tracers
    as polynomials in pressure and is exact when the continuous profile is
    linear in pressure, so this is the stratification on which its error
    vanishes.  Two properties make that exactness usable:

    * The layer values are exact layer means rather than point samples.
      Both models carry a layer-mean tracer, and the mean is taken over the
      mass of the layer, which is the same as over its pressure range.  For
      a profile linear in pressure that mean is the value at the arithmetic
      mid-pressure of the layer, which is exactly what
      :py:func:`polaris.ocean.vertical.ztilde.pressure_from_geom_thickness`
      returns as ``p_mid``, so no quadrature is needed.
    * The profile is a fixed point, not a formula.  Temperature is
      prescribed as a function of pressure, pressure follows from the
      geometric layer thicknesses through the specific volume, and the
      specific volume follows from the temperature.  Iterating to round-off
      is what makes the profile linear in the pressure the model itself
      carries rather than in an approximation to it; a profile that is
      merely close would leave a residual pressure-gradient error and defeat
      the purpose of the configuration.

    The prescribed temperature is the model's own tracer under either
    equation of state -- potential temperature for the linear one,
    conservative temperature for TEOS-10 -- so unlike the Beckmann and
    Haidvogel stratifications there is nothing to invert.  The two equations
    of state therefore span the same temperature range here but not the same
    density range.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration with the ``[seamount]`` and ``[ocean]`` equation of
        state options.

    layer_thickness : xarray.DataArray
        The geometric thickness (m) of each layer.

    surf_pressure : xarray.DataArray or float, optional
        The sea-surface gauge pressure (Pa), zero if not given.

    logger : logging.Logger, optional
        A logger for the fixed-point iteration.

    Returns
    -------
    temperature : xarray.DataArray
        Potential temperature for a linear equation of state, conservative
        temperature for TEOS-10 (degC).

    salinity : xarray.DataArray
        Practical salinity for a linear equation of state, absolute
        salinity for TEOS-10.
    """
    section = config['seamount']
    coef = section.getfloat('seamount_temperature_coef_linear_pressure')
    gradient = section.getfloat(
        'seamount_temperature_gradient_linear_pressure'
    )
    pressure_ref = section.getfloat('seamount_pressure_ref_linear_pressure')
    constant_salinity = section.getfloat('constant_salinity')

    eos_type = config.get('ocean', 'eos_type').strip()
    if eos_type not in ('linear', 'teos-10'):
        raise ValueError(
            f'The seamount task does not support eos_type: {eos_type}'
        )

    if surf_pressure is None:
        surf_pressure = xr.zeros_like(layer_thickness.isel(nVertLevels=0))

    # dT/dp in degC Pa-1, from a range in degC over a range in dbar
    dtemperature_dp = -gradient / (pressure_ref * DBAR_TO_PA)

    salinity = constant_salinity * xr.ones_like(layer_thickness)
    # start from the reference density, as the pressure calculation in
    # polaris.ocean.vertical.ztilde does
    spec_vol = 1.0 / RhoSw * xr.ones_like(layer_thickness)
    temperature = None

    for iteration in range(MAX_PRESSURE_ITERATIONS):
        _, p_mid = pressure_from_geom_thickness(
            surf_pressure=surf_pressure,
            geom_layer_thickness=layer_thickness,
            spec_vol=spec_vol,
        )
        new_temperature = coef + dtemperature_dp * p_mid

        if temperature is not None:
            max_delta = np.abs(new_temperature - temperature).max().item()
            if logger is not None:
                logger.info(
                    f'Max change in temperature during linear-in-pressure '
                    f'iteration {iteration}: {max_delta:.3e} degC'
                )
            if max_delta < PRESSURE_ITERATION_TOLERANCE:
                temperature = new_temperature
                break

        temperature = new_temperature
        spec_vol = compute_specvol(
            config=config,
            temperature=temperature,
            salinity=salinity,
            pressure=p_mid,
        )
    else:
        raise ValueError(
            f'The linear-in-pressure profile did not converge in '
            f'{MAX_PRESSURE_ITERATIONS} iterations.  Without a converged '
            f'fixed point the profile is not linear in the pressure the '
            f'model carries.'
        )

    assert isinstance(temperature, xr.DataArray)
    if eos_type == 'linear':
        temperature.attrs['long_name'] = 'potential temperature'
        salinity.attrs['long_name'] = 'practical salinity'
        salinity.attrs['units'] = 'PSU'
    else:
        temperature.attrs['long_name'] = 'conservative temperature'
        salinity.attrs['long_name'] = 'absolute salinity'
        salinity.attrs['units'] = 'g kg-1'

    temperature.attrs['units'] = 'degC'
    return temperature, salinity
