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

import pytest
import yaml
from jinja2 import Template

from polaris.component import Component
from polaris.tasks.ocean.horiz_press_grad.forward import SCHEME_HPGA, SCHEMES
from polaris.tasks.ocean.horiz_press_grad.resting_state_task import (
    HorizPressGradRestingStateTask,
)
from polaris.tasks.ocean.horiz_press_grad.task import HorizPressGradTask

from .two_column import GRADIENT_VARIANTS, VARIANTS, make_config

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
