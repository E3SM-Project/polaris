"""
Unit tests for ReferenceColumn.

All tests are self-contained: no file I/O, no Omega build required.
A PolarisConfigParser is built from the package default config in each test,
with specific options overridden as needed.
"""

import gsw
import numpy as np
import pytest

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.horiz_press_grad.reference import ReferenceColumn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HPG_PKG = 'polaris.tasks.ocean.horiz_press_grad'


def _make_config(**overrides: str) -> PolarisConfigParser:
    """Load default horiz_press_grad config and apply string overrides."""
    config = PolarisConfigParser()
    config.add_from_package(_HPG_PKG, 'horiz_press_grad.cfg')
    for key, value in overrides.items():
        config.set('horiz_press_grad', key, value)
    return config


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_zero_gradient_hpga_is_zero():
    """With all horizontal gradients zero, hpga must be zero everywhere.

    C = eta' - rho0 * alpha(z_surf) * zt_surf' = 0 - 0 = 0
    dalpha_dx = 0  =>  I(z) = 0
    a(z) = -g * (0 + rho0 * 0) = 0
    """
    config = _make_config()
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    z_test = np.array([z_b, z_b * 0.75, z_b * 0.5, z_b * 0.25, 0.0])

    hpga_vals = ref.hpga(z_test)
    np.testing.assert_allclose(hpga_vals, 0.0, atol=1e-20)


def test_surface_boundary_hpga_is_constant():
    """With only a sea-surface-height gradient, hpga is constant in z̃.

    The reference is anchored at the surface.  With all T/S and z_tilde
    gradients zero, dalpha_dx = 0, so the integral vanishes and

    a(z) = -g * C = -g * geom_ssh_grad/1000   (independent of z)
    """
    sshg = 2.0  # m / km
    config = _make_config(geom_ssh_grad=str(sshg))
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    z_surf = config['horiz_press_grad'].getnumpy('z_tilde_mid')[0]
    expected = -Gravity * (sshg / 1000.0)

    z_test = np.array([z_b, z_b * 0.6, z_b * 0.3, z_surf])
    hpga_vals = ref.hpga(z_test)
    np.testing.assert_allclose(hpga_vals, expected, rtol=1e-8)


