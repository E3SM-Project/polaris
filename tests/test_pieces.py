"""
Tests for handing out pieces of a step's work.

Two residents forked from the test process stand in for two nodes, and the
pieces are real children of theirs.  Concurrency is checked from the start
and end times the pieces themselves recorded, never from how long a call
took.
"""

import os
import signal
import socket
import time

import pytest
from mache.parallel import ResourcePlacement

from polaris import Component, Step
from polaris.run.confinement import PLACEMENT_MISMATCH_LOG
from polaris.run.pieces import PieceFailed, Pieces, slots_from
from polaris.run.residents import Residents

# what the pieces run, which must be importable from the residents just as a
# step's work must be


def add(first, second):
    return first + second


def where(index):
    return {
        'index': index,
        'parent': os.getppid(),
        'cores': sorted(os.sched_getaffinity(0)),
        'cwd': os.getcwd(),
    }


def span(seconds):
    began = time.time()
    time.sleep(seconds)
    return began, time.time()


def fail_on(index, bad):
    if index == bad:
        raise ValueError(f'item {index} is bad')
    return index


def fail_or_snooze(kind, path):
    if kind == 'fail':
        time.sleep(0.5)
        raise RuntimeError('this one fails')
    with open(path, 'w') as handle:
        handle.write(str(os.getpid()))
    time.sleep(60)


def leave(code):
    os._exit(code)


def take_my_resident_with_me(_):
    os.kill(os.getppid(), signal.SIGKILL)
    time.sleep(60)


def say(text):
    print(text)
    return text


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['nodeA', 'nodeB'])
        started.wait_until_ready(timeout=60)
        yield started


def _step(tmp_path):
    step = Step(component=Component(name='ocean'), name='maps', subdir='maps')
    step.work_dir = str(tmp_path)
    return step


def _two_cores():
    allowed = sorted(os.sched_getaffinity(0))
    return allowed[0], allowed[-1]


def _pieces(tmp_path, residents, slots=None):
    first, last = _two_cores()
    slots = slots or [('nodeA', first), ('nodeB', last)]
    return Pieces(_step(tmp_path), slots, residents.directory)


