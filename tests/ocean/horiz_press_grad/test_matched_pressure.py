"""
Unit tests for the matched-pressure integrand, ``[dalpha]``.

This is deliverable D9: the fixed-pressure contrast in specific volume must be
zero **at every quadrature point** on the exact set, not merely in the layer
mean.
"""

import numpy as np
import pytest

from polaris.ocean.vertical.ztilde import Gravity
from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    anchor_difference,
    centered_shift,
    column_scan,
    delta_specvol_at_pressure,
    finite_volume_hpga,
    hpga_from_shift,
    hydrostatic_scale,
    layer_containing_pressure,
    matched_pressure_pieces,
    scan_increments,
)
from polaris.tasks.ocean.horiz_press_grad.reference import ReferenceColumn

from .two_column import LINEAR_VARIANT, build_state, make_config, sweep

# Machine-precision tolerance as a multiple of the hydrostatic scale, matching
# tests/ocean/horiz_press_grad/test_finite_volume.py.
_ROUNDOFF_TOL = 1.0e-14

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


# ---------------------------------------------------------------------------
# 9g: the column scan and the anchor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'vert_res, tilt', [(256.0, 1.0), (256.0, 50.0), (64.0, 50.0)]
)
def test_scan_is_zero_at_every_interface_on_the_exact_set(vert_res, tilt):
    """``D_k`` is zero to round-off at every ``k``, not only in the mean.

    Asserting it at every interface rather than in the layer mean is what
    separates the two failure modes the plan names: a residual that grows with
    depth would point at the scan, and one that is flat would point at the
    anchor.

    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    difference = column_scan(matched_pressure_pieces(ds))

    worst = float(np.max(np.abs(difference)))
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert worst <= tolerance, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: max |D_k| = {worst:.3e} m, '
        f'more than {tolerance:.3e} m'
    )


@pytest.mark.parametrize(
    'variant, vert_res, tilt',
    [
        (LINEAR_VARIANT, 256.0, 50.0),
        ('hydrostatic_consistency', 256.0, 50.0),
        ('bathymetry_step', 256.0, 200.0),
    ],
)
def test_anchor_is_exactly_zero_without_a_surface_pressure_gradient(
    variant, vert_res, tilt
):
    """With equal surface pressures the anchor is identically zero.

    Both short integrals of ``[anchor]`` then run over a zero-width interval
    and the sea-surface heights are equal, so nothing is left to cancel.  This
    is the trivial half of D10; the informative half is the next test.
    """
    ds = build_state(variant, 4.0, vert_res, tilt)
    assert anchor_difference(matched_pressure_pieces(ds)) == 0.0


def test_anchor_reports_the_inverse_barometer_residual():
    """D10, and the check of condition 3 (design §3.5.1).

    ``surface_pressure_gradient`` is a resting state with a surface-pressure
    gradient, so the anchor is where condition 3 is actually tested.  It comes
    out **nonzero**, at 6.1e-4 m, and that is correct rather than a defect:
    Polaris initializes the sea surface from the *reference-density* inverse
    barometer, ``-p_surf / (rho0 g)``, so the state it produces genuinely has a
    fixed-pressure height difference of that size -- the residual of two 3.57 m
    terms, of relative size ``(alpha - 1/rho0)/alpha``.

    The design's claim that ``D_1`` is zero for a resting ocean is therefore
    conditional on an *exact* inverse barometer, which this initialization does
    not use.  The scheme is right to report it: the quasi-analytic reference
    reports the same tendency (see the accuracy test below).

    ``D_k`` is flat with depth here, which is the anchor signature rather than
    a scan defect.
    """
    ds = build_state('surface_pressure_gradient', 4.0, 4.0, None)
    pieces = matched_pressure_pieces(ds)
    difference = column_scan(pieces)

    anchor = anchor_difference(pieces)
    assert 1.0e-4 < abs(anchor) < 1.0e-2, (
        f'anchor is {anchor:.3e} m, outside the range the reference-density '
        'inverse barometer explains'
    )
    # flat with depth: the anchor offsets the whole column, the scan adds
    # essentially nothing
    assert float(np.ptp(difference)) < 1.0e-3 * abs(anchor), (
        f'D_k varies by {float(np.ptp(difference)):.3e} m down the column, '
        'which points at the scan rather than the anchor'
    )


def test_scan_matches_the_reference_where_the_state_is_not_at_rest():
    """The scan reproduces the quasi-analytic reference, and beats `Centered`.

    On ``surface_pressure_gradient`` the true tendency is not zero, so this is
    an accuracy check rather than an exactness one -- and it is the first
    direct comparison of the new scheme against the reference.  Measured rms
    against the reference: 3.9e-10 m s-2 for the scan against 8.1e-10 for
    ``PressureGradCentered`` on the same state.

    The layer mean proper is 9h's job; the interface trapezoid used here is a
    stand-in, so treat the margin as provisional rather than as the final
    accuracy result.

    """
    ds = build_state('surface_pressure_gradient', 4.0, 4.0, None)
    pieces = matched_pressure_pieces(ds)
    difference = column_scan(pieces)
    deepest = _deepest_shared(pieces)

    implied = -(Gravity / 4.0e3) * 0.5 * (difference[:-1] + difference[1:])
    reference = ReferenceColumn(
        make_config('surface_pressure_gradient'), x_sign=1.0
    )
    z_tilde = 0.5 * (
        ds.ZTildeInterface.isel(Time=0, nCells=0).values
        + ds.ZTildeInterface.isel(Time=0, nCells=1).values
    )
    expected = reference.layer_mean_hpga(z_tilde[: deepest + 2])
    centered = ds.HPGA.isel(Time=0).values[: deepest + 1]

    scan_error = float(np.sqrt(np.mean((implied - expected) ** 2)))
    centered_error = float(np.sqrt(np.mean((centered - expected) ** 2)))
    assert scan_error < centered_error, (
        f'the scan is {scan_error:.3e} from the reference against '
        f'{centered_error:.3e} for the centered scheme'
    )


@pytest.mark.parametrize(
    'variant, vert_res, tilt',
    [(LINEAR_VARIANT, 256.0, 50.0), ('hydrostatic_consistency', 64.0, 50.0)],
)
def test_scan_increments_are_small(variant, vert_res, tilt):
    """§3.7.5's claim, quantified: nothing large is formed or cancelled.

    Each increment is an integral of a horizontal contrast, so it should be
    tiny against the hydrostatic scale -- the ~7e3 m of column that a scheme
    comparing at fixed layer index has to difference and cancel.
    """
    ds = build_state(variant, 4.0, vert_res, tilt)
    increments = scan_increments(matched_pressure_pieces(ds))

    ratio = float(np.max(np.abs(increments))) / hydrostatic_scale(ds)
    assert ratio < 1.0e-6, (
        f'{variant}: largest scan increment is {ratio:.3e} of the hydrostatic '
        'scale'
    )


@pytest.mark.parametrize('vert_res, tilt', [(256.0, 50.0), (64.0, 1.0)])
def test_scan_round_trips(vert_res, tilt):
    """Accumulating back up the column recovers the same ``D_k``.

    The previous formulation had two physically distinct anchors to compare;
    this one has only the surface, so what is testable is that the increments
    are individually accurate enough that the direction of accumulation does
    not matter in double precision.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)
    difference = column_scan(pieces)
    increments = scan_increments(pieces)

    upward = np.empty_like(difference)
    upward[-1] = difference[-1]
    for level in range(len(increments) - 1, -1, -1):
        upward[level] = upward[level + 1] - increments[level]

    worst = float(np.max(np.abs(upward - difference)))
    assert worst <= _ROUNDOFF_TOL * hydrostatic_scale(ds)


