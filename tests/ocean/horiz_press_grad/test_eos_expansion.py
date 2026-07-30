"""
Unit tests for the edge-shared equation-of-state expansion.

Mostly self-contained: hand-built two-column DataArrays for the algebra, plus
the real two-column states from :py:mod:`two_column` for the size of the
second-order remainder.  No file I/O either way.
"""

import gsw
import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.horiz_press_grad.eos_expansion import (
    edge_expansion,
    edge_specvol,
    edge_specvol_layer_mean,
    specvol_coefficients,
)

from .two_column import build_state

_DIMS = ['Time', 'nCells', 'nVertLevels']

# A two-column state with a real horizontal contrast in both tracers and a
# realistic pressure range, so the expansion is worked rather than exercised at
# a single point.
_THETA = np.array([[[22.0, 12.0, 4.0, 1.5], [19.0, 10.0, 3.0, 1.0]]])
_SALINITY = np.array([[[35.6, 35.0, 34.7, 34.66], [35.2, 34.8, 34.6, 34.55]]])
_PRESSURE = np.array(
    [[[1.0e6, 1.0e7, 2.5e7, 4.0e7], [1.1e6, 1.05e7, 2.6e7, 4.1e7]]]
)


def _state(
    theta=_THETA, salinity=_SALINITY, pressure=_PRESSURE
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    return (
        xr.DataArray(theta, dims=_DIMS),
        xr.DataArray(salinity, dims=_DIMS),
        xr.DataArray(pressure, dims=_DIMS),
    )


# ---------------------------------------------------------------------------
# Coefficients, and the units convention
# ---------------------------------------------------------------------------


def test_alpha_0_is_gsw_specvol():
    """``alpha_0`` is exactly the specific volume Polaris already computes."""
    theta, salinity, pressure = _state()
    coefficients = specvol_coefficients(theta, salinity, pressure)

    expected = gsw.specvol(
        salinity.values, theta.values, pressure.values * 1.0e-4
    )
    np.testing.assert_allclose(
        coefficients.alpha_0.values, expected, rtol=1e-15
    )


@pytest.mark.parametrize(
    'name, index, step',
    [
        ('alpha_theta', 0, 1.0e-4),  # degC
        ('alpha_s', 1, 1.0e-4),  # g/kg
        ('alpha_p', 2, 1.0e2),  # Pa
    ],
)
def test_derivatives_match_centred_finite_differences(name, index, step):
    """Each derivative matches a centred difference of ``gsw.specvol``.

    This is also the units check, and it is the reason the check exists.
    ``gsw.specvol_first_derivatives`` takes pressure in dbar but returns the
    pressure derivative per **Pa** -- the convention of neither argument -- so
    ``alpha_p`` must match a finite difference taken in Pa, and would be wrong
    by exactly 1e4 if the note were misread.  The other two follow the units of
    their arguments.
    """
    theta, salinity, pressure = _state()
    coefficients = specvol_coefficients(theta, salinity, pressure)

    arguments = [theta.values, salinity.values, pressure.values]
    plus = [value.copy() for value in arguments]
    minus = [value.copy() for value in arguments]
    plus[index] = plus[index] + step
    minus[index] = minus[index] - step

    def specvol(values):
        return gsw.specvol(values[1], values[0], values[2] * 1.0e-4)

    finite_difference = (specvol(plus) - specvol(minus)) / (2.0 * step)

    # gsw's analytic derivatives are self-consistent with gsw.specvol to about
    # 1e-5 relative; the tolerance is set by that, not by the differencing.
    np.testing.assert_allclose(
        coefficients[name].values, finite_difference, rtol=2e-5
    )


def test_alpha_p_is_per_pascal_not_per_dbar():
    """Pin the units of ``alpha_p`` directly, in the form that can go wrong."""
    theta, salinity, pressure = _state()
    alpha_p = specvol_coefficients(theta, salinity, pressure).alpha_p.values

    step_pa = 1.0e2
    high = gsw.specvol(
        salinity.values, theta.values, (pressure.values + step_pa) * 1.0e-4
    )
    low = gsw.specvol(
        salinity.values, theta.values, (pressure.values - step_pa) * 1.0e-4
    )
    per_pascal = (high - low) / (2.0 * step_pa)

    np.testing.assert_allclose(alpha_p, per_pascal, rtol=2e-5)
    # and emphatically not per dbar
    # atol must be zero: these values are ~4e-13, far below the default
    # atol, so a default-tolerance comparison passes against anything
    assert not np.allclose(alpha_p, per_pascal * 1.0e4, rtol=1e-2, atol=0.0)


def test_invalid_layers_stay_invalid():
    """``NaN`` in the state gives ``NaN`` in every coefficient, not a crash."""
    theta, salinity, pressure = _state()
    theta = theta.copy()
    theta[0, 1, 3] = np.nan

    coefficients = specvol_coefficients(theta, salinity, pressure)
    for name in coefficients.data_vars:
        values = coefficients[name].values
        assert np.isnan(values[0, 1, 3])
        assert np.all(np.isfinite(np.delete(values.ravel(), 7)))


def test_mismatched_shapes_are_rejected():
    theta, salinity, pressure = _state()
    with pytest.raises(ValueError, match='same shape'):
        specvol_coefficients(theta, salinity, pressure.isel(nVertLevels=0))


# ---------------------------------------------------------------------------
# The edge-shared expansion
# ---------------------------------------------------------------------------


def test_expansion_is_the_edge_average_of_the_coefficients():
    """``[edge-ref]``: coefficients and reference state are edge averages."""
    theta, salinity, pressure = _state()
    coefficients = specvol_coefficients(theta, salinity, pressure)
    expansion = edge_expansion(theta, salinity, pressure)

    for name in coefficients.data_vars:
        expected = 0.5 * (
            coefficients[name].isel(nCells=0)
            + coefficients[name].isel(nCells=1)
        )
        np.testing.assert_allclose(
            expansion[name].values, expected.values, rtol=1e-15
        )
    for name, field in [
        ('theta_ref', theta),
        ('s_ref', salinity),
        ('p_ref', pressure),
    ]:
        expected = 0.5 * (field.isel(nCells=0) + field.isel(nCells=1))
        np.testing.assert_allclose(
            expansion[name].values, expected.values, rtol=1e-15
        )
    assert 'nCells' not in expansion.dims


def test_expansion_is_symmetric_under_swapping_the_columns():
    """The edge sees one equation of state, so column order cannot matter."""
    theta, salinity, pressure = _state()
    forward = edge_expansion(theta, salinity, pressure)
    swapped = edge_expansion(
        theta.isel(nCells=[1, 0]),
        salinity.isel(nCells=[1, 0]),
        pressure.isel(nCells=[1, 0]),
    )

    for name in forward.data_vars:
        np.testing.assert_allclose(
            forward[name].values, swapped[name].values, rtol=1e-15
        )


def test_edge_specvol_at_the_expansion_point_returns_alpha_0():
    """Evaluated at its own expansion point the profile returns ``alpha_0``.

    Worth pinning because ``alpha_0`` is the *mean of the two cells' specific
    volumes*, not specific volume at the mean state; an implementation that
    conflated the two would still pass a smoothness check.
    """
    theta, salinity, pressure = _state()
    expansion = edge_expansion(theta, salinity, pressure)

    at_reference = edge_specvol(
        expansion,
        expansion.theta_ref,
        expansion.s_ref,
        expansion.p_ref,
    )
    np.testing.assert_allclose(
        at_reference.values, expansion.alpha_0.values, rtol=1e-15
    )


def test_both_columns_share_one_profile():
    """The same function of pressure is used on both sides of the edge.

    Condition 1 of §3.7.2.  Evaluating the profile with each column's own state
    must differ *only* through that state, never through the coefficients, so
    feeding the two columns identical states must give identical answers even
    though the expansion was built from a contrast.
    """
    theta, salinity, pressure = _state()
    expansion = edge_expansion(theta, salinity, pressure)

    probe_theta = xr.DataArray(np.full((1, 2, 4), 8.0), dims=_DIMS)
    probe_salinity = xr.DataArray(np.full((1, 2, 4), 34.9), dims=_DIMS)
    probe_pressure = xr.DataArray(np.full((1, 2, 4), 1.5e7), dims=_DIMS)

    specvol = edge_specvol(
        expansion, probe_theta, probe_salinity, probe_pressure
    )
    np.testing.assert_allclose(
        specvol.isel(nCells=0).values,
        specvol.isel(nCells=1).values,
        rtol=1e-15,
    )


def test_expansion_reduces_to_the_exact_eos_when_the_columns_coincide():
    """With identical columns the profile returns exact TEOS-10 at that state.

    Then ``alpha_0`` is the cell's own specific volume and the reference state
    is the cell's own state, so the second-order remainder that source 4 of the
    remainder accounts for is identically zero.
    """
    theta, salinity, pressure = _state()
    # isel with a list moves nCells to the end, so put it back
    uniform = [
        field.isel(nCells=[0, 0]).transpose(*_DIMS)
        for field in (theta, salinity, pressure)
    ]
    expansion = edge_expansion(*uniform)

    layer_mean = edge_specvol_layer_mean(expansion, *uniform)
    exact = gsw.specvol(
        uniform[1].values, uniform[0].values, uniform[2].values * 1.0e-4
    )
    np.testing.assert_allclose(layer_mean.values, exact, rtol=1e-15)


# ---------------------------------------------------------------------------
# The layer mean
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('shape', ['linear', 'quadratic'])
def test_layer_mean_matches_a_direct_average_of_the_profile(shape):
    """``[alpha-edge-layer-mean]`` equals a numerical average of the profile.

    The identity depends only on the layer *means* of the reconstruction, and
    not on its shape, because ``[alpha-taylor]`` is linear in its arguments.
    The quadratic case is the point: a mean-preserving parabola has the same
    mean as the line, so it must give the same answer, and an implementation
    that had smuggled in a nonlinear term would fail it while passing the
    linear
    case.
    """
    theta, salinity, pressure = _state()
    expansion = edge_expansion(theta, salinity, pressure)

    closed_form = edge_specvol_layer_mean(expansion, theta, salinity, pressure)

    # A mean-preserving profile across one layer, in pressure.  The integrand
    # is
    # a polynomial of degree at most 2 in pressure, so a four-point
    # Gauss-Legendre rule integrates it exactly and the comparison is limited
    # by
    # round-off rather than by quadrature -- which a trapezoid rule on the
    # quadratic case is not, by about 1e-11 relative.
    thickness = 2.0e6
    nodes, weights = np.polynomial.legendre.leggauss(4)
    nodes = 0.5 * nodes
    weights = 0.5 * weights
    theta_slope = 3.0e-6  # degC / Pa
    salinity_slope = 2.0e-8

    direct = np.zeros_like(closed_form.values)
    for icell in range(2):
        for level in range(4):
            centre = pressure.values[0, icell, level]
            probe = centre + nodes * thickness
            offset = probe - centre
            if shape == 'linear':
                theta_profile = (
                    theta.values[0, icell, level] + theta_slope * offset
                )
                salinity_profile = (
                    salinity.values[0, icell, level] + salinity_slope * offset
                )
            else:
                # mean-preserving parabola: <offset^2 - h^2/12> = 0
                bump = offset**2 - thickness**2 / 12.0
                theta_profile = (
                    theta.values[0, icell, level] + theta_slope * bump / 1.0e6
                )
                salinity_profile = (
                    salinity.values[0, icell, level]
                    + salinity_slope * bump / 1.0e6
                )
            profile = edge_specvol(
                expansion.isel(nVertLevels=level, Time=0),
                xr.DataArray(theta_profile, dims=['probe']),
                xr.DataArray(salinity_profile, dims=['probe']),
                xr.DataArray(probe, dims=['probe']),
            )
            direct[0, icell, level] = float(np.sum(weights * profile.values))

    np.testing.assert_allclose(direct, closed_form.values, rtol=1e-12)


# ---------------------------------------------------------------------------
# On real two-column states: how hard is the expansion being worked?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt',
    [
        ('hydrostatic_consistency', 4.0, 256.0, 50.0),
        ('hydrostatic_consistency_linear', 4.0, 256.0, 50.0),
        ('bathymetry_step', 4.0, 256.0, 200.0),
        ('temperature_gradient', 4.0, 4.0, None),
        ('temperature_gradient', 0.5, 0.5, None),
        ('salinity_gradient', 4.0, 4.0, None),
        ('ztilde_gradient', 4.0, 4.0, None),
        ('surface_pressure_gradient', 4.0, 4.0, None),
    ],
)
def test_second_order_eos_remainder_is_small(
    variant, horiz_res, vert_res, tilt
):
    """The first-order expansion is not being worked beyond its usefulness.

    ``[eos-remainder]`` is the mismatch between each cell's exact specific
    volume and the layer mean of the edge-shared profile, and §3.5 identifies
    it
    as precisely the *second-order* Taylor remainder of the equation of state
    across the edge.  It is source 4 of the remainder and the direct diagnostic
    the design asks for against assumption A2 (§3.7.6): if it were not small,
    the second-order expansion option of §3.3 would be needed.

    Measured relative to specific volume, the largest value over these
    configurations is 8.0e-6, in ``temperature_gradient`` at 4 km -- a 12 degC
    contrast across the edge, which is the hardest case in the family. Every
    other configuration is at 2.8e-9 or below, and the resting-state variants,
    being horizontally uniform in temperature and salinity, are at 2e-9 or
    below. The bound here is loose enough not to be a tripwire on round-off and
    tight enough to catch the expansion being applied across a contrast it
    cannot represent.
    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    expansion = edge_expansion(ds.temperature, ds.salinity, ds.pressure)
    layer_mean = edge_specvol_layer_mean(
        expansion, ds.temperature, ds.salinity, ds.pressure
    )

    remainder = (ds.SpecVol - layer_mean) / ds.SpecVol
    largest = float(np.abs(remainder).max())
    assert largest < 1.0e-4, (
        f'{variant} at horiz_res={horiz_res} km, vert_res={vert_res} m, '
        f'tilt={tilt}: second-order EOS remainder reaches {largest:.3e} of '
        'specific volume'
    )


def test_eos_remainder_vanishes_without_a_horizontal_contrast():
    """With no cross-edge contrast the remainder is identically zero.

    Guards the test above: it would pass trivially for an implementation whose
    remainder was always tiny for the wrong reason.
    """
    ds = build_state('hydrostatic_consistency', 4.0, 256.0, 0.05)
    # force the two columns to coincide exactly
    uniform = {
        name: ds[name].isel(nCells=[0, 0]).transpose(*ds[name].dims)
        for name in ['temperature', 'salinity', 'pressure']
    }
    expansion = edge_expansion(**uniform)
    layer_mean = edge_specvol_layer_mean(expansion, **uniform)
    exact = specvol_coefficients(**uniform).alpha_0

    difference = float(np.abs((layer_mean - exact)).max())
    assert difference == 0.0, (
        f'remainder is {difference:.3e} for two identical columns'
    )
