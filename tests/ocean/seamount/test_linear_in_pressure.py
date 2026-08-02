"""
Unit tests for the seamount ``linear_pressure`` stratification.

The finite-volume horizontal pressure gradient is exact when the continuous
tracer profile is linear in pressure, so this stratification exists to be a
configuration on which that scheme's error vanishes and any surviving
spurious velocity has another source.  That argument is only worth as much
as the profile's exactness, which is what these tests measure: the layer
values must be exact layer means of a straight line in the pressure the
model itself carries, not point samples, and not a straight line in
something merely correlated with pressure.

The Beckmann and Haidvogel profiles are carried through the same
measurements as negative controls.  A guard that cannot fail is worth
nothing, and "density linear in depth" is close enough to "temperature
linear in pressure" that the difference has to be demonstrated rather than
asserted.

All tests are self-contained: no file I/O, no full Polaris step framework.
"""

from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.vertical.diagnostics import pseudothickness_from_ds
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.seamount.init_utils import (
    DBAR_TO_PA,
    compute_target_density,
    compute_tracers,
    compute_tracers_linear_in_pressure,
)

# the linear-in-pressure profile, as configured for the seamount
TEMPERATURE_COEF = 20.0
TEMPERATURE_GRADIENT = 15.0
PRESSURE_REF = 5000.0

# Beckmann and Haidvogel parameters and the linear EOS they are inverted
# through, as configured for the seamount
DENSITY_COEF_EXP = 1028.0
DENSITY_GRADIENT_EXP = 3.0
DENSITY_DEPTH_EXP = 500.0
DENSITY_COEF_LINEAR = 1024.0
DENSITY_GRADIENT_LINEAR = 0.1
DENSITY_DEPTH_LINEAR = 4500.0
EOS_RHOREF = 1001.0
EOS_ALPHA = 0.2
EOS_BETA = 0.8
SALINITY = 35.0

MAX_BOTTOM_DEPTH = 5000.0
SEAMOUNT_HEIGHT = 4500.0
SEAMOUNT_WIDTH = 40.0e3
VERT_LEVELS = 32


def _make_config(eos_type, coord_type='sigma', partial_cell_type='None'):
    config = ConfigParser()

    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', str(VERT_LEVELS))
    config.set('vertical_grid', 'bottom_depth', str(MAX_BOTTOM_DEPTH))
    config.set('vertical_grid', 'coord_type', coord_type)
    config.set('vertical_grid', 'partial_cell_type', partial_cell_type)
    config.set('vertical_grid', 'min_pc_fraction', '0.1')
    config.set('vertical_grid', 'min_vert_levels', '1')
    config.set('vertical_grid', 'min_layer_thickness', '0.0')
    config.set('vertical_grid', 'pseudothickness_iter_count', '20')

    config.add_section('seamount')
    config.set('seamount', 'seamount_stratification_type', 'linear_pressure')
    config.set(
        'seamount',
        'seamount_temperature_coef_linear_pressure',
        str(TEMPERATURE_COEF),
    )
    config.set(
        'seamount',
        'seamount_temperature_gradient_linear_pressure',
        str(TEMPERATURE_GRADIENT),
    )
    config.set(
        'seamount', 'seamount_pressure_ref_linear_pressure', str(PRESSURE_REF)
    )
    config.set('seamount', 'seamount_density_coef_exp', str(DENSITY_COEF_EXP))
    config.set(
        'seamount',
        'seamount_density_gradient_exp',
        str(DENSITY_GRADIENT_EXP),
    )
    config.set(
        'seamount', 'seamount_density_depth_exp', str(DENSITY_DEPTH_EXP)
    )
    config.set(
        'seamount', 'seamount_density_coef_linear', str(DENSITY_COEF_LINEAR)
    )
    config.set(
        'seamount',
        'seamount_density_gradient_linear',
        str(DENSITY_GRADIENT_LINEAR),
    )
    config.set(
        'seamount',
        'seamount_density_depth_linear',
        str(DENSITY_DEPTH_LINEAR),
    )
    config.set('seamount', 'constant_salinity', str(SALINITY))

    config.add_section('ocean')
    config.set('ocean', 'eos_type', eos_type)
    config.set('ocean', 'eos_linear_rhoref', str(EOS_RHOREF))
    config.set('ocean', 'eos_linear_alpha', str(EOS_ALPHA))
    config.set('ocean', 'eos_linear_beta', str(EOS_BETA))
    config.set('ocean', 'eos_linear_Tref', '0.0')
    config.set('ocean', 'eos_linear_Sref', '0.0')
    return config