# ---------------------------------------------------------------------------
# 9h: the assembled scheme, HPGAFiniteVolume, and the A5 rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'vert_res, tilt', [(256.0, 1.0), (256.0, 50.0), (64.0, 50.0)]
)
def test_assembled_hpga_is_zero_on_the_exact_set(vert_res, tilt):
    """D4'': the assembled tendency is machine zero on the exact set.

    Measured at 3.7e-18 m s-2 against ``PressureGradCentered``'s 6.9e-05 on the
    same state -- thirteen orders.  This is the property the whole exercise is
    for.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    hpga = finite_volume_hpga(ds, 4.0e3)

    valid = np.isfinite(hpga.values)
    worst = float(np.max(np.abs(hpga.values[valid])))
    centered = float(np.abs(ds.HPGA).max())
    assert worst < 1.0e-15, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: max |HPGA| = {worst:.3e} '
        f'm s-2 (centered gives {centered:.3e})'
    )


def test_exactness_survives_differing_max_level_cell():
    """D8': the below-floor extrapolation does not break exactness.

    At 50 m/km the two columns of ``hydrostatic_consistency_linear`` reach
    different ``maxLevelCell`` (13 and 14), so the deepest edge layer evaluates
    one column's reconstruction below its own floor.  Exactness is unaffected,
    which is what design §3.5 consequence 3 predicts and what demotes A5 from
    an exactness risk to an accuracy question.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    pieces = matched_pressure_pieces(ds)
    assert pieces['deepest'][0] != pieces['deepest'][1], (
        'this configuration no longer exercises differing maxLevelCell, so '
        'the test has stopped checking what it claims to'
    )

    hpga = finite_volume_hpga(ds, 4.0e3)
    valid = np.isfinite(hpga.values)
    assert float(np.max(np.abs(hpga.values[valid]))) < 1.0e-15


def test_assembled_hpga_beats_centered_off_the_exact_set():
    """On the curved and stepped variants the scheme is a large improvement.

    Not exactness -- these are outside the exact set -- but the accuracy gain
    is what Phase 1 is for.  ``bathymetry_step`` is the one that matters most:
    it is the two-column analogue of the bottom-layer error seen in realistic
    global runs, and the deepest edge layer there extends up to 65% below the
    shallower column's floor.
    """
    for variant, tilt in [
        ('hydrostatic_consistency', 50.0),
        ('bathymetry_step', 200.0),
    ]:
        ds = build_state(variant, 4.0, 256.0, tilt)
        hpga = finite_volume_hpga(ds, 4.0e3)
        valid = np.isfinite(hpga.values)
        scheme = float(np.max(np.abs(hpga.values[valid])))
        centered = float(np.abs(ds.HPGA).max())
        assert scheme < 0.2 * centered, (
            f'{variant}: finite volume gives {scheme:.3e} against centered '
            f'{centered:.3e}'
        )


