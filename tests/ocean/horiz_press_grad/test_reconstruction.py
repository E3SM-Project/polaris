"""
Unit tests for the mean-preserving linear and parabolic reconstructions.

Pure numpy/xarray: no config, no dataset, no file I/O, and no parametrization
over the configured sweeps.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.horiz_press_grad.reconstruction import (
    _ppm_derivatives,
    _ppm_window,
    layer_deviation,
    linear_slope,
    ppm_coefficients,
    reconstruct,
)

_DIMS = ['Time', 'nCells', 'nVertLevels']
_INTERFACE_DIMS = ['Time', 'nCells', 'nVertLevelsP1']

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


# A quadratic, a cubic and an exponential in pressure, each paired with its
# exact mean over a layer [a, b], written so that nothing is lost to
# cancellation when the layer is thin.  The polynomials are sized so that every
# term matters over the 16.75 MPa of the non-uniform column; the exponential is
# smooth but in no polynomial's exact set, like a thermocline.
_E_FOLDING = 8.0e6
_QUADRATIC = (
    lambda p: 12.0 - 3.0e-7 * p + 4.0e-14 * p**2,
    lambda a, b: (
        12.0 - 1.5e-7 * (a + b) + 4.0e-14 * (a * a + a * b + b * b) / 3.0
    ),
)
_CUBIC = (
    lambda p: 12.0 - 3.0e-7 * p + 4.0e-14 * p**2 - 2.0e-21 * p**3,
    lambda a, b: (
        12.0
        - 1.5e-7 * (a + b)
        + 4.0e-14 * (a * a + a * b + b * b) / 3.0
        - 5.0e-22 * (a**3 + a * a * b + a * b * b + b**3)
    ),
)
_EXPONENTIAL = (
    lambda p: 2.0 + 18.0 * np.exp(-p / _E_FOLDING),
    lambda a, b: (
        2.0
        - 18.0
        * _E_FOLDING
        * np.exp(-a / _E_FOLDING)
        * np.expm1(-(b - a) / _E_FOLDING)
        / (b - a)
    ),
)


def _exact_means(layer_mean, interfaces: np.ndarray) -> np.ndarray:
    """Exact layer averages of a profile."""
    return layer_mean(interfaces[:-1], interfaces[1:])


def _ppm(interfaces: np.ndarray, means: np.ndarray):
    """The parabolic slope and curvature of one column, as flat arrays."""
    slope, curvature = ppm_coefficients(
        xr.DataArray(means[np.newaxis, np.newaxis, :], dims=_DIMS),
        xr.DataArray(
            interfaces[np.newaxis, np.newaxis, :], dims=_INTERFACE_DIMS
        ),
    )
    return slope.values.ravel(), curvature.values.ravel()


def _parabola(interfaces, means, slope, curvature, layer, pressure):
    """One layer's reconstruction, ``[ppm-recon]``, at some pressures."""
    return reconstruct(
        means[layer],
        slope[layer],
        0.5 * (interfaces[layer] + interfaces[layer + 1]),
        pressure,
        curvature=curvature[layer],
        thickness=interfaces[layer + 1] - interfaces[layer],
    )


@pytest.mark.parametrize(
    'thickness, label', [(_NON_UNIFORM, 'non-uniform'), (_UNIFORM, 'uniform')]
)
def test_ppm_is_exact_for_a_quadratic_profile(thickness, label):
    """The slope and curvature of a quadratic are recovered exactly.

    This is the property that moves a quadratic-in-pressure profile into the
    exact set of §3.7.3, and it has to hold on the non-uniform grid, at every
    layer including the two at each end, where the window is one-sided and the
    coefficients come from ``[ppm-coeffs-end]``.
    """
    interfaces, mid = _column(thickness)
    profile, layer_mean = _QUADRATIC
    slope, curvature = _ppm(interfaces, _exact_means(layer_mean, interfaces))

    np.testing.assert_allclose(
        slope, -3.0e-7 + 8.0e-14 * mid, rtol=1e-12, err_msg=label
    )
    np.testing.assert_allclose(curvature, 4.0e-14, rtol=1e-12, err_msg=label)


def test_ppm_reproduces_a_quadratic_beyond_the_column():
    """Each layer's parabola is the quadratic, inside the layer and beyond.

    Beyond matters because the outermost layers are evaluated past the ends of
    the column (assumption A5), and exactness on the exact set must survive
    that: an extrapolated reconstruction still reproduces a profile it
    resolves.
    """
    interfaces, _ = _column(_NON_UNIFORM)
    profile, layer_mean = _QUADRATIC
    means = _exact_means(layer_mean, interfaces)
    slope, curvature = _ppm(interfaces, means)

    count = len(means)
    for layer in range(count):
        probe = np.linspace(interfaces[layer], interfaces[layer + 1], 5)
        if layer == 0:
            probe = np.concatenate([probe, [-2.0e6, -1.0e6]])
        if layer == count - 1:
            probe = np.concatenate([probe, interfaces[-1] + [1.0e6, 6.0e6]])
        np.testing.assert_allclose(
            _parabola(interfaces, means, slope, curvature, layer, probe),
            profile(probe),
            rtol=1e-11,
            err_msg=f'layer {layer}',
        )


