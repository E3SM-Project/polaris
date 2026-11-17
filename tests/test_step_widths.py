"""
Tests for how wide a step runs when steps share an allocation: from its
width, the geometric mean of its target and minimum, up to its target.
"""

from polaris import Component, Step
from polaris.run.allocation import NodeResources
from polaris.run.pool import ResourcePool
from polaris.run.width import StepWidths

_CORES = 64


def _pool():
    node = NodeResources(
        name='node0',
        cores=_CORES,
        gpus=0,
        memory=None,
        memory_source='available',
        memory_total=None,
        memory_configured=None,
    )
    return ResourcePool([node], local_node='node0')


def _available():
    return dict(
        cores=_CORES,
        nodes=1,
        cores_per_node=_CORES,
        gpus=0,
        gpus_per_node=0,
        memory=None,
        memory_per_node=None,
        mpi_allowed=True,
    )


def _step(name, ntasks, min_tasks):
    return Step(
        component=Component(name='ocean'),
        name=name,
        subdir=name,
        ntasks=ntasks,
        min_tasks=min_tasks,
    )


def _widths(*steps):
    """Record widths and targets as the concurrent runner does."""
    widths = StepWidths()
    widths.record_widths(steps)
    for step in steps:
        step.constrain_resources(_available())
    widths.record_targets(steps, _available())
    return widths


def _occupy(pool, cores):
    """Take some cores with a fixed-size step, as another running step."""
    other = _step('other', ntasks=cores, min_tasks=cores)
    other.constrain_resources(_available())
    assert pool.reserve(other) is not None


def test_a_step_on_an_idle_allocation_gets_its_target():
    elastic = _step('elastic', ntasks=64, min_tasks=4)
    widths = _widths(elastic)

    reservation = widths.reserve(_pool(), elastic)

    assert reservation is not None
    assert reservation.placement.total_cores == 64
    assert elastic.ntasks == 64


def test_a_step_on_a_busy_allocation_takes_what_is_free():
    """30 cores free is more than its width of 16, so it starts on 30."""
    elastic = _step('elastic', ntasks=64, min_tasks=4)
    widths = _widths(elastic)
    pool = _pool()
    _occupy(pool, 34)

    reservation = widths.reserve(pool, elastic)

    assert reservation is not None
    assert reservation.placement.total_cores == 30
    assert elastic.ntasks == 30


def test_a_step_waits_until_its_width_is_free():
    """10 cores free is less than its width of 16, though above its 4."""
    elastic = _step('elastic', ntasks=64, min_tasks=4)
    widths = _widths(elastic)
    pool = _pool()
    _occupy(pool, 54)

    assert widths.reserve(pool, elastic) is None
    # and it is left at its target, to be tried again later
    assert elastic.ntasks == 64


def test_a_step_that_cannot_shrink_waits_for_all_it_needs():
    fixed = _step('fixed', ntasks=32, min_tasks=32)
    widths = _widths(fixed)
    pool = _pool()
    _occupy(pool, 40)

    assert widths.reserve(pool, fixed) is None


def test_a_step_with_no_recorded_width_is_reserved_as_it_is():
    """What the loop does with steps it was not asked to size."""
    step = _step('plain', ntasks=8, min_tasks=1)
    step.constrain_resources(_available())

    reservation = StepWidths().reserve(_pool(), step)

    assert reservation is not None
    assert reservation.placement.total_cores == 8
