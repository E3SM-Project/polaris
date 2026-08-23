"""
Tests for how a step says what resources it needs.

Phase A of task parallelism changes GPUs from a count per MPI task to a
total for the step.  The difference is not cosmetic: measurements on both
GPU machines showed the per-task form does not confine a step at all when
steps run at the same time, while a total does.
"""

import logging

import pytest

from polaris import Component, Step


def _make_step(**kwargs):
    return Step(component=Component(name='ocean'), name='step', **kwargs)


def _resources(cores=64, cores_per_node=64, gpus=0, mpi_allowed=True):
    return dict(
        cores=cores,
        nodes=max(1, cores // cores_per_node),
        cores_per_node=cores_per_node,
        gpus=gpus,
        gpus_per_node=gpus,
        mpi_allowed=mpi_allowed,
    )


def test_a_step_needs_no_gpus_unless_it_says_so():
    step = _make_step(ntasks=4)
    assert step.gpus == 0
    assert step.min_gpus == 0


def test_a_step_states_its_gpus_as_a_total():
    step = _make_step(ntasks=4, gpus=4, min_gpus=2)
    assert step.gpus == 4
    assert step.min_gpus == 2


def test_zero_gpus_stays_zero_even_with_tasks():
    """An explicit "none" must not be confused with "unstated"."""
    step = _make_step(ntasks=8, gpus=0, min_gpus=0)
    assert step.gpus == 0
    assert step.min_gpus == 0


def test_a_per_task_count_is_deprecated_but_still_understood():
    with pytest.warns(DeprecationWarning, match='gpus_per_task'):
        step = _make_step(
            ntasks=4, min_tasks=2, gpus_per_task=2, min_gpus_per_task=1
        )
    assert step.gpus == 8
    assert step.min_gpus == 2


def test_a_per_task_count_follows_a_later_change_in_tasks():
    """A total derived from a per-task count has to track the task count."""
    with pytest.warns(DeprecationWarning):
        step = _make_step(ntasks=4, gpus_per_task=1)
    step.ntasks = 6
    assert step.gpus == 6


def test_set_resources_takes_the_total():
    step = _make_step(ntasks=4)
    step.set_resources(gpus=3, min_gpus=1)
    assert step.gpus == 3
    assert step.min_gpus == 1


def test_set_resources_warns_about_the_per_task_count():
    step = _make_step(ntasks=4)
    with pytest.warns(DeprecationWarning, match='gpus_per_task'):
        step.set_resources(gpus_per_task=1)
    assert step.gpus == 4


def test_a_step_that_wants_no_gpus_is_left_alone():
    step = _make_step(ntasks=4, cpus_per_task=1)
    step.constrain_resources(_resources(gpus=0))
    assert step.ntasks == 4
    assert step.gpus == 0


def test_gpus_are_capped_by_what_the_machine_has():
    """Fewer GPUs means fewer tasks, and the two stay in proportion."""
    step = _make_step(ntasks=8, min_tasks=1, cpus_per_task=1, gpus=8)
    step.constrain_resources(_resources(gpus=4))
    assert step.ntasks == 4
    assert step.gpus == 4


def test_gpus_are_left_alone_when_there_are_enough():
    step = _make_step(ntasks=4, min_tasks=1, cpus_per_task=1, gpus=4)
    step.constrain_resources(_resources(gpus=8))
    assert step.ntasks == 4
    assert step.gpus == 4


def test_asking_for_gpus_on_a_machine_without_them_fails():
    step = _make_step(ntasks=1, cpus_per_task=1, gpus=1)
    with pytest.raises(ValueError, match='no GPUs are available'):
        step.constrain_resources(_resources(gpus=0))


def test_falling_below_the_minimum_gpus_fails():
    step = _make_step(
        ntasks=8, min_tasks=1, cpus_per_task=1, gpus=8, min_gpus=8
    )
    with pytest.raises(ValueError, match='below the minimum'):
        step.constrain_resources(_resources(gpus=4))


def test_falling_below_the_minimum_tasks_fails():
    step = _make_step(ntasks=8, min_tasks=8, cpus_per_task=1, gpus=8)
    with pytest.raises(ValueError, match='below the minimum'):
        step.constrain_resources(_resources(gpus=4))


def test_the_deprecated_form_constrains_the_same_way():
    """The translation has to leave the old behavior exactly as it was."""
    with pytest.warns(DeprecationWarning):
        step = _make_step(
            ntasks=8, min_tasks=1, cpus_per_task=1, gpus_per_task=1
        )
    step.constrain_resources(_resources(gpus=4))
    assert step.ntasks == 4
    assert step.gpus == 4


class _RecordingSystem:
    """A parallel system that records what it was asked to launch."""

    def __init__(self):
        self.calls = []

    def get_parallel_command(
        self, args, ntasks, cpus_per_task=0, gpus_per_task=0, placement=None
    ):
        self.calls.append(
            dict(
                args=args,
                ntasks=ntasks,
                cpus_per_task=cpus_per_task,
                gpus_per_task=gpus_per_task,
                placement=placement,
            )
        )
        return ['true']


def _run(component, **kwargs):
    component.run_parallel_command(
        args=['model'],
        cpus_per_task=1,
        openmp_threads=1,
        logger=logging.getLogger('test'),
        **kwargs,
    )
    return component.parallel_system.calls[-1]


def test_a_total_reaches_the_launcher_as_a_per_task_count():
    """
    mache expresses GPUs per task when there is no placement to carry a
    total, so the total has to be divided back out.
    """
    component = Component(name='ocean')
    component.parallel_system = _RecordingSystem()
    call = _run(component, ntasks=4, gpus=4)
    assert call['gpus_per_task'] == 1


def test_a_total_that_does_not_divide_evenly_rounds_up():
    component = Component(name='ocean')
    component.parallel_system = _RecordingSystem()
    call = _run(component, ntasks=4, gpus=6)
    assert call['gpus_per_task'] == 2


def test_no_gpus_asks_the_launcher_for_none():
    component = Component(name='ocean')
    component.parallel_system = _RecordingSystem()
    call = _run(component, ntasks=4, gpus=0)
    assert call['gpus_per_task'] == 0


def test_the_deprecated_per_task_argument_still_works():
    component = Component(name='ocean')
    component.parallel_system = _RecordingSystem()
    with pytest.warns(DeprecationWarning, match='gpus_per_task'):
        call = _run(component, ntasks=4, gpus_per_task=2)
    assert call['gpus_per_task'] == 2


def test_a_step_declares_no_memory_by_default():
    step = _make_step()
    assert step.max_memory is None
    assert step.min_memory is None


def test_a_step_declares_memory_as_a_target_and_a_minimum():
    step = _make_step(max_memory=8000, min_memory=2000)
    assert step.max_memory == 8000
    assert step.min_memory == 2000
    step.set_resources(max_memory=16000, min_memory=4000)
    assert step.max_memory == 16000
    assert step.min_memory == 4000


def test_needing_more_memory_than_it_asks_for_is_a_mistake():
    step = _make_step(
        ntasks=1, cpus_per_task=1, max_memory=1000, min_memory=2000
    )
    with pytest.raises(ValueError, match='at least 2000 MB'):
        step.constrain_resources(_resources())
