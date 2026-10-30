"""
Unit tests for the mean-preserving linear reconstruction.

Pure numpy/xarray: no config, no dataset, no file I/O, and no parametrization
over the configured sweeps.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.horiz_press_grad.reconstruction import (
    layer_deviation,
    linear_slope,
    reconstruct,
)

_DIMS = ['Time', 'nCells', 'nVertLevels']

# Deliberately non-uniform layer pressure thicknesses, and a uniform set as the
# control.  The control is the point of the pair: an estimator that quietly
# assumed uniform thickness passes on the uniform grid and fails on the other.
_NON_UNIFORM = np.array([0.5, 3.0, 1.0, 4.0, 2.0, 0.25, 6.0]) * 1.0e6
_UNIFORM = np.full(7, 2.0e6)


def _column(thickness: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Interface and mid-layer pressures for one column, from thicknesses."""
    interfaces = np.concatenate([[0.0], np.cumsum(thickness)])
    mid = 0.5 * (interfaces[:-1] + interfaces[1:])
    return interfaces, mid


def _as_state(mid: np.ndarray, values: np.ndarray):
    """Wrap a single column as a (Time, nCells, nVertLevels) pair."""
    return (
        xr.DataArray(values[np.newaxis, np.newaxis, :], dims=_DIMS),
        xr.DataArray(mid[np.newaxis, np.newaxis, :], dims=_DIMS),
    )


@pytest.mark.parametrize(
    'thickness, label', [(_NON_UNIFORM, 'non-uniform'), (_UNIFORM, 'uniform')]
)
def test_slope_is_exact_for_a_linear_profile(thickness, label):
    """The slope of a linear profile is recovered exactly, on any grid.

    For a profile linear in pressure the layer means lie exactly on the line as
    a function of mid-layer pressure, because the mean of a linear function
    over a layer is its value at the layer's midpoint.  So this must hold to
    round-off on the non-uniform grid as well as the uniform one.
    """
    _, mid = _column(thickness)
    intercept = 12.0
    slope = -3.0e-7
    values, pressure_mid = _as_state(mid, intercept + slope * mid)

    recovered = linear_slope(values, pressure_mid)
    np.testing.assert_allclose(
        recovered.values.ravel(), slope, rtol=1e-12, err_msg=label
    )


def test_reconstruction_reproduces_a_linear_profile_everywhere():
    """Not just the slope: the reconstructed profile is the original line."""
    interfaces, mid = _column(_NON_UNIFORM)
    intercept = 34.9
    slope = 1.5e-8
    values, pressure_mid = _as_state(mid, intercept + slope * mid)
    recovered = linear_slope(values, pressure_mid)

    # evaluate at each layer's own interfaces, where the shift is largest
    for edge in [interfaces[:-1], interfaces[1:]]:
        probe = xr.DataArray(edge[np.newaxis, np.newaxis, :], dims=_DIMS)
        reconstructed = reconstruct(values, recovered, pressure_mid, probe)
        np.testing.assert_allclose(
            reconstructed.values.ravel(),
            intercept + slope * edge,
            rtol=1e-12,
        )


def test_deviation_integrates_to_zero_over_its_layer():
    """The mean-preserving constraint, which ``[z-increment-exact]`` rests on.

    Checked by exact quadrature rather than sampling: the deviation is linear
    in pressure, so a two-point Gauss rule integrates it exactly and the result
    is limited by round-off.
    """
    interfaces, mid = _column(_NON_UNIFORM)
    values, pressure_mid = _as_state(
        mid, np.array([22.0, 18.0, 8.0, 6.0, 4.0, 2.0, 1.0])
    )
    slope = linear_slope(values, pressure_mid)

    offset = 1.0 / np.sqrt(3.0)
    thickness = interfaces[1:] - interfaces[:-1]
    integral = np.zeros(len(mid))
    for sign in [-1.0, 1.0]:
        probe = xr.DataArray(
            (mid + sign * 0.5 * offset * thickness)[np.newaxis, np.newaxis, :],
            dims=_DIMS,
        )
        integral += (
            0.5
            * thickness
            * layer_deviation(slope, pressure_mid, probe).values.ravel()
        )

    # scale by what the layer mean itself contributes over the layer
    scale = np.abs(values.values.ravel() * thickness)
    np.testing.assert_allclose(integral / scale, 0.0, atol=1e-15)


def test_reconstruction_returns_the_layer_mean_at_the_midpoint():
    """By construction, and worth pinning: Requirement 2.4 depends on it."""
    _, mid = _column(_NON_UNIFORM)
    values, pressure_mid = _as_state(mid, np.linspace(20.0, 2.0, 7))
    slope = linear_slope(values, pressure_mid)

    reconstructed = reconstruct(values, slope, pressure_mid, pressure_mid)
    np.testing.assert_array_equal(reconstructed.values, values.values)


