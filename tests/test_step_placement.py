"""
Tests for confining a step to part of its allocation.

Phase A adds the machinery for saying "run this here" and nothing that
decides where "here" is.  These tests therefore drive the placement in by
hand, the way a scheduler will in Phase B, and check two things: that a
placement reaches the launcher untouched, and that a step given one is told
about what it was given rather than about the whole job.
"""

import logging

import pytest
from mache.parallel import ResourcePlacement

from polaris import Component, Step


class _RecordingSystem:
    """A parallel system that records what it was asked to launch."""

    def __init__(self):
        self.calls = []
        self.cores = 192
        self.nodes = 3
        self.cores_per_node = 64
        self.gpus = 12
        self.gpus_per_node = 4
        self.mpi_allowed = True
        self.config = {'memory_per_node': 256000}

    def get_config_int(self, key, default=0):
        return self.config.get(key, default)

    def get_parallel_command(
        self, args, ntasks, cpus_per_task=0, gpus_per_task=0, placement=None
    ):
        self.calls.append(dict(placement=placement, ntasks=ntasks))
        return ['true']


def _make_component():
    component = Component(name='ocean')
    component.parallel_system = _RecordingSystem()
    return component


def _placement(nodes=('node0001',), cores=8, gpus=0):
    return ResourcePlacement(nodes=nodes, cores=tuple(range(cores)), gpus=gpus)


def test_a_step_is_not_confined_by_default():
    step = Step(component=Component(name='ocean'), name='step')
    assert step.placement is None


def test_no_placement_reaches_the_launcher_as_none():
    """A step that does not ask to be confined gets today's command."""
    component = _make_component()
    component.run_parallel_command(
        args=['model'],
        cpus_per_task=1,
        ntasks=2,
        openmp_threads=1,
        logger=logging.getLogger('test'),
    )
    assert component.parallel_system.calls[-1]['placement'] is None


def test_a_placement_reaches_the_launcher_untouched():
    component = _make_component()
    placement = _placement()
    component.run_parallel_command(
        args=['model'],
        cpus_per_task=1,
        ntasks=2,
        openmp_threads=1,
        logger=logging.getLogger('test'),
        placement=placement,
    )
    assert component.parallel_system.calls[-1]['placement'] is placement


def test_a_placement_that_disagrees_about_gpus_is_refused():
    """
    A placement carries the GPUs itself, so the two saying different things
    means whatever built the placement has drifted from the step.
    """
    component = _make_component()
    with pytest.raises(ValueError, match='They must agree'):
        component.run_parallel_command(
            args=['model'],
            cpus_per_task=1,
            ntasks=2,
            openmp_threads=1,
            logger=logging.getLogger('test'),
            gpus=2,
            placement=_placement(gpus=1),
        )


def test_resources_without_a_placement_are_the_whole_allocation():
    component = _make_component()
    resources = component.get_available_resources()
    assert resources['cores'] == 192
    assert resources['nodes'] == 3
    assert resources['gpus'] == 12


def test_resources_with_a_placement_are_only_what_it_gives():
    component = _make_component()
    resources = component.get_available_resources(
        _placement(nodes=('node0001', 'node0002'), cores=8, gpus=4)
    )
    assert resources['cores'] == 16
    assert resources['nodes'] == 2
    assert resources['cores_per_node'] == 8
    assert resources['gpus'] == 4
    assert resources['gpus_per_node'] == 2
    assert resources['mpi_allowed'] is True


def test_a_confined_step_is_sized_by_its_placement():
    """The point of the view: the step must not size itself on the job."""
    component = _make_component()
    step = Step(component=component, name='step', ntasks=1, cpus_per_task=64)
    resources = component.get_available_resources(_placement(cores=8))
    step.constrain_resources(resources)
    assert step.cpus_per_task == 8


def test_cores_are_capped_at_one_node_today():
    """
    Pin the behavior Polaris has always had, which is under review.

    `cpus_per_task` is capped at one node's cores for every step, and for a
    single-task step that is the whole core count, so such a step can never
    be given more than one node's worth.  That is right for a step whose
    parallelism is shared-memory -- `viz_combine_topo` sets numba's thread
    count from it -- and wrong for one driving a distributed scheduler,
    which is what the analysis work will do.  Polaris cannot currently tell
    the two apart.

    This is not an endorsement, it is a tripwire: whoever changes the cap
    should have to change this too, deliberately.
    """
    component = _make_component()
    step = Step(component=component, name='step', ntasks=1, cpus_per_task=192)
    step.constrain_resources(component.get_available_resources())
    assert step.cpus_per_task == 64


def test_the_resource_view_carries_memory():
    """
    Phase C sizes worker memory from this, and the mistake it prevents is
    deriving memory from cores.
    """
    component = _make_component()
    resources = component.get_available_resources()
    assert resources['memory_per_node'] == 256000
    assert resources['memory'] == 256000 * 3


def test_a_placement_carries_a_share_of_the_memory_it_took():
    """A placement has no memory of its own; no launcher acts on one."""
    component = _make_component()
    resources = component.get_available_resources(
        _placement(nodes=('node0001',), cores=32)
    )
    # half a node's cores, so half a node's memory
    assert resources['memory'] == 128000
    assert resources['memory_per_node'] == 256000


def test_memory_is_left_undeclared_where_a_machine_has_not_said():
    component = _make_component()
    component.parallel_system.config = {}
    resources = component.get_available_resources()
    assert resources['memory'] is None
    assert resources['memory_per_node'] is None