def test_hpga_finite_volume_is_written_to_the_state():
    """``HPGAFiniteVolume`` lands alongside ``HPGA``, which is unchanged.

    ``HPGA`` keeping its name, meaning and values is what leaves the recorded
    baselines valid; if it moved, something in the assembly would be wrong.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)

    assert 'HPGAFiniteVolume' in ds
    assert ds.HPGAFiniteVolume.dims == ('Time', 'nVertLevels')
    np.testing.assert_array_equal(
        ds.HPGAFiniteVolume.values, finite_volume_hpga(ds, 4.0e3).values
    )
    np.testing.assert_allclose(
        ds.HPGA.values,
        hpga_from_shift(centered_shift(ds), 4.0e3).values,
        rtol=0.0,
        atol=1.0e-14 * hydrostatic_scale(ds) * Gravity / 4.0e3,
    )
    deepest = int(ds.maxLevelCell.min()) - 1
    finite = np.isfinite(ds.HPGAFiniteVolume.values[0])
    assert bool(finite[: deepest + 1].all())
    assert not bool(finite[deepest + 1 :].any())


@pytest.mark.parametrize(
    'guard, must_fire',
    [
        ('cell_local_expansion', True),
        ('state_by_index', False),
        ('anchor_delta_z_only', False),
    ],
)
def test_guards_on_the_exact_set(guard, must_fire):
    """Which deliberate mistakes break exactness, and which cannot.

    Only one of the three does, and that is itself the finding: the scheme's
    exactness is structural enough that most plausible errors leave it intact.

    * ``cell_local_expansion`` **fires**, at 1e-5.  Design §3.5 consequence 1
      says the shared coefficients may take *any value*; it does not say the
      two columns may use *different* ones.  ``[dalpha]`` only collapses to a
      coefficient times a contrast when one set multiplies both columns, so the
      edge-shared expansion point of §3.3.1 remains load-bearing for exactness.
    * ``state_by_index`` cannot fire here: this variant's profile is a single
      line in pressure, so every layer's reconstruction is that same line and
      looking up the wrong layer costs nothing.
    * ``anchor_delta_z_only`` cannot fire here either, because the two columns
      share a surface pressure and the correction it drops is zero.  It fires
      hard where they do not -- see the next test.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    correct = finite_volume_hpga(ds, 4.0e3)
    perturbed = finite_volume_hpga(ds, 4.0e3, guards={guard})

    valid = np.isfinite(correct.values)
    baseline = float(np.max(np.abs(correct.values[valid])))
    result = float(np.max(np.abs(perturbed.values[valid])))

    if must_fire:
        assert result > 1.0e6 * baseline, (
            f'{guard} left the tendency at {result:.3e}, so it is not a guard'
        )
    else:
        assert result < 1.0e3 * baseline, (
            f'{guard} changed the tendency to {result:.3e}, which contradicts '
            'the reason given for why it cannot'
        )


def test_anchor_guard_fires_where_surface_pressures_differ():
    """``anchor_delta_z_only`` is a real guard, on the right configuration.

    Dropping the correction to a common pressure leaves the raw sea-surface
    height difference, which is 3.57 m rather than the 6.1e-4 m residual, and
    the tendency comes out some thousands of times too large.
    """
    ds = build_state('surface_pressure_gradient', 4.0, 4.0, None)
    correct = finite_volume_hpga(ds, 4.0e3)
    perturbed = finite_volume_hpga(ds, 4.0e3, guards={'anchor_delta_z_only'})

    valid = np.isfinite(correct.values)
    ratio = float(np.max(np.abs(perturbed.values[valid]))) / float(
        np.max(np.abs(correct.values[valid]))
    )
    assert ratio > 1.0e3, (
        f'the anchor guard only changed things by {ratio:.1f}x'
    )


def test_operator_is_antisymmetric_under_swapping_the_columns():
    """Swapping the two columns negates the tendency, to round-off.

    The edge normal reverses, so nothing else may.
    """
    ds = build_state('hydrostatic_consistency', 4.0, 256.0, 50.0)
    swapped = ds.copy()
    for name in ds.data_vars:
        if 'nCells' in ds[name].dims:
            swapped[name] = (
                ds[name].isel(nCells=[1, 0]).transpose(*ds[name].dims)
            )

    forward = finite_volume_hpga(ds, 4.0e3)
    reverse = finite_volume_hpga(swapped, 4.0e3)
    valid = np.isfinite(forward.values) & np.isfinite(reverse.values)

    residual = float(np.max(np.abs((forward.values + reverse.values)[valid])))
    scale = float(np.max(np.abs(forward.values[valid])))
    assert residual < 1.0e-10 * scale, (
        f'swapping the columns left {residual:.3e} against a signal of '
        f'{scale:.3e}'
    )