def test_slope_is_zero_for_a_uniform_profile():
    """A vertically uniform profile reconstructs as a constant."""
    _, mid = _column(_NON_UNIFORM)
    values, pressure_mid = _as_state(mid, np.full(7, 34.7))

    slope = linear_slope(values, pressure_mid)
    np.testing.assert_array_equal(slope.values, 0.0)


def test_reconstruction_is_second_order_on_a_quadratic_profile():
    """Off the exact set the reconstruction is second order, not exact.

    The honest limit of a linear reconstruction, and what §3.7.3 means by
    The honest limit of a linear reconstruction, and what §3.7.3 means by
    putting a quadratic-in-pressure profile at O(h^2) for Phase 1 rather than
    at machine precision.  Two things are worth knowing about how it gets
    there, both of which this test is arranged to respect:

    * On a *uniform* grid the estimator is exact even for a quadratic, because
      the ``h^2/12`` offsets in the neighbouring layer means cancel and the
      centred difference of ``mid^2`` is exact.  So the refinement below uses a
      self-similar non-uniform grid; a uniform one would measure round-off.
    * On a non-uniform grid the *slope* error is only first order, but the
      *reconstruction* error is second order, because the slope multiplies
      ``(p - p^mid)``, which is itself O(h).  Second order in the reconstructed
      profile is what the scheme consumes, so that is what is asserted.

    """
    curvature = 4.0e-14
    total = 1.6e7
    pattern = np.array([1.0, 2.5, 0.5, 1.8])
    errors = []
    for repeats in [4, 8, 16]:
        thickness = np.tile(pattern, repeats)
        thickness = thickness * (total / thickness.sum())
        interfaces, mid = _column(thickness)
        # exact layer mean of a quadratic: <p^2> = mid^2 + h^2/12
        exact_mean = curvature * (mid**2 + thickness**2 / 12.0)
        values, pressure_mid = _as_state(mid, exact_mean)
        slope = linear_slope(values, pressure_mid)

        largest = 0.0
        for fraction in [-0.5, -0.25, 0.0, 0.25, 0.5]:
            probe = mid + fraction * thickness
            reconstructed = reconstruct(
                values,
                slope,
                pressure_mid,
                xr.DataArray(probe[np.newaxis, np.newaxis, :], dims=_DIMS),
            )
            error = reconstructed.values.ravel() - curvature * probe**2
            # interior only; the one-sided ends are lower order by construction
            largest = max(largest, float(np.max(np.abs(error[1:-1]))))
        errors.append(largest)

    for coarse, fine in zip(errors[:-1], errors[1:], strict=True):
        order = np.log2(coarse / fine)
        assert 1.8 < order < 2.2, (
            f'observed order {order:.2f} in the reconstructed profile'
        )


def test_masked_layers_and_short_columns():
    """Invalid layers stay ``NaN``; the ends of the valid column are one-sided.

    With tilt or a stepped floor the two columns have different numbers of
    valid layers, so the estimator has to find the ends of each column rather
    than of the array.
    """
    _, mid = _column(_NON_UNIFORM)
    intercept = 10.0
    slope_value = -2.0e-7
    profile = intercept + slope_value * mid

    # column 0 valid throughout; column 1 stops two layers early
    values = np.stack([profile, profile])
    pressure = np.stack([mid, mid])
    values[1, -2:] = np.nan
    pressure[1, -2:] = np.nan

    slope = linear_slope(
        xr.DataArray(values[np.newaxis, ...], dims=_DIMS),
        xr.DataArray(pressure[np.newaxis, ...], dims=_DIMS),
    )

    assert np.all(np.isnan(slope.values[0, 1, -2:]))
    # still exact for the linear profile in both columns, including at the
    # deepest valid layer of the shortened one
    np.testing.assert_allclose(slope.values[0, 0, :], slope_value, rtol=1e-12)
    np.testing.assert_allclose(
        slope.values[0, 1, :-2], slope_value, rtol=1e-12
    )


def test_single_valid_layer_gives_a_constant():
    """One layer has nothing to difference against."""
    _, mid = _column(_NON_UNIFORM)
    values = np.full(7, np.nan)
    pressure = np.full(7, np.nan)
    values[0] = 15.0
    pressure[0] = mid[0]

    slope = linear_slope(
        xr.DataArray(values[np.newaxis, np.newaxis, :], dims=_DIMS),
        xr.DataArray(pressure[np.newaxis, np.newaxis, :], dims=_DIMS),
    )
    assert slope.values[0, 0, 0] == 0.0
    assert np.all(np.isnan(slope.values[0, 0, 1:]))


def test_dimension_checks():
    _, mid = _column(_NON_UNIFORM)
    values, pressure_mid = _as_state(mid, np.linspace(20.0, 2.0, 7))
    with pytest.raises(ValueError, match='same dimensions'):
        linear_slope(values, pressure_mid.rename({'nCells': 'nOther'}))
    with pytest.raises(ValueError, match='nVertLevels'):
        linear_slope(
            values.transpose('Time', 'nVertLevels', 'nCells'),
            pressure_mid.transpose('Time', 'nVertLevels', 'nCells'),
        )
