"""
The overflow smoke test that keeps Omega's centered pressure gradient covered
now that the finite-volume scheme is Omega's default.
"""

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.overflow import add_overflow_tasks

CENTERED_TASK = (
    'planar/overflow/nonlinear/pstar/'
    'smoke_test_horiz_adv_order_4_del4_centered_pgf'
)
FV_TWIN_TASK = (
    'planar/overflow/nonlinear/pstar/smoke_test_horiz_adv_order_4_del4'
)


def test_centered_pgf_task_only_in_nonlinear_pstar():
    component = _make_component()

    centered = [name for name in component.tasks if 'centered_pgf' in name]

    assert centered == [CENTERED_TASK]


def test_centered_pgf_forward_sets_omega_scheme():
    component = _make_component()
    forward = component.tasks[CENTERED_TASK].steps['forward']

    options = _omega_options(forward)

    assert {'PressureGradType': 'Centered'} in options


def test_fv_twin_leaves_omega_default():
    component = _make_component()
    forward = component.tasks[FV_TWIN_TASK].steps['forward']

    options = _omega_options(forward)

    assert all('PressureGradType' not in entry for entry in options)


def _make_component():
    """An Omega ocean component with the overflow tasks added"""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    add_overflow_tasks(component)
    return component


def _omega_options(forward):
    """The Omega options a nonlinear p-star forward step adds at setup"""
    config = PolarisConfigParser()
    for package, filename in [
        ('polaris.ocean', 'ocean.cfg'),
        ('polaris.ocean.eos', 'teos10.cfg'),
        ('polaris.tasks.ocean.overflow', 'overflow.cfg'),
        ('polaris.tasks.ocean.overflow', 'overflow_pstar.cfg'),
    ]:
        config.add_from_package(package, filename)
    config.set('ocean', 'model', 'omega')
    forward.config = config
    forward.dynamic_model_config(at_setup=True)
    return [
        entry['options']
        for entry in forward.model_config_data
        if 'options' in entry and entry['config_model'] == 'Omega'
    ]
