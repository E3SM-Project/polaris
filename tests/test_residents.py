"""
Tests for the residents: one process per node that imports once and then
only forks.

These fork real residents from the test process, the way a run with only
one node starts its resident, and talk to them over real sockets.  Two
residents on one machine stand in for two nodes.
"""

import os
import pickle
import signal
import socket
import time
from multiprocessing import AuthenticationError
from multiprocessing.connection import wait

import pytest

from polaris.config import PolarisConfigParser
from polaris.run.connections import connect, new_key
from polaris.run.residents import (
    ResidentDirectory,
    Residents,
    resident_options,
)

# what the pieces below run, which must be importable from the residents
# just as a step's work must be


def add(first, second):
    return first + second


def where():
    return {
        'pid': os.getpid(),
        'parent': os.getppid(),
        'cores': sorted(os.sched_getaffinity(0)),
        'cwd': os.getcwd(),
    }


def fail(message):
    raise ValueError(message)


def leave(code):
    os._exit(code)


def note_and_snooze(path, seconds):
    with open(path, 'w') as handle:
        handle.write(str(os.getpid()))
    time.sleep(seconds)
    return 'woke'


def meddle():
    os.environ['POLARIS_TEST_MEDDLED'] = 'yes'
    os.chdir('/')
    return os.getpid()


def look():
    return {
        'meddled': os.environ.get('POLARIS_TEST_MEDDLED'),
        'cwd': os.getcwd(),
    }


def chatter():
    print('hello from a piece')
    return 'said'


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['nodeA'])
        started.wait_until_ready(timeout=60)
        yield started


def _client(residents, node='nodeA'):
    return connect(residents.directory.address(node), residents.key)


def _hand_out(conn, request_id, function, *args, **where_to_run):
    conn.send(
        (
            'piece',
            request_id,
            {'work': pickle.dumps((function, args, {})), **where_to_run},
        )
    )


def _answer(conn, timeout=60):
    assert conn.poll(timeout), 'the resident did not answer'
    return conn.recv()


def _pid_from(path, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path) as handle:
                return int(handle.read())
        time.sleep(0.02)
    raise AssertionError(f'{path} was never written')


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


def test_a_resident_says_hello_with_where_it_listens(residents):
    facts = residents.facts['nodeA']
    assert residents.ready
    assert residents.addresses['nodeA'] == tuple(facts['address'])
    assert facts['pid'] != os.getpid()
    # forking from it is only safe if it holds almost no threads
    assert 0 < facts['threads'] <= 4


def test_a_piece_runs_in_a_child_and_its_answer_comes_back(residents):
    conn = _client(residents)
    _hand_out(conn, 1, add, 2, 3)
    kind, request_id, payload = _answer(conn)
    assert (kind, request_id, payload['value']) == ('done', 1, 5)
    assert payload['pid'] != residents.facts['nodeA']['pid']


def test_a_piece_is_confined_to_the_cores_it_was_given(residents):
    core = sorted(os.sched_getaffinity(0))[-1]
    conn = _client(residents)
    _hand_out(conn, 1, where, cores=[core])
    _, _, payload = _answer(conn)
    assert payload['value']['cores'] == [core]


def test_a_piece_runs_in_the_work_directory_it_was_given(residents, tmp_path):
    conn = _client(residents)
    _hand_out(conn, 1, where, work_dir=str(tmp_path))
    _, _, payload = _answer(conn)
    assert payload['value']['cwd'] == str(tmp_path)


def test_a_piece_that_raises_says_why(residents):
    conn = _client(residents)
    _hand_out(conn, 7, fail, 'no such season')
    kind, request_id, payload = _answer(conn)
    assert (kind, request_id, payload['kind']) == ('failed', 7, 'ValueError')
    assert 'ValueError: no such season' in payload['error']


def test_a_piece_that_leaves_its_process_is_reported_as_dead(residents):
    conn = _client(residents)
    _hand_out(conn, 3, leave, 3)
    kind, request_id, payload = _answer(conn)
    assert (kind, request_id, payload['returncode']) == ('died', 3, 3)