def _make_coord(config):
    """The seamount bathymetry and the geometric vertical coordinate on it."""
    radius = np.linspace(0.0, 160.0e3, 24)
    bottom_depth = MAX_BOTTOM_DEPTH - SEAMOUNT_HEIGHT * np.exp(
        -(radius**2) / SEAMOUNT_WIDTH**2
    )
    ds = xr.Dataset()
    ds['bottomDepth'] = xr.DataArray(bottom_depth, dims=['nCells'])
    ds['ssh'] = xr.zeros_like(ds.bottomDepth)
    init_vertical_coord(config, ds)
    return ds


def _model_interface_pressure(ds, config):
    """
    The gauge pressure at layer interfaces that the model itself carries.

    Omega's prognostic thickness is a pseudo-thickness, so interface
    pressure is fixed by the pseudo-thickness alone.  Going through
    ``pseudothickness_from_ds()`` measures the profile against that pressure
    rather than against the pressure the profile was built from.
    """
    pseudo_thickness, _ = pseudothickness_from_ds(
        ds, config=config, src_var_name='layerThickness', surf_pressure=0.0
    )
    assert pseudo_thickness is not None
    h_tilde = np.nan_to_num(pseudo_thickness.squeeze('Time').values)
    zeros = np.zeros((h_tilde.shape[0], 1))
    return (
        RhoSw
        * Gravity
        * np.cumsum(np.concatenate([zeros, h_tilde], axis=1), axis=1)
    )


def _continuous_temperature(pressure):
    """The continuous profile the layer values are meant to average."""
    return TEMPERATURE_COEF - TEMPERATURE_GRADIENT * pressure / (
        PRESSURE_REF * DBAR_TO_PA
    )


def _analytic_layer_mean(p_interface):
    """
    The exact mean of the continuous profile over each layer's pressure
    range.

    The mean of a straight line over an interval is its value at the
    midpoint, so this is written as the average of the two endpoint values:
    an expression of the continuous profile and the layer bounds that does
    not repeat how the initial condition computes the mean.
    """
    return 0.5 * (
        _continuous_temperature(p_interface[:, :-1])
        + _continuous_temperature(p_interface[:, 1:])
    )


def _straight_line_residual(temperature, p_mid):
    """
    Max departure of each column from its own least-squares straight line in
    pressure, as a fraction of the column's temperature range.
    """
    fractions = []
    for i in range(temperature.shape[0]):
        valid = np.isfinite(temperature[i, :]) & np.isfinite(p_mid[i, :])
        values = temperature[i, valid]
        pressure = p_mid[i, valid]
        if values.size < 3:
            continue
        coef = np.polyfit(pressure, values, 1)
        residual = np.max(np.abs(values - np.polyval(coef, pressure)))
        fractions.append(residual / (values.max() - values.min()))
    return np.max(fractions)


@pytest.mark.parametrize('eos_type', ['linear', 'teos-10'])
@pytest.mark.parametrize(
    'coord_type,partial_cell_type',
    [('sigma', 'None'), ('z-star', 'partial')],
)
def test_layer_values_are_exact_layer_means(
    eos_type, coord_type, partial_cell_type
):
    """
    The layer values must be exact means of the continuous profile over the
    layer's pressure range.  Both models carry a layer-mean tracer, and the
    finite-volume scheme reconstructs a mean-preserving polynomial from it,
    so a point sample at the layer midpoint would leave an O(h^2) error that
    the exactness argument does not allow for.
    """
    config = _make_config(eos_type, coord_type, partial_cell_type)
    ds = _make_coord(config)

    temperature, salinity = compute_tracers_linear_in_pressure(
        config, layer_thickness=ds.layerThickness
    )
    ds['temperature'] = temperature
    ds['salinity'] = salinity

    p_interface = _model_interface_pressure(ds, config)
    expected = _analytic_layer_mean(p_interface)
    actual = temperature.squeeze('Time').values

    valid = np.isfinite(actual)
    assert valid.any()
    assert np.max(np.abs(actual[valid] - expected[valid])) < 1.0e-10


@pytest.mark.parametrize('eos_type', ['linear', 'teos-10'])
def test_profile_is_straight_in_the_pressure_the_model_carries(eos_type):
    """
    The property the finite-volume scheme's exactness rests on.  Measured
    against the pressure reconstructed from the pseudo-thickness, so that a
    profile which is straight only in the pressure it was built from would
    fail.
    """
    config = _make_config(eos_type)
    ds = _make_coord(config)

    temperature, salinity = compute_tracers(
        config, ds.zMid, layer_thickness=ds.layerThickness
    )
    ds['temperature'] = temperature
    ds['salinity'] = salinity

    p_interface = _model_interface_pressure(ds, config)
    p_mid = 0.5 * (p_interface[:, :-1] + p_interface[:, 1:])

    residual = _straight_line_residual(
        temperature.squeeze('Time').values, p_mid
    )
    assert residual < 1.0e-12


