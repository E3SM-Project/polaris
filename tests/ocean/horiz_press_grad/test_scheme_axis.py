"""
The pressure-gradient scheme axis: that each variant builds one forward step
per scheme over one shared init step, that the ``forward.yaml`` template
renders what Omega expects, and that each scheme is paired with the right
Polaris-side field.

These are cheap structural checks, but they cover the wiring that no numerical
test can reach: the numerical tests build states directly and never construct a
task, so a scheme axis that silently collapsed to one scheme, or paired
``finite_volume`` with the centered ``HPGA``, would leave every one of them
passing.
"""

import importlib.resources as imp_res

import numpy as np
import pytest
import yaml
from jinja2 import Template

from polaris.component import Component
from polaris.tasks.ocean.horiz_press_grad.forward import SCHEME_HPGA, SCHEMES
from polaris.tasks.ocean.horiz_press_grad.metrics import rms
from polaris.tasks.ocean.horiz_press_grad.resting_state_task import (
    HorizPressGradRestingStateTask,
)
from polaris.tasks.ocean.horiz_press_grad.task import HorizPressGradTask

from .two_column import (
    GRADIENT_VARIANTS,
    VARIANTS,
    build_state,
    make_config,
)

_HPG_PKG = 'polaris.tasks.ocean.horiz_press_grad'


def _task(name):
    """Build one variant's task against a throwaway component.

    Deliberately not via ``polaris.tasks.get_components()``: that builds every
    component in the repository, and the e3sm/init tests clear the shared
    component objects those tasks are registered on, so a later call from
    inside the test suite raises.  Constructing the one task under test needs
    none of that and cannot be perturbed by it.
    """
    component = Component(name='ocean')
    if name in VARIANTS:
        return HorizPressGradRestingStateTask(component=component, name=name)
    return HorizPressGradTask(component=component, name=name)


def test_schemes_and_their_polaris_fields_line_up():
    """Every scheme maps to an Omega name and to a Polaris counterpart.

    The pairing in ``SCHEME_HPGA`` is what stops the analysis comparing Omega's
    finite-volume output against the centered ``HPGA``, which would measure the
    difference between two schemes and report it as an implementation
    disagreement.
    """
    assert set(SCHEMES) == set(SCHEME_HPGA)
    assert SCHEMES['centered'] == 'Centered'
    assert SCHEMES['finite_volume'] == 'FiniteVolume'
    assert SCHEME_HPGA['centered'] == 'HPGA'
    assert SCHEME_HPGA['finite_volume'] == 'HPGAFiniteVolume'


@pytest.mark.parametrize('variant', GRADIENT_VARIANTS + VARIANTS)
def test_one_forward_step_per_scheme_over_a_shared_init(variant):
    """The scheme axis multiplies forward steps and not init steps.

    Init is scheme-independent -- it writes both schemes' Polaris-side HPGA
    from the same state -- so sharing it is what lets the analysis compare the
    two schemes at an identical initial condition rather than at two states
    that merely ought to match.
    """
    task = _task(variant)
    schemes = make_config(variant)['horiz_press_grad'].getexpression(
        'pressure_grad_types'
    )
    assert len(schemes) > 1, 'the shipped config should exercise both schemes'

    names = list(task.steps)
    init_steps = [name for name in names if name.startswith('init')]
    forward_steps = [name for name in names if name.startswith('forward')]

    assert len(forward_steps) == len(schemes) * len(init_steps)
    for scheme in schemes:
        matching = [
            name for name in forward_steps if name.endswith(f'_{scheme}')
        ]
        assert len(matching) == len(init_steps)


@pytest.mark.parametrize('scheme', sorted(SCHEMES))
def test_forward_yaml_renders_what_omega_expects(scheme):
    """The template produces a valid ``PressureGrad`` block.

    ``PressureGradType`` must come out a string: an unrecognized value is fatal
    on the Omega side rather than falling back to ``Centered``, which is the
    behaviour that stops a typo here producing centered answers that read as a
    pass.
    """
    text = imp_res.files(_HPG_PKG).joinpath('forward.yaml').read_text()
    rendered = Template(text).render(
        pressure_grad_type=SCHEMES[scheme], quadrature_points=2
    )
    block = yaml.safe_load(rendered)['Omega']['PressureGrad']

    assert block['PressureGradType'] == SCHEMES[scheme]
    assert isinstance(block['PressureGradType'], str)
    assert block['QuadraturePoints'] == 2
    # HorzOrder and VerticalReconstruction are deliberately absent, so Omega's
    # Phase 1 defaults apply; the Phase 2 values are rejected with an error
    assert 'HorzOrder' not in block
    assert 'VerticalReconstruction' not in block


# The sweep point where each resting-state variant's advantage is smallest,
# found by scanning the full sweeps offline.  Gating at the worst point is what
# makes resting_state_improvement_min meaningful; gating at a typical one would
# pass while the variant regressed somewhere else in its sweep.
_WORST_IMPROVEMENT = {
    'hydrostatic_consistency': (4.0, 128.0, 50.0, 2.58),
    'hydrostatic_consistency_linear': (4.0, 64.0, 50.0, 7.71),
    'bathymetry_step': (4.0, 256.0, 200.0, 1169.54),
    'bathymetry_step_linear': (4.0, 256.0, 200.0, 58828.46),
}


@pytest.mark.parametrize('variant', sorted(_WORST_IMPROVEMENT))
def test_improvement_gate_is_below_what_the_kernel_delivers(variant):
    """``resting_state_improvement_min`` is set from measurement, with margin.

    The configured gates were taken from these numbers rather than guessed, so
    this test is what stops the two drifting apart: if the kernel changes, the
    measured ratio moves and either this assertion or the recorded one fails,
    rather than the gate silently becoming vacuous or unreachable.

    It also pins the *shape* of the result, which is the interesting part.  The
    advantage spans four orders of magnitude across the four variants, smallest
    where the profile is curved and the coordinate is tilted and largest where
    the profile is resolved and the sea floor steps -- so a single shared gate
    would be either vacuous on one end or wrong on the other.
    """
    horiz_res, vert_res, tilt, expected = _WORST_IMPROVEMENT[variant]
    ds = build_state(variant, horiz_res, vert_res, tilt)
    n_valid = int(ds.maxLevelCell.min())

    centered = rms(ds.HPGA.isel(Time=0).values[:n_valid])
    finite_volume = rms(ds.HPGAFiniteVolume.isel(Time=0).values[:n_valid])
    measured = centered / finite_volume

    np.testing.assert_allclose(measured, expected, rtol=0.02, atol=0.0)

    configured = make_config(variant)['horiz_press_grad'].getfloat(
        'resting_state_improvement_min'
    )
    assert configured < measured, (
        f'{variant}: the configured improvement gate {configured:g} is at or '
        f'above the {measured:.2f}x the kernel actually delivers at its worst '
        'sweep point, so the gate cannot pass'
    )
