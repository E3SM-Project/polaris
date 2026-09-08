"""
Tests for the loop that runs steps at the same time.

These start real processes, so the concurrency is real: what a step does is
a shell script written into its work directory, which is the only thing
faked.  Running an actual Polaris step needs a suite that has been set up,
and that is what the on-machine testing is for.

Overlap is checked from the start and end times the run recorded, never
from how long the whole thing took.  A test that concluded "it was faster,
so it must have overlapped" would pass on a machine where nothing
overlapped at all.
"""

import os

import pytest

from polaris import Component, Step
from polaris.run import STEP_COMPLETE_LOG
from polaris.run.allocation import NodeResources
from polaris.run.events import EventStream, read_events
from polaris.run.graph import build_step_graph
from polaris.run.parallel import _credit_memory, _loop
from polaris.run.pool import ResourcePool

# what each synthetic step's process runs, in its own work directory
STEP_SCRIPT = 'run.sh'


@pytest.fixture(autouse=True)
def _run_the_script(monkeypatch):
    """Make a step's process run its own script rather than polaris."""
    monkeypatch.setattr(
        'polaris.run.executor.STEP_COMMAND', ['sh', STEP_SCRIPT]
    )


def _nodes(count=1, cores=8):
    return [
        NodeResources(
            name=f'node{index}',
            cores=cores,
            gpus=0,
            memory=None,
            memory_source='available',
            memory_total=None,
            memory_configured=None,
        )
        for index in range(count)
    ]


def _step(tmp_path, name, body, cores=1, inputs=(), outputs=()):
    """A step whose process runs ``body``."""
    step = Step(
        component=Component(name='ocean'),
        name=name,
        subdir=name,
        cores=cores,
    )
    step.work_dir = str(tmp_path / name)
    os.makedirs(step.work_dir, exist_ok=True)
    step.inputs = [str(path) for path in inputs]
    step.outputs = [str(path) for path in outputs]
    step.memory_budget = None
    with open(os.path.join(step.work_dir, STEP_SCRIPT), 'w') as handle:
        handle.write(body)
    return step


def _run(tmp_path, steps, nodes=None):
    """Drive the loop over these steps and give back what it recorded."""
    import logging

    nodes = nodes or _nodes()
    pool = ResourcePool(nodes, local_node=nodes[0].name)
    graph = build_step_graph(steps)
    events_path = str(tmp_path / 'events.jsonl')
    by_path = {step.path: step for step in steps}
    with EventStream(events_path) as events:
        outcomes = _loop(
            graph,
            pool,
            by_path,
            logging.getLogger('test'),
            events,
            str(tmp_path),
            True,
        )
    return outcomes, read_events(events_path)


def _peak_concurrency(events):
    """The most steps running at any one instant, from what was recorded."""
    starts = {}
    spans = []
    for event in events:
        if event['event'] == 'step_started':
            starts[event['step']] = event['seconds']
        elif event['event'] == 'step_finished':
            begin = starts.pop(event['step'], None)
            if begin is not None:
                spans.append((begin, event['seconds']))

    moments = []
    for begin, end in spans:
        moments.append((begin, 1))
        moments.append((end, -1))
    moments.sort()
    current = peak = 0
    for _, delta in moments:
        current += delta
        peak = max(peak, current)
    return peak


def test_independent_steps_genuinely_overlap(tmp_path):
    """Measured from recorded times, not from how long the run took."""
    steps = [
        _step(tmp_path, f'step{index}', 'sleep 0.4\n') for index in range(4)
    ]

    outcomes, events = _run(tmp_path, steps, _nodes(cores=8))

    assert all(outcome.succeeded for outcome in outcomes.values())
    assert _peak_concurrency(events) == 4


def test_steps_that_do_not_fit_wait_their_turn(tmp_path):
    """Two cores, four steps of one core each: never more than two at once."""
    steps = [
        _step(tmp_path, f'step{index}', 'sleep 0.3\n') for index in range(4)
    ]

    outcomes, events = _run(tmp_path, steps, _nodes(cores=2))

    assert len(outcomes) == 4
    assert all(outcome.succeeded for outcome in outcomes.values())
    assert _peak_concurrency(events) <= 2


def test_a_step_waits_for_what_it_consumes(tmp_path):
    """The file is the whole declaration; neither step names the other."""
    shared = tmp_path / 'made.txt'
    producer = _step(
        tmp_path, 'producer', f'sleep 0.2\ntouch {shared}\n', outputs=[shared]
    )
    consumer = _step(
        tmp_path, 'consumer', f'test -f {shared}\n', inputs=[shared]
    )

    outcomes, events = _run(tmp_path, [consumer, producer])

    assert outcomes['ocean/consumer'].succeeded
    order = [
        event['step'] for event in events if event['event'] == 'step_started'
    ]
    assert order == ['ocean/producer', 'ocean/consumer']


def test_a_failure_blocks_what_depended_on_it_and_nothing_else(tmp_path):
    shared = tmp_path / 'made.txt'
    failing = _step(tmp_path, 'failing', 'exit 3\n', outputs=[shared])
    dependent = _step(tmp_path, 'dependent', 'true\n', inputs=[shared])
    unrelated = _step(tmp_path, 'unrelated', 'true\n')

    outcomes, events = _run(tmp_path, [failing, dependent, unrelated])

    assert not outcomes['ocean/failing'].succeeded
    assert outcomes['ocean/failing'].returncode == 3
    assert outcomes['ocean/unrelated'].succeeded
    assert 'ocean/dependent' not in outcomes
    skipped = [
        event['step'] for event in events if event['event'] == 'step_skipped'
    ]
    assert skipped == ['ocean/dependent']


