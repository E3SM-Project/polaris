import os
import textwrap

import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.analysis_output.task import (
    AnalysisOutput,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps import (
    adjustment_subdir,
    get_realistic_dynamic_adjustment_steps,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.task import (
    RealisticGlobalDynamicAdjustment,
)
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    StepInitialCondition,
)
from polaris.tasks.ocean.realistic_global.forward.task import (
    RealisticGlobalForward,
)
from polaris.tasks.ocean.realistic_global.forward.tasks import (
    get_cached_initial_condition,
)
from polaris.tasks.ocean.realistic_global.init.steps import (
    get_realistic_init_steps,
    init_subdir,
)
from polaris.tasks.ocean.realistic_global.init.task import RealisticGlobalInit
from polaris.tasks.ocean.realistic_global.mesh_info import (
    estimate_ocean_cell_count,
    min_res_for_mesh,
)
from polaris.tasks.ocean.realistic_global.models import (
    get_configured_model,
    model_subdir,
)

MESH_NAME = 'u-oi240-lr240'

#: The init steps whose outputs are written for one ocean model
MODEL_INIT_STEPS = {'initial_state', 'forcing', 'viz'}


def test_model_subdir_rejects_an_unknown_model():
    with pytest.raises(ValueError, match='mpas-ocean, omega'):
        model_subdir('init', 'mom6')


@pytest.mark.parametrize(
    ('lines', 'expected'),
    [
        ([], 'mpas-ocean'),
        (['[ocean]', 'model = omega'], 'omega'),
        (['[ocean]', 'model = unknown'], 'mpas-ocean'),
    ],
)
def test_configured_model_falls_back_to_the_built_one(
    tmp_path, lines, expected
):
    config = PolarisConfigParser()
    if lines:
        path = tmp_path / 'model.cfg'
        path.write_text('\n'.join(lines) + '\n')
        config.add_from_file(str(path))
    assert get_configured_model(config, 'mpas-ocean') == expected


def test_init_steps_for_each_model_share_the_model_neutral_ones():
    component = Ocean()
    mpaso, mpaso_config = get_realistic_init_steps(
        component=component, mesh_name=MESH_NAME, include_viz=True
    )
    omega, omega_config = get_realistic_init_steps(
        component=component,
        mesh_name=MESH_NAME,
        include_viz=True,
        model='omega',
    )
    assert mpaso.keys() == omega.keys()
    base = init_subdir(MESH_NAME)
    for name, step in omega.items():
        if name in MODEL_INIT_STEPS:
            assert step.subdir == f'{base}/omega/{name}'
            assert mpaso[name].subdir == f'{base}/mpas-ocean/{name}'
            assert step.config.filepath == f'ocean/{base}/omega/init.cfg'
        else:
            assert step is mpaso[name], name
    # the neutral config is the one the init task uses, for both models
    assert omega_config is mpaso_config
    assert mpaso_config.filepath == f'ocean/{base}/init.cfg'


def test_every_adjustment_step_is_in_the_models_directory():
    component = Ocean()
    steps, config, stages = get_realistic_dynamic_adjustment_steps(
        component=component,
        mesh_name=MESH_NAME,
        include_viz=True,
        model='omega',
    )
    base = f'{adjustment_subdir(MESH_NAME)}/omega'
    assert config.filepath == f'ocean/{base}/dynamic_adjustment.cfg'
    init = init_subdir(MESH_NAME)
    for name, step in steps.items():
        if step.subdir.startswith(f'{adjustment_subdir(MESH_NAME)}/'):
            assert step.subdir.startswith(f'{base}/'), name
            assert step.config is config, name
        elif name in MODEL_INIT_STEPS:
            assert step.subdir.startswith(f'{init}/omega/'), name
        else:
            assert 'omega' not in step.subdir.split('/'), name
    # the stages' restarts are beside them, in the model's directory
    restart_out = stages[-1].restart_out
    assert restart_out is not None
    restart = os.path.normpath(
        os.path.join(steps[stages[-1].name].subdir, '..', restart_out)
    )
    assert restart.startswith(f'{base}/restarts/')


def test_init_task_swaps_its_model_dependent_steps():
    component = Ocean()
    task = RealisticGlobalInit(component=component, mesh_name=MESH_NAME)
    before = dict(task.steps)
    config = task.config

    _set_model(task, 'omega')
    task.configure()

    assert task.model == 'omega'
    assert task.config is config
    _assert_no_mpas_ocean_steps(task)
    for name, step in task.steps.items():
        if name in MODEL_INIT_STEPS:
            assert '/init/omega/' in step.subdir, name
        else:
            assert step is before[name], name


def test_task_built_for_the_configured_model_is_left_alone():
    component = Ocean()
    task = RealisticGlobalInit(component=component, mesh_name=MESH_NAME)
    before = dict(task.steps)
    _set_model(task, 'mpas-ocean')
    task.configure()
    assert task.steps == before


def test_dynamic_adjustment_task_swaps_its_steps_and_config():
    component = Ocean()
    task = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name=MESH_NAME
    )
    stage_names = [stage.name for stage in task.stages]

    _set_model(task, 'omega')
    task.configure()

    assert task.model == 'omega'
    _assert_no_mpas_ocean_steps(task)
    base = f'{adjustment_subdir(MESH_NAME)}/omega'
    assert task.config.filepath == f'ocean/{base}/dynamic_adjustment.cfg'
    assert [stage.name for stage in task.stages] == stage_names
    for name in stage_names:
        assert task.steps[name].subdir == f'{base}/{name}'
        assert task.steps[name].config is task.config


