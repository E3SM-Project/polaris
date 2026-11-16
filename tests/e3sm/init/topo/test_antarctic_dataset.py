"""
Unit tests for choosing the Antarctic dataset that remapped topography comes
from with ``[remap_topography] antarctic_dataset``.
"""

from types import SimpleNamespace

import pytest

from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.antarctic_dataset import (
    check_combine_topo_dataset,
    get_antarctic_dataset,
    select_antarctic_dataset,
)
from polaris.tasks.e3sm.init.topo.combine.files import ANTARCTIC
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.remap.steps import get_remap_topo_steps

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
