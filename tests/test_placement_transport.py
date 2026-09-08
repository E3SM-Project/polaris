"""
Tests for carrying a placement into the process that runs a step.

The scheduler decides which part of the allocation a step gets, and the step
runs in a process of its own, so the decision has to survive the crossing.
What these guard against most is the placement being *quietly* lost: a step
that runs on the whole allocation looks like it worked and oversubscribes
the machine beside everything else running.
"""

import pytest
from mache.parallel import ResourcePlacement

from polaris.run.placement import (
    PLACEMENT_VAR,
    placement_from_env,
    placement_to_env,
)


def _round_trip(placement):
    """Send a placement through the environment and read it back."""
    return placement_from_env(placement_to_env(placement))


def test_no_placement_carries_nothing():
    """A step run on its own adds no variable at all."""
    assert placement_to_env(None) == {}
    assert placement_from_env({}) is None


def test_a_placement_survives_the_crossing():
    placement = ResourcePlacement(
        nodes=('nid001', 'nid002'),
        cores=((0, 1, 2, 3), (0, 1, 2, 3)),
        gpus=0,
    )

    assert _round_trip(placement) == placement


def test_the_same_cores_on_each_node_survive():
    """Node-local numbering is the case the old flat shape could not hold."""
    placement = ResourcePlacement(
        nodes=('a', 'b'), cores=((8, 9), (8, 9)), gpus=0
    )

    carried = _round_trip(placement)

    assert carried.cores == ((8, 9), (8, 9))
    assert carried.total_cores == 4


def test_different_cores_on_each_node_survive():
    placement = ResourcePlacement(
        nodes=('a', 'b'), cores=((0, 1), (6, 7)), gpus=0
    )

    assert _round_trip(placement).cores == ((0, 1), (6, 7))


def test_gpus_survive_as_a_total():
    placement = ResourcePlacement(nodes=('a',), cores=((0, 1),), gpus=2)

    carried = _round_trip(placement)

    assert carried.gpus == 2
    assert carried.gpu_ids is None


def test_named_gpus_survive():
    """PALS has no scheduler to assign them, so the caller names them."""
    placement = ResourcePlacement(
        nodes=('x1',), cores=((1, 2),), gpus=2, gpu_ids=(4, 5)
    )

    assert _round_trip(placement).gpu_ids == (4, 5)


def test_a_placement_with_no_named_nodes_survives():
    placement = ResourcePlacement(nodes=(), cores=((2, 3),), gpus=0)

    carried = _round_trip(placement)

    assert carried.nodes == ()
    assert carried.cores == ((2, 3),)


def test_an_unreadable_placement_refuses_to_run_on_everything():
    """
    The failure this exists to prevent.  Treating a value that cannot be
    read as "no placement" would put the step on the whole allocation,
    where it would appear to work.
    """
    with pytest.raises(ValueError, match='Refusing to run it on all of it'):
        placement_from_env({PLACEMENT_VAR: 'not json'})


@pytest.mark.parametrize(
    'value',
    [
        '{"nodes": ["a"]}',
        '{"cores": [[0]]}',
        '{"nodes": ["a", "b"], "cores": [[0]]}',
        '{"nodes": ["a"], "cores": [[0]], "gpus": -1}',
        '[]',
    ],
)
def test_a_placement_that_does_not_make_sense_is_refused(value):
    """A truncated or inconsistent value is as dangerous as a corrupt one."""
    with pytest.raises(ValueError, match=PLACEMENT_VAR):
        placement_from_env({PLACEMENT_VAR: value})


def test_an_empty_variable_is_no_placement():
    """Set and empty is how an environment says nothing, not a failure."""
    assert placement_from_env({PLACEMENT_VAR: ''}) is None
