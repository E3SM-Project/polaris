"""
Unit tests for the ``FiniteVolume`` HPGA of the two-column ``horiz_press_grad``
configurations.

All tests are self-contained: no file I/O, no mesh generation and no Omega
build.  Each builds the same two-column state
:py:class:`~polaris.tasks.ocean.horiz_press_grad.init.Init` writes to
``init.nc``, from the packaged config of one of the task's variants, and
compares the new code against the ``HPGA`` field that step already produces.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical.ztilde import Gravity, RhoSw
from polaris.tasks.ocean.horiz_press_grad.column import (
    get_array_from_mid_grad,
)
from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    centered_shift,
    centered_shift_accumulated,
    hpga_from_shift,
    hydrostatic_scale,
    shift_increments,
)

from .two_column import (
    GRADIENT_VARIANTS,
    LINEAR_VARIANT,
    REPRESENTATIVE,
    VARIANTS,
    build_state,
    make_config,
    resolution_pairs,
    sweep,
)

# Machine-precision tolerance, as a multiple of the hydrostatic scale rather
# than as an absolute number (``PGradHighOrder.md`` §3.7.5).  The largest
# discrepancy measured over every state below is 0.5 * eps of that scale, so
# this leaves a factor of ~90.  It is still far from vacuous: the closest
# plausible mis-derivation tried -- a cell-local rather than an edge-averaged
# specific volume -- misses by 700 times this tolerance at the smallest tilt in
# the sweep, and dropping the pressure term misses by 1e9 times it.
_ROUNDOFF_TOL = 1.0e-14

# Tolerance for "exactly linear in pressure", relative to the magnitude of the
# field.  The largest departure measured over the linear variant's sweep is
# 2.3 * eps, so this leaves a factor of ~200; a genuinely curved profile like
# hydrostatic_consistency's departs by ~3e-3 of its salinity, ten orders of
# magnitude above this.
_LINEARITY_TOL = 1.0e-13

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_hpga(
    ds: xr.Dataset, horiz_res: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Return the HPGA from ``centered_shift``, the HPGA the ``Init`` step wrote,
    and the round-off tolerance, over the layers valid in both columns.

    """
    dx = 1e3 * horiz_res
    hpga = hpga_from_shift(centered_shift(ds), dx)
    reference = ds.HPGA
    valid = np.logical_and(np.isfinite(hpga), np.isfinite(reference))
    assert int(valid.sum()) > 0, 'no layer is valid in both columns'
    tol = _ROUNDOFF_TOL * (Gravity / dx) * hydrostatic_scale(ds)
    return hpga.values[valid.values], reference.values[valid.values], tol


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'horiz_res, vert_res, tilt',
    [point[1:] for point in REPRESENTATIVE if point[0] == LINEAR_VARIANT],
)
def test_linear_variant_is_in_the_exact_set(horiz_res, vert_res, tilt):
    """``hydrostatic_consistency_linear`` puts the state in the exact set.

    Two conditions have to hold, and they are different claims:

    1. In each column, the layer-mean temperature and salinity are exactly
       linear functions of the layer-mean pressure.  This is what a linear
       mean-preserving reconstruction can reproduce exactly, and it is what
       makes ``PGradHighOrder.md`` §3.7.3's "linear in pressure" row apply.
    2. The two columns give the *same* line.  This is the condition that
       actually matters (§3.7.2, condition 1): the two columns must describe
       one water column as a function of pressure, however differently their
       layers are distributed.  It holds here even at large tilt, where the
       two columns' layer means differ substantially, because the map from
       pressure to state is universal.

    Without this test the exactness measurement in a later commit could be run
    on a configuration that cannot show exactness -- which is finding F-P1, and
    is the case for the curved ``hydrostatic_consistency`` variant.

    """
    ds = build_state(LINEAR_VARIANT, horiz_res, vert_res, tilt)

    for field in ['temperature', 'salinity']:
        # tolerances are relative to the size of the values being differenced,
        # not to the profile's range, since that is what sets the round-off
        lines = []
        ranges = []
        magnitude = float(np.abs(ds[field]).max())
        tol = _LINEARITY_TOL * magnitude

        for icell in range(ds.sizes['nCells']):
            pressure = ds.pressure.isel(Time=0, nCells=icell).values
            values = ds[field].isel(Time=0, nCells=icell).values
            valid = np.logical_and(np.isfinite(pressure), np.isfinite(values))
            pressure = pressure[valid]
            values = values[valid]
            assert len(pressure) >= 3

            # the line through the shallowest and deepest valid layers
            slope = (values[-1] - values[0]) / (pressure[-1] - pressure[0])

            def line(at, values=values, pressure=pressure, slope=slope):
                return values[0] + slope * (at - pressure[0])

            residual = float(np.max(np.abs(values - line(pressure))))
            assert residual <= tol, (
                f'{field} in column {icell} at vert_res={vert_res} m, '
                f'tilt={tilt} m/km departs from a line in pressure by '
                f'{residual:.3e}, more than {tol:.3e}'
            )
            lines.append(line)
            ranges.append((pressure[0], pressure[-1]))

        # The two columns must describe the same function of pressure.  Compare
        # the two lines over the pressures both columns span, rather than
        # comparing slopes and intercepts, so the check is in the units of the
        # field and does not amplify by an extrapolation distance.
        low = max(ranges[0][0], ranges[1][0])
        high = min(ranges[0][1], ranges[1][1])
        probe = np.array([low, 0.5 * (low + high), high])
        disagreement = float(np.max(np.abs(lines[0](probe) - lines[1](probe))))
        assert disagreement <= tol, (
            f'{field} at vert_res={vert_res} m, tilt={tilt} m/km: the two '
            f'columns describe functions of pressure differing by '
            f'{disagreement:.3e}, more than {tol:.3e}'
        )


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt',
    [(variant, *point) for variant in VARIANTS for point in sweep(variant)],
)
def test_centered_shift_reproduces_centered_hpga(
    variant, horiz_res, vert_res, tilt
):
    """``-(g / d_e) * S`` is the centered HPGA, at every point in the sweep.

    This is the design's ``[centered-shift]`` identity: the centered scheme's
    Montgomery-potential apparatus is nothing but the first-order conversion
    from a height difference at fixed layer index to one at fixed pressure.
    The whole of the decomposition ``T^p = -(g/d_e)(S + R)`` rests on it, so it
    is checked against the answer ``Init`` already produces -- including that
    step's convention that the mid-layer Montgomery potential is the mean of
    the two interface values, which is what makes the identity hold.

    Run at every tilt because the identity is claimed to be exact at any tilt;
    a single-tilt check could pass by coincidence.

    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    hpga, reference, tol = _valid_hpga(ds, horiz_res)

    max_diff = float(np.max(np.abs(hpga - reference)))
    assert max_diff <= tol, (
        f'{variant} at horiz_res={horiz_res} km, vert_res={vert_res} m, '
        f'tilt={tilt} m/km: max |S-derived HPGA - Init HPGA| = '
        f'{max_diff:.3e} m s-2 exceeds {tol:.3e} m s-2'
    )


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res',
    [
        (variant, *pair)
        for variant in GRADIENT_VARIANTS
        for pair in resolution_pairs(variant)
    ],
)
def test_centered_shift_with_horizontal_structure(
    variant, horiz_res, vert_res
):
    """The same identity on the four gradient variants.

    The resting-state configurations are horizontally uniform in temperature
    and salinity, and their surface pressure is the same in both columns, so
    ``Delta_e q`` vanishes at the top interface there.  These configurations
    put horizontal structure in the state instead, and
    ``surface_pressure_gradient`` differs in surface pressure across the edge.
    The identity is algebraic and should not care, which is the point of
    checking.

    """
    ds = build_state(variant, horiz_res, vert_res, None)
    hpga, reference, tol = _valid_hpga(ds, horiz_res)

    max_diff = float(np.max(np.abs(hpga - reference)))
    assert max_diff <= tol, (
        f'{variant} at horiz_res={horiz_res} km, vert_res={vert_res} m: '
        f'max |S-derived HPGA - Init HPGA| = {max_diff:.3e} m s-2 exceeds '
        f'{tol:.3e} m s-2'
    )


@pytest.mark.parametrize('variant, horiz_res, vert_res, tilt', REPRESENTATIVE)
def test_state_is_valid_exactly_where_the_column_is(
    variant, horiz_res, vert_res, tilt
):
    """Temperature and salinity are finite in every valid layer and no others.

    The layer means are taken over each layer's two interfaces, and in every
    configuration the outermost interfaces sit on the outermost profile nodes
    up to round-off -- the column is summed upward from the sea floor, so
    whether the top interface lands just inside or just outside its node is the
    sign of a round-off error.  Landing outside yields a NaN there, which then
    feeds back through the p-star iteration and corrupts the whole column.  The
    corruption is silent: the HPGA identity above still holds on a corrupted
    state, since both sides are computed from it, and the masked comparison
    simply skips the NaN.  Measured with the clipping in
    ``get_pchip_layer_mean`` removed, this test fires on
    ``temperature_gradient`` while every other test in this file still passes.

    """
    ds = build_state(variant, horiz_res, vert_res, tilt)

    level = xr.DataArray(
        np.arange(ds.sizes['nVertLevels']), dims=['nVertLevels']
    )
    # minLevelCell and maxLevelCell are 1-based
    expected = np.logical_and(
        level >= ds.minLevelCell - 1, level <= ds.maxLevelCell - 1
    )

    for field in ['temperature', 'salinity', 'SpecVol']:
        finite = np.isfinite(ds[field].isel(Time=0))
        assert bool((finite == expected).all()), (
            f'{variant} at horiz_res={horiz_res} km, vert_res={vert_res} m, '
            f'tilt={tilt}: {field} is finite in '
            f'{int(finite.sum())} layers but the columns span '
            f'{int(expected.sum())}'
        )

    # a mean of a monotone profile cannot leave the range of its own nodes
    config = make_config(variant)
    x = horiz_res * np.array([-0.5, 0.5])
    for field in ['temperature', 'salinity']:
        nodes = get_array_from_mid_grad(config, field, x)
        values = ds[field].isel(Time=0).values
        for icell in range(ds.sizes['nCells']):
            column = values[icell, :]
            column = column[np.isfinite(column)]
            assert column.min() >= nodes[icell, :].min() - 1e-10
            assert column.max() <= nodes[icell, :].max() + 1e-10


@pytest.mark.parametrize('variant', VARIANTS)
def test_centered_shift_grows_with_tilt(variant):
    """``S`` is not identically zero and grows with tilt.

    Guard (a) of ``PGradHighOrder.md`` §5.2, and the check that the identity
    above has content: a scheme that returned zero, or that had become
    insensitive to tilt, would satisfy the identity trivially.

    Strict monotonicity is asserted only up to ``tilt_fit_max``, beyond which
    the two columns' ``maxLevelCell`` values start to differ and the config
    itself declares the response a staircase rather than a power law.  Across
    the whole sweep only overall growth is required.

    """
    config = make_config(variant)
    section = config['horiz_press_grad']
    horiz_res = float(section.getexpression('horiz_resolutions')[0])
    vert_res = float(section.getexpression('vert_resolutions')[0])
    tilts = [float(tilt) for tilt in section.getexpression('tilt_values')]
    tilt_fit = section.getboolean('tilt_fit')
    tilt_fit_max = section.getfloat('tilt_fit_max')

    rms = []
    for tilt in tilts:
        ds = build_state(variant, horiz_res, vert_res, tilt)
        hpga, _, _ = _valid_hpga(ds, horiz_res)
        rms.append(float(np.sqrt(np.mean(hpga**2))))

    for tilt, value in zip(tilts, rms, strict=True):
        assert value > 0.0, (
            f'{variant}: RMS HPGA from S is zero at tilt={tilt} m/km'
        )

    assert rms[-1] > rms[0], (
        f'{variant}: RMS HPGA from S does not grow across the tilt sweep, '
        f'{rms[0]:.3e} at tilt={tilts[0]} to {rms[-1]:.3e} at '
        f'tilt={tilts[-1]} m/km'
    )

    if not tilt_fit:
        return

    fit_range = [
        (tilt, value)
        for tilt, value in zip(tilts, rms, strict=True)
        if tilt <= tilt_fit_max
    ]
    for (tilt, value), (next_tilt, next_value) in zip(
        fit_range[:-1], fit_range[1:], strict=True
    ):
        assert next_value > value, (
            f'{variant}: RMS HPGA from S does not increase from '
            f'tilt={tilt} ({value:.3e}) to tilt={next_tilt} '
            f'({next_value:.3e} m s-2)'
        )


# ---------------------------------------------------------------------------
# 9d: the cancellation-free accumulation
# ---------------------------------------------------------------------------

# A representative handful of states rather than the full sweeps: the identity
# these check is state-independent, and the sweeps are already covered above.
_ACCUMULATION_CASES = [
    ('hydrostatic_consistency', 4.0, 256.0, 50.0),
    ('hydrostatic_consistency', 4.0, 64.0, 50.0),
    ('hydrostatic_consistency_linear', 4.0, 256.0, 0.05),
    ('bathymetry_step', 4.0, 128.0, 200.0),
    ('temperature_gradient', 4.0, 4.0, None),
]


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt', _ACCUMULATION_CASES
)
def test_accumulated_shift_matches_the_direct_form(
    variant, horiz_res, vert_res, tilt
):
    """``[gamma-increments]`` reproduces ``[centered-shift]`` to round-off.

    The two evaluate the same quantity in a different order, so §3.9's
    reduction to the centered scheme becomes algebraic rather than bit-for-bit
    -- the trade §3.5.1 accepts in exchange for never forming the two large
    terms.
    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    direct = centered_shift(ds)
    accumulated = centered_shift_accumulated(ds)

    valid = np.logical_and(np.isfinite(direct), np.isfinite(accumulated))
    difference = float(
        np.max(np.abs((direct - accumulated).values[valid.values]))
    )
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert difference <= tolerance, (
        f'{variant} at vert_res={vert_res} m, tilt={tilt}: accumulated and '
        f'direct forms of S differ by {difference:.3e} m, more than '
        f'{tolerance:.3e} m'
    )


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt', _ACCUMULATION_CASES
)
def test_both_anchors_agree(variant, horiz_res, vert_res, tilt):
    """Accumulating from the surface or from the bathymetry gives the same S.

    §3.7.4 leaves the choice of end open, calling it a round-off question
    rather than a consistency one.  This settles it by measurement for double
    precision: the two agree to round-off, so the choice is free here.
    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    from_surface = centered_shift_accumulated(ds, anchor='surface')
    from_bathymetry = centered_shift_accumulated(ds, anchor='bathymetry')

    valid = np.logical_and(
        np.isfinite(from_surface), np.isfinite(from_bathymetry)
    )
    difference = float(
        np.max(np.abs((from_surface - from_bathymetry).values[valid.values]))
    )
    tolerance = _ROUNDOFF_TOL * hydrostatic_scale(ds)
    assert difference <= tolerance, (
        f'{variant} at vert_res={vert_res} m, tilt={tilt}: the two anchors '
        f'differ by {difference:.3e} m, more than {tolerance:.3e} m'
    )


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt', _ACCUMULATION_CASES
)
def test_increments_are_small_against_the_terms_they_replace(
    variant, horiz_res, vert_res, tilt
):
    """Deliverable D7: how much precision the accumulation actually saves.

    ``[centered-shift]`` differences ``Delta_e Z`` directly, which reaches 160
    m
    at 50 m/km of tilt.  The increments of ``[gamma-increments]`` are products
    of a small factor with a bounded one, so they are far smaller, and the
    ratio is the quantitative form of "no large-number cancellation occurs".

    Measured: 1.1e-3 on ``hydrostatic_consistency`` at 256 m layers and 50
    m/km, 2.7e-4 at 64 m, 2.0e-4 on ``bathymetry_step`` -- roughly three
    decimal digits of headroom recovered, against the five §3.7.5 estimates are
    consumed in
    ``[centered-shift]``.  The gradient variants sit near 7e-2 because their
    coordinate is flat, so ``Delta_e Z`` is only 0.18 m to begin with and there
    is little to save; the bound below is loose enough to cover both regimes.

    """
    ds = build_state(variant, horiz_res, vert_res, tilt)
    increments = shift_increments(ds)

    largest = max(
        float(np.abs(increments.within_layer).max()),
        float(np.abs(increments.between_layers).max()),
    )
    replaced = float(np.abs(increments.delta_z_interface).max())
    assert largest < 0.2 * replaced, (
        f'{variant} at vert_res={vert_res} m, tilt={tilt}: largest increment '
        f'{largest:.3e} m against max |Delta_e Z| {replaced:.3e} m'
    )


def _redistribution_state(equal_totals: bool) -> tuple[xr.Dataset, dict]:
    """A synthetic state in the limit ``[centered-error]`` is written for.

    Specific volume horizontally uniform within each layer, equal surface
    pressure and equal surface height, so ``Gamma_0 = 0``.  ``equal_totals``
    selects whether the coordinate merely *redistributes* thickness between the
    columns (``sum_j Delta_e htilde_j = 0``) or also changes the total, which
    is what a ``z_tilde_bot`` tilt does.
    """
    alpha = np.array([9.60e-4, 9.65e-4, 9.72e-4, 9.78e-4, 9.83e-4, 9.90e-4])
    thickness_0 = np.array([200.0, 260.0, 300.0, 340.0, 380.0, 420.0])
    if equal_totals:
        offset = np.array([30.0, -10.0, 20.0, -25.0, -40.0, 25.0])
    else:
        offset = np.array([30.0, -10.0, 20.0, -25.0, -40.0, 60.0])
    thickness_1 = thickness_0 + offset

    thickness = np.stack([thickness_0, thickness_1])
    q = np.zeros((2, len(alpha) + 1))
    z = np.zeros((2, len(alpha) + 1))
    for icell in range(2):
        for level in range(len(alpha)):
            q[icell, level + 1] = (
                q[icell, level] + RhoSw * Gravity * thickness[icell, level]
            )
            z[icell, level + 1] = (
                z[icell, level]
                - RhoSw * alpha[level] * thickness[icell, level]
            )

    ds = xr.Dataset(
        {
            'GeomZInterface': xr.DataArray(
                z[np.newaxis, ...], dims=['Time', 'nCells', 'nVertLevelsP1']
            ),
            'ZTildeInterface': xr.DataArray(
                -q[np.newaxis, ...] / (RhoSw * Gravity),
                dims=['Time', 'nCells', 'nVertLevelsP1'],
            ),
            'SpecVol': xr.DataArray(
                np.broadcast_to(alpha, (1, 2, len(alpha))).copy(),
                dims=['Time', 'nCells', 'nVertLevels'],
            ),
            'PseudoThickness': xr.DataArray(
                thickness[np.newaxis, ...],
                dims=['Time', 'nCells', 'nVertLevels'],
            ),
        }
    )
    return ds, {'alpha': alpha, 'delta_thickness': offset}


@pytest.mark.parametrize('equal_totals', [True, False])
def test_centered_error_reconciliation(equal_totals):
    """Reconcile ``[gamma-increments]`` against ``[centered-error]`` (§3.5.1).

    In the limit ``[centered-error]`` is written for -- specific volume
    horizontally uniform within each layer -- summation by parts gives

        S_k = rho0 sum_{j>k} (alpha_j - alpha_k) d_j
              + C + rho0 * alpha_k * sum_j d_j
        C   = Gamma_0 - rho0 sum_j d_j alpha_j

    with ``d_j = Delta_e htilde_j``.  The constant ``C`` is identified
    explicitly rather than fitted, and it is set by the anchor.

    The sharper half, which is why the plan asks for the check *without*
    assuming
    ``sum_j d_j = 0``: the two expressions agree up to a k-independent constant
    **only** when the two columns have the same total pseudo-thickness.
    Otherwise the extra ``rho0 alpha_k sum_j d_j`` depends on k through
    ``alpha_k`` and cannot be absorbed into an anchor.  That case is the normal
    one here -- a ``z_tilde_bot`` tilt gives the two columns different
    pseudo-bottom depths -- so the design's expectation holds only in the
    redistribution limit its own text assumes.

    """
    ds, parts = _redistribution_state(equal_totals)
    alpha = parts['alpha']
    delta_thickness = parts['delta_thickness']

    shift = centered_shift_accumulated(ds).values[0, :]

    layers = len(alpha)
    centered_error = np.array(
        [
            RhoSw
            * np.sum(
                (alpha[level + 1 :] - alpha[level])
                * delta_thickness[level + 1 :]
            )
            for level in range(layers)
        ]
    )
    # Gamma_0 is zero by construction: equal surface pressure and height
    constant = -RhoSw * np.sum(delta_thickness * alpha)
    extra = RhoSw * alpha * np.sum(delta_thickness)

    # atol because the shallowest layer's value is an exact zero here, which a
    # relative tolerance cannot express; the terms being summed are ~4e2, so
    # 1e-12 m is about ten times their round-off
    np.testing.assert_allclose(
        shift, centered_error + constant + extra, rtol=1e-12, atol=1e-12
    )

    residual = shift - centered_error
    if equal_totals:
        assert np.allclose(np.sum(delta_thickness), 0.0, atol=1e-12)
        # k-independent: the residual is the anchor constant and nothing else
        np.testing.assert_allclose(residual, constant, rtol=1e-12, atol=1e-12)
    else:
        assert abs(np.sum(delta_thickness)) > 1.0
        # not k-independent, and demonstrably so
        assert np.ptp(residual) > 1.0e-3 * abs(constant)
        np.testing.assert_allclose(
            residual, constant + extra, rtol=1e-12, atol=1e-12
        )