@pytest.mark.parametrize('eos_type', ['linear', 'teos-10'])
@pytest.mark.parametrize('stratification', ['linear', 'exponential'])
def test_beckmann_haidvogel_profiles_are_not_straight_in_pressure(
    eos_type, stratification
):
    """
    The negative control.  Neither Beckmann and Haidvogel profile is linear
    in pressure -- the exponential one obviously, the linear one because
    specific volume varies down the column, so a density linear in geometric
    depth makes pressure quadratic in depth.  The linear profile's departure
    is small, which is exactly why it needs measuring: at 1e-5 to 1e-3 of the
    profile's range it is far above round-off but easily mistaken for it.
    """
    config = _make_config(eos_type)
    config.set('seamount', 'seamount_stratification_type', stratification)
    ds = _make_coord(config)

    temperature, salinity = compute_tracers(config, ds.zMid)
    ds['temperature'] = temperature
    ds['salinity'] = salinity

    p_interface = _model_interface_pressure(ds, config)
    p_mid = 0.5 * (p_interface[:, :-1] + p_interface[:, 1:])

    residual = _straight_line_residual(
        temperature.squeeze('Time').values, p_mid
    )
    assert residual > 1.0e-6


def test_temperature_spans_the_configured_range():
    """
    The swept quantity has to keep meaning what it says: the profile spans
    the configured temperature range over the configured pressure range, and
    so, under the linear equation of state, the 3 kg m-3 the exponential
    Beckmann and Haidvogel profile spans.
    """
    config = _make_config('linear')
    ds = _make_coord(config)

    temperature, _ = compute_tracers_linear_in_pressure(
        config, layer_thickness=ds.layerThickness
    )
    values = temperature.values[np.isfinite(temperature.values)]

    assert values.max() < TEMPERATURE_COEF
    assert values.max() > TEMPERATURE_COEF - 0.5
    # the deepest layer midpoint sits just above the 5000 dbar reference
    assert values.min() < TEMPERATURE_COEF - TEMPERATURE_GRADIENT + 0.5
    assert values.min() > TEMPERATURE_COEF - TEMPERATURE_GRADIENT - 0.5
    density_range = EOS_ALPHA * (values.max() - values.min())
    assert np.abs(density_range - DENSITY_GRADIENT_EXP) < 0.1


def test_surface_pressure_shifts_the_profile():
    """
    Pressure is what the profile is a function of, so a nonzero surface
    pressure must move it.  The seamount runs with a zero surface pressure,
    which would let the argument go unexercised.
    """
    config = _make_config('linear')
    ds = _make_coord(config)

    temperature_zero, _ = compute_tracers_linear_in_pressure(
        config, layer_thickness=ds.layerThickness
    )
    offset = 100.0 * DBAR_TO_PA
    temperature_offset, _ = compute_tracers_linear_in_pressure(
        config, layer_thickness=ds.layerThickness, surf_pressure=offset
    )

    expected_shift = -TEMPERATURE_GRADIENT * 100.0 / PRESSURE_REF
    shift = (temperature_offset - temperature_zero).values
    shift = shift[np.isfinite(shift)]
    # the shift is not exactly uniform, since the added pressure changes the
    # specific volume and so the pressure range each layer spans
    assert np.abs(np.mean(shift) - expected_shift) < 1.0e-3
    assert np.all(shift < 0.0)


def test_target_density_rejects_linear_pressure():
    """
    The linear-in-pressure profile is prescribed on temperature, so asking
    for its target density is a mistake worth naming rather than silently
    treating as one of the density profiles.
    """
    config = _make_config('linear')
    ds = _make_coord(config)
    with pytest.raises(ValueError, match='prescribes temperature'):
        compute_target_density(config, ds.zMid)


def test_compute_tracers_requires_layer_thickness():
    config = _make_config('linear')
    ds = _make_coord(config)
    with pytest.raises(ValueError, match='layer_thickness'):
        compute_tracers(config, ds.zMid)


def test_unsupported_eos_raises():
    config = _make_config('constant')
    ds = _make_coord(_make_config('linear'))
    with pytest.raises(ValueError, match='eos_type'):
        compute_tracers_linear_in_pressure(
            config, layer_thickness=ds.layerThickness
        )
