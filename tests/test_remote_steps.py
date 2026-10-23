"""
Tests for a step that launches nothing being forked on another node.

Two residents forked from the test process stand in for the residents of
two nodes, each node offered one core of this machine.  The scheduler's own
node is full once one step runs there, so the next step goes to the other
node, where its resident forks it.
"""

import json
import logging
import os
import signal
import time
from types import SimpleNamespace

import pytest

from polaris import Step
from polaris.config import PolarisConfigParser
from polaris.run import parallel as parallel_module
from polaris.run.allocation import NodeResources
from polaris.run.events import EventStream, read_events
from polaris.run.graph import build_step_graph
from polaris.run.parallel import _forks_anywhere, _loop, _start_residents
from polaris.run.pool import ResourcePool
from polaris.run.residents import Residents
from tests.test_hand_out import _squares


class _WhereAmI(Step):
    """Writes down where it ran, and waits a moment so the other runs too."""

    def run(self):
        with open(self.work_path('where.json'), 'w') as handle:
            json.dump(
                {
                    'parent': os.getppid(),
                    'cores': sorted(os.sched_getaffinity(0)),
                    'cwd': os.getcwd(),
                },
                handle,
            )


class _Raises(Step):
    """Fails on purpose."""

    def run(self):
        raise ValueError('this step fails on purpose')


class _Sleeps(Step):
    """Keeps the scheduler's node busy for a while."""

    def run(self):
        time.sleep(3)


class _TakesItsResident(Step):
    """Takes the resident that forked it, and so itself, with it."""

    def run(self):
        os.kill(os.getppid(), signal.SIGKILL)


@pytest.fixture
def residents():
    with Residents() as started:
        started.start_local(['node0', 'node1'])
        started.wait_until_ready(timeout=60)
        yield started


def _two_nodes():
    """One core of this machine for each of two nodes."""
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 2:
        pytest.skip('needs two cores')
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
        for name, core in (('node0', allowed[0]), ('node1', allowed[1]))
    ]


def _drive(tmp_path, steps, residents):
    """Run the scheduler's loop over these steps on the two nodes."""
    for step in steps:
        step.memory_budget = None
    pool = ResourcePool(_two_nodes(), local_node='node0')
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
            )
    finally:
        recorded = read_events(path)
    nodes = {
        event['step']: event['nodes']
        for event in recorded
        if event['event'] == 'step_started'
    }
    return outcomes, nodes


def _pair(tmp_path, kind):
    """A step for the scheduler's node, and one of a kind for the other."""
    here = _squares(tmp_path, cores=1, kind=_WhereAmI, name='here')
    there = _squares(tmp_path, cores=1, kind=kind, name='there')
    return here, there


def test_a_step_with_no_room_here_is_forked_by_another_nodes_resident(
    tmp_path, residents
):
    here, there = _pair(tmp_path, _WhereAmI)
    outcomes, nodes = _drive(tmp_path, [here, there], residents)
    assert outcomes[here.path].succeeded
    assert outcomes[there.path].succeeded
    assert nodes == {here.path: ['node0'], there.path: ['node1']}
    with open(there.work_path('where.json')) as handle:
        where = json.load(handle)
    # forked by the resident for node1, on node1's core, in its work dir
    assert where['parent'] == residents.facts['node1']['pid']
    assert where['cores'] == [_two_nodes()[1].core_ids[0]]
    assert where['cwd'] == there.work_dir
    assert outcomes[there.path].work_seconds is not None


def test_a_step_forked_elsewhere_that_fails_fails_the_run(tmp_path, residents):
    here, there = _pair(tmp_path, _Raises)
    outcomes, nodes = _drive(tmp_path, [here, there], residents)
    assert nodes[there.path] == ['node1']
    assert not outcomes[there.path].succeeded
    with open(tmp_path / 'case_outputs' / 'ocean_there.log') as handle:
        assert 'this step fails on purpose' in handle.read()


