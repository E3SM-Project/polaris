"""
Unit tests for choosing the Antarctic dataset that remapped topography comes
from with ``[remap_topography] antarctic_dataset``.
"""

from types import SimpleNamespace

import pytest

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.antarctic_dataset import (
    check_combine_topo_dataset,
    get_antarctic_dataset,
    replace_steps,
    select_antarctic_dataset,
)
from polaris.tasks.e3sm.init.topo.combine.files import ANTARCTIC
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.remap.steps import get_remap_topo_steps
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    get_woa23_steps,
    select_woa23_antarctic_dataset,
)

OTHER = 'bedmachinev4'


@pytest.fixture
def remap_task():
    """
    A task with the shared remap steps for a mesh.  The steps are shared
    module-wide, so the default dataset is put back afterwards.
    """
    task = Task(component=e3sm_init, name='test', subdir='test/dataset')
    steps, _ = get_remap_topo_steps(mesh_name='icos240km')
    for symlink, step in steps.items():
        task.add_step(step, symlink=symlink)
    yield task
    select_antarctic_dataset(e3sm_init, list(task.steps.values()), ANTARCTIC)
    for step in list(task.steps.values()):
        task.remove_step(step)


def _combine_steps(task):
    return [
        step for step in task.steps.values() if isinstance(step, CombineStep)
    ]


def _with_upstream(combine):
    return [combine.prepare_step, combine.weights_step, combine]


def _users_of_combine(task):
    return [
        step
        for step in task.steps.values()
        if hasattr(step, 'combine_topo_step')
    ]


def test_user_config_swaps_in_the_other_datasets_combine_steps(remap_task):
    config = PolarisConfigParser()
    config.set('remap_topography', 'antarctic_dataset', OTHER)
    names_before = list(remap_task.steps)
    symlinks_before = dict(remap_task.step_symlinks)

    e3sm_init.configure(config, list(remap_task.steps.values()))

    (combine,) = _combine_steps(remap_task)
    assert combine.antarctic_dataset == OTHER
    for step in _users_of_combine(remap_task):
        assert step.combine_topo_step is combine
    # the prepare and weights steps that feed it come along
    assert combine.prepare_step.name in remap_task.steps
    assert combine.weights_step.name in remap_task.steps
    # in the same places, under the same symlinks
    names_after = list(remap_task.steps)
    assert len(names_after) == len(names_before)
    for step in _with_upstream(combine):
        old_name = step.name.replace(OTHER, ANTARCTIC)
        assert names_after.index(step.name) == names_before.index(old_name)
        assert (
            remap_task.step_symlinks[step.name] == (symlinks_before[old_name])
        )


def test_default_dataset_changes_nothing(remap_task):
    steps_before = dict(remap_task.steps)

    e3sm_init.configure(PolarisConfigParser(), list(steps_before.values()))

    assert remap_task.steps == steps_before


def test_unknown_dataset_is_an_error():
    config = PolarisConfigParser()
    config.set('remap_topography', 'antarctic_dataset', 'bedmap2')

    with pytest.raises(ValueError, match='antarctic_dataset'):
        get_antarctic_dataset(config)


def test_setup_refuses_a_combine_step_from_another_dataset():
    """A step whose combine step was not swapped must not set up."""
    config = PolarisConfigParser()
    config.set('remap_topography', 'antarctic_dataset', OTHER)
    step = SimpleNamespace(
        path='e3sm/init/mesh/topo/remap/mask',
        config=config,
        combine_topo_step=SimpleNamespace(antarctic_dataset=ANTARCTIC),
    )

    with pytest.raises(ValueError, match=OTHER):
        check_combine_topo_dataset(step)


class _Consumer(Step):
    """A step that refers to the WOA23 extrapolation, as init steps do"""

    def __init__(self, extrapolate_step):
        super().__init__(component=ocean, name='consumer', subdir='test/use')
        self.extrapolate_step = extrapolate_step


@pytest.fixture
def woa23_task():
    """
    A task with the shared WOA23 steps, the extrapolation free-running, and
    a step that refers to the extrapolation as the realistic_global init
    steps do.  The default dataset is put back afterwards.
    """
    task = Task(component=ocean, name='test', subdir='test/woa23_dataset')
    steps, _ = get_woa23_steps(component=ocean, include_viz=True)
    for symlink, step in steps.items():
        task.add_step(step, symlink=symlink)
    extrapolate = steps['woa23_extrapolate']
    task.free_running_steps.add(extrapolate.subdir)
    consumer = _Consumer(extrapolate)
    task.add_step(consumer)
    yield task, consumer
    select_woa23_antarctic_dataset(ocean, list(task.steps.values()), ANTARCTIC)
    for step in list(task.steps.values()):
        task.remove_step(step)


def test_woa23_follows_the_antarctic_dataset(woa23_task):
    task, consumer = woa23_task
    old_extrapolate = consumer.extrapolate_step

    select_woa23_antarctic_dataset(ocean, list(task.steps.values()), OTHER)

    extrapolate = consumer.extrapolate_step
    assert extrapolate is not old_extrapolate
    assert extrapolate.combine_topo_step.antarctic_dataset == OTHER
    # its own path, so its cached output is not the default dataset's
    assert extrapolate.subdir != old_extrapolate.subdir
    assert task.steps[extrapolate.name] is extrapolate
    assert extrapolate.subdir in task.free_running_steps
    assert old_extrapolate.subdir not in task.free_running_steps
    (combine,) = _combine_steps(task)
    assert combine is extrapolate.combine_topo_step
    viz = task.steps['viz']
    assert viz.extrapolate_step is extrapolate
    assert viz.combine_topo_step is combine


def test_a_replaced_dependency_is_refused():
    """The input file that carries a dependency is fixed when it is added."""
    old = Step(component=ocean, name='old', subdir='test/old')
    new = Step(component=ocean, name='new', subdir='test/new')
    consumer = Step(component=ocean, name='consumer', subdir='test/user')
    consumer.add_dependency(old)

    with pytest.raises(ValueError, match='depends on'):
        replace_steps([(old, new)], [consumer])
