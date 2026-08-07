"""
Unit tests for the profile helpers in
:py:mod:`polaris.tasks.ocean.horiz_press_grad.column`.

These are pure numpy/scipy tests: no config, no dataset, no file I/O.
"""

import numpy as np
import pytest

from polaris.tasks.ocean.horiz_press_grad.column import (
    get_pchip_interpolator,
    get_pchip_layer_mean,
)

# A deliberately non-uniform set of layers.  A formula that quietly assumes
# uniform thickness, or that averages in the wrong variable, passes on a
# uniform grid and fails here.
_NON_UNIFORM = np.array([0.0, -10.0, -35.0, -100.0, -300.0, -1000.0])

# Nodes of a curved profile, decreasing in z_tilde as the configs write them.
_CURVED_Z = np.array([0.0, -100.0, -250.0, -500.0, -1000.0])
_CURVED_T = np.array([22.0, 18.0, 8.0, 4.0, 1.0])


def _fine_mean(z_nodes, values, z_top, z_bot, n=200001):
    """A brute-force layer mean, for comparison with the exact one."""
    interp = get_pchip_interpolator(z_nodes, values, 'temperature')
    z = np.linspace(z_top, z_bot, n)
    return np.trapezoid(interp(z), z) / (z_bot - z_top)


def test_layer_mean_exact_for_linear_profile():
    """For a linear profile the layer mean is the midpoint value, exactly.

    This is the property that makes the choice between layer averaging and
    midpoint sampling irrelevant on the scheme's exact set, so it is worth
    pinning down rather than assuming.
    """
    z_nodes = np.array([0.0, -1000.0])
    t_nodes = np.array([22.0, 2.0])
    layer_mean = get_pchip_layer_mean(z_nodes, t_nodes, 'temperature')

    top = _NON_UNIFORM[:-1]
    bot = _NON_UNIFORM[1:]
    means = layer_mean(top, bot)

    z_mid = 0.5 * (top + bot)
    expected = 22.0 + (2.0 - 22.0) * (z_mid - 0.0) / (-1000.0 - 0.0)
    np.testing.assert_allclose(means, expected, rtol=1e-14)


def test_layer_mean_matches_brute_force_on_curved_profile():
    """On a curved profile the exact mean matches a fine numerical average."""
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    top = _NON_UNIFORM[:-1]
    bot = _NON_UNIFORM[1:]
    means = layer_mean(top, bot)

    expected = np.array(
        [
            _fine_mean(_CURVED_Z, _CURVED_T, z_top, z_bot)
            for z_top, z_bot in zip(top, bot, strict=True)
        ]
    )
    np.testing.assert_allclose(means, expected, rtol=1e-8)


def test_layer_mean_differs_from_midpoint_on_curved_profile():
    """The curved case is not a no-op: means and midpoint samples differ.

    Without this the test above could pass for an implementation that had
    silently gone back to sampling at midpoints.
    """
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')
    interp = get_pchip_interpolator(_CURVED_Z, _CURVED_T, 'temperature')

    top = _NON_UNIFORM[:-1]
    bot = _NON_UNIFORM[1:]
    means = layer_mean(top, bot)
    midpoints = interp(0.5 * (top + bot))

    assert np.max(np.abs(means - midpoints)) > 1e-3


def test_layer_mean_is_mean_preserving():
    """Thickness-weighted layer means reproduce the whole-column integral.

    ``[z-increment-exact]`` in the design rests on the reconstruction
    integrating to the layer mean, which in turn requires the layer means the
    initial condition supplies to be consistent with the profile they came
    from.
    """
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    top = _NON_UNIFORM[:-1]
    bot = _NON_UNIFORM[1:]
    thickness = top - bot
    total = float(np.sum(layer_mean(top, bot) * thickness))

    expected = _fine_mean(
        _CURVED_Z, _CURVED_T, _NON_UNIFORM[0], _NON_UNIFORM[-1]
    ) * (_NON_UNIFORM[0] - _NON_UNIFORM[-1])
    np.testing.assert_allclose(total, expected, rtol=1e-8)


