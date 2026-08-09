import os

import pytest

from polaris import Component, Step, Task
from polaris.component_graph import (
    get_components_in_use,
    get_steps_by_component,
)
from polaris.config import PolarisConfigParser
from polaris.setup import (
    _get_basic_config,
    _get_component_args,
    _get_component_configs,
    _setup_configs,
)


class RecordingComponent(Component):
    """A component that records what its configure() method was given"""

    def __init__(self, name):
        super().__init__(name=name)
        self.configured_steps = None

    def configure(self, config, steps):
        self.configured_steps = steps
        config.set('recording', 'configured', self.name)


@pytest.fixture
def basic_config(tmp_path, monkeypatch):
    """The machine and command-line config options, with no component"""
    monkeypatch.setenv('POLARIS_COMPILER', 'gnu')
    monkeypatch.setenv('POLARIS_MPI', 'openmpi')
    return _get_basic_config(
        config_file=None,
        machine='chrysalis',
        build=None,
        cmake_flags=None,
        debug=None,
        clean_build=None,
        quiet_build=None,
        work_dir=str(tmp_path),
    )


def get_shared_step(component, name, subdir):
    """Build a step in ``component`` with a shared config of its own"""
    step = Step(component=component, name=name, subdir=subdir)
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, subdir, f'{name}.cfg')
    )
    step.set_shared_config(config, link=f'{name}.cfg')
    return step


def setup_configs(basic_config, tasks, work_dir):
    """Run the config half of setup for ``tasks``"""
    component = next(iter(tasks.values())).component
    components_in_use = get_components_in_use(tasks)
    component_args = _get_component_args(
        component=component,
        components_in_use=components_in_use,
        model=None,
        component_path=None,
        branch=None,
        component_args=dict(),
    )
    component_configs = _get_component_configs(
        basic_config=basic_config,
        components_in_use=components_in_use,
        component_args=component_args,
    )
    steps_by_component = get_steps_by_component(tasks)
    for component_in_use in components_in_use:
        name = component_in_use.name
        component_in_use.configure(
            component_configs[name], steps_by_component[name]
        )
    _setup_configs(
        component_configs=component_configs,
        tasks=tasks,
        work_dir=work_dir,
        copy_executable=False,
    )
    return component_configs