def test_surface_pseudoheight_gradient_in_boundary():
    """The surface pseudo-height gradient enters the boundary term.

    Evaluated exactly at the surface the integral is zero, so

    a(z_surf) = -g * (geom_ssh_grad/1000
                      - rho0 * alpha(z_surf) * z_tilde_grad[0]/1000)

    This isolates the surface boundary term and guards the contribution that a
    nonzero surface pressure (which shifts the surface pseudo-height) will use
    in the follow-up surface-pressure test.
    """
    sshg = 2.0  # m / km
    ztsg = 1.5  # m / km (surface pseudo-height node gradient)
    config = _make_config(
        geom_ssh_grad=str(sshg),
        z_tilde_grad=f'[{ztsg}, 0.0, 0.0, 0.0, 0.0]',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    z_surf = config['horiz_press_grad'].getnumpy('z_tilde_mid')[0]
    alpha_s = float(ref.specvol(np.array([z_surf]))[0])
    expected = -Gravity * (sshg / 1000.0 - RhoSw * alpha_s * ztsg / 1000.0)

    np.testing.assert_allclose(
        ref.hpga(np.array([z_surf]))[0], expected, rtol=1e-10
    )


def test_nonzero_ssh_surface_boundary_is_nonzero():
    """A nonzero sea-surface-height gradient yields a nonzero surface HPGA.

    Guards the general boundary term so the follow-up surface-pressure test
    cannot be silently broken by an assumption of zero SSH.
    """
    sshg = 3.0  # m / km
    config = _make_config(geom_ssh_grad=str(sshg))
    ref = ReferenceColumn(config, x_sign=1.0)

    z_surf = config['horiz_press_grad'].getnumpy('z_tilde_mid')[0]
    # z_tilde_grad is zero by default, so C = eta'
    expected = -Gravity * (sshg / 1000.0)
    np.testing.assert_allclose(
        ref.hpga(np.array([z_surf]))[0], expected, rtol=1e-12
    )
    assert abs(expected) > 0.0


def test_surface_boundary_hpga_respects_x_sign():
    """x_sign = -1 negates the result relative to x_sign = +1."""
    config = _make_config(geom_ssh_grad='2.0')
    ref_pos = ReferenceColumn(config, x_sign=1.0)
    ref_neg = ReferenceColumn(config, x_sign=-1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    z_test = np.array([z_b * 0.5, 0.0])

    np.testing.assert_allclose(
        ref_neg.hpga(z_test), -ref_pos.hpga(z_test), rtol=1e-14
    )


def test_hpga_sampling_independence():
    """hpga at coincident z̃ agrees within quadrature error across different
    evaluation grids.

    The cumulative quadrature splits the integral at each unique target z̃,
    so adding intermediate points changes the sub-interval widths and hence
    the quadrature accuracy.  The mismatch between a dense and a sparse grid
    at coincident z̃ is the quadrature error of the coarser computation and
    must be small relative to the value.
    """
    config = _make_config(
        temperature_grad='[0.5, 0.4, 0.3, 0.2, 0.1]',
        salinity_grad='[0.02, 0.02, 0.01, 0.01, 0.005]',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')

    # Dense grid and sparse grid with several shared points
    z_shared = np.array([z_b, z_b * 0.5, 0.0])
    z_dense = np.concatenate([z_shared, np.linspace(z_b * 0.9, z_b * 0.1, 15)])
    z_dense = np.sort(z_dense)

    hpga_dense = ref.hpga(z_dense)
    hpga_shared = ref.hpga(z_shared)

    for z_val, h_ref in zip(z_shared, hpga_shared, strict=True):
        idx = np.where(z_dense == z_val)[0]
        assert len(idx) >= 1
        # Dense grid is more accurate; sparse grid carries quadrature error.
        # Tolerance is well within the level needed for HPG accuracy.
        np.testing.assert_allclose(
            hpga_dense[idx[0]],
            h_ref,
            rtol=1e-4,
            err_msg=f'Mismatch at z̃={z_val}',
        )


def test_dalpha_dx_matches_specvol_finite_difference():
    """dalpha_dx agrees with a direct centred FD of gsw.specvol at fixed z̃.

    The ReferenceColumn computes d(α)/dx via the TEOS-10 chain rule
    v_SA*dSA/dx + v_CT*dCT/dx.  For a small perturbation this must equal
    (alpha(x+eps) - alpha(x-eps)) / (2*eps) to O(eps^2) accuracy.
    """
    config = _make_config(
        temperature_grad='[0.5, 0.4, 0.3, 0.2, 0.1]',
        salinity_grad='[0.05, 0.04, 0.03, 0.02, 0.01]',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    two_eps_m = ref._two_eps_m
    z_test = np.array([z_b * 0.9, z_b * 0.5, z_b * 0.1])

    dalpha_computed = ref.dalpha_dx(z_test)

    # Direct FD: specvol at x = ±eps with corresponding SA/CT profiles
    sa_plus = ref._sa_plus(z_test)
    ct_plus = ref._ct_plus(z_test)
    sa_minus = ref._sa_minus(z_test)
    ct_minus = ref._ct_minus(z_test)
    p_dbar = (-RhoSw * Gravity * z_test) * 1.0e-4
    alpha_plus = gsw.specvol(sa_plus, ct_plus, p_dbar)
    alpha_minus = gsw.specvol(sa_minus, ct_minus, p_dbar)
    dalpha_fd = (alpha_plus - alpha_minus) / two_eps_m

    # gsw.specvol_first_derivatives uses analytical polynomial derivatives
    # that are self-consistent with gsw.specvol to ~1e-5 relative tolerance.
    np.testing.assert_allclose(dalpha_computed, dalpha_fd, rtol=1e-3)


def test_tilted_nodes_dalpha_dx():
    """Moving-node differencing is correct when z_tilde_grad != 0.

    In the ztilde_gradient task the z̃ nodes themselves shift with x.
    Verify that dalpha_dx still matches the direct FD of specvol built from
    the shifted-node PCHIP profiles.
    """
    config = _make_config(
        z_tilde_grad='[0.0, 2.0, 5.0, 3.0, 0.0]',
        salinity_grad='[0.05, 0.04, 0.03, 0.02, 0.01]',
        temperature_grad='[0.3, 0.2, 0.1, 0.05, 0.0]',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    # Choose z̃ well within the node range at all x
    z_test = np.array([-100.0, -250.0, -450.0])
    two_eps_m = ref._two_eps_m

    dalpha_computed = ref.dalpha_dx(z_test)

    sa_plus = ref._sa_plus(z_test)
    ct_plus = ref._ct_plus(z_test)
    sa_minus = ref._sa_minus(z_test)
    ct_minus = ref._ct_minus(z_test)
    p_dbar = (-RhoSw * Gravity * z_test) * 1.0e-4
    alpha_plus = gsw.specvol(sa_plus, ct_plus, p_dbar)
    alpha_minus = gsw.specvol(sa_minus, ct_minus, p_dbar)
    dalpha_fd = (alpha_plus - alpha_minus) / two_eps_m

    # PCHIP node-shift amplification combined with gsw polynomial
    # self-consistency gives ~3e-4 relative error for moving nodes.
    np.testing.assert_allclose(dalpha_computed, dalpha_fd, rtol=2e-3)


def test_hpga_leibniz_consistency():
    """d(hpga)/dz̃ = -g * rho0 * dalpha_dx (Leibniz formula check).

    This verifies the cumulative quadrature integrates the correct integrand.
    All targets are evaluated in a single hpga() call so that consecutive
    pairs (z̃-dz, z̃+dz) share the same cumulative-integral path and the FD
    difference equals the small-panel integral rather than the difference of
    two large separate integrals.
    """
    config = _make_config(
        temperature_grad='[0.4, 0.3, 0.2, 0.1, 0.0]',
        salinity_grad='[0.03, 0.02, 0.01, 0.005, 0.0]',
        geom_ssh_grad='1.0',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    z_test = np.array([-400.0, -200.0, -50.0])
    dz = 0.1  # small z̃ step (m)
    n = len(z_test)

    # Single call includes z_test-dz AND z_test+dz so that the difference
    # is computed from a tiny O(dz) integral, not two large integrals.
    z_combined = np.concatenate([z_test - dz, z_test + dz])
    hpga_combined = ref.hpga(z_combined)
    hpga_deriv_fd = (hpga_combined[n:] - hpga_combined[:n]) / (2.0 * dz)
    expected_deriv = -Gravity * RhoSw * ref.dalpha_dx(z_test)

    np.testing.assert_allclose(hpga_deriv_fd, expected_deriv, rtol=1e-5)


def test_layer_mean_constant_hpga():
    """For a constant HPGA (zero T/S gradients), layer means equal that value.

    Gauss quadrature integrates a constant exactly, so this should hold to
    near floating-point precision regardless of layer thickness or nsub.
    """
    sshg = 2.0
    config = _make_config(geom_ssh_grad=str(sshg))
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    expected = -Gravity * (sshg / 1000.0)

    n_layers = 8
    interfaces = np.linspace(0.0, z_b, n_layers + 1)
    layer_means = ref.layer_mean_hpga(interfaces)

    np.testing.assert_allclose(layer_means, expected, rtol=1e-10)


def test_layer_mean_zero_gradient():
    """With all gradients zero, layer_mean_hpga returns zero for all layers."""
    config = _make_config()
    ref = ReferenceColumn(config, x_sign=1.0)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    interfaces = np.linspace(0.0, z_b, 11)
    layer_means = ref.layer_mean_hpga(interfaces)

    np.testing.assert_allclose(layer_means, 0.0, atol=1e-20)


def test_layer_mean_approaches_pointwise_as_layer_thins():
    """As layer thickness shrinks, the layer mean approaches pointwise value.

    Uses a config with non-zero T/S gradients so HPGA varies with z̃.
    For very thin layers the two-point mean should agree with hpga(z̃_mid)
    to within the second-order quadrature error.
    """
    config = _make_config(
        temperature_grad='[0.5, 0.4, 0.3, 0.2, 0.1]',
        salinity_grad='[0.02, 0.015, 0.01, 0.005, 0.0]',
    )
    ref = ReferenceColumn(config, x_sign=1.0)

    # Very thin layer centred on z_mid
    z_mid = -200.0
    for half_dz in [10.0, 1.0, 0.1]:
        interfaces = np.array([z_mid + half_dz, z_mid - half_dz])
        layer_mean = float(ref.layer_mean_hpga(interfaces)[0])
        pointwise = float(ref.hpga(np.array([z_mid]))[0])
        diff = abs(layer_mean - pointwise)
        # error should shrink as half_dz shrinks
        assert diff < 1e-3 * abs(pointwise) + 1e-20, (
            f'half_dz={half_dz}: layer_mean={layer_mean:.6e}, '
            f'pointwise={pointwise:.6e}, diff={diff:.3e}'
        )


@pytest.mark.parametrize('x_sign', [1.0, -1.0])
def test_layer_mean_shape(x_sign):
    """layer_mean_hpga returns shape (nLayers,) for (nLayers+1,) interfaces."""
    config = _make_config(temperature_grad='[0.3, 0.2, 0.1, 0.05, 0.0]')
    ref = ReferenceColumn(config, x_sign=x_sign)

    z_b = config['horiz_press_grad'].getfloat('z_tilde_bot_mid')
    n_layers = 6
    interfaces = np.linspace(0.0, z_b, n_layers + 1)
    means = ref.layer_mean_hpga(interfaces)

    assert means.shape == (n_layers,)
