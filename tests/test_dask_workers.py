"""
Tests for a step that computes with Dask on its cores.

Two residents forked from the test process stand in for two nodes, and each
forks a real Dask worker that connects over TLS to a real scheduler in the
step's own process.  The step is forked as the scheduler forks it, and says
what it saw in a file, because the test process itself must never run Dask:
distributed keeps a thread pool whose thread does not survive a fork, so
anything forked after it has been used waits on it forever.
"""

import json
import os
import signal

import dask.array
import pytest
from distributed import KilledWorker

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run.allocation import NodeResources
from polaris.run.executor import reap_one, start_step
from polaris.run.pieces import PIECES_SUMMARY
from polaris.run.pool import ResourcePool
from polaris.run.residents import Residents

# what the workers run, which must be importable from them


def where_am_i(dask_worker):
    return {
        'pid': os.getpid(),
        'parent': os.getppid(),
        'cores': sorted(os.sched_getaffinity(0)),
        'threads': dask_worker.state.nthreads,
        'memory_limit': dask_worker.memory_manager.memory_limit,
        'cwd': os.getcwd(),
    }


def die(_):
    os.kill(os.getpid(), signal.SIGKILL)


class _Computes(Step):
    """Computes with Dask, and writes down where its workers were."""

    def run_pieces(self, pieces):
        with pieces.dask() as client:
            facts = list(client.run(where_am_i).values())
            total = dask.array.ones((1000, 1000), chunks=100).sum().compute()
            address = client.scheduler.address
        _write(self, {'facts': facts, 'total': int(total), 'address': address})


class _MapsAround(Step):
    """Tries to hand out pieces while its Dask workers hold its cores."""

    def run_pieces(self, pieces):
        with pieces.dask():
            try:
                pieces.map(abs, [-1])
                refused = None
            except RuntimeError as error:
                refused = str(error)
        _write(self, {'refused': refused, 'after': pieces.map(abs, [-1])})


class _LosesAWorker(Step):
    """Loses a worker under a task, and catches what Dask raises."""

    def run_pieces(self, pieces):
        with pieces.dask() as client:
            future = client.submit(die, 0, pure=False)
            try:
                future.result()
            except KilledWorker:
                _write(self, {'killed': True})


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['nodeA', 'nodeB'])
        started.wait_until_ready(timeout=60)
        yield started


def _write(step, facts):
    with open(step.work_path('facts.json'), 'w') as handle:
        json.dump(facts, handle)


def _read(step):
    with open(step.work_path('facts.json')) as handle:
        return json.load(handle)


def _two_nodes():
    """A core of this machine for each of two nodes named as the residents."""
    allowed = sorted(os.sched_getaffinity(0))
    return [
        NodeResources(
            name=name,
            cores=1,
            core_ids=(core,),
            gpus=0,
            memory=None,
            memory_source='available',
            memory_total=None,
            memory_configured=None,
        )
        for name, core in (('nodeA', allowed[0]), ('nodeB', allowed[-1]))
    ]


def _run(kind, tmp_path, residents, budget=None):
    """Run a step as the scheduler does, on a core of each node."""
    step = kind(
        component=Component(name='ocean'), name='big', subdir='big', cores=2
    )
    step.work_dir = str(tmp_path / 'big')
    step.base_work_dir = str(tmp_path)
    os.makedirs(step.work_dir, exist_ok=True)
    step.outputs = []
    step.memory_budget = budget
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.filepath = os.path.join(step.work_dir, 'big.cfg')
    with open(config.filepath, 'w') as handle:
        config.write(handle)
    step.config = config
    pool = ResourcePool(_two_nodes(), local_node='nodeA')
    reservation = pool.reserve(step)
    assert reservation is not None
    log_filename = str(tmp_path / 'big.log')
    running = start_step(
        step, reservation, log_filename, 'nodeA', residents.directory
    )
    outcome = reap_one({step.path: running})
    with open(log_filename) as handle:
        return step, outcome, handle.read()


def _gone(pid):
    """Whether a process has exited, counting one awaiting its reaping."""
    try:
        with open(f'/proc/{pid}/stat') as handle:
            state = handle.read().rpartition(')')[2].split()[0]
    except OSError:
        return True
    return state == 'Z'


def test_a_step_computes_through_a_worker_on_each_node(tmp_path, residents):
    step, outcome, log = _run(_Computes, tmp_path, residents)
    assert outcome.succeeded, log
    seen = _read(step)
    assert seen['total'] == 1_000_000
    assert seen['address'].startswith('tls://')
    parents = {
        residents.facts['nodeA']['pid'],
        residents.facts['nodeB']['pid'],
    }
    cores = {node.core_ids[0] for node in _two_nodes()}
    assert len(seen['facts']) == 2
    for fact in seen['facts']:
        # forked by a resident, on the one core it was given there
        assert fact['parent'] in parents
        assert len(fact['cores']) == 1 and fact['cores'][0] in cores
        assert fact['threads'] == 1
        assert fact['cwd'] == step.work_dir
    assert 'started 2 Dask worker(s) with 2 thread(s)' in log


def test_the_workers_are_gone_when_the_step_lets_them_go(tmp_path, residents):
    step, outcome, log = _run(_Computes, tmp_path, residents)
    assert outcome.succeeded, log
    for fact in _read(step)['facts']:
        assert _gone(fact['pid'])
    scratch = os.path.join(step.work_dir, 'dask', 'dask-scratch-space')
    assert not os.path.exists(scratch)


def test_each_worker_holds_its_node_share_of_the_memory(tmp_path, residents):
    step, outcome, log = _run(_Computes, tmp_path, residents, budget=3000)
    assert outcome.succeeded, log
    limits = [fact['memory_limit'] for fact in _read(step)['facts']]
    assert limits == [1500 * 2**20, 1500 * 2**20]


def test_pieces_cannot_be_handed_out_while_the_workers_hold_the_cores(
    tmp_path, residents
):
    step, outcome, log = _run(_MapsAround, tmp_path, residents)
    assert outcome.succeeded, log
    seen = _read(step)
    assert 'Dask workers hold' in seen['refused']
    # and they can be once the workers are gone
    assert seen['after'] == [1]


def test_a_worker_that_dies_fails_the_step_by_name(tmp_path, residents):
    step, outcome, log = _run(_LosesAWorker, tmp_path, residents)
    # the step caught what Dask raised, and failed anyway
    assert _read(step) == {'killed': True}
    assert not outcome.succeeded
    assert 'WorkerLost' in log
    assert 'died with exit code -9' in log
    assert 'on node nodeA' in log or 'on node nodeB' in log


def test_what_the_workers_cost_is_summarized(tmp_path, residents):
    step, outcome, log = _run(_Computes, tmp_path, residents)
    assert outcome.succeeded, log
    with open(os.path.join(step.work_dir, PIECES_SUMMARY)) as handle:
        summary = json.load(handle)
    assert summary['pieces'] == 0
    assert summary['dask_workers'] == 2
    assert summary['hosts'] == ['nodeA', 'nodeB']
    # the cores the workers held count as busy
    assert summary['busy_seconds'] > 0.0
