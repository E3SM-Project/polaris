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
    anchor_index,
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
def test_scan_is_flat_on_the_exact_set(vert_res, tilt):
    """``D_k`` is *constant* down the column to round-off.

    Asserting it at every interface rather than in the layer mean is what
    separates the two failure modes the plan names: a residual that grows with
    depth points at the scan, and one that is flat points at the anchor.  This
    asserts the first is absent -- every increment of ``[d-recurrence]`` is
    zero to round-off, because ``[dalpha]`` is zero at every quadrature point
    on the exact set.

    It asserts flatness rather than zero.  ``D_k`` is *not* zero here, and the
    offset is entirely the anchor: see
    :py:func:`test_anchor_carries_the_bottom_pressure_offset` for what sets it
    and why it is a property of the state rather than of the scheme.  Anchored
    at the sea surface these were the same assertion, which is why this test
    used to be able to demand zero.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    difference = column_scan(matched_pressure_pieces(ds))

    worst = float(np.ptp(difference))
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert worst <= tolerance, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: D_k varies by '
        f'{worst:.3e} m down the column, more than {tolerance:.3e} m, which '
        'points at the scan rather than the anchor'
    )


@pytest.mark.parametrize(
    'variant, vert_res, tilt',
    [
        (LINEAR_VARIANT, 256.0, 0.05),
        (LINEAR_VARIANT, 128.0, 5.0),
        ('hydrostatic_consistency', 256.0, 0.05),
    ],
)
def test_anchor_carries_the_bottom_pressure_offset(variant, vert_res, tilt):
    """The sea-floor anchor is nonzero, and it is the state that makes it so.

    Anchored at the sea floor (design §3.7.4) the anchor is

        Delta_e Z + alphabar * Delta_e p_bot / g

    at the deepest interface valid in both columns.  Both columns' floors sit
    at the same geometric height here, so ``Delta_e Z`` is zero and the whole
    anchor is the second term: the two columns reach *different bottom
    pressures* at the same depth, so at a common pressure their heights
    genuinely differ.

    Why they differ, though both hold the same water and the profile is inside
    the reconstruction's exact set: ``VertCoord`` accumulates
    ``rho0 * alpha_k * htilde_k`` with ``alpha_k`` the exact TEOS-10 specific
    volume *at the layer-mean state*, and alpha is nonlinear in pressure, so
    that is not the layer average of ``alpha(p)``.  Two columns partitioned
    differently by the tilt therefore accumulate slightly different masses.
    This is the O(htilde^2) effect design §3.7.4 invokes to argue for the floor
    anchor in the first place; at the floor it lands in the bottom pressure
    instead of in the derived sea-surface height.

    So the scheme is right to report this, and the assertion is against the
    offset the state implies rather than against zero.  The residual is
    ``alpha`` versus its edge-shared linearization over the interval, a few
    parts in 1e3.
    """
    ds = build_state(variant, 4.0, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)
    interface = anchor_index(pieces)

    if pieces['deepest'][0] != pieces['deepest'][1]:
        pytest.skip('prediction assumes both columns end at the same index')

    delta_z = (
        pieces['interface_height'][1, interface]
        - pieces['interface_height'][0, interface]
    )
    delta_p = (
        pieces['interface'][1, interface] - pieces['interface'][0, interface]
    )
    alpha = float(ds.SpecVol.isel(Time=0).values[:, interface - 1].mean())
    predicted = delta_z + alpha * delta_p / Gravity

    measured = anchor_difference(pieces)
    assert measured != 0.0
    np.testing.assert_allclose(measured, predicted, rtol=5.0e-3, atol=0.0)


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
    # Flat with depth: the anchor offsets the whole column and the scan adds
    # essentially nothing on top of it.  "Essentially nothing" is ~1e-3 of the
    # anchor, not round-off -- the two columns' p-star grids differ because
    # their surface pressures do, so there is a genuine small contrast for the
    # scan to integrate.  The bound is 5e-3 rather than the measured value
    # because that value moves with the quadrature: 2.1e-3, 1.1e-3, 1.4e-3 and
    # 9.8e-4 of the anchor at one through four points, since the integrand is
    # piecewise linear with breakpoints at the union of the two columns'
    # interfaces and no fixed rule resolves them.  A threshold pinned to any
    # one of those readings tests the quadrature rather than the scan.
    assert float(np.ptp(difference)) < 5.0e-3 * abs(anchor), (
        f'D_k varies by {float(np.ptp(difference)):.3e} m down the column, '
        f'{float(np.ptp(difference)) / abs(anchor):.1e} of the anchor, '
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


@pytest.mark.parametrize('horiz_res, vert_res, tilt', sweep(LINEAR_VARIANT))
def test_assembled_hpga_is_the_anchor_on_the_exact_set(
    horiz_res, vert_res, tilt
):
    """C2 / D4'': on the exact set the whole tendency is the anchor.

    Run across the whole tilt sweep at three vertical resolutions, because this
    is the measurement the entire exercise exists to make.

    **This asserted machine zero when the scan was anchored at the sea
    surface, and it no longer can.**  Anchored at the sea floor (design §3.7.4)
    the anchor is not zero on a Polaris-initialized state -- see
    :py:func:`test_anchor_carries_the_bottom_pressure_offset` -- so the
    tendency inherits it.  What survives, and is asserted here instead, is the
    sharper statement: the residual is the anchor *and nothing else*, to a part
    in 1e7 across the whole sweep, so every increment of the scan is still zero
    to round-off and the scheme's central property is intact.

    Read together with the flatness assertion on the scan, this localizes the
    residual completely: it enters at one interface, as one number, from the
    state rather than from the discretization.

    The scheme still beats ``PressureGradCentered`` on the same state by 21x to
    1049x over this sweep.  The floor of 15x is below the measured minimum
    rather than at it.
    """
    ds = build_state(LINEAR_VARIANT, horiz_res, vert_res, tilt)
    dx = 1.0e3 * horiz_res
    hpga = finite_volume_hpga(ds, dx)

    valid = np.isfinite(hpga.values)
    worst = float(np.max(np.abs(hpga.values[valid])))
    centered = float(np.abs(ds.HPGA).max())

    anchor = abs(anchor_difference(matched_pressure_pieces(ds)))
    np.testing.assert_allclose(
        worst, Gravity * anchor / dx, rtol=1.0e-6, atol=0.0
    )
    assert worst < centered / 15.0, (
        f'vert_res={vert_res} m, tilt={tilt} m/km: the scheme is only '
        f'{centered / worst:.1f} times better than centered'
    )


def test_exactness_survives_differing_max_level_cell():
    """D8': the below-floor extrapolation does not break exactness.

    At 50 m/km the two columns of ``hydrostatic_consistency_linear`` reach
    different ``maxLevelCell``, so the deepest edge layer evaluates one
    column's reconstruction below its own floor.  Exactness is unaffected,
    which is what design §3.5 consequence 3 predicts and what demotes A5 from
    an exactness risk to an accuracy question.

    "Unaffected" is asserted as *the scan stays flat*: the extrapolation feeds
    the integrand, and if it broke the cancellation the increments would stop
    being zero and ``D_k`` would drift with depth.  It is deliberately not
    asserted as a small tendency, which the sea-floor anchor's own offset
    would dominate and which would therefore not be testing the extrapolation
    at all.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    pieces = matched_pressure_pieces(ds)
    assert pieces['deepest'][0] != pieces['deepest'][1], (
        'this configuration no longer exercises differing maxLevelCell, so '
        'the test has stopped checking what it claims to'
    )

    difference = column_scan(pieces)
    assert float(np.ptp(difference)) <= _ROUNDOFF_TOL * hydrostatic_scale(ds)


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


