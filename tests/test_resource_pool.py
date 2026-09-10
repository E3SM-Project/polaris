"""
Tests for what the pool will and will not start.

Packing is where oversubscribing the machine would come from, so these
lean on the cases that distinguish a constraint from a total: cores free
across an allocation but not on any one node, memory that blocks a step
cores would admit, and GPUs that are free somewhere other than where the
cores are.

The last test is a property rather than a case.  It is the guarantee that
introducing memory accounting cannot degrade an existing suite, and it is
cheap to check against a core-only reference.
"""

import random

import pytest

from polaris import Component, Step
from polaris.run.allocation import NodeResources
from polaris.run.pool import ResourcePool


def _nodes(count=2, cores=64, gpus=0, memory=None):
    return [
        NodeResources(
            name=f'node{index}',
            cores=cores,
            gpus=gpus,
            memory=memory,
            memory_source='available',
            memory_total=memory,
            memory_configured=memory,
        )
        for index in range(count)
    ]


def _step(
    name,
    ntasks=None,
    cpus_per_task=1,
    cores=None,
    gpus=0,
    budget=None,
    may_span_nodes=None,
):
    """A step with its resources already fixed, as the scheduler leaves it."""
    component = Component(name='ocean')
    step = Step(
        component=component,
        name=name,
        subdir=name,
        ntasks=1 if ntasks is None else ntasks,
        cpus_per_task=cpus_per_task,
        cores=cores,
        gpus=gpus,
        may_span_nodes=may_span_nodes,
    )
    step.memory_budget = budget
    return step


def _reserve(pool, step):
    """Reserve, and say so as a test failure rather than as a type error."""
    reservation = pool.reserve(step)
    assert reservation is not None
    return reservation


def test_steps_that_all_fit_all_start():
    pool = ResourcePool(_nodes(count=2, cores=64))
    steps = [
        _step(f'step{index}', ntasks=32, may_span_nodes=True)
        for index in range(4)
    ]

    assert all(pool.reserve(step) is not None for step in steps)


def test_a_step_that_does_not_fit_waits():
    pool = ResourcePool(_nodes(count=1, cores=64))
    assert pool.reserve(_step('first', ntasks=64, may_span_nodes=True))
    assert pool.reserve(_step('second', ntasks=1, may_span_nodes=True)) is None


def test_what_a_step_held_comes_back():
    pool = ResourcePool(_nodes(count=1, cores=64))
    first = _reserve(pool, _step('first', ntasks=64, may_span_nodes=True))
    assert (
        pool.reserve(_step('second', ntasks=64, may_span_nodes=True)) is None
    )

    pool.release(first)

    assert pool.reserve(_step('second', ntasks=64, may_span_nodes=True))


def test_a_step_that_may_not_span_stays_on_the_scheduler_node():
    """It does its work in its own process, which is on that node."""
    pool = ResourcePool(_nodes(count=2, cores=64), local_node='node0')

    reservation = _reserve(pool, _step('step', cores=8))

    assert reservation.placement.nodes == ('node0',)
    assert reservation.placement.total_cores == 8


def test_a_step_that_may_not_span_waits_for_its_own_node():
    """Even with a whole node free elsewhere, which is the constraint."""
    pool = ResourcePool(_nodes(count=2, cores=64), local_node='node0')
    assert pool.reserve(_step('first', cores=64))

    assert pool.reserve(_step('second', cores=8)) is None


def test_cores_free_across_the_allocation_but_not_on_one_node():
    """
    The case that makes the span rule a constraint rather than a total.
    Eighty-eight cores are free and a hundred-core step cannot start,
    because no arrangement of the nodes serves its ranks.
    """
    pool = ResourcePool(_nodes(count=2, cores=64), local_node='node0')
    pool.reserve(_step('busy', cores=40))

    wide = _step('wide', ntasks=100, may_span_nodes=True)

    assert pool.reserve(wide) is None


def test_a_step_that_may_span_uses_several_nodes():
    pool = ResourcePool(_nodes(count=2, cores=64))

    reservation = _reserve(
        pool, _step('wide', ntasks=100, may_span_nodes=True)
    )

    assert len(reservation.placement.nodes) == 2
    assert reservation.placement.total_cores == 100
    # the launchers spread ranks evenly, so the nodes have to serve that
    assert [len(cores) for cores in reservation.placement.cores] == [50, 50]


def test_a_step_that_may_span_takes_no_more_nodes_than_it_must():
    pool = ResourcePool(_nodes(count=4, cores=64))

    reservation = _reserve(
        pool, _step('narrow', ntasks=8, may_span_nodes=True)
    )

    assert len(reservation.placement.nodes) == 1


def test_memory_blocks_a_step_that_cores_would_admit():
    pool = ResourcePool(_nodes(count=1, cores=64, memory=1000))
    assert pool.reserve(_step('first', cores=8, budget=900))

    second = _step('second', cores=8, budget=900)

    assert pool.reserve(second) is None


