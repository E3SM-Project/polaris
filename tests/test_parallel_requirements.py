"""
Tests for what Polaris requires of mache.

Phase A depends on a mache that can confine a launch to part of an
allocation.  Until that lands in a release, Polaris has to be deployed
against the branch, and the failure when it is not has to say so.
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
