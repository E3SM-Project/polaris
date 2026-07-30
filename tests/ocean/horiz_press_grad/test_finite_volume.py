"""
Unit tests for the ``FiniteVolume`` HPGA of the two-column ``horiz_press_grad``
configurations.

All tests are self-contained: no file I/O, no mesh generation and no Omega
build.  Each builds the same two-column state
:py:class:`~polaris.tasks.ocean.horiz_press_grad.init.Init` writes to
``init.nc``, from the packaged config of a resting-state variant, and compares
the new code against the ``HPGA`` field that step already produces.
"""

import logging

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.ztilde import Gravity
from polaris.tasks.ocean.horiz_press_grad.finite_volume import (
    centered_shift,
    hpga_from_shift,
    hydrostatic_scale,
)
from polaris.tasks.ocean.horiz_press_grad.init import Init

_HPG_PKG = 'polaris.tasks.ocean.horiz_press_grad'

# The resting-state variants and their sweeps.  These are the configurations
# whose true HPGA is identically zero, so whatever the centered scheme returns
# there is error, and they are the only ones that sweep a tilt.
_VARIANTS = ['hydrostatic_consistency', 'bathymetry_step']

# The four gradient variants, which sweep resolution rather than tilt.  They
# add nothing to the algebra but a good deal to the states it is checked on:
# temperature and salinity contrasts across the edge, pseudo-height nodes that
# move with x, and -- in surface_pressure_gradient -- a different surface
# pressure in the two columns, so that Delta_e q is nonzero at the top
# interface and not only in the interior.
_GRADIENT_VARIANTS = [
    'temperature_gradient',
    'salinity_gradient',
    'ztilde_gradient',
    'surface_pressure_gradient',
]

# Machine-precision tolerance, as a multiple of the hydrostatic scale rather
# than as an absolute number (``PGradHighOrder.md`` §3.7.5).  The largest
# discrepancy measured over every state below is 0.5 * eps of that scale, so
# this leaves a factor of ~90.  It is still far from vacuous: the closest
# plausible mis-derivation tried -- a cell-local rather than an edge-averaged
# specific volume -- misses by 700 times this tolerance at the smallest tilt in
# the sweep, and dropping the pressure term misses by 1e9 times it.
_ROUNDOFF_TOL = 1.0e-14

# Built states are reused across tests, at roughly 0.25 s each.
_STATE_CACHE: dict[tuple[str, float, float, float | None], xr.Dataset] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(variant: str) -> PolarisConfigParser:
    """Load the packaged config for one resting-state variant."""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(_HPG_PKG, 'horiz_press_grad.cfg')
    config.add_from_package(_HPG_PKG, f'{variant}.cfg')
    return config


def _sweep(variant: str) -> list[tuple[float, float, float]]:
    """The ``(horiz_res, vert_res, tilt)`` points of a variant's sweep."""
    section = _make_config(variant)['horiz_press_grad']
    horiz_resolutions = section.getexpression('horiz_resolutions')
    vert_resolutions = section.getexpression('vert_resolutions')
    tilt_values = section.getexpression('tilt_values')
    return [
        (float(horiz_res), float(vert_res), float(tilt))
        for horiz_res, vert_res in zip(
            horiz_resolutions, vert_resolutions, strict=True
        )
        for tilt in tilt_values
    ]


def _resolution_pairs(variant: str) -> list[tuple[float, float]]:
    """The coarsest and finest ``(horiz_res, vert_res)`` pairs of a sweep."""
    section = _make_config(variant)['horiz_press_grad']
    pairs = [
        (float(horiz_res), float(vert_res))
        for horiz_res, vert_res in zip(
            section.getexpression('horiz_resolutions'),
            section.getexpression('vert_resolutions'),
            strict=True,
        )
    ]
    return [pairs[0], pairs[-1]]


def _build_state(
    variant: str, horiz_res: float, vert_res: float, tilt: float | None
) -> xr.Dataset:
    """
    Build (or return a cached) two-column state for one sweep point.

    ``tilt`` is the value of the variant's ``tilt_option``, or ``None`` for the
    gradient variants, which override no option -- exactly as
    :py:class:`~polaris.tasks.ocean.horiz_press_grad.task.HorizPressGradTask`
    constructs the step.

    The Polaris ``Step`` constructor is bypassed, as in
    ``tests/ocean/vertical/test_pstar_init.py``, so that no component, work
    directory or config file is needed.
    """
    key = (variant, horiz_res, vert_res, tilt)
    if key in _STATE_CACHE:
        return _STATE_CACHE[key]

    config = _make_config(variant)
    step = object.__new__(Init)
    step.config = config
    step.logger = logging.getLogger('test_finite_volume')
    step.horiz_res = horiz_res
    step.vert_res = vert_res
    if tilt is None:
        step.tilt_option = None
    else:
        step.tilt_option = config.get('horiz_press_grad', 'tilt_option')
    step.tilt = tilt
    step.x = np.array([])

    ds_mesh = xr.Dataset({'xCell': xr.DataArray(np.zeros(2), dims=['nCells'])})
    ds = step.build_column_state(ds_mesh)

    _STATE_CACHE[key] = ds
    return ds


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
    'variant, horiz_res, vert_res, tilt',
    [(variant, *point) for variant in _VARIANTS for point in _sweep(variant)],
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
    ds = _build_state(variant, horiz_res, vert_res, tilt)
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
        for variant in _GRADIENT_VARIANTS
        for pair in _resolution_pairs(variant)
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
    ds = _build_state(variant, horiz_res, vert_res, None)
    hpga, reference, tol = _valid_hpga(ds, horiz_res)

    max_diff = float(np.max(np.abs(hpga - reference)))
    assert max_diff <= tol, (
        f'{variant} at horiz_res={horiz_res} km, vert_res={vert_res} m: '
        f'max |S-derived HPGA - Init HPGA| = {max_diff:.3e} m s-2 exceeds '
        f'{tol:.3e} m s-2'
    )


@pytest.mark.parametrize('variant', _VARIANTS)
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
    config = _make_config(variant)
    section = config['horiz_press_grad']
    horiz_res = float(section.getexpression('horiz_resolutions')[0])
    vert_res = float(section.getexpression('vert_resolutions')[0])
    tilts = [float(tilt) for tilt in section.getexpression('tilt_values')]
    tilt_fit = section.getboolean('tilt_fit')
    tilt_fit_max = section.getfloat('tilt_fit_max')

    rms = []
    for tilt in tilts:
        ds = _build_state(variant, horiz_res, vert_res, tilt)
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