def test_a_step_declaring_less_than_its_share_packs_on_the_smaller_figure():
    """A measured step that needs little gets to run beside more."""
    pool = ResourcePool(_nodes(count=1, cores=64, memory=1000))

    steps = [_step(f'step{index}', cores=8, budget=200) for index in range(5)]

    assert all(pool.reserve(step) is not None for step in steps)


def test_memory_is_charged_where_the_cores_were_taken():
    pool = ResourcePool(_nodes(count=2, cores=64, memory=1000))

    reservation = _reserve(
        pool, _step('wide', ntasks=100, may_span_nodes=True, budget=1000)
    )

    assert reservation.memory == {'node0': 500, 'node1': 500}


def test_gpus_have_to_be_free_where_the_cores_are():
    pool = ResourcePool(_nodes(count=1, cores=64, gpus=4), local_node='node0')
    assert pool.reserve(_step('first', cores=1, gpus=4))

    assert pool.reserve(_step('second', cores=1, gpus=1)) is None


def test_a_step_on_one_node_names_the_devices_it_got():
    """PALS has no scheduler to assign them, so the caller names them."""
    pool = ResourcePool(_nodes(count=1, cores=64, gpus=4), local_node='node0')

    reservation = _reserve(pool, _step('step', cores=8, gpus=2))

    assert reservation.placement.gpus == 2
    assert reservation.placement.gpu_ids == (0, 1)


def test_a_step_that_spans_nodes_takes_the_same_devices_on_each():
    """
    Device numbers are node-local, so a launch spanning nodes uses the same
    ones on each.  Its placement leaves them unnamed, because a placement's
    indices have to match its GPU *total* and four devices on each of two
    nodes is four indices against a total of eight.
    """
    pool = ResourcePool(_nodes(count=2, cores=64, gpus=4))

    reservation = _reserve(
        pool,
        _step('wide', ntasks=16, cpus_per_task=8, gpus=8, may_span_nodes=True),
    )

    assert reservation.placement.gpus == 8
    assert reservation.placement.gpu_ids is None
    assert (
        reservation.gpus['node0']
        == reservation.gpus['node1']
        == (
            0,
            1,
            2,
            3,
        )
    )


def test_a_step_the_allocation_can_never_run_is_named():
    pool = ResourcePool(_nodes(count=2, cores=64))

    reason = pool.why_impossible(
        _step('huge', ntasks=1000, may_span_nodes=True)
    )

    assert reason is not None
    assert 'ocean/huge' in reason
    assert '1000 cores' in reason


def test_a_step_the_allocation_can_run_is_not_named():
    pool = ResourcePool(_nodes(count=2, cores=64))

    assert (
        pool.why_impossible(_step('fine', ntasks=64, may_span_nodes=True))
        is None
    )


def test_impossibility_is_asked_of_an_empty_allocation():
    """What is running now is not what decides whether a step could ever."""
    pool = ResourcePool(_nodes(count=1, cores=64))
    pool.reserve(_step('busy', ntasks=64, may_span_nodes=True))

    assert (
        pool.why_impossible(_step('fine', ntasks=64, may_span_nodes=True))
        is None
    )


def test_a_step_that_may_not_span_is_told_which_node_bound_it():
    pool = ResourcePool(_nodes(count=4, cores=64), local_node='node0')

    reason = pool.why_impossible(_step('wide', cores=200))

    assert reason is not None
    assert 'node0' in reason
    assert 'may span nodes' in reason


def test_the_steps_on_a_node_are_known():
    """What the report for a step killed by the node is built from."""
    pool = ResourcePool(_nodes(count=1, cores=64), local_node='node0')
    pool.reserve(_step('first', cores=8))
    second = _reserve(pool, _step('second', cores=8))

    assert pool.resident('node0') == ('ocean/first', 'ocean/second')

    pool.release(second)

    assert pool.resident('node0') == ('ocean/first',)


def test_a_machine_that_says_nothing_about_memory_packs_on_cores():
    pool = ResourcePool(_nodes(count=1, cores=64, memory=None))

    steps = [_step(f'step{index}', cores=16) for index in range(4)]

    assert all(pool.reserve(step) is not None for step in steps)