def test_a_cancelled_piece_is_killed(residents, tmp_path):
    conn = _client(residents)
    noted = str(tmp_path / 'pid')
    _hand_out(conn, 1, note_and_snooze, noted, 60)
    _pid_from(noted)
    conn.send(('cancel', 1, None))
    kind, _, payload = _answer(conn)
    assert (kind, payload['returncode']) == ('died', -signal.SIGKILL)


def test_what_one_piece_changes_does_not_reach_the_next(residents):
    conn = _client(residents)
    _hand_out(conn, 1, meddle)
    assert _answer(conn)[0] == 'done'
    _hand_out(conn, 2, look)
    _, _, payload = _answer(conn)
    assert payload['value']['meddled'] is None
    assert payload['value']['cwd'] != '/'


def test_a_piece_keeps_its_log_only_if_it_said_something(residents, tmp_path):
    conn = _client(residents)
    said = str(tmp_path / 'pieces' / 'said.log')
    quiet = str(tmp_path / 'pieces' / 'quiet.log')
    _hand_out(conn, 1, chatter, log=said)
    _hand_out(conn, 2, add, 1, 1, log=quiet)
    answers = {}
    for _ in range(2):
        _, request_id, payload = _answer(conn)
        answers[request_id] = payload
    assert answers[1]['log'] == said
    with open(said) as handle:
        assert 'hello from a piece' in handle.read()
    assert answers[2]['log'] is None
    assert not os.path.exists(quiet)


def test_a_step_that_goes_away_takes_its_pieces_with_it(residents, tmp_path):
    conn = _client(residents)
    noted = str(tmp_path / 'pid')
    _hand_out(conn, 1, note_and_snooze, noted, 60)
    pid = _pid_from(noted)
    conn.close()
    assert _gone(pid)


def test_stopping_the_residents_leaves_nothing_running(tmp_path):
    with Residents() as residents:
        residents.start_local(['nodeA'])
        residents.wait_until_ready(timeout=60)
        resident = residents.facts['nodeA']['pid']
        conn = _client(residents)
        noted = str(tmp_path / 'pid')
        _hand_out(conn, 1, note_and_snooze, noted, 60)
        piece = _pid_from(noted)
    assert _gone(resident)
    assert _gone(piece)


def test_a_resident_whose_run_goes_away_stops(tmp_path):
    residents = Residents()
    try:
        residents.start_local(['nodeA'])
        residents.wait_until_ready(timeout=60)
        resident = residents.facts['nodeA']['pid']
        conn = _client(residents)
        noted = str(tmp_path / 'pid')
        _hand_out(conn, 1, note_and_snooze, noted, 60)
        piece = _pid_from(noted)
        # the run's end of the connection closing is what a resident
        # notices when the run is gone, however it went
        residents._control['nodeA'].close()
        assert _gone(resident)
        assert _gone(piece)
    finally:
        residents.stop()


def test_a_stranger_without_the_key_is_refused(residents):
    with pytest.raises(AuthenticationError):
        connect(residents.directory.address('nodeA'), new_key())
    conn = _client(residents)
    _hand_out(conn, 1, add, 1, 2)
    assert _answer(conn)[2]['value'] == 3


def test_each_resident_answers_for_its_own_node():
    with Residents() as residents:
        residents.start_local(['nodeA', 'nodeB'])
        residents.wait_until_ready(timeout=60)
        for node in ('nodeA', 'nodeB'):
            conn = _client(residents, node)
            _hand_out(conn, 1, where)
            _, _, payload = _answer(conn)
            assert payload['value']['parent'] == residents.facts[node]['pid']


def test_a_resident_that_dies_is_noticed():
    with Residents() as residents:
        residents.start_local(['nodeA'])
        residents.wait_until_ready(timeout=60)
        os.kill(residents.facts['nodeA']['pid'], signal.SIGKILL)
        deadline = time.time() + 30
        while 'nodeA' not in residents.lost and time.time() < deadline:
            for source in wait(residents.sources(), timeout=1.0):
                residents.hear(source)
        assert 'nodeA' in residents.lost
        assert 'nodeA' not in residents.directory.addresses


