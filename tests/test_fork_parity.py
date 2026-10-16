"""
What a forked child produces, held against what the serial path produces.

A step run concurrently has to be the same step. The failure mode worth
guarding is not results drifting -- a first attempt at forking produced
science output identical digit for digit -- but the *log* quietly losing its
preamble and footer, because the child called the step's own `run()` rather
than the wrapper `polaris serial` puts around it. Nobody notices that until
they go looking for a step that did not run.

These use a real `Step` rather than a shell script, since the wrapper is
what is under test.
"""

import os
import re
import time

import pytest

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run import STEP_COMPLETE_LOG
from polaris.run.allocation import NodeResources
from polaris.run.executor import reap_one, start_step
from polaris.run.parallel import _abandon
from polaris.run.pool import ResourcePool
from polaris.run.serial import run_step_in_process

# the two lines the wrapper adds around a step's own work, and the ones a
# first attempt at forking lost
PREAMBLE = 'Running step:'
FOOTER = 'execution:'


class _Writer(Step):
    """A step that leaves something behind, so its outputs can be compared."""

    def run(self):
        with open('made.txt', 'w') as handle:
            handle.write('the step ran')


def _writer(tmp_path, name):
    """A real step, set up as far as running one needs."""
    step = _Writer(component=Component(name='ocean'), name=name, subdir=name)
    step.work_dir = str(tmp_path / name)
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)
    step.outputs = [os.path.join(step.work_dir, 'made.txt')]

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, f'{name}.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    return step


def _reserve(step):
    """A reservation for a step, from a pool with room for it."""
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


def _tidy(text):
    """Strip what cannot match between two runs: timings, colours, paths."""
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    text = re.sub(r'\d+:\d\d:\d\d', '<time>', text)
    return re.sub(r'/\S*?/(?=\w+\.cfg|\w+\.log)', '<path>/', text)


def test_a_forked_child_writes_the_log_the_serial_path_writes(tmp_path):
    """The preamble and footer, which are what a first attempt lost."""
    forked = _writer(tmp_path, 'forked')
    log_filename = str(tmp_path / 'forked.log')

    running = start_step(forked, _reserve(forked), log_filename, 'node0')
    outcome = reap_one({forked.path: running})

    assert outcome.succeeded, f'the child failed: {open(log_filename).read()}'
    log = open(log_filename).read()
    assert PREAMBLE in log, f'no step preamble in the log:\n{log}'
    assert FOOTER in log, f'no execution footer in the log:\n{log}'
    assert 'runtime:' in log


def test_a_forked_child_leaves_what_the_serial_path_leaves(tmp_path):
    """Outputs and the completion marker, which a rerun depends on."""
    forked = _writer(tmp_path, 'forked')
    running = start_step(
        forked, _reserve(forked), str(tmp_path / 'forked.log'), 'node0'
    )
    assert reap_one({forked.path: running}).succeeded

    serial = _writer(tmp_path, 'serial')
    here = os.getcwd()
    try:
        os.chdir(serial.work_dir)
        run_step_in_process(serial)
    finally:
        os.chdir(here)

    for name in ('made.txt', STEP_COMPLETE_LOG):
        forked_path = os.path.join(forked.work_dir, name)
        serial_path = os.path.join(serial.work_dir, name)
        assert os.path.exists(forked_path), f'the child left no {name}'
        assert os.path.exists(serial_path), f'the serial path left no {name}'

    with open(os.path.join(forked.work_dir, 'made.txt')) as handle:
        assert handle.read() == 'the step ran'


def test_a_child_that_fails_says_so_rather_than_hanging(tmp_path):
    """A step that raises has to be reaped, not waited on forever."""

    class _Raiser(_Writer):
        def run(self):
            raise RuntimeError('this step does not work')

    step = _writer(tmp_path, 'raiser')
    step.__class__ = _Raiser
    step.outputs = []
    log_filename = str(tmp_path / 'raiser.log')

    running = start_step(step, _reserve(step), log_filename, 'node0')
    outcome = reap_one({step.path: running})

    assert not outcome.succeeded
    assert not outcome.terminated
    assert 'this step does not work' in open(log_filename).read()


@pytest.mark.parametrize('cores', [1, 2, 4])
def test_a_child_is_confined_to_the_cores_it_was_given(tmp_path, cores):
    """The affinity the child sets for itself, since nothing else can."""
    if len(os.sched_getaffinity(0)) < 4:
        pytest.skip('need four cores to place a step on fewer')

    class _Reporter(_Writer):
        def run(self):
            with open('made.txt', 'w') as handle:
                handle.write(f'{len(os.sched_getaffinity(0))}')

    step = _writer(tmp_path, f'reporter{cores}')
    step.__class__ = _Reporter
    step.cpus_per_task = cores
    step.min_cpus_per_task = 1

    running = start_step(
        step, _reserve(step), str(tmp_path / 'reporter.log'), 'node0'
    )
    assert reap_one({step.path: running}).succeeded

    with open(os.path.join(step.work_dir, 'made.txt')) as handle:
        assert int(handle.read()) == cores


class _Quiet:
    """A logger and an event stream that say nothing."""

    def warning(self, *args, **kwargs):
        pass

    def record(self, *args, **kwargs):
        pass


def test_a_torn_down_run_leaves_nothing_running(tmp_path):
    """
    A forked child is a direct child of the scheduler.

    An interrupt that left one running would leave a step holding cores with
    nothing watching it, and a child never reaped is a zombie for as long as
    the scheduler lives.
    """

    class _Sleeper(_Writer):
        def run(self):
            time.sleep(120)

    step = _writer(tmp_path, 'sleeper')
    step.__class__ = _Sleeper
    step.outputs = []
    running = {
        step.path: start_step(
            step, _reserve(step), str(tmp_path / 'sleeper.log'), 'node0'
        )
    }
    pid = running[step.path].pid

    _abandon(running, _Quiet(), _Quiet())

    assert running == {}
    # reaped rather than left a zombie, so the pid is gone entirely
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    raise AssertionError(f'pid {pid} is still there after tearing down')