def test_quadrature_points_comes_from_config():
    """The Gauss rule is the configured one, not a default in the kernel.

    ``quadrature_points`` fills in Omega's ``PressureGrad:QuadraturePoints``
    and the Python kernel's rule from one option, because
    ``omega_vs_polaris_rms_threshold`` only checks Omega's arithmetic if both
    sides integrate the same way.  Two sides quadrating differently are two
    algorithms, and their disagreement is not distinguishable from a bug in
    either.

    ``surface_pressure_gradient`` rather than the linear variant: on the exact
    set the integrand is zero at every point, so *every* rule gives the same
    answer and the test could not fail.
    """
    default = build_state('surface_pressure_gradient', 4.0, 4.0, None)
    two = build_state(
        'surface_pressure_gradient', 4.0, 4.0, None, quadrature_points=2
    )
    one = build_state(
        'surface_pressure_gradient', 4.0, 4.0, None, quadrature_points=1
    )

    # the shipped value is 2, matching Omega's Phase 1 default
    np.testing.assert_array_equal(
        default.HPGAFiniteVolume.values, two.HPGAFiniteVolume.values
    )

    # and a different rule gives a different answer, so the option is read
    # rather than ignored
    valid = np.isfinite(two.HPGAFiniteVolume.values[0])
    assert not np.allclose(
        one.HPGAFiniteVolume.values[0][valid],
        two.HPGAFiniteVolume.values[0][valid],
        rtol=1.0e-12,
        atol=0.0,
    ), (
        'one- and two-point quadrature give the same HPGAFiniteVolume, so '
        'quadrature_points is not reaching the kernel'
    )


