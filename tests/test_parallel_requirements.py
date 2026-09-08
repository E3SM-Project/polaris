"""
Tests for what Polaris requires of mache.

Polaris depends on a mache that can confine a launch to part of an
allocation, and that says which cores a launch may use one node at a time.
Until that lands in a release, Polaris has to be deployed against the
branch, and the failure when it is not has to say so.
"""

import inspect

import pytest
from mache.parallel import ParallelSystem

from polaris.parallel import check_mache_supports_placement


def test_the_deployed_mache_supports_placement():
    """The environment this runs in has to be one Phase A can use."""
    check_mache_supports_placement()


def test_a_mache_without_placement_is_refused(monkeypatch):
    """
    A mache that cannot place would otherwise fail partway through a run,
    with a TypeError from inside the launcher rather than a reason.
    """

    def no_placement(self, args, ntasks, cpus_per_task=0, gpus_per_task=0):
        return []

    monkeypatch.setattr(ParallelSystem, 'get_parallel_command', no_placement)
    assert (
        'placement'
        not in inspect.signature(
            ParallelSystem.get_parallel_command
        ).parameters
    )
    with pytest.raises(RuntimeError, match='cannot confine a launch'):
        check_mache_supports_placement()


def test_a_mache_whose_placement_cores_are_flat_is_refused(monkeypatch):
    """
    A mache taking one flat set of cores for the whole launch cannot
    describe a launch spanning nodes on the machines that bind cores
    explicitly, since core numbers are node-local and it requires them to
    be unique.  Polaris has to hear that here rather than when the
    scheduler first places a step across nodes.
    """

    class _FlatCoresPlacement:
        def __init__(self, nodes, cores, gpus=0, gpu_ids=None):
            # what the older mache did: one set of unique ints
            self.cores = tuple(int(core) for core in cores)

    monkeypatch.setattr(
        'polaris.parallel.ResourcePlacement', _FlatCoresPlacement
    )
    with pytest.raises(RuntimeError, match='one set for the whole launch'):
        check_mache_supports_placement()


def test_a_placement_that_miscounts_its_cores_is_refused(monkeypatch):
    """
    Accepting the per-node shape and then meaning something else by it is
    the worse failure, because nothing about it looks wrong.
    """

    class _MiscountingPlacement:
        def __init__(self, nodes, cores, gpus=0, gpu_ids=None):
            self.cores = tuple(tuple(entry) for entry in cores)

        @property
        def total_cores(self):
            return 1

    monkeypatch.setattr(
        'polaris.parallel.ResourcePlacement', _MiscountingPlacement
    )
    with pytest.raises(RuntimeError, match='rather than 2'):
        check_mache_supports_placement()