def _gone(pid, timeout=30):
    """Whether a process has exited, counting one awaiting its reaping."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(f'/proc/{pid}/stat') as handle:
                state = handle.read().rpartition(')')[2].split()[0]
        except OSError:
            return True
        if state == 'Z':
            return True
        time.sleep(0.05)
    return False


def test_results_come_back_in_the_order_of_the_items(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        assert pieces.map(add, [1, 2, 3], [10, 20, 30]) == [11, 22, 33]
    # nothing was said, so no logs, and no directory for them
    assert not os.path.exists(tmp_path / 'pieces')


def test_each_piece_runs_on_a_core_it_was_given(tmp_path, residents):
    first, last = _two_cores()
    with _pieces(tmp_path, residents) as pieces:
        results = pieces.map(where, range(6))
    parents = {
        first: residents.facts['nodeA']['pid'],
        last: residents.facts['nodeB']['pid'],
    }
    for result in results:
        assert len(result['cores']) == 1
        core = result['cores'][0]
        assert core in parents
        # the resident for the core's node forked it
        assert result['parent'] == parents[core]
        assert result['cwd'] == str(tmp_path)


def test_no_more_pieces_run_at_once_than_there_are_cores(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        spans = pieces.map(span, [0.3] * 6)
    moments = sorted(
        [(began, 1) for began, _ in spans] + [(end, -1) for _, end in spans]
    )
    current = peak = 0
    for _, change in moments:
        current += change
        peak = max(peak, current)
    assert peak == 2


def test_a_piece_that_raises_fails_the_call_and_names_itself(
    tmp_path, residents
):
    with _pieces(tmp_path, residents) as pieces:
        with pytest.raises(PieceFailed) as raised:
            pieces.map(fail_on, range(4), [2] * 4)
    assert raised.value.index == 2
    assert 'Piece 2 of step ocean/maps' in str(raised.value)
    assert 'ValueError: item 2 is bad' in str(raised.value)


def test_a_failure_stops_the_pieces_still_running(tmp_path, residents):
    noted = str(tmp_path / 'pid')
    began = time.time()
    with _pieces(tmp_path, residents) as pieces:
        with pytest.raises(PieceFailed, match='this one fails'):
            pieces.map(fail_or_snooze, ['snooze', 'fail'], [noted, noted])
    assert time.time() - began < 30
    with open(noted) as handle:
        assert _gone(int(handle.read()))


def test_a_piece_whose_process_dies_fails_the_call(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        with pytest.raises(PieceFailed, match='died with exit code 5'):
            pieces.map(leave, [5])


def test_a_piece_lost_with_its_resident_fails_the_call(tmp_path, residents):
    first, _ = _two_cores()
    with _pieces(tmp_path, residents, [('nodeA', first)]) as pieces:
        with pytest.raises(PieceFailed, match='resident on its node went'):
            pieces.map(take_my_resident_with_me, [0])


def test_an_empty_call_hands_out_nothing(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        assert pieces.map(add, [], []) == []
        assert pieces._connections == {}


def test_what_a_piece_says_is_kept_in_the_step(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        assert pieces.map(say, ['hello from a piece']) == [
            'hello from a piece'
        ]
    with open(tmp_path / 'pieces' / 'piece_0000.log') as handle:
        assert 'hello from a piece' in handle.read()


def test_a_stopped_piece_leaves_no_empty_log(tmp_path, residents):
    noted = str(tmp_path / 'pid')
    with _pieces(tmp_path, residents) as pieces:
        with pytest.raises(PieceFailed, match='piece_0001.log'):
            pieces.map(fail_or_snooze, ['snooze', 'fail'], [noted, noted])
    # the piece that was stopped said nothing, and the one that failed
    # left its traceback
    assert os.listdir(tmp_path / 'pieces') == ['piece_0001.log']


def test_a_lambda_is_refused_when_it_is_handed_out(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        with pytest.raises(TypeError, match='a function a module defines'):
            pieces.map(lambda item: item, [1])


def test_each_piece_is_recorded(tmp_path, residents):
    with _pieces(tmp_path, residents) as pieces:
        pieces.map(add, [1, 2, 3], [1, 2, 3])
    assert len(pieces.records) == 3
    assert {record['outcome'] for record in pieces.records} == {'done'}
    assert {record['node'] for record in pieces.records} <= {'nodeA', 'nodeB'}


def test_slots_come_from_a_placement():
    named = ResourcePlacement(nodes=('a', 'b'), cores=((0, 1), (2,)), gpus=0)
    assert slots_from(named) == [('a', 0), ('a', 1), ('b', 2)]
    unnamed = ResourcePlacement(nodes=(), cores=((3, 4),), gpus=0)
    assert slots_from(unnamed) == [('', 3), ('', 4)]


def test_a_piece_that_ran_off_its_core_is_reported(tmp_path, residents):
    step = _step(tmp_path)
    slots = [('nodeA', 10**6)]
    with Pieces(step, slots, residents.directory) as pieces:
        assert pieces.map(add, [1], [2]) == [3]
    with open(tmp_path / PLACEMENT_MISMATCH_LOG) as handle:
        report = handle.read()
    assert 'given core 1000000 on nodeA was allowed' in report


def test_pieces_that_ran_where_they_were_meant_to_leave_no_report(
    tmp_path, residents
):
    with _pieces(tmp_path, residents) as pieces:
        pieces.map(add, [1, 2], [3, 4])
    assert not os.path.exists(tmp_path / PLACEMENT_MISMATCH_LOG)
    assert {record['host'] for record in pieces.records} == {
        socket.gethostname().split('.')[0]
    }
