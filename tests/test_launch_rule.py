"""
A step launches at most one thing, and only through its command.

The framework marks its launch of a step's command, and
`run_parallel_command()` refuses to launch anything else.  A launch from a
step's `run()` would not be confined to the step's part of the allocation,
and the placement check cannot see it, because its probe is launched with
the placement.  These tests are what keep the rule from eroding.
"""

import logging
import os

import pytest
from mache.parallel import ParallelSystem

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.parallel import is_launching_step_command, launching_step_command
from polaris.run.allocation import NodeResources
from polaris.run.executor import reap_one, start_step
from polaris.run.pool import ResourcePool


class _LaunchesFromRun(Step):
    """A step that breaks the rule by launching from its own run()"""

    def run(self):
        self.component.run_parallel_command(
            args=['true'],
            cpus_per_task=1,
            ntasks=1,
            openmp_threads=1,
            logger=self.logger,
        )


class _LaunchesItsCommand(Step):
    """A step that keeps the rule, launching only through its command"""

    def __init__(self, component, name, subdir):
        super().__init__(component=component, name=name, subdir=subdir)
        self.args = [['touch', 'launched.txt']]


def test_a_launch_outside_a_command_is_refused():
    component = Component(name='ocean')
    with pytest.raises(RuntimeError, match='only through its command'):
        component.run_parallel_command(
            args=['model'],
            cpus_per_task=1,
            ntasks=1,
            openmp_threads=1,
            logger=logging.getLogger('test'),
        )


def test_the_mark_covers_only_the_launch():
    assert not is_launching_step_command()
    with launching_step_command():
        assert is_launching_step_command()
    assert not is_launching_step_command()


def test_a_step_that_launches_from_run_fails(tmp_path, monkeypatch):
    """
    Run the way the scheduler runs a step with no command, in a forked
    child, which is where a launch would escape the step's placement.
    """
    _launch_without_a_launcher(monkeypatch)
    step = _make_step(tmp_path, _LaunchesFromRun, 'from_run')
    log_filename = str(tmp_path / 'from_run.log')

    running = start_step(step, _reserve(step), log_filename, 'node0')
    outcome = reap_one({step.path: running})

    assert not outcome.succeeded
    assert 'only through its command' in open(log_filename).read()


def test_a_step_that_launches_its_command_succeeds(tmp_path, monkeypatch):
    _launch_without_a_launcher(monkeypatch)
    step = _make_step(tmp_path, _LaunchesItsCommand, 'command')
    step.outputs = [os.path.join(step.work_dir, 'launched.txt')]
    log_filename = str(tmp_path / 'command.log')

    running = start_step(step, _reserve(step), log_filename, 'node0')
    outcome = reap_one({step.path: running})

    assert outcome.succeeded, f'the child failed: {open(log_filename).read()}'


def _launch_without_a_launcher(monkeypatch):
    """Run a command as it is, so no MPI launcher is needed"""

    def get_parallel_command(
        self,
        args,
        ntasks,
        cpus_per_task=0,
        gpus_per_task=0,
        placement=None,
        memory_cap=None,
    ):
        return args

    monkeypatch.setattr(
        ParallelSystem, 'get_parallel_command', get_parallel_command
    )


def _make_step(tmp_path, step_cls, name):
    """A step, set up as far as running one needs"""
    step = step_cls(component=Component(name='ocean'), name=name, subdir=name)
    step.work_dir = str(tmp_path / name)
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, f'{name}.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    return step


def _reserve(step):
    """A reservation for a step, from a pool with room for it"""
    nodes = [
        NodeResources(
            name='node0',
            cores=8,
            gpus=0,
            memory=None,
            memory_source='available',
            memory_total=None,
            memory_configured=None,
        )
    ]
    step.memory_budget = None
    pool = ResourcePool(nodes, local_node='node0')
    reservation = pool.reserve(step)
    assert reservation is not None
    return reservation
