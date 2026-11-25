import importlib.resources as imp_res

import pytest
import yaml

from polaris.mpas.time import get_time_interval_string
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    StepInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage
from polaris.tasks.ocean.realistic_global.forward.task import (
    RealisticGlobalForward,
)
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
)
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
    min_res_for_mesh,
)
from polaris.tasks.ocean.realistic_global.ssh_adjustment import (
    RealisticGlobalSshAdjustment,
    RealisticSshAdjustment,
    SshForward,
    get_realistic_ssh_adjustment_steps,
)

MESH_NAME = 'qu240km'


def _ssh_forward(steps, iteration=0) -> SshForward:
    step = steps[f'ssh_forward_{iteration}']
    assert isinstance(step, SshForward)
    return step


def _init_target(step):
    init_condition = step.init_condition
    assert isinstance(init_condition, StepInitialCondition)
    return init_condition.init_target


def _set_cavities(config):
    config.set(
        'spherical_mesh',
        'antarctic_boundary_convention',
        'grounding_line',
        user=True,
    )


def test_steps_alternate_and_chain():
    """
    Each step from rest starts from the adjustment before it, and runs from
    the adjusted state start from the last adjustment
    """
    steps, config, adjusted_target = get_realistic_ssh_adjustment_steps(
        component=Ocean(), mesh_name=MESH_NAME
    )
    iterations = config.getint('ssh_adjustment', 'iterations')
    assert list(steps) == [
        name
        for iteration in range(iterations)
        for name in (f'ssh_forward_{iteration}', f'ssh_adjust_{iteration}')
    ]
    for iteration in range(iterations):
        assert isinstance(steps[f'ssh_forward_{iteration}'], SshForward)
        assert isinstance(
            steps[f'ssh_adjust_{iteration}'], RealisticSshAdjustment
        )
    for iteration in range(1, iterations):
        forward = _ssh_forward(steps, iteration)
        previous = steps[f'ssh_adjust_{iteration - 1}']
        assert _init_target(forward) == f'{previous.path}/output.nc'
    last = steps[f'ssh_adjust_{iterations - 1}']
    assert adjusted_target == f'{last.path}/output.nc'


def test_step_from_rest_is_one_time_step():
    """
    The measuring run is a single step of solve_dt_per_km times the minimum
    resolution, with output at its start and end, so the solve sees the
    state from rest and after one step
    """
    steps, config, _ = get_realistic_ssh_adjustment_steps(
        component=Ocean(), mesh_name=MESH_NAME
    )
    _set_cavities(config)
    config.set('ssh_adjustment', 'solve_dt_per_km', '2.5')
    step = _ssh_forward(steps)
    stage = step.get_stage()

    dt = get_time_interval_string(seconds=2.5 * step.init_condition.min_res)
    assert stage.run_duration == dt
    assert stage.output_interval == dt
    assert stage.dt == dt
    assert stage.rk4_dt == dt
    # a run from rest, not a continuation of another run
    assert not stage.do_restart
    assert stage.restart_out is None
    # melting would add a buoyancy forcing that is not part of the balance
    # between SSH and the land-ice pressure
    assert stage.land_ice_flux_mode == 'off'


def test_step_from_rest_uses_the_forward_runs_integrator():
    """
    The acceleration is measured with the integrator the forward runs use,
    including its replacement for split_explicit_ab2 with cavities
    """
    steps, config, _ = get_realistic_ssh_adjustment_steps(
        component=Ocean(), mesh_name=MESH_NAME
    )
    _set_cavities(config)
    config.set(
        'realistic_global_forward', 'mpaso_time_integrator', 'some_scheme'
    )
    assert _ssh_forward(steps).get_stage().mpaso_time_integrator == (
        'some_scheme'
    )
    config.set(
        'realistic_global_forward',
        'mpaso_time_integrator',
        'split_explicit_ab2',
    )
    forward_stage = ForwardStage.from_config(config)
    assert _ssh_forward(steps).get_stage().mpaso_time_integrator == (
        forward_stage.mpaso_time_integrator
    )


def test_only_the_solve_method_is_supported():
    steps, config, _ = get_realistic_ssh_adjustment_steps(
        component=Ocean(), mesh_name=MESH_NAME
    )
    config.set('ssh_adjustment', 'method', 'iterate')
    with pytest.raises(ValueError, match='method = solve'):
        _ssh_forward(steps).get_stage()


def test_step_from_rest_writes_what_the_solve_reads():
    """
    The solve needs the state at the start of the step and the time between
    the two records, which the forward runs do not write
    """
    package = 'polaris.tasks.ocean.realistic_global.ssh_adjustment'
    text = imp_res.files(package).joinpath('ssh_forward.yaml').read_text()
    options = yaml.safe_load(text)['mpas-ocean']
    assert options['io']['config_write_output_on_startup'] is True
    contents = options['streams']['output']['contents']
    for field in ['daysSinceStartOfSim', 'minLevelCell', 'maxLevelCell']:
        assert field in contents


def test_task_needs_cavities():
    task = RealisticGlobalSshAdjustment(component=Ocean(), mesh_name=MESH_NAME)
    with pytest.raises(ValueError, match='ice-shelf cavities'):
        task.configure()


def test_task_runs_the_init_and_ssh_adjustment_steps():
    component = Ocean()
    task = RealisticGlobalSshAdjustment(
        component=component, mesh_name=MESH_NAME
    )
    # setup sets the model before configuring the task
    task.config.set('ocean', 'model', 'mpas-ocean')
    _set_cavities(task.config)
    task.configure()
    steps, _, _ = get_realistic_ssh_adjustment_steps(
        component=component, mesh_name=MESH_NAME
    )
    for name, step in steps.items():
        assert task.steps[name] is step
    assert 'initial_state' in task.steps


def _forward_task(component):
    init_steps, _ = get_realistic_init_steps(
        component=component, mesh_name=MESH_NAME, include_viz=False
    )
    init_condition = StepInitialCondition(
        init_steps['initial_state'],
        min_res=min_res_for_mesh(MESH_NAME),
        approx_cell_count=estimate_ocean_cell_count(MESH_NAME),
        forcing_step=init_steps['forcing'],
    )
    return RealisticGlobalForward(
        component=component,
        mesh_name=MESH_NAME,
        init_condition=init_condition,
        init_steps=init_steps,
    )


def test_forward_task_starts_from_adjusted_ssh_with_cavities():
    component = Ocean()
    task = _forward_task(component)
    _set_cavities(task.config)
    task.configure()

    steps, _, adjusted_target = get_realistic_ssh_adjustment_steps(
        component=component, mesh_name=MESH_NAME
    )
    for name, step in steps.items():
        assert task.steps[name] is step
    assert _init_target(task.forward_step) == adjusted_target


def test_forward_task_without_cavities_starts_from_the_init():
    task = _forward_task(Ocean())
    task.configure()
    assert not any(name.startswith('ssh_') for name in task.steps)
    init_step = task.steps['initial_state']
    assert _init_target(task.forward_step) == f'{init_step.path}/init.nc'