def test_a_step_killed_by_a_signal_is_reported_as_terminated(tmp_path):
    """
    Not as an ordinary failure.  Memory is not enforced, so a step that
    used more than it declared exhausts the node and the operating system
    kills whichever process it chooses.
    """
    killed = _step(tmp_path, 'killed', 'kill -9 $$\n')

    outcomes, events = _run(tmp_path, [killed])

    outcome = outcomes['ocean/killed']
    assert outcome.terminated
    assert not outcome.succeeded
    assert outcome.signal_name == 'SIGKILL'
    finished = [event for event in events if event['event'] == 'step_finished']
    assert finished[0]['status'] == 'terminated'
    assert finished[0]['signal'] == 'SIGKILL'


def test_a_completed_step_is_skipped_on_a_rerun(tmp_path):
    """What makes a rerun resume from what succeeded."""
    done = _step(tmp_path, 'done', 'exit 1\n')
    with open(os.path.join(done.work_dir, STEP_COMPLETE_LOG), 'w') as handle:
        handle.write('done')
    other = _step(tmp_path, 'other', 'true\n')

    outcomes, events = _run(tmp_path, [done, other])

    # its script would have failed had it been run
    assert 'ocean/done' not in outcomes
    assert outcomes['ocean/other'].succeeded
    skipped = [
        event['step'] for event in events if event['event'] == 'step_skipped'
    ]
    assert skipped == ['ocean/done']


def test_a_step_is_told_where_it_was_placed(tmp_path):
    """The placement crosses into the process, which is what confines it."""
    reader = _step(
        tmp_path,
        'reader',
        'printf "%s" "$POLARIS_PLACEMENT" > placement.json\n',
        cores=2,
    )

    outcomes, _ = _run(tmp_path, [reader])

    assert outcomes['ocean/reader'].succeeded
    with open(os.path.join(reader.work_dir, 'placement.json')) as handle:
        carried = handle.read()
    assert '"cores"' in carried
    assert 'node0' in carried


def test_a_step_is_confined_to_the_cores_it_was_given(tmp_path):
    """
    The standing check that a placed step got what it was promised.

    A step that is not launched is bound by the executor, so what it can
    see of the machine is the placement.
    """
    if len(os.sched_getaffinity(0)) < 4:
        pytest.skip('need four cores to tell a placement from the machine')

    reader = _step(
        tmp_path,
        'reader',
        "awk '/Cpus_allowed_list/ {print $2}' /proc/self/status > cores.txt\n",
        cores=2,
    )

    outcomes, _ = _run(tmp_path, [reader], _nodes(cores=4))

    assert outcomes['ocean/reader'].succeeded
    with open(os.path.join(reader.work_dir, 'cores.txt')) as handle:
        allowed = handle.read().strip()
    count = 0
    for chunk in allowed.split(','):
        if '-' in chunk:
            low, _, high = chunk.partition('-')
            count += int(high) - int(low) + 1
        elif chunk:
            count += 1
    assert count == 2


def test_every_step_records_when_it_ran(tmp_path):
    """The record a slow run is diagnosed from."""
    steps = [_step(tmp_path, f'step{index}', 'true\n') for index in range(3)]

    _, events = _run(tmp_path, steps)

    kinds = [event['event'] for event in events]
    assert kinds.count('step_started') == 3
    assert kinds.count('step_finished') == 3
    assert all('seconds' in event for event in events)


def test_a_step_is_sized_against_what_the_nodes_credit():
    """
    The interaction that stopped the first real run, with its numbers.

    A step that declares no memory is budgeted at its proportional share of
    a node, which is what makes memory accounting neutral: the memory
    inequality and the core inequality become the same one.  That holds
    only while the share is taken from the same figure the pool charges
    against.  Chrysalis reported about 5% less than its configured 253000
    MiB, so a step wanting all three nodes was budgeted 759000 MiB against
    the 730758 MiB they credited and could never start.
    """
    credited = [238308, 239450, 253000]
    nodes = [
        NodeResources(
            name=f'chr-{index}',
            cores=64,
            gpus=0,
            memory=memory,
            memory_source='available',
            memory_total=257155,
            memory_configured=253000,
        )
        for index, memory in enumerate(credited)
    ]
    configured = dict(
        cores=192,
        nodes=3,
        cores_per_node=64,
        gpus=0,
        gpus_per_node=0,
        memory=253000 * 3,
        memory_per_node=253000,
        mpi_allowed=True,
    )

    available = _credit_memory(configured, nodes)

    assert available['memory_per_node'] == min(credited)
    assert available['memory'] == sum(credited)

    # and the step that could not start now does: budgeted on the credited
    # figure, a step wanting every core fits every node exactly
    step = Step(
        component=Component(name='ocean'),
        name='wide',
        subdir='wide',
        ntasks=192,
        cpus_per_task=1,
        may_span_nodes=True,
    )
    step.constrain_resources(available)
    pool = ResourcePool(nodes)

    assert pool.why_impossible(step) is None
    assert pool.reserve(step) is not None


def test_a_view_from_nodes_that_said_nothing_is_left_alone():
    """A machine with no reading to offer keeps the configured figure."""
    nodes = [
        NodeResources(
            name='node0',
            cores=64,
            gpus=0,
            memory=None,
            memory_source='config',
            memory_total=None,
            memory_configured=None,
        )
    ]
    configured = dict(cores=64, memory_per_node=253000, memory=253000)

    assert _credit_memory(configured, nodes) == configured