@pytest.mark.parametrize('seed', range(20))
def test_default_declarations_pack_exactly_as_cores_alone_do(seed):
    """
    The guarantee that memory accounting cannot degrade an existing suite.

    A step that declares nothing is budgeted at its proportional share of a
    node, so the memory inequality and the core inequality are the same
    inequality.  Packing a generated set of such steps must therefore admit
    exactly the steps that packing on cores alone admits, step for step.
    """
    random.seed(seed)
    cores_per_node = 64
    memory_per_node = 253000
    count = random.randint(1, 12)
    widths = [random.choice([1, 2, 4, 8, 16, 32, 64]) for _ in range(count)]

    with_memory = ResourcePool(
        _nodes(count=2, cores=cores_per_node, memory=memory_per_node)
    )
    cores_only = ResourcePool(_nodes(count=2, cores=cores_per_node))

    admitted_with_memory = []
    admitted_on_cores = []
    for index, width in enumerate(widths):
        budget = width * memory_per_node // cores_per_node
        step = _step(
            f'step{index}', ntasks=width, may_span_nodes=True, budget=budget
        )
        if with_memory.reserve(step) is not None:
            admitted_with_memory.append(index)

        bare = _step(f'step{index}', ntasks=width, may_span_nodes=True)
        if cores_only.reserve(bare) is not None:
            admitted_on_cores.append(index)

    assert admitted_with_memory == admitted_on_cores


def test_a_step_that_spans_nodes_takes_the_same_cores_on_each():
    """
    The only core numbering a launcher can be given for several nodes.

    Slurm's ``--cpu-bind=mask_cpu`` assigns masks by a task's index on its
    own node and reuses the list on every node, so the first node's masks
    are what every node applies.  Two nodes with different core sets means
    the second silently runs on the first one's cores -- measured on
    Chrysalis, where the launch succeeded and the pool went on believing
    cores were free that were not.
    """
    # node0 loses its first two cores to something else, so taking each
    # node's own first free cores would give the two nodes different numbers
    pool = ResourcePool(_nodes(count=2, cores=8))
    _reserve(pool, _step('resident', ntasks=2))

    # twelve cores, so it cannot fit on one node
    reservation = _reserve(
        pool, _step('wide', ntasks=6, cpus_per_task=2, may_span_nodes=True)
    )

    assert set(reservation.cores) == {'node0', 'node1'}
    assert reservation.cores['node0'] == reservation.cores['node1']


def test_uneven_ranks_still_take_a_prefix_of_the_same_cores():
    """
    A node with fewer ranks gets the front of the same list.

    That is what the launcher would apply to it in any case, since it takes
    the first masks of the one list it was given.
    """
    pool = ResourcePool(_nodes(count=2, cores=8))

    # five ranks of two cores over two nodes: three ranks on one, two on
    # the other, so the nodes want six cores and four
    reservation = _reserve(
        pool, _step('lopsided', ntasks=5, cpus_per_task=2, may_span_nodes=True)
    )

    first = reservation.cores['node0']
    second = reservation.cores['node1']
    shorter, longer = sorted((first, second), key=len)
    assert shorter == longer[: len(shorter)]


def test_nodes_without_cores_free_in_common_wait():
    """
    Correct rather than eager.

    The two nodes have four cores free each and none of them the same, so
    there is no placement a launcher could be given.  Refusing now is right;
    the step is not impossible, and a later moment may serve it.
    """
    pool = ResourcePool(_nodes(count=2, cores=8))
    # take the front of node0 and the back of node1, leaving disjoint halves
    first = pool.reserve(_step('front', ntasks=4))
    assert first is not None
    pool._nodes[1].free_cores = [0, 1, 2, 3]
    pool._nodes[0].free_cores = [4, 5, 6, 7]

    wide = _step('wide', ntasks=8, may_span_nodes=True)

    assert pool.reserve(wide) is None
    assert pool.why_impossible(wide) is None


def test_tasks_are_balanced_over_nodes_the_way_a_launcher_balances_them():
    """
    The launchers balance; they do not fill each node and leave a remainder.

    Getting this wrong under-reserves on the nodes that end up with more
    tasks than the model expected, so other steps are placed on cores that
    are already in use.  Measured on Chrysalis with omega_nightly on 13
    nodes: the last node was reserved 56 cores and Slurm put 61 tasks on it.
    """
    pool = ResourcePool(_nodes(count=13, cores=64))

    reservation = _reserve(
        pool, _step('wide', ntasks=800, may_span_nodes=True)
    )

    counts = sorted((len(c) for c in reservation.cores.values()), reverse=True)
    # 800 over 13 is seven nodes of 62 and six of 61 -- not twelve of 62 and
    # one of 56, which is what filling each node in turn would say
    assert counts == [62] * 7 + [61] * 6
    assert sum(counts) == 800


def test_an_even_division_is_unchanged():
    """
    The case that always worked, and hid the one above.

    Sized to need every node: a step is given the fewest nodes that can
    serve it, so 128 tasks would take two of these rather than four.
    """
    pool = ResourcePool(_nodes(count=4, cores=64))

    reservation = _reserve(
        pool, _step('even', ntasks=256, may_span_nodes=True)
    )

    counts = [len(c) for c in reservation.cores.values()]
    assert counts == [64, 64, 64, 64]
