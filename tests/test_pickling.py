"""
Tests for what a step carries into its pickle.

A step is pickled at setup and unpickled to run, so the pickle has to hold
the step's own state and the state of its dependencies.  It must not hold
the rest of the component: every task and step points back at the component,
so anything that keeps that link makes each step's pickle a copy of the
whole component.
"""

import pickle

from polaris import Component, Step, Task
from polaris.config import PolarisConfigParser


def _make_component(name='ocean', task_count=1):
    """Build a component with ``task_count`` tasks of one step each."""
    component = Component(name=name)
    for index in range(task_count):
        task = Task(component=component, name=f'task_{index}')
        task.add_step(Step(component=component, name=f'step_{index}'))
        component.add_task(task)
    return component


def _first_step(component):
    task = component.tasks['task_0']
    return task.steps['step_0']


def test_a_step_keeps_its_own_state():
    component = _make_component()
    step = _first_step(component)
    step.work_dir = '/work/ocean/task_0/step_0'
    step.base_work_dir = '/work'
    step.ntasks = 12
    step.cached = True

    restored = pickle.loads(pickle.dumps(step))

    assert restored.name == 'step_0'
    assert restored.path == 'ocean/step_0'
    assert restored.work_dir == '/work/ocean/task_0/step_0'
    assert restored.base_work_dir == '/work'
    assert restored.ntasks == 12
    assert restored.cached


def test_a_step_keeps_the_state_of_its_dependencies():
    """
    The pickle is how a step learns what its dependencies did, whether or not
    it is starting up in a subprocess, so a dependency has to round-trip
    whole rather than as a name.
    """
    component = _make_component()
    step = _first_step(component)
    dependency = Step(component=component, name='dependency')
    dependency.work_dir = '/work/ocean/dependency'
    step.add_dependency(dependency)
    # a dependency works out its outputs as it runs, which is the whole
    # reason the dependent step reads it back from a pickle
    dependency.outputs.append('/work/ocean/dependency/mesh.nc')

    restored = pickle.loads(pickle.dumps(step))

    assert list(restored.dependencies) == ['dependency']
    restored_dependency = restored.dependencies['dependency']
    assert restored_dependency.work_dir == '/work/ocean/dependency'
    assert '/work/ocean/dependency/mesh.nc' in restored_dependency.outputs


def test_a_step_keeps_its_config():
    component = _make_component()
    step = _first_step(component)
    config = PolarisConfigParser(filepath='ocean/ocean.cfg')
    config.add_from_package('polaris', 'default.cfg')
    step.set_shared_config(config, link='ocean.cfg')

    restored = pickle.loads(pickle.dumps(step))

    assert restored.config.filepath == 'ocean/ocean.cfg'
    assert restored.config_filename == 'ocean.cfg'
    assert restored.config.has_section('io')


def test_a_step_does_not_carry_the_rest_of_the_component():
    """
    ``tasks``, ``steps`` and ``configs`` describe how a component was set up.
    Nothing reads them after setup, and they reach every other task.
    """
    component = _make_component(task_count=3)
    step = _first_step(component)

    restored = pickle.loads(pickle.dumps(step))

    assert restored.component.name == 'ocean'
    assert restored.component.tasks == dict()
    assert restored.component.steps == dict()
    assert restored.component.configs == dict()


def test_a_config_does_not_carry_the_tasks_that_share_it():
    component = _make_component(task_count=3)
    config = PolarisConfigParser(filepath='ocean/ocean.cfg')
    for task in component.tasks.values():
        task.set_shared_config(config, link='ocean.cfg')
    assert len(config.tasks) == 3

    restored = pickle.loads(pickle.dumps(config))

    assert restored.filepath == 'ocean/ocean.cfg'
    assert restored.tasks == set()


def test_a_step_pickle_does_not_grow_with_the_component():
    """
    The size of a step's pickle should describe the step, so adding tasks
    elsewhere in the component must not change it.
    """
    small = pickle.dumps(_first_step(_make_component(task_count=1)))
    large = pickle.dumps(_first_step(_make_component(task_count=50)))

    assert len(small) == len(large)


def test_a_task_still_carries_its_own_steps():
    """
    The suite and task pickles are read through their tasks, so a task has
    to keep the steps it runs even though the component does not.
    """
    component = _make_component(task_count=2)
    suite = {
        'name': 'test',
        'tasks': {task.path: task for task in component.tasks.values()},
        'work_dir': '/work',
    }

    restored = pickle.loads(pickle.dumps(suite))

    assert sorted(restored['tasks']) == ['ocean/task_0', 'ocean/task_1']
    for task in restored['tasks'].values():
        assert len(task.steps) == 1


def test_an_unpickled_component_can_still_have_steps_added():
    """
    ``polaris serial`` builds a dummy task around an unpickled step, which
    adds the step back to its component.  That has to work on a component
    whose dictionaries were left out of the pickle.
    """
    restored = pickle.loads(pickle.dumps(_first_step(_make_component())))
    task = Task(component=restored.component, name='dummy_task')
    task.add_step(restored)

    assert task.steps['step_0'] is restored
    assert restored.component.steps['step_0'] is restored