def test_layer_mean_precision_does_not_degrade_with_thin_layers():
    """The layer mean stays at a few eps however thin the layers are.

    Computing the mean by differencing the interpolant's antiderivative is
    exact in principle but differences two large numbers, so its error grows
    like 1/h -- reaching ~1e-13 of the salinity at the 8 m layers used here and
    3.7e-14 at 32 m.  That would put a floor under how exactly the initial
    sits in the finite-volume scheme's exact set, and hence under the
    machine-precision test the whole scheme is judged by.  Quadrature per node
    interval has no such cancellation.
    """
    z_nodes = np.array([0.0, -6144.0])
    s_nodes = np.array([35.6, 34.66])
    layer_mean = get_pchip_layer_mean(z_nodes, s_nodes, 'salinity')

    edges = -np.arange(0.0, 4096.0 + 8.0, 8.0)
    top = edges[:-1]
    bot = edges[1:]
    means = layer_mean(top, bot)

    # exact for a linear profile: the value at the layer midpoint
    z_mid = 0.5 * (top + bot)
    expected = 35.6 + (34.66 - 35.6) * z_mid / (-6144.0)
    np.testing.assert_allclose(means, expected, rtol=1e-15)


@pytest.mark.parametrize('nudge', [0.0, 1.0e-12, -1.0e-12])
def test_layer_mean_at_the_outermost_nodes(nudge):
    """Interfaces on, or a round-off distance outside, the outermost nodes.

    Every configuration puts its shallowest node at ``z_tilde = 0`` while the
    column is summed upward from the sea floor, and the gradient variants put
    the deepest node exactly at the pseudo-bottom, so both outermost interfaces
    land on a node up to round-off.  Two things must hold there.

    Extrapolating must not be an error and must not produce a NaN: a NaN in
    the top or bottom layer feeds back through the p-star iteration and
    corrupts the whole column state without raising anything.

    And the round-off excursion must be absorbed *consistently* -- the interval
    the quadrature covers and the thickness it is divided by must be the same
    interval.  Clipping one but not the other scales the outermost layer's mean
    by ``h / (h + nudge)``, which is invisible on a thick layer and is why the
    layers here are thin.
    """
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    thin = 8.0
    top = np.array([0.0 + nudge, -1000.0 + thin])
    bot = np.array([-thin, -1000.0 + nudge])
    means = layer_mean(top, bot)

    assert np.all(np.isfinite(means))
    reference = layer_mean(
        np.array([0.0, -1000.0 + thin]), np.array([-thin, -1000.0])
    )
    np.testing.assert_allclose(means, reference, rtol=1e-15)


def test_layer_mean_rejects_real_extrapolation():
    """A layer genuinely outside the node range raises rather than clipping."""
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    with pytest.raises(ValueError, match='node range'):
        layer_mean(np.array([-900.0]), np.array([-1100.0]))
    with pytest.raises(ValueError, match='node range'):
        layer_mean(np.array([10.0]), np.array([-100.0]))


def test_layer_mean_node_order_does_not_matter():
    """Increasing and decreasing node order give the same layer means."""
    decreasing = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')
    increasing = get_pchip_layer_mean(
        _CURVED_Z[::-1], _CURVED_T[::-1], 'temperature'
    )

    top = _NON_UNIFORM[:-1]
    bot = _NON_UNIFORM[1:]
    np.testing.assert_allclose(
        increasing(top, bot), decreasing(top, bot), rtol=1e-14
    )


def test_layer_mean_rejects_non_positive_thickness():
    """A layer whose interfaces are equal or inverted raises."""
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    with pytest.raises(ValueError, match='positive thickness'):
        layer_mean(np.array([-100.0]), np.array([-100.0]))
    with pytest.raises(ValueError, match='positive thickness'):
        layer_mean(np.array([-200.0]), np.array([-100.0]))


def test_layer_mean_rejects_non_finite_interfaces():
    """Invalid layers must be masked out by the caller, not passed through."""
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    with pytest.raises(ValueError, match='finite'):
        layer_mean(np.array([0.0, np.nan]), np.array([-100.0, -200.0]))


def test_layer_mean_rejects_mismatched_shapes():
    """``z_tilde_top`` and ``z_tilde_bot`` must describe the same layers."""
    layer_mean = get_pchip_layer_mean(_CURVED_Z, _CURVED_T, 'temperature')

    with pytest.raises(ValueError, match='same shape'):
        layer_mean(np.array([0.0, -100.0]), np.array([-100.0]))


def test_layer_mean_validates_nodes():
    """Node validation is shared with ``get_pchip_interpolator``."""
    with pytest.raises(ValueError, match='strictly monotonic'):
        get_pchip_layer_mean(
            np.array([0.0, -100.0, -50.0]),
            np.array([22.0, 18.0, 8.0]),
            'temperature',
        )
    with pytest.raises(ValueError, match='At least two'):
        get_pchip_layer_mean(np.array([0.0]), np.array([22.0]), 'temperature')
    with pytest.raises(ValueError, match='must match'):
        get_pchip_layer_mean(_CURVED_Z, _CURVED_T[:-1], 'temperature')