def test_the_new_models_config_starts_from_the_tasks(tmp_path):
    """
    Setup gives a task's config the common and user options before
    configure(), and the new model's config is read for the schedule during
    configure().  An override the user made has to reach it.
    """
    component = Ocean()
    task = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name=MESH_NAME
    )
    schedule = tmp_path / 'schedule.yaml'
    schedule.write_text(
        textwrap.dedent(
            """
            dynamic_adjustment:
              stages:
                simulation:
                  run_duration: 5_00:00:00
            """
        )
    )
    override = tmp_path / 'override.cfg'
    override.write_text(
        f'[{SECTION}]\nschedule = {schedule}\n[ocean]\nmodel = omega\n'
    )
    task.config.add_user_config(str(override))

    task.configure()

    assert task.model == 'omega'
    assert [stage.name for stage in task.stages] == ['simulation']
    assert task.steps['simulation'].stage.run_duration == '5_00:00:00'
    assert '/omega/' in task.steps['simulation'].subdir


def test_forward_task_reads_the_configured_models_init_steps():
    component = Ocean()
    task = _forward_task(component)
    _set_model(task, 'omega')
    task.configure()

    assert task.model == 'omega'
    _assert_no_mpas_ocean_steps(task)
    init_condition = task.forward_step.init_condition
    assert isinstance(init_condition, StepInitialCondition)
    assert init_condition.init_step is task.steps['initial_state']
    assert init_condition.forcing_step is task.steps['forcing']
    assert '/init/omega/' in init_condition.init_step.subdir
    assert task.forward_step.graph_target == init_condition.graph_target
    assert init_condition.min_res == min_res_for_mesh(MESH_NAME)


def test_analysis_output_task_reads_the_configured_models_init_steps():
    component = Ocean()
    init_steps, _ = get_realistic_init_steps(
        component=component, mesh_name=MESH_NAME, include_viz=False
    )
    task = AnalysisOutput(
        component=component,
        mesh_name=MESH_NAME,
        init_condition=_step_initial_condition(init_steps),
        init_steps=init_steps,
    )
    _set_model(task, 'omega')
    task.configure()

    _assert_no_mpas_ocean_steps(task)
    init_condition = task.forward_step.init_condition
    assert isinstance(init_condition, StepInitialCondition)
    assert init_condition.init_step is task.steps['initial_state']


def test_cached_forward_task_has_no_init_steps_to_swap():
    component = Ocean()
    init_condition = get_cached_initial_condition('e3sm-qu240')
    task = RealisticGlobalForward(
        component=component,
        mesh_name='e3sm-qu240',
        init_condition=init_condition,
        subdir_name='cached_forward',
    )
    before = dict(task.steps)
    _set_model(task, 'omega')
    task.configure()
    assert task.steps == before
    assert task.forward_step.init_condition is init_condition


def test_tasks_on_one_model_share_its_init_steps():
    component = Ocean()
    forward = _forward_task(component)
    adjustment = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name=MESH_NAME
    )
    for task in [forward, adjustment]:
        _set_model(task, 'omega')
        task.configure()
    for name in ['initial_state', 'forcing', 'pstar_init']:
        assert forward.steps[name] is adjustment.steps[name], name


def _forward_task(component):
    """A forward task on the shared init chain, as the task registry makes."""
    init_steps, _ = get_realistic_init_steps(
        component=component, mesh_name=MESH_NAME, include_viz=False
    )
    return RealisticGlobalForward(
        component=component,
        mesh_name=MESH_NAME,
        init_condition=_step_initial_condition(init_steps),
        init_steps=init_steps,
    )


def _step_initial_condition(init_steps):
    return StepInitialCondition(
        init_steps['initial_state'],
        min_res=min_res_for_mesh(MESH_NAME),
        approx_cell_count=estimate_ocean_cell_count(MESH_NAME),
        forcing_step=init_steps['forcing'],
    )


def _set_model(task, model):
    """What the ocean component's configuration leaves in a task's config."""
    task.config.set('ocean', 'model', model)


def _assert_no_mpas_ocean_steps(task):
    stale = [
        step.subdir
        for step in task.steps.values()
        if 'mpas-ocean' in step.subdir.split('/')
    ]
    assert not stale, stale
