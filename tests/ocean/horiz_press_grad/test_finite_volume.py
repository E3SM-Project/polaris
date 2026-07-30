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

from polaris.ocean.vertical.ztilde import Gravity
from polaris.tasks.ocean.horiz_press_grad.column import (
    get_array_from_mid_grad,
)
from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    centered_shift,
    hpga_from_shift,
    hydrostatic_scale,
)

from .two_column import (
    GRADIENT_VARIANTS,
    LINEAR_VARIANT,
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


@pytest.mark.parametrize('horiz_res, vert_res, tilt', sweep(LINEAR_VARIANT))
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


@pytest.mark.parametrize(
    'variant, horiz_res, vert_res, tilt',
    [(variant, *point) for variant in VARIANTS for point in sweep(variant)]
    + [
        (variant, *pair, None)
        for variant in GRADIENT_VARIANTS
        for pair in resolution_pairs(variant)
    ],
)
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