def test_a_directory_finds_a_node_by_its_short_name():
    directory = ResidentDirectory(
        key=b'key', addresses={'chr-0493': ('10.0.0.1', 4000)}
    )
    assert directory.address('chr-0493.lcrc.anl.gov') == ('10.0.0.1', 4000)
    # a run with no allocation names its only node ''
    assert directory.address('') == ('10.0.0.1', 4000)
    with pytest.raises(KeyError):
        directory.address('chr-0494')


def test_many_quick_pieces_all_answer(residents):
    """
    A child that answers and exits at once can be reaped before its answer
    is read, which once lost the answer and stopped the resident.
    """
    conn = _client(residents)
    for request_id in range(40):
        _hand_out(conn, request_id, add, request_id, 1)
    answers = {}
    for _ in range(40):
        kind, request_id, payload = _answer(conn)
        answers[request_id] = (kind, payload.get('value'))
    assert answers == {index: ('done', index + 1) for index in range(40)}


class _Launcher:
    """
    A parallel system whose launch is just the payload, so that one
    resident starts on this machine rather than one on each node.
    """

    def __init__(self, command=None):
        self.calls = []
        self._command = command

    def get_parallel_command(self, args, ntasks, cpus_per_task, placement):
        self.calls.append(
            {
                'args': list(args),
                'ntasks': ntasks,
                'cpus_per_task': cpus_per_task,
                'placement': placement,
            }
        )
        return self._command or list(args)


def _here():
    return socket.gethostname().split('.')[0]


def test_a_launch_starts_a_resident_on_each_node(tmp_path):
    core = sorted(os.sched_getaffinity(0))[0]
    launcher = _Launcher()
    with Residents() as residents:
        command = residents.launch(
            launcher,
            [_here()],
            core_id=core,
            log_filename=str(tmp_path / 'residents.log'),
            preload=(),
        )
        residents.wait_until_ready(timeout=600)
        assert residents.ready
    call = launcher.calls[0]
    assert (call['ntasks'], call['cpus_per_task']) == (1, 1)
    assert call['placement'].cores == ((core,),)
    assert call['placement'].gpus == 0
    # the key travels in the environment, never on a command line
    assert residents.key.hex() not in ' '.join(command)


def test_a_launch_that_fails_is_reported_at_once(tmp_path):
    with Residents() as residents:
        residents.launch(
            _Launcher(command=['false']),
            ['somewhere'],
            core_id=0,
            log_filename=str(tmp_path / 'residents.log'),
            preload=(),
        )
        began = time.time()
        with pytest.raises(RuntimeError, match='exited with 1 before every'):
            residents.wait_until_ready(timeout=600)
        assert time.time() - began < 60


def test_stopping_a_launch_leaves_nothing_running(tmp_path):
    with Residents() as residents:
        residents.launch(
            _Launcher(),
            [_here()],
            core_id=sorted(os.sched_getaffinity(0))[0],
            log_filename=str(tmp_path / 'residents.log'),
            preload=(),
        )
        residents.wait_until_ready(timeout=600)
        resident = residents.facts[_here()]['pid']
    assert residents.launcher_returncode is not None
    assert _gone(resident)


def test_resident_options_come_from_the_config():
    config = PolarisConfigParser()
    assert resident_options(config) == (None, 1800.0)
    config.add_from_package('polaris', 'default.cfg')
    assert resident_options(config) == (None, 1800.0)
    config.set('residents', 'interface', 'ib0')
    config.set('residents', 'start_timeout', '60')
    assert resident_options(config) == ('ib0', 60.0)


def test_a_piece_says_where_it_ran(residents):
    core = sorted(os.sched_getaffinity(0))[-1]
    conn = _client(residents)
    _hand_out(conn, 1, add, 1, 2, cores=[core])
    _, _, payload = _answer(conn)
    assert payload['where'] == {'host': _here(), 'cores': [core]}


def test_a_piece_given_a_core_it_cannot_have_still_runs(residents):
    conn = _client(residents)
    _hand_out(conn, 1, add, 1, 2, cores=[10**6])
    kind, _, payload = _answer(conn)
    assert (kind, payload['value']) == ('done', 3)
    assert payload['where']['cores'] != [10**6]