def test_ppm_interface_values_are_exact_for_a_cubic():
    """The interface values are fourth-order: exact for a cubic profile.

    A cubic's cumulative integral is a quartic, which the polynomial through
    five interfaces reproduces on any grid.  So each layer's parabola, though
    it cannot be the cubic, meets it exactly at both of its interfaces, and the
    two layers meeting at an interface agree there: the reconstruction is
    continuous in pressure.
    """
    interfaces, _ = _column(_NON_UNIFORM)
    profile, layer_mean = _CUBIC
    means = _exact_means(layer_mean, interfaces)
    slope, curvature = _ppm(interfaces, means)

    scale = np.max(np.abs(means))
    for layer in range(len(means)):
        ends = interfaces[layer : layer + 2]
        error = _parabola(
            interfaces, means, slope, curvature, layer, ends
        ) - profile(ends)
        np.testing.assert_allclose(
            error / scale, 0.0, atol=1e-13, err_msg=f'layer {layer}'
        )


def test_ppm_deviation_integrates_to_zero_over_its_layer():
    """The mean-preserving constraint, on means from no particular profile.

    The deviation is quadratic in pressure, so a two-point Gauss rule
    integrates it exactly and the result is limited by round-off.  In the
    deepest layer the deviation at the Gauss points is comparable to the small
    mean there, so the tolerance allows a few more units in the last place than
    the linear case needs.
    """
    interfaces, mid = _column(_NON_UNIFORM)
    values = np.array([22.0, 18.0, 8.0, 6.0, 4.0, 2.0, 1.0])
    slope, curvature = _ppm(interfaces, values)

    offset = 1.0 / np.sqrt(3.0)
    thickness = np.diff(interfaces)
    integral = np.zeros(len(mid))
    for sign in [-1.0, 1.0]:
        probe = mid + sign * 0.5 * offset * thickness
        integral += (
            0.5
            * thickness
            * layer_deviation(
                slope,
                mid,
                probe,
                curvature=curvature,
                thickness=thickness,
            )
        )

    np.testing.assert_allclose(
        integral / np.abs(values * thickness), 0.0, atol=1e-14
    )


def test_ppm_is_third_order_on_a_smooth_profile():
    """Off the exact set the parabolic reconstruction is third order.

    Measured on a self-similar non-uniform grid, so that a uniform grid's
    extra cancellations cannot flatter it, and over every layer, so that the
    one-sided windows at the two ends are held to the same order as the
    interior.
    """
    profile, layer_mean = _EXPONENTIAL
    total = 1.6e7
    pattern = np.array([1.0, 2.5, 0.5, 1.8])
    errors = []
    for repeats in [4, 8, 16]:
        thickness = np.tile(pattern, repeats)
        thickness = thickness * (total / thickness.sum())
        interfaces, _ = _column(thickness)
        means = _exact_means(layer_mean, interfaces)
        slope, curvature = _ppm(interfaces, means)

        largest = 0.0
        for layer in range(len(means)):
            probe = np.linspace(interfaces[layer], interfaces[layer + 1], 5)
            error = _parabola(
                interfaces, means, slope, curvature, layer, probe
            ) - profile(probe)
            largest = max(largest, float(np.max(np.abs(error))))
        errors.append(largest)

    for coarse, fine in zip(errors[:-1], errors[1:], strict=True):
        order = np.log2(coarse / fine)
        assert 2.8 < order < 3.4, (
            f'observed order {order:.2f} in the reconstructed profile'
        )


def test_ppm_short_columns():
    """With fewer than four valid layers the polynomial uses every interface.

    Its degree is then the number of valid layers: three stay exact for a
    quadratic, two give exactly the linear reconstruction, and one a constant.
    """
    interfaces, _ = _column(_NON_UNIFORM)
    profile, layer_mean = _QUADRATIC
    means = _exact_means(layer_mean, interfaces)

    slope, curvature = _ppm(interfaces[:4], means[:3])
    for layer in range(3):
        probe = np.linspace(interfaces[layer], interfaces[layer + 1], 5)
        np.testing.assert_allclose(
            _parabola(interfaces, means, slope, curvature, layer, probe),
            profile(probe),
            rtol=1e-11,
        )

    slope, curvature = _ppm(interfaces[:3], means[:2])
    mid = 0.5 * (interfaces[:2] + interfaces[1:3])
    linear = linear_slope(*_as_state(mid, means[:2])).values.ravel()
    np.testing.assert_allclose(slope, linear, rtol=1e-12)
    np.testing.assert_array_equal(curvature, 0.0)

    slope, curvature = _ppm(interfaces[:2], means[:1])
    np.testing.assert_array_equal(slope, 0.0)
    np.testing.assert_array_equal(curvature, 0.0)