def test_a_shared_step_gets_its_own_components_options(basic_config, tmp_path):
    """
    A shared ocean step in a task from another component gets the ocean's
    config options, which is what its own component provides and the task's
    component knows nothing about.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    step = get_shared_step(ocean, 'a_shared_step', 'shared')
    task = Task(component=e3sm_init, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    setup_configs(basic_config, tasks, str(tmp_path))

    # [ocean] model is defined in polaris/ocean/ocean.cfg and nowhere else
    assert step.config.get('ocean', 'model') == 'detect'


def test_a_task_does_not_get_another_components_options(
    basic_config, tmp_path
):
    """
    The task's own config gets its own component's options, not those of the
    components its shared steps belong to.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    step = get_shared_step(ocean, 'a_shared_step', 'shared')
    task = Task(component=e3sm_init, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    setup_configs(basic_config, tasks, str(tmp_path))

    assert not task.config.has_option('ocean', 'model')


def test_a_shared_step_does_not_depend_on_who_set_it_up(
    basic_config, tmp_path
):
    """
    The config options of a shared step are the same whether the task that
    pulls it in belongs to its own component or to another one.
    """
    options = list()
    for task_component_name in ['ocean', 'e3sm/init']:
        ocean = Component(name='ocean')
        task_component = (
            ocean
            if task_component_name == 'ocean'
            else Component(name=task_component_name)
        )
        step = get_shared_step(ocean, 'a_shared_step', 'shared')
        task = Task(component=task_component, name='a_task')
        task.add_step(step=step)
        tasks = {task.path: task}

        work_dir = os.path.join(str(tmp_path), task_component_name)
        setup_configs(basic_config, tasks, work_dir)

        step.config.combine(raw=True)
        options.append(
            {
                (section, option): value
                for section in step.config.combined.sections()
                for option, value in step.config.combined.items(section)
                # the task's own section names the task, not the step
                if section != 'a_task'
            }
        )

    assert options[0] == options[1]


def test_each_component_in_use_is_configured(basic_config, tmp_path):
    """
    Every component in use has its configure() method called, on its own
    config options and with the steps it owns.
    """
    shared_component = RecordingComponent(name='ocean')
    task_component = RecordingComponent(name='e3sm/init')
    step = get_shared_step(shared_component, 'a_shared_step', 'shared')
    task = Task(component=task_component, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    component_configs = setup_configs(basic_config, tasks, str(tmp_path))

    assert shared_component.configured_steps == [step]
    assert task_component.configured_steps == []
    assert component_configs['ocean'].get('recording', 'configured') == 'ocean'
    assert (
        component_configs['e3sm/init'].get('recording', 'configured')
        == 'e3sm/init'
    )
    # what each component's configure() set reaches the configs it owns
    assert step.config.get('recording', 'configured') == 'ocean'
    assert task.config.get('recording', 'configured') == 'e3sm/init'


def test_a_shared_config_belongs_to_one_component(basic_config, tmp_path):
    """
    A shared config used by steps from two components has no single component
    to get its config options from, so setup refuses it.
    """
    ocean = Component(name='ocean')
    mesh = Component(name='mesh')
    e3sm_init = Component(name='e3sm/init')
    ocean_step = get_shared_step(ocean, 'an_ocean_step', 'shared')
    mesh_step = Step(component=mesh, name='a_mesh_step', subdir='mesh_shared')
    mesh_step.set_shared_config(ocean_step.config, link='an_ocean_step.cfg')
    task = Task(component=e3sm_init, name='a_task')
    task.add_step(step=ocean_step)
    task.add_step(step=mesh_step)
    tasks = {task.path: task}

    with pytest.raises(ValueError, match='more than one component'):
        setup_configs(basic_config, tasks, str(tmp_path))


def test_a_step_from_another_component_must_be_shared(basic_config, tmp_path):
    """
    A step from another component with no shared config would get its config
    options from the task, and so from the wrong component.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    step = Step(component=ocean, name='a_step')
    task = Task(component=e3sm_init, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    with pytest.raises(ValueError, match='must be a shared step'):
        setup_configs(basic_config, tasks, str(tmp_path))


def test_unqualified_flags_go_to_the_tasks_component():
    """
    --model, -p and --branch apply to the component that owns the tasks, as
    they always have.
    """
    ocean = Component(name='ocean')

    component_args = _get_component_args(
        component=ocean,
        components_in_use=[ocean],
        model='omega',
        component_path='/a/build',
        branch=None,
        component_args=dict(),
    )

    assert component_args == {
        'ocean': {'model': 'omega', 'component_path': '/a/build'}
    }


def test_unqualified_flags_need_a_component_with_a_model():
    """
    A task in a component with no model gives -p nothing to apply to, so
    setup says which flag to use instead rather than quietly ignoring it.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')

    with pytest.raises(ValueError, match='--ocean_path'):
        _get_component_args(
            component=e3sm_init,
            components_in_use=[e3sm_init, ocean],
            model=None,
            component_path='/a/build',
            branch=None,
            component_args=dict(),
        )


def test_a_qualified_flag_reaches_another_components_config(
    basic_config, tmp_path
):
    """
    --ocean_path points the ocean's steps at an ocean build even though the
    task belongs to another component.
    """
    ocean = Component(name='ocean')
    e3sm_init = Component(name='e3sm/init')
    step = get_shared_step(ocean, 'a_shared_step', 'shared')
    task = Task(component=e3sm_init, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    component_configs = _get_component_configs(
        basic_config=basic_config,
        components_in_use=get_components_in_use(tasks),
        component_args=_get_component_args(
            component=e3sm_init,
            components_in_use=get_components_in_use(tasks),
            model=None,
            component_path=None,
            branch=None,
            component_args={'ocean': {'component_path': '/a/build'}},
        ),
    )

    assert (
        component_configs['ocean'].get('paths', 'component_path') == '/a/build'
    )
    assert not component_configs['e3sm/init'].has_option(
        'paths', 'component_path'
    )


def test_a_qualified_flag_needs_its_component_to_be_in_use():
    """
    --ocean_path in a setup with no ocean steps would have no effect, so it
    is an error rather than a silent no-op.
    """
    mesh = Component(name='mesh')

    with pytest.raises(ValueError, match='not\nused|not used'):
        _get_component_args(
            component=mesh,
            components_in_use=[mesh],
            model=None,
            component_path=None,
            branch=None,
            component_args={'ocean': {'component_path': '/a/build'}},
        )


def test_a_single_component_setup_gets_its_own_options(basic_config, tmp_path):
    """
    The common case: a task and its steps all belong to one component, which
    provides the config options for all of them.
    """
    ocean = Component(name='ocean')
    step = get_shared_step(ocean, 'a_shared_step', 'shared')
    task = Task(component=ocean, name='a_task')
    task.add_step(step=step)
    tasks = {task.path: task}

    setup_configs(basic_config, tasks, str(tmp_path))

    assert task.config.get('ocean', 'model') == 'detect'
    assert step.config.get('ocean', 'model') == 'detect'
    assert os.path.exists(os.path.join(str(tmp_path), 'ocean.cfg'))
