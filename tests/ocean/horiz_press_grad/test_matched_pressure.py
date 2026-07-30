"""
Unit tests for the matched-pressure integrand, ``[dalpha]``.

This is deliverable D9: the fixed-pressure contrast in specific volume must be
zero **at every quadrature point** on the exact set, not merely in the layer
mean.
"""

import numpy as np
import pytest

from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    delta_specvol_at_pressure,
    layer_containing_pressure,
    matched_pressure_pieces,
)

from .two_column import LINEAR_VARIANT, build_state, sweep

# Four-point Gauss-Legendre, as the column scan will use.
_NODES, _ = np.polynomial.legendre.leggauss(4)

# Pointwise tolerance, relative to the size of the terms being differenced --
# alpha_theta times the temperature range.  Measured worst case over the linear
# variant's sweep is ~1e-17 of specific volume; this leaves several decades.
_POINTWISE_TOL = 1.0e-14


def _quadrature_points(pieces, edge_layer):
    edges = pieces['edge_interface']
    top, bot = edges[edge_layer], edges[edge_layer + 1]
    return 0.5 * (top + bot) + 0.5 * (bot - top) * _NODES


def _deepest_shared(pieces):
    return int(min(pieces['deepest']))


@pytest.mark.parametrize('horiz_res, vert_res, tilt', sweep(LINEAR_VARIANT))
def test_integrand_is_pointwise_zero_on_the_exact_set(
    horiz_res, vert_res, tilt
):
    """``[dalpha]`` is zero at every quadrature point of every edge layer.

    This is the central property of the scheme (design §3.5).  Because the
    integrand itself vanishes rather than its integral, exactness cannot depend
    on the quadrature, on the coefficients, or on the two columns' interfaces
    lining up -- and asserting it pointwise rather than in the layer mean is
    what distinguishes "zero" from "integrates to zero by cancellation".
    """
    ds = build_state(LINEAR_VARIANT, horiz_res, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)
    scale = float(np.abs(pieces['expansion'].alpha_theta).max()) * float(
        np.nanmax(pieces['theta']) - np.nanmin(pieces['theta'])
    )

    worst = 0.0
    for edge_layer in range(_deepest_shared(pieces) + 1):
        pressure = _quadrature_points(pieces, edge_layer)
        contrast = delta_specvol_at_pressure(pieces, edge_layer, pressure)
        worst = max(worst, float(np.max(np.abs(contrast))))

    assert worst <= _POINTWISE_TOL * scale, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: max |Delta_e alpha| = '
        f'{worst:.3e} m3 kg-1, more than {_POINTWISE_TOL * scale:.3e}'
    )


@pytest.mark.parametrize(
    'vert_res, tilt, expected_offset',
    [(256.0, 50.0, 1), (64.0, 50.0, 2)],
)
def test_lookup_returns_a_layer_other_than_the_edge_layer(
    vert_res, tilt, expected_offset
):
    """Under tilt, a column's layer containing p is not its layer ``k``.

    Without this the suite cannot tell matched-pressure from matched-index: if
    the lookup silently returned ``k`` the scheme would be a different one, and
    that is the defect the previous formulation failed on.  The offset grows
    with tilt and with refinement -- at 64 m and 50 m/km the two columns' layer
    ``k`` do not overlap in pressure at all.

    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)

    largest = 0
    for edge_layer in range(_deepest_shared(pieces) + 1):
        pressure = _quadrature_points(pieces, edge_layer)
        for icell in range(2):
            index = layer_containing_pressure(pieces, icell, pressure)
            largest = max(largest, int(np.max(np.abs(index - edge_layer))))

    assert largest >= expected_offset, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: the lookup never departs '
        f'from the edge layer by more than {largest}, so this configuration '
        'cannot distinguish matched-pressure from matched-index'
    )


@pytest.mark.parametrize('vert_res, tilt', [(256.0, 50.0), (64.0, 1.0)])
def test_lookup_returns_the_layer_that_brackets_the_pressure(vert_res, tilt):
    """The layer returned actually contains the pressure, in that column."""
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)

    for edge_layer in range(_deepest_shared(pieces) + 1):
        pressure = _quadrature_points(pieces, edge_layer)
        for icell in range(2):
            index = layer_containing_pressure(pieces, icell, pressure)
            top = pieces['interface'][icell, index]
            bot = pieces['interface'][icell, index + 1]
            assert np.all(top <= pressure), (
                f'column {icell}: a returned layer starts below its pressure'
            )
            assert np.all(pressure <= bot), (
                f'column {icell}: a returned layer ends above its pressure'
            )


def test_lookup_clamps_outside_the_column():
    """Above the surface and below the floor, the outermost layer is used.

    Exactness does not depend on this (design §3.5, consequence 3): an
    extrapolated reconstruction still reproduces a profile it resolves.  What
    it costs off the exact set is deliverable D8'.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    pieces = matched_pressure_pieces(ds)

    for icell in range(2):
        deepest = int(pieces['deepest'][icell])
        surface = pieces['interface'][icell, 0]
        floor = pieces['interface'][icell, deepest + 1]
        above = layer_containing_pressure(
            pieces, icell, np.array([surface - 1.0e5])
        )
        below = layer_containing_pressure(
            pieces, icell, np.array([floor + 1.0e5])
        )
        assert above[0] == 0
        assert below[0] == deepest


def test_integrand_is_nonzero_off_the_exact_set():
    """The pointwise test above has content.

    On the curved ``hydrostatic_consistency`` profile the reconstruction cannot
    reproduce the true profile, so the two columns describe slightly different
    water and the contrast is genuinely nonzero -- eleven orders of magnitude
    above the exact-set result.  Without this, the pointwise test could pass
    for an implementation that returned zero unconditionally.
    """
    ds = build_state('hydrostatic_consistency', 4.0, 256.0, 50.0)
    pieces = matched_pressure_pieces(ds)

    worst = 0.0
    for edge_layer in range(_deepest_shared(pieces) + 1):
        pressure = _quadrature_points(pieces, edge_layer)
        contrast = delta_specvol_at_pressure(pieces, edge_layer, pressure)
        worst = max(worst, float(np.max(np.abs(contrast))))

    assert worst > 1.0e-9, (
        f'max |Delta_e alpha| is only {worst:.3e} on a curved profile'
    )