def test_ppm_masked_layers():
    """Invalid layers stay ``NaN``, and each column finds its own ends.

    One column is valid throughout, one loses its two deepest layers, and one
    its shallowest, as a column under an ice shelf would.
    """
    interfaces, mid = _column(_NON_UNIFORM)
    profile, layer_mean = _QUADRATIC
    means = _exact_means(layer_mean, interfaces)

    values = np.stack([means, means, means])
    values[1, -2:] = np.nan
    values[2, 0] = np.nan
    slope, curvature = ppm_coefficients(
        xr.DataArray(values[np.newaxis, ...], dims=_DIMS),
        xr.DataArray(
            np.stack([interfaces] * 3)[np.newaxis, ...], dims=_INTERFACE_DIMS
        ),
    )

    valid = np.isfinite(values)
    np.testing.assert_array_equal(np.isfinite(slope.values[0]), valid)
    np.testing.assert_array_equal(np.isfinite(curvature.values[0]), valid)
    expected_slope = np.broadcast_to(-3.0e-7 + 8.0e-14 * mid, values.shape)
    np.testing.assert_allclose(
        slope.values[0][valid], expected_slope[valid], rtol=1e-9
    )
    np.testing.assert_allclose(curvature.values[0][valid], 4.0e-14, rtol=1e-9)


@pytest.mark.parametrize(
    'end, fraction, broken',
    [('bottom', 1.0e-9, 1.0), ('top', 1.0e-12, 1.0e-6)],
)
def test_ppm_thin_end_layer_extrapolates_smoothly(end, fraction, broken):
    """A thin outermost layer does not amplify round-off past the column.

    The outermost layers take their coefficients from ``[ppm-coeffs-end]``,
    the polynomial's own derivatives at the layer midpoint.  Formed instead
    from the two interface values, ``[ppm-coeffs]``, a thin layer's curvature
    is a small difference of nearly equal values divided by the square of its
    thickness: harmless inside the layer, and amplified without limit once the
    reconstruction is extrapolated (design §6.7).

    The profile is a quadratic, which the reconstruction reproduces exactly
    even when extrapolated, so whatever error remains is round-off.  In single
    precision the amplification shows at a cell a thousandth of a layer thick;
    in double it needs a far thinner one, thinnest at the top, where the
    pressures are small and a thin layer's thickness carries less round-off of
    its own.  The interface form is evaluated alongside, to show the test can
    tell the two apart.
    """
    profile, layer_mean = _QUADRATIC
    count = 16
    layer_thickness = 4.0e7 / count
    interfaces = np.linspace(0.0, 4.0e7, count + 1)
    if end == 'bottom':
        interfaces[-1] = interfaces[-2] + fraction * layer_thickness
        layer = count - 1
        probe = interfaces[-1] + np.linspace(0.0, 2.0, 21) * layer_thickness
    else:
        interfaces[0] = interfaces[1] - fraction * layer_thickness
        layer = 0
        probe = interfaces[0] - np.linspace(0.0, 2.0, 21) * layer_thickness
    means = _exact_means(layer_mean, interfaces)
    slope, curvature = _ppm(interfaces, means)

    error = _parabola(
        interfaces, means, slope, curvature, layer, probe
    ) - profile(probe)
    assert np.max(np.abs(error)) < 1e-10

    window = _ppm_window(layer, count)
    assert window == _ppm_window(layer + 1, count)
    top = _ppm_derivatives(
        means, interfaces, window, interfaces[layer], means[layer]
    )[0]
    bot = _ppm_derivatives(
        means, interfaces, window, interfaces[layer + 1], means[layer]
    )[0]
    thin = interfaces[layer + 1] - interfaces[layer]
    slope[layer] = (bot - top) / thin
    curvature[layer] = 3.0 * (top + bot) / thin**2
    error = _parabola(
        interfaces, means, slope, curvature, layer, probe
    ) - profile(probe)
    assert np.max(np.abs(error)) > broken


def test_ppm_dimension_checks():
    interfaces, mid = _column(_NON_UNIFORM)
    values = xr.DataArray(
        np.linspace(20.0, 2.0, 7)[np.newaxis, np.newaxis, :], dims=_DIMS
    )
    pressure = xr.DataArray(
        interfaces[np.newaxis, np.newaxis, :], dims=_INTERFACE_DIMS
    )
    with pytest.raises(ValueError, match='nVertLevelsP1'):
        ppm_coefficients(values, pressure.rename({'nVertLevelsP1': 'nOther'}))
    with pytest.raises(ValueError, match='leading'):
        ppm_coefficients(values, pressure.rename({'nCells': 'nOther'}))
    with pytest.raises(ValueError, match='one more level'):
        ppm_coefficients(values, pressure.isel(nVertLevelsP1=slice(0, 7)))
    gappy = values.copy()
    gappy[0, 0, 3] = np.nan
    with pytest.raises(ValueError, match='contiguous'):
        ppm_coefficients(gappy, pressure)