def test_a_step_lost_with_its_resident_fails_and_says_so(tmp_path, residents):
    here, there = _pair(tmp_path, _TakesItsResident)
    outcomes, nodes = _drive(tmp_path, [here, there], residents)
    assert nodes[there.path] == ['node1']
    assert not outcomes[there.path].succeeded
    with open(tmp_path / 'case_outputs' / 'ocean_there.log') as handle:
        assert 'went away' in handle.read()


def test_only_a_step_that_launches_nothing_is_forked_elsewhere(tmp_path):
    plain = _squares(tmp_path, cores=1, kind=_WhereAmI, name='plain')
    assert _forks_anywhere(plain)
    plain.args = []
    assert not _forks_anywhere(plain)


def test_a_node_whose_resident_has_gone_is_not_offered_again(
    tmp_path, residents
):
    here = _squares(tmp_path, cores=1, kind=_Sleeps, name='here')
    there = _squares(tmp_path, cores=1, kind=_TakesItsResident, name='there')
    later = _squares(tmp_path, cores=1, kind=_WhereAmI, name='later')
    outcomes, nodes = _drive(tmp_path, [here, there, later], residents)
    assert nodes[there.path] == ['node1']
    assert not outcomes[there.path].succeeded
    # node1 had room again once its step was lost, but no resident to fork
    # anything there, so the last step waited for the scheduler's node
    assert outcomes[later.path].succeeded
    assert nodes[later.path] == ['node0']


def test_a_run_on_two_nodes_starts_residents_for_steps_that_launch_nothing(
    tmp_path, monkeypatch
):
    launched = []
    monkeypatch.setattr(
        Residents,
        'launch',
        lambda self, system, names, *args, **kwargs: launched.append(names),
    )
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    plain = _squares(tmp_path, cores=1, kind=_WhereAmI, name='plain')
    nodes = _two_nodes()
    pool = ResourcePool(nodes, local_node='node0')

    def start(steps):
        residents, _ = _start_residents(
            component=SimpleNamespace(parallel_system=None),
            config=config,
            nodes=nodes,
            pool=pool,
            graph=build_step_graph(steps),
            logger=logging.getLogger('test'),
            events=EventStream(),
            work_dir=str(tmp_path),
        )
        return residents

    assert start([plain]) is not None
    assert launched == [['node0', 'node1']]
    # a step that launches has nothing for a resident to do
    plain.args = [['true']]
    launched.clear()
    assert start([plain]) is None
    assert launched == []


def test_a_launched_step_placed_elsewhere_is_still_started_here(
    tmp_path, monkeypatch
):
    started = []

    def record(how):
        def start(step, *args, **kwargs):
            started.append((step.name, how))
            return SimpleNamespace(pid=None)

        return start

    monkeypatch.setattr(parallel_module, 'start_step', record('here'))
    monkeypatch.setattr(
        parallel_module, 'start_remote_step', record('resident')
    )
    plain = _squares(tmp_path, cores=1, kind=_WhereAmI, name='plain')
    launched = _squares(tmp_path, cores=1, kind=_WhereAmI, name='launched')
    launched.args = [['true']]
    launched.may_span_nodes = True
    for step in (plain, launched):
        step.memory_budget = None
    pool = ResourcePool(_two_nodes(), local_node='node0')
    graph = build_step_graph([plain, launched])
    ready = SimpleNamespace(
        ready=True,
        reaches=lambda name: True,
        directory=None,
        inherited=lambda: (),
    )
    parallel_module._start_what_fits(
        graph,
        pool,
        {plain.path, launched.path},
        {},
        set(),
        {},
        logging.getLogger('test'),
        EventStream(),
        str(tmp_path),
        True,
        residents=ready,
    )
    # the plain step took the scheduler's node, and the launched one was
    # placed on node1 but forked here, to launch its work there
    assert started == [('plain', 'here'), ('launched', 'here')]
