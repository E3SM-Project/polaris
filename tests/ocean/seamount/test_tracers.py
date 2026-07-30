"""
Unit tests for the seamount initial condition under both equations of state.

The seamount specifies its stratification as a Beckmann and Haidvogel
density profile rather than as a temperature profile, so each equation of
state has to be inverted for the tracers that reproduce it.  These tests
check that both inversions land on the same potential density -- which is
what makes the linear and nonlinear trees comparable -- and that the
nonlinear tree really does gain a pressure dependence the linear one cannot
have.

All tests are self-contained: no file I/O, no full Polaris step framework.
"""

from configparser import ConfigParser

import gsw
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.eos import compute_density
from polaris.tasks.ocean.seamount.init_utils import (
    compute_target_density,
    compute_tracers,
)

# Beckmann and Haidvogel exponential stratification, as configured for the
# seamount, together with the linear EOS parameters it is inverted through
DENSITY_COEF = 1028.0
DENSITY_GRADIENT = 3.0
DENSITY_DEPTH = 500.0
EOS_RHOREF = 1001.0
EOS_ALPHA = 0.2
EOS_BETA = 0.8
SALINITY = 35.0

MAX_BOTTOM_DEPTH = 5000.0
SUMMIT_DEPTH = 531.45
VERT_LEVELS = 32


def _make_config(eos_type, stratification='exponential'):
    config = ConfigParser()

    config.add_section('seamount')
    config.set('seamount', 'seamount_stratification_type', stratification)
    config.set('seamount', 'seamount_density_coef_exp', str(DENSITY_COEF))
    config.set(
        'seamount', 'seamount_density_gradient_exp', str(DENSITY_GRADIENT)
    )
    config.set('seamount', 'seamount_density_depth_exp', str(DENSITY_DEPTH))
    config.set('seamount', 'seamount_density_coef_linear', '1024.0')
    config.set('seamount', 'seamount_density_gradient_linear', '0.1')
    config.set('seamount', 'seamount_density_depth_linear', '4500.0')
    config.set('seamount', 'constant_salinity', str(SALINITY))

    config.add_section('ocean')
    config.set('ocean', 'eos_type', eos_type)
    config.set('ocean', 'eos_linear_rhoref', str(EOS_RHOREF))
    config.set('ocean', 'eos_linear_alpha', str(EOS_ALPHA))
    config.set('ocean', 'eos_linear_beta', str(EOS_BETA))
    config.set('ocean', 'eos_linear_Tref', '0.0')
    config.set('ocean', 'eos_linear_Sref', '0.0')
    return config


def _sigma_z_mid():
    """
    Sigma layer midpoints for a pair of columns spanning the seamount's
    depth range: the deep flank and the summit.
    """
    depths = np.array([MAX_BOTTOM_DEPTH, SUMMIT_DEPTH])
    frac = (np.arange(VERT_LEVELS) + 0.5) / VERT_LEVELS
    z_mid = -depths[:, np.newaxis] * frac[np.newaxis, :]
    return xr.DataArray(z_mid, dims=('nCells', 'nVertLevels'))


def test_target_density_matches_beckmann_haidvogel():
    config = _make_config('linear')
    z_mid = _sigma_z_mid()

    density = compute_target_density(config, z_mid)

    expected = DENSITY_COEF - DENSITY_GRADIENT * np.exp(
        z_mid.values / DENSITY_DEPTH
    )
    assert_allclose(density.values, expected)
    # the profile the seamount actually configures
    assert_allclose(density.values.min(), 1025.0494, atol=1e-4)
    assert_allclose(density.values.max(), 1027.9998, atol=1e-4)


def test_linear_back_solve_reproduces_target():
    config = _make_config('linear')
    z_mid = _sigma_z_mid()

    density = compute_target_density(config, z_mid)
    temperature, salinity = compute_tracers(config, z_mid)

    # the linear EOS has no pressure dependence, so density is exactly the
    # target with no reference pressure to choose
    modeled = compute_density(config, temperature, salinity)
    assert isinstance(modeled, xr.DataArray)
    assert_allclose(modeled.values, density.values, atol=1e-12)
    assert_allclose(salinity.values, SALINITY)


def test_nonlinear_reproduces_target_as_potential_density():
    config = _make_config('teos-10')
    z_mid = _sigma_z_mid()

    density = compute_target_density(config, z_mid)
    ct, sa = compute_tracers(config, z_mid)

    # at zero reference pressure the TEOS-10 tracers reproduce the same
    # Beckmann and Haidvogel profile the linear back-solve does
    sigma_0 = compute_density(config, ct, sa, pressure=0.0)
    assert isinstance(sigma_0, xr.DataArray)
    assert_allclose(sigma_0.values, density.values, atol=1e-11)
    assert sa.attrs['units'] == 'g kg-1'


def test_both_equations_of_state_share_a_stratification():
    """
    The property that makes the two trees comparable: a difference in
    spurious velocity between them is due to the equation of state, not to
    a different N^2.
    """
    z_mid = _sigma_z_mid()

    t_lin, s_lin = compute_tracers(_make_config('linear'), z_mid)
    ct, sa = compute_tracers(_make_config('teos-10'), z_mid)

    rho_lin = compute_density(_make_config('linear'), t_lin, s_lin)
    assert isinstance(rho_lin, xr.DataArray)
    sigma_0 = gsw.rho(sa.values, ct.values, 0.0)

    assert_allclose(sigma_0, rho_lin.values, atol=1e-11)
    # the temperature fields are close but not identical, since the two
    # equations of state reach the same density by different routes
    assert np.abs(ct.values - t_lin.values).max() > 1.0


def test_nonlinear_gains_a_pressure_dependence():
    """
    The negative control: if in-situ density under TEOS-10 did not depart
    from the surface-referenced profile, the nonlinear tree would be
    measuring nothing the linear tree does not already measure.
    """
    config = _make_config('teos-10')
    z_mid = _sigma_z_mid()

    ct, sa = compute_tracers(config, z_mid)

    pressure = -z_mid * 1026.0 * 9.80665
    rho_in_situ = compute_density(config, ct, sa, pressure=pressure)
    sigma_0 = compute_density(config, ct, sa, pressure=0.0)
    assert isinstance(rho_in_situ, xr.DataArray)
    assert isinstance(sigma_0, xr.DataArray)

    departure = (rho_in_situ - sigma_0).values
    # compression dominates and is monotonic with depth; at 5000 m it is
    # far larger than the 3 kg m-3 the whole profile spans
    assert departure.min() >= 0.0
    assert departure.max() > 20.0
    deep_column = departure[0, :]
    assert np.all(np.diff(deep_column) > 0.0)


def test_linear_stratification_branch():
    config = _make_config('linear', stratification='linear')
    z_mid = _sigma_z_mid()

    density = compute_target_density(config, z_mid)

    expected = 1024.0 - 0.1 * z_mid.values / 4500.0
    assert_allclose(density.values, expected)


def test_unsupported_stratification_raises():
    config = _make_config('linear', stratification='quadratic')
    with pytest.raises(ValueError, match='seamount_stratification_type'):
        compute_target_density(config, _sigma_z_mid())


def test_unsupported_eos_raises():
    config = _make_config('constant')
    with pytest.raises(ValueError, match='eos_type'):
        compute_tracers(config, _sigma_z_mid())
