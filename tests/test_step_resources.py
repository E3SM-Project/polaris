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


def _resources(
    cores=64,
    cores_per_node=64,
    gpus=0,
    gpus_per_node=None,
    memory_per_node=None,
    mpi_allowed=True,
):
    nodes = max(1, cores // cores_per_node)
    if gpus_per_node is None:
        gpus_per_node = gpus
    return dict(
        cores=cores,
        nodes=nodes,
        cores_per_node=cores_per_node,
        gpus=gpus,
        gpus_per_node=gpus_per_node,
        memory=None if memory_per_node is None else memory_per_node * nodes,
        memory_per_node=memory_per_node,
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


def test_cores_cutting_the_tasks_first_does_not_cut_the_gpus_twice():
    """
    The GPU proportion is the one the step declared.

    By the time GPUs are constrained, `ntasks` may already have been cut back
    by the cores available.  Measuring one GPU per task against the reduced
    count makes each surviving task look like it needs two, and cuts the
    tasks again.
    """
    step = _make_step(ntasks=8, min_tasks=1, cpus_per_task=1, gpus=8)
    step.constrain_resources(_resources(cores=4, cores_per_node=4, gpus=4))
    assert step.ntasks == 4
    assert step.gpus == 4


def test_the_deprecated_form_survives_the_same_squeeze():
    """The per-task form is the behavior the total has to reproduce."""
    with pytest.warns(DeprecationWarning):
        step = _make_step(
            ntasks=8, min_tasks=1, cpus_per_task=1, gpus_per_task=1
        )
    step.constrain_resources(_resources(cores=4, cores_per_node=4, gpus=4))
    assert step.ntasks == 4
    assert step.gpus == 4


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
    assert step.memory is None
    assert step.min_memory is None


def test_a_step_declares_memory_as_a_target_and_a_minimum():
    step = _make_step(memory=8000, min_memory=2000)
    assert step.memory == 8000
    assert step.min_memory == 2000
    step.set_resources(memory=16000, min_memory=4000)
    assert step.memory == 16000
    assert step.min_memory == 4000


def test_needing_more_memory_than_it_asks_for_is_a_mistake():
    step = _make_step(ntasks=1, cpus_per_task=1, memory=1000, min_memory=2000)
    with pytest.raises(ValueError, match='at least 2000 MB'):
        step.constrain_resources(_resources())


def test_cores_are_the_product_when_a_step_speaks_in_ranks():
    step = _make_step(
        ntasks=4, min_tasks=2, cpus_per_task=8, min_cpus_per_task=4
    )
    assert step.cores == 32
    assert step.min_cores == 8


def test_a_step_can_state_its_cores_directly():
    """A non-MPI step has no meaningful number of ranks."""
    step = _make_step(cores=200, min_cores=16)
    assert step.cores == 200
    assert step.min_cores == 16


def test_stated_cores_do_not_move_with_the_task_count():
    step = _make_step(cores=200)
    step.ntasks = 8
    assert step.cores == 200


def test_derived_cores_follow_the_task_count():
    step = _make_step(ntasks=2, cpus_per_task=4)
    step.ntasks = 4
    assert step.cores == 16


def test_an_mpi_step_may_span_nodes_by_default():
    """A launcher spreading ranks is the one mechanism Polaris has today."""
    assert _make_step(ntasks=4).may_span_nodes


def test_a_single_task_step_may_not_span_by_default():
    assert not _make_step(ntasks=1).may_span_nodes
    assert not _make_step(cores=200).may_span_nodes


def test_a_step_can_say_it_spans_regardless_of_ranks():
    """What a distributed pool will set, and nothing sets in Phase A."""
    step = _make_step(cores=200, may_span_nodes=True)
    assert step.may_span_nodes
    step = _make_step(ntasks=4, may_span_nodes=False)
    assert not step.may_span_nodes


def test_set_resources_takes_the_new_fields():
    step = _make_step(ntasks=1)
    step.set_resources(cores=64, min_cores=8, may_span_nodes=True)
    assert step.cores == 64
    assert step.min_cores == 8
    assert step.may_span_nodes


# ---- the memory default ----


def test_a_step_that_says_nothing_gets_its_share_of_a_node():
    step = _make_step(ntasks=1, cpus_per_task=8)
    step.constrain_resources(
        _resources(cores=64, cores_per_node=64, memory_per_node=256000)
    )
    assert step.memory == 8 * 256000 // 64


def test_a_step_that_says_what_it_needs_keeps_it():
    step = _make_step(ntasks=1, cpus_per_task=8, memory=100)
    step.constrain_resources(
        _resources(cores=64, cores_per_node=64, memory_per_node=256000)
    )
    assert step.memory == 100


def test_no_default_where_the_machine_has_not_said_its_memory():
    """A wrong figure here would propagate into every step's default."""
    step = _make_step(ntasks=1, cpus_per_task=8)
    step.constrain_resources(_resources(cores=64, cores_per_node=64))
    assert step.memory is None


def test_defaulting_steps_pack_on_memory_exactly_as_they_pack_on_cores():
    """
    The property the default exists for.

    A run in which every step defaults must never be rejected by memory
    when cores would have accepted it, or introducing memory accounting
    would let Phase B schedule an existing suite worse than it does now.
    """
    cores_per_node = 64
    memory_per_node = 253000
    nodes = 3
    for core_counts in ([1] * 192, [8, 16, 32, 64], [3, 5, 7, 11, 13, 64]):
        memories = []
        for cores in core_counts:
            step = _make_step(ntasks=1, cpus_per_task=cores)
            step.constrain_resources(
                _resources(
                    cores=cores_per_node * nodes,
                    cores_per_node=cores_per_node,
                    memory_per_node=memory_per_node,
                )
            )
            memories.append(step.memory)
        fits_on_cores = sum(core_counts) <= cores_per_node * nodes
        fits_in_memory = sum(memories) <= memory_per_node * nodes
        assert fits_on_cores == fits_in_memory, core_counts


# ---- the node-span rule ----


def test_a_step_that_may_not_span_is_held_to_one_node():
    step = _make_step(cores=200, min_cores=1)
    step.constrain_resources(_resources(cores=192, cores_per_node=64))
    assert step.cores == 64


def test_a_step_that_may_span_is_held_to_the_allocation():
    step = _make_step(cores=200, min_cores=1, may_span_nodes=True)
    step.constrain_resources(_resources(cores=192, cores_per_node=64))
    assert step.cores == 192


def test_a_minimum_that_no_node_can_meet_is_an_error():
    """Not a silent reduction: the step has said it cannot run smaller."""
    step = _make_step(cores=200, min_cores=100)
    with pytest.raises(ValueError, match='may not use more than one node'):
        step.constrain_resources(_resources(cores=192, cores_per_node=64))


def test_that_same_minimum_is_fine_for_a_step_that_may_span():
    step = _make_step(cores=200, min_cores=100, may_span_nodes=True)
    step.constrain_resources(_resources(cores=192, cores_per_node=64))
    assert step.cores == 192


def test_an_mpi_step_still_spreads_across_the_allocation():
    """The rule must leave every step Polaris has today where it was."""
    step = _make_step(ntasks=192, min_tasks=1, cpus_per_task=1)
    step.constrain_resources(_resources(cores=192, cores_per_node=64))
    assert step.ntasks == 192


def test_gpus_are_held_to_one_node_for_a_step_that_may_not_span():
    step = _make_step(ntasks=1, cpus_per_task=1, gpus=8, min_gpus=1)
    step.constrain_resources(
        _resources(cores=192, cores_per_node=64, gpus=12, gpus_per_node=4)
    )
    assert step.gpus <= 4


def test_needing_more_gpus_than_a_node_has_is_the_same_error():
    step = _make_step(ntasks=1, cpus_per_task=1, gpus=8, min_gpus=8)
    with pytest.raises(ValueError, match='may not use more than one node'):
        step.constrain_resources(
            _resources(cores=192, cores_per_node=64, gpus=12, gpus_per_node=4)
        )
