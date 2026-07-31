"""
Shared fixtures for the two-column ``horiz_press_grad`` tests.

Builds the same state
:py:class:`~polaris.tasks.ocean.horiz_press_grad.init.Init` writes to
``init.nc``, from the packaged config of one of the task's variants, with no
mesh generation and no file I/O.  Several test modules need these states, so
they live here rather than in whichever module wanted them first.
"""

import logging

import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.horiz_press_grad.init import Init

__all__ = [
    'REPRESENTATIVE',
    'VARIANTS',
    'LINEAR_VARIANT',
    'GRADIENT_VARIANTS',
    'make_config',
    'sweep',
    'resolution_pairs',
    'build_state',
]

_HPG_PKG = 'polaris.tasks.ocean.horiz_press_grad'

# The resting-state variants and their sweeps.  These are the configurations
# whose true HPGA is identically zero, so whatever the centered scheme returns
# there is error, and they are the only ones that sweep a tilt.
VARIANTS = [
    'hydrostatic_consistency',
    'hydrostatic_consistency_linear',
    'bathymetry_step',
]

# The one variant whose profile is linear in pressure, and so the only one in
# the finite-volume scheme's exact set.
LINEAR_VARIANT = 'hydrostatic_consistency_linear'

# The four gradient variants, which sweep resolution rather than tilt.  They
# add nothing to the algebra but a good deal to the states it is checked on:
# temperature and salinity contrasts across the edge, pseudo-height nodes that
# move with x, and -- in surface_pressure_gradient -- a different surface
# pressure in the two columns, so that Delta_e q is nonzero at the top
# interface and not only in the interior.
GRADIENT_VARIANTS = [
    'temperature_gradient',
    'salinity_gradient',
    'ztilde_gradient',
    'surface_pressure_gradient',
]

# Built states are reused across tests, at roughly 0.25 s each.
_STATE_CACHE: dict[tuple[str, float, float, float | None], xr.Dataset] = {}


# A representative subset of the sweeps, for tests whose point is not "at every
# tilt".  The full sweeps are kept only for the S identity, which is the
# cheapest test and the one whose whole claim is that it holds everywhere.
# Trimming this rather than the number of test functions is what keeps the
# collected count reasonable: the functions are few, the parametrization was
# what grew.
REPRESENTATIVE = [
    ('hydrostatic_consistency', 4.0, 256.0, 0.05),
    ('hydrostatic_consistency', 4.0, 64.0, 50.0),
    ('hydrostatic_consistency_linear', 4.0, 256.0, 0.05),
    ('hydrostatic_consistency_linear', 4.0, 256.0, 50.0),
    ('hydrostatic_consistency_linear', 4.0, 64.0, 50.0),
    ('bathymetry_step', 4.0, 256.0, 1.0),
    ('bathymetry_step', 4.0, 128.0, 200.0),
    ('temperature_gradient', 4.0, 4.0, None),
    ('surface_pressure_gradient', 4.0, 4.0, None),
    ('ztilde_gradient', 0.5, 0.5, None),
]


def make_config(variant: str) -> PolarisConfigParser:
    """Load the packaged config for one variant of the task."""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package(_HPG_PKG, 'horiz_press_grad.cfg')
    config.add_from_package(_HPG_PKG, f'{variant}.cfg')
    return config


def sweep(variant: str) -> list[tuple[float, float, float]]:
    """The ``(horiz_res, vert_res, tilt)`` points of a variant's sweep."""
    section = make_config(variant)['horiz_press_grad']
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


def resolution_pairs(variant: str) -> list[tuple[float, float]]:
    """The coarsest and finest ``(horiz_res, vert_res)`` pairs of a sweep."""
    section = make_config(variant)['horiz_press_grad']
    pairs = [
        (float(horiz_res), float(vert_res))
        for horiz_res, vert_res in zip(
            section.getexpression('horiz_resolutions'),
            section.getexpression('vert_resolutions'),
            strict=True,
        )
    ]
    return [pairs[0], pairs[-1]]


def build_state(
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

    config = make_config(variant)
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
