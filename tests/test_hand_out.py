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
from types import SimpleNamespace

import dask.array
import pytest

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run import STEP_COMPLETE_LOG
from polaris.run import residents as residents_module
from polaris.run import serial as serial_module
from polaris.run.allocation import NodeResources
from polaris.run.confinement import PLACEMENT_MISMATCH_LOG, check_confinement
from polaris.run.events import EventStream, read_events
from polaris.run.executor import reap_one, start_step
from polaris.run.graph import build_step_graph
from polaris.run.parallel import (
    _hands_out_work,
    _loop,
    _OnDemandResidents,
    _report,
)
from polaris.run.pieces import PIECES_SUMMARY
from polaris.run.pool import ResourcePool
from polaris.run.residents import Residents, stop_serial_residents
from polaris.run.serial import run_step_in_process

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


class _DaskSum(Step):
    """A step that computes with Dask on its cores."""

    def run_pieces(self, pieces):
        with pieces.dask():
            total = dask.array.ones((400, 400), chunks=100).sum().compute()
        with open(self.work_path('sum.txt'), 'w') as handle:
            handle.write(str(int(total)))


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


def test_a_step_computes_with_dask_as_the_scheduler_runs_it(
    tmp_path, residents
):
    step = _squares(tmp_path, kind=_DaskSum, name='dask_sum')
    outcome, log = _run(step, tmp_path, residents.directory)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, 'sum.txt')) as handle:
        assert handle.read() == '160000'
    assert 'started 1 Dask worker(s) with 2 thread(s)' in log


def test_a_step_computes_with_dask_under_polaris_serial(tmp_path):
    step = _squares(tmp_path, kind=_DaskSum, name='dask_sum')
    # polaris serial runs the step in its own process, but the test process
    # must never run Dask: what it forks afterwards would hang
    pid = os.fork()
    if pid == 0:
        status = 1
        try:
            run_step_in_process(step, quiet=True)
            status = 0
        finally:
            stop_serial_residents()
            os._exit(status)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    with open(os.path.join(step.work_dir, 'sum.txt')) as handle:
        assert handle.read() == '160000'


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
    squares = _squares(tmp_path)
    assert not _hands_out_work(build_step_graph([plain]))
    assert _hands_out_work(build_step_graph([plain, squares]))
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    on_demand = _OnDemandResidents(
        component=None,
        config=config,
        nodes=_node0(),
        pool=ResourcePool(_node0(), local_node='node0'),
        logger=logging.getLogger('test'),
        events=EventStream(),
        work_dir=str(tmp_path),
    )
    # nothing started until asked, and on one node, nothing to fork on
    assert on_demand.residents is None
    assert not on_demand.spans_nodes
    assert on_demand.start_timeout == 1800.0


def test_polaris_serial_starts_a_resident_for_a_step_that_hands_out_work(
    tmp_path,
):
    step = _squares(tmp_path)
    try:
        run_step_in_process(step, quiet=True)
        started = residents_module._SERIAL
        assert started is not None
        resident_pids = [facts['pid'] for facts in started.facts.values()]
    finally:
        stop_serial_residents()
    with open(os.path.join(step.work_dir, 'squares.txt')) as handle:
        assert handle.read() == '0,1,4,9,16'
    assert residents_module._SERIAL is None
    for pid in resident_pids:
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)


def test_the_run_records_and_reports_what_was_handed_out(
    tmp_path, residents, caplog
):
    step = _squares(tmp_path)
    outcomes, recorded = _drive(tmp_path, [step], residents)
    pieces = [event for event in recorded if event['event'] == 'step_pieces']
    assert len(pieces) == 1
    assert pieces[0]['pieces'] == 5 and pieces[0]['cores'] == 2
    assert pieces[0]['idle'] >= 0.0
    with caplog.at_level(logging.INFO, logger='report'):
        _report(
            outcomes, [], {step.path: step}, logging.getLogger('report'), 1.0
        )
    assert 'Handed-out work: 5 piece(s) from 1 step(s) on 1 node(s)' in (
        caplog.text
    )


def test_a_summary_from_an_earlier_run_is_not_reported(tmp_path, residents):
    step = _squares(tmp_path)
    stale = os.path.join(step.work_dir, PIECES_SUMMARY)
    with open(stale, 'w') as handle:
        handle.write('{"pieces": 99}')
    _drive(tmp_path, [step], residents)
    with open(stale) as handle:
        assert '"pieces": 5' in handle.read()


def test_the_run_reports_the_dask_workers_a_step_started(
    tmp_path, residents, caplog
):
    step = _squares(tmp_path, kind=_DaskSum, name='dask_sum')
    outcomes, recorded = _drive(tmp_path, [step], residents)
    assert outcomes[step.path].succeeded
    pieces = [event for event in recorded if event['event'] == 'step_pieces']
    assert pieces[0]['pieces'] == 0 and pieces[0]['dask_workers'] == 1
    with caplog.at_level(logging.INFO, logger='report'):
        _report(
            outcomes, [], {step.path: step}, logging.getLogger('report'), 1.0
        )
    assert 'Dask workers: 1, which took' in caplog.text


def test_polaris_serial_starts_residents_before_any_step(
    tmp_path, monkeypatch
):
    started: list = []
    monkeypatch.setattr(
        serial_module, 'start_serial_residents', started.append
    )
    plain = _squares(tmp_path, cores=1, kind=_Plain, name='plain')
    squares = _squares(tmp_path)
    task = SimpleNamespace(
        steps={'plain': plain, 'squares': squares},
        steps_to_run=['plain', 'squares'],
    )
    serial_module._start_residents_first({'task': task}, None, None)
    assert started == [squares]
    # nothing to start when the step that hands out work is skipped
    started.clear()
    serial_module._start_residents_first({'task': task}, None, ['squares'])
    serial_module._start_residents_first({'task': task}, ['plain'], None)
    assert started == []