@pytest.mark.parametrize(
    'guard, must_fire',
    [
        ('cell_local_expansion', True),
        ('state_by_index', False),
        ('anchor_delta_z_only', True),
    ],
)
def test_guards_on_the_exact_set(guard, must_fire):
    """Which deliberate mistakes break the scheme here, and which cannot.

    * ``cell_local_expansion`` **fires**, taking the tendency to 2.6e-5 m s-2,
      comparable to what the centered scheme gives on the same state.  Design
      §3.5 consequence 1 says the shared coefficients may take *any value*; it
      does not say the two columns may use *different* ones.  ``[dalpha]`` only
      collapses to a coefficient times a contrast when one set multiplies both
      columns, so the edge-shared expansion point of §3.3.1 remains
      load-bearing.
    * ``state_by_index`` cannot fire here: this variant's profile is a single
      line in pressure, so every layer's reconstruction is that same line and
      looking up the wrong layer costs nothing.
    * ``anchor_delta_z_only`` **fires**, at 3e5 times the correct answer.  This
      is a change: with the scan anchored at the sea surface it could not fire
      on this variant, because both columns shared a surface pressure and the
      correction it drops was zero.  Anchored at the sea floor, this tilt gives
      the columns different ``maxLevelCell``, so the anchor interface is one
      column's floor and the other's interior and the raw ``Delta_e Z`` there
      is 28 m against a corrected anchor of 8e-5 m.  The guard is therefore
      sharper than it was -- though note it is the *tilt* that gives it teeth:
      over a flat floor with matching ``maxLevelCell``, ``Delta_e Z`` is
      ~1e-13 m and dropping the correction would again cost almost nothing.

    Thresholds are ratios against the correct tendency, which on the exact set
    is now the anchor rather than machine zero, so a firing guard shows as
    1e2--1e5 rather than the 1e6+ a zero baseline used to give.  The absolute
    magnitudes the guards produce are unchanged.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, 256.0, 50.0)
    correct = finite_volume_hpga(ds, 4.0e3)
    perturbed = finite_volume_hpga(ds, 4.0e3, guards={guard})

    valid = np.isfinite(correct.values)
    baseline = float(np.max(np.abs(correct.values[valid])))
    result = float(np.max(np.abs(perturbed.values[valid])))

    if must_fire:
        assert result > 50.0 * baseline, (
            f'{guard} left the tendency at {result:.3e}, so it is not a guard'
        )
    else:
        assert result < 2.0 * baseline, (
            f'{guard} changed the tendency to {result:.3e}, which contradicts '
            'the reason given for why it cannot'
        )


@pytest.mark.parametrize('vert_res, tilt', [(256.0, 0.05), (256.0, 50.0)])
def test_anchor_at_surface_guard_is_sensitive(vert_res, tilt):
    """The retained surface anchor is a guard that actually moves the answer.

    Design §3.7.4 settles the anchor at the sea floor and §3.5.1's prose still
    says the surface, so the surface end is kept as a switch rather than
    deleted -- but a switch nobody checks is the "guard that cannot fire" this
    branch has already been caught by twice.

    On a Polaris-initialized state the two ends differ by the whole anchor: the
    initial condition pins the sea surface, so the surface anchor returns
    round-off, while the floor anchor reports the offset the state's bottom
    pressures imply.  Asserting the surface end is at round-off is what makes
    this a sharp check rather than a loose one -- and it is also the
    measurement behind the claim that the residual comes from the state and
    not from the scan.
    """
    ds = build_state(LINEAR_VARIANT, 4.0, vert_res, tilt)
    pieces = matched_pressure_pieces(ds)

    assert anchor_index(pieces) != 0
    assert anchor_index(pieces, guards={'anchor_at_surface'}) == 0

    at_floor = anchor_difference(pieces)
    at_surface = anchor_difference(pieces, guards={'anchor_at_surface'})

    assert abs(at_surface) <= _ROUNDOFF_TOL * hydrostatic_scale(ds), (
        f'the surface anchor is {at_surface:.3e} m, above round-off, so this '
        'state no longer pins the sea surface and the comparison below means '
        'something different'
    )
    assert abs(at_floor) > 1.0e-9, (
        f'the two anchors agree to {at_floor:.3e} m, so the guard is not '
        'sensitive on this configuration'
    )


def test_anchor_guard_fires_where_surface_pressures_differ():
    """``anchor_delta_z_only`` is a real guard, on the right configuration.

    Dropping the correction to a common pressure leaves the raw geometric
    height difference at the anchor interface, and the tendency comes out some
    thousands of times wrong.

    **The direction is inverted relative to a surface anchor**, which is worth
    stating because it looks like a broken guard otherwise.  At the sea surface
    the uncorrected difference was the raw 3.57 m sea-surface offset against a
    6.1e-4 m residual, so the guard inflated the answer.  At the sea floor the
    floor is flat, so the uncorrected difference is ~1e-13 m and the guard
    *discards* the entire 6.1e-4 m signal instead.  Either way the correction
    to a common pressure is the whole content of the anchor here; the assertion
    is therefore that the ratio is far from one, not that it is large.
    """
    ds = build_state('surface_pressure_gradient', 4.0, 4.0, None)
    correct = finite_volume_hpga(ds, 4.0e3)
    perturbed = finite_volume_hpga(ds, 4.0e3, guards={'anchor_delta_z_only'})

    valid = np.isfinite(correct.values)
    ratio = float(np.max(np.abs(perturbed.values[valid]))) / float(
        np.max(np.abs(correct.values[valid]))
    )
    assert ratio > 1.0e3 or ratio < 1.0e-3, (
        f'the anchor guard only changed things by {ratio:.3e}x'
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


@pytest.mark.parametrize('tilt', [1.0, 10.0])
def test_second_order_off_the_exact_set(tilt):
    """C3: the residual shrinks like h^2 under vertical refinement.

    Without this, C2 could pass for a scheme that returned zero for the wrong
    reason -- a scheme insensitive to the state would also be "exact".

    Measured order on ``hydrostatic_consistency``'s curved profile is 1.55 to
    2.02 across 256 -> 128 -> 64 m, consistent with the O(h^2) design §3.7.3
    gives Phase 1 for a generally smooth profile.

    Worth recording alongside: ``PressureGradCentered`` converges *faster* than
    this on the same profile (1.88 to 2.93), from a much larger starting value,
    so the finite-volume advantage narrows with refinement -- 6.5x at 256 m,
    2.4x at 64 m.  The orders-of-magnitude win is on the exact set, not here.
    That anomaly in the centered scheme's order is the one noted in the
    findings document and is not yet explained.
    """
    errors = []
    for vert_res in [256.0, 128.0, 64.0]:
        ds = build_state('hydrostatic_consistency', 4.0, vert_res, tilt)
        hpga = finite_volume_hpga(ds, 4.0e3)
        valid = np.isfinite(hpga.values)
        errors.append(float(np.sqrt(np.mean(hpga.values[valid] ** 2))))

    for coarse, fine in zip(errors[:-1], errors[1:], strict=True):
        order = np.log2(coarse / fine)
        assert 1.4 < order < 2.6, (
            f'tilt={tilt} m/km: observed order {order:.2f}, outside the range '
            'a second-order scheme should show'
        )
