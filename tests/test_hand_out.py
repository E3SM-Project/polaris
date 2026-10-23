"""
Tests for a step that hands out pieces of its work, run the way the
scheduler runs it.

The step is forked by the executor and goes through the same lifecycle as
any other, so its log, its outputs and its completion marker are checked as
well as its pieces.  A resident forked from the test process stands in for
the resident on the step's node.
"""

import logging
import os

import pytest

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run import STEP_COMPLETE_LOG
from polaris.run.allocation import NodeResources
from polaris.run.confinement import PLACEMENT_MISMATCH_LOG, check_confinement
from polaris.run.events import EventStream, read_events
from polaris.run.executor import reap_one, start_step
from polaris.run.graph import build_step_graph
from polaris.run.parallel import _loop, _start_residents
from polaris.run.pool import ResourcePool
from polaris.run.residents import Residents

PREAMBLE = 'Running step:'
FOOTER = 'execution:'


def square(value):
    return value * value


class _Plain(Step):
    """A step that does its own work, in its own process."""

    def run(self):
        with open(self.work_path('plain.txt'), 'w') as handle:
            handle.write('ran')


class _Squares(Step):
    """A step that hands out its work and writes down what came back."""

    def run_pieces(self, pieces):
        squares = pieces.map(square, range(5))
        with open(self.work_path('squares.txt'), 'w') as handle:
            handle.write(','.join(str(each) for each in squares))
        with open(self.work_path('own_cores.txt'), 'w') as handle:
            handle.write(str(len(os.sched_getaffinity(0))))


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['node0'])
        started.wait_until_ready(timeout=60)
        yield started


def _squares(tmp_path, cores=2, kind=None, name='squares'):
    kind = kind or _Squares
    step = kind(
        component=Component(name='ocean'), name=name, subdir=name, cores=cores
    )
    step.work_dir = str(tmp_path / name)
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)
    step.outputs = []

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, f'{name}.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    return step


def _node0():
    """This machine's own cores, as a node named as the resident is."""
    allowed = tuple(sorted(os.sched_getaffinity(0)))
    return [
        NodeResources(
            name='node0',
            cores=len(allowed),
            core_ids=allowed,
            gpus=0,
            memory=None,
            memory_source='available',
            memory_total=None,
            memory_configured=None,
        )
    ]


def _reserve(step):
    """A reservation on this machine's own cores, named as the resident."""
    step.memory_budget = None
    reservation = ResourcePool(_node0(), local_node='node0').reserve(step)
    assert reservation is not None
    return reservation


def _run(step, tmp_path, residents=None):
    log_filename = str(tmp_path / 'squares.log')
    running = start_step(
        step, _reserve(step), log_filename, 'node0', residents=residents
    )
    outcome = reap_one({step.path: running})
    with open(log_filename) as handle:
        return outcome, handle.read()


def test_a_step_hands_out_its_work_through_the_residents(tmp_path, residents):
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents.directory)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, 'squares.txt')) as handle:
        assert handle.read() == '0,1,4,9,16'
    assert PREAMBLE in log and FOOTER in log
    assert 'handing out 5 piece(s) of square over 2 core(s)' in log
    assert os.path.exists(os.path.join(step.work_dir, STEP_COMPLETE_LOG))


def test_its_own_process_is_not_bound_to_its_cores(tmp_path, residents):
    if len(os.sched_getaffinity(0)) < 3:
        pytest.skip('needs more cores than the step takes')
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents.directory)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, 'own_cores.txt')) as handle:
        assert int(handle.read()) == len(os.sched_getaffinity(0))


def test_a_step_that_hands_out_work_without_residents_says_so(tmp_path):
    step = _squares(tmp_path)
    outcome, log = _run(step, tmp_path, residents=None)
    assert not outcome.succeeded
    assert 'no residents were started' in log


def test_its_own_process_is_not_held_to_its_cores(tmp_path):
    step = _squares(tmp_path)
    step.placement = _reserve(step).placement
    check_confinement(step, logging.getLogger('test'))
    mismatch = os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG)
    assert not os.path.exists(mismatch)


class _Launcher:
    """A parallel system whose launch is a stand-in command run here."""

    def __init__(self, command):
        self._command = command

    def get_parallel_command(self, args, ntasks, cpus_per_task, placement):
        return list(self._command)


def _drive(tmp_path, steps, residents, start_timeout=1800.0):
    """Run the scheduler's loop over these steps, and read what it said."""
    for step in steps:
        step.memory_budget = None
    pool = ResourcePool(_node0(), local_node='node0')
    graph = build_step_graph(steps)
    path = str(tmp_path / 'events.jsonl')
    try:
        with EventStream(path) as events:
            outcomes, _ = _loop(
                graph,
                pool,
                {step.path: step for step in steps},
                logging.getLogger('test'),
                events,
                str(tmp_path),
                True,
                residents=residents,
                start_timeout=start_timeout,
            )
    finally:
        recorded = read_events(path)
    return outcomes, recorded


def test_the_scheduler_runs_a_step_that_hands_out_work(tmp_path, residents):
    step = _squares(tmp_path)
    outcomes, _ = _drive(tmp_path, [step], residents)
    assert outcomes[step.path].succeeded
    with open(os.path.join(step.work_dir, 'squares.txt')) as handle:
        assert handle.read() == '0,1,4,9,16'


def test_a_step_that_hands_out_work_waits_for_its_residents(tmp_path):
    squares = _squares(tmp_path)
    plain = _squares(tmp_path, cores=1, kind=_Plain, name='plain')
    residents = Residents()
    try:
        # a launch whose residents never say hello
        residents.launch(
            _Launcher(['sleep', '60']),
            ['node0'],
            core_id=0,
            log_filename=str(tmp_path / 'residents.log'),
            preload=(),
        )
        with pytest.raises(RuntimeError, match='Not every resident said'):
            _drive(tmp_path, [squares, plain], residents, start_timeout=3)
    finally:
        residents.stop()
    recorded = read_events(str(tmp_path / 'events.jsonl'))
    blocked = [
        event
        for event in recorded
        if event['event'] == 'step_blocked' and event['step'] == squares.path
    ]
    assert blocked and blocked[0]['reason'] == 'residents'
    finished = {
        event['step']: event['status']
        for event in recorded
        if event['event'] == 'step_finished'
    }
    # the step that does its own work did not wait
    assert finished == {plain.path: 'succeeded'}


def test_residents_that_go_away_before_hello_fail_the_run_at_once(tmp_path):
    residents = Residents()
    try:
        residents.launch(
            _Launcher(['false']),
            ['node0'],
            core_id=0,
            log_filename=str(tmp_path / 'residents.log'),
            preload=(),
        )
        with pytest.raises(RuntimeError, match='residents went away'):
            _drive(tmp_path, [_squares(tmp_path)], residents)
    finally:
        residents.stop()


def test_a_run_with_no_work_to_hand_out_starts_no_residents(tmp_path):
    plain = _squares(tmp_path, cores=1, kind=_Plain, name='plain')
    graph = build_step_graph([plain])
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    residents, timeout = _start_residents(
        component=None,
        config=config,
        nodes=_node0(),
        pool=ResourcePool(_node0(), local_node='node0'),
        graph=graph,
        logger=logging.getLogger('test'),
        events=EventStream(),
        work_dir=str(tmp_path),
    )
    assert residents is None
    assert timeout == 1800.0
