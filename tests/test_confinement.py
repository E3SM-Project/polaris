"""
Tests for the check that a placed step got what it was given.

The launcher half is exercised for real: a single-node launcher confines a
launch with ordinary process affinity, so the probe, the parse and the
comparison all run on any Linux machine rather than only inside an
allocation.  A check that only ran where nobody runs it would report
nothing.

The case with teeth is the one where a launch escapes its placement.  That
is the regression the whole check exists for -- a site stops honoring the
arguments and every step quietly sees the whole allocation -- so it is
built here out of a launcher that widens affinity rather than narrowing it.
"""

import os
import socket

import pytest
from mache.parallel import PlacementSupport, ResourcePlacement
from mache.parallel.single_node import SingleNodeSystem

from polaris import Component, Step
from polaris.config import PolarisConfigParser
from polaris.run.confinement import (
    MARKER,
    PLACEMENT_MISMATCH_LOG,
    Report,
    _bound_cores,
    _check_launch,
    _compare,
    _parse,
    _ranges,
    check_confinement,
)
from tests.test_topology import fake_topology

# stands in for mpirun: drops the `-n N -c M` mache renders and runs the
# payload.  It is not a launcher; the placement under test is the `taskset`
# prefix mache puts in front of it.
LAUNCHER = """#!/bin/sh
shift 4
exec "$@"
"""

# the same, but resetting affinity to everything first.  This is a machine
# that has stopped honoring the placement it was given.
WIDENING_LAUNCHER = """#!/bin/sh
shift 4
exec taskset -c {cores} "$@"
"""

# a launcher that fails, which must read as "not checked" and never as a
# mismatch
FAILING_LAUNCHER = """#!/bin/sh
echo 'no launcher here' >&2
exit 1
"""


class _Logger:
    """Collects what the check said, so a test can read it back."""

    def __init__(self):
        self.messages = []
        self.warnings = []

    def info(self, message=''):
        self.messages.append(message)

    def warning(self, message=''):
        self.warnings.append(message)


def _logger():
    return _Logger()


def _hostname():
    return socket.gethostname().split('.')[0]


def _step(tmp_path, placement, ntasks=1, cpus_per_task=1, system=None):
    """A step as ``run_step`` has it: placed, sized and in its work dir."""
    component = Component(name='ocean')
    component.parallel_system = system
    step = Step(component=component, name='step', subdir='step')
    step.work_dir = str(tmp_path / 'step')
    os.makedirs(step.work_dir, exist_ok=True)
    step.placement = placement
    step.ntasks = ntasks
    step.cpus_per_task = cpus_per_task
    return step


def _system(launcher, cores_per_node):
    """Mache's real single-node system, with a stand-in launcher."""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.set('parallel', 'parallel_executable', launcher, user=True)
    config.set('parallel', 'cores_per_node', f'{cores_per_node}', user=True)
    config.combine()
    return SingleNodeSystem(config.combined)


def _script(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body)
    path.chmod(0o755)
    return str(path)


def _mismatch_file(step):
    return os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG)


def _seen(cores, devices=()):
    """What a node's ranks reported, as ``_parse`` collects it."""
    return Report(set(cores), set(devices))


def test_core_numbers_are_reported_the_way_a_person_reads_them():
    assert _ranges([]) == 'none'
    assert _ranges([3]) == '3'
    assert _ranges([0, 1, 2, 3]) == '0-3'
    assert _ranges([0, 1, 2, 7, 9, 10]) == '0-2,7,9-10'


def test_what_each_rank_reported_is_collected_by_node():
    output = (
        f'{MARKER} nodeA 0,1 -\n{MARKER} nodeA 2,3 -\n{MARKER} nodeB 0,1 -\n'
    )

    assert _parse(output) == {
        'nodeA': _seen({0, 1, 2, 3}),
        'nodeB': _seen({0, 1}),
    }


def test_a_launcher_that_labels_its_output_is_still_read():
    """Some launchers prefix every line with the rank that wrote it."""
    output = f'0: {MARKER} nodeA 0,1 -\n1: {MARKER} nodeA 2 -\n'

    assert _parse(output) == {'nodeA': _seen({0, 1, 2})}


def test_a_line_that_is_not_a_report_is_ignored():
    """A launcher's own chatter shares the stream with the payload."""
    output = (
        'srun: job 12 queued and waiting for resources\n'
        f'{MARKER} nodeA 0,1 -\n'
        f'{MARKER} nodeA not,numbers -\n'
        f'{MARKER} nodeA 0,1\n'
        f'{MARKER} nodeA\n'
    )

    assert _parse(output) == {'nodeA': _seen({0, 1})}


def test_the_devices_each_rank_can_see_are_collected_by_node():
    """
    Each rank reports the devices it can see, and a node's ranks are
    taken together.  The identifiers are whatever the vendor's variable
    holds, so they are kept as they are rather than read as numbers.
    """
    output = (
        f'{MARKER} nodeA 0 0\n{MARKER} nodeA 1 1\n'
        f'{MARKER} nodeB 0 0.0,0.1\n{MARKER} nodeC 0 -\n'
    )

    seen = _parse(output)

    assert seen['nodeA'].devices == {'0', '1'}
    assert seen['nodeB'].devices == {'0.0', '0.1'}
    assert seen['nodeC'].devices == set()


def test_a_placement_on_this_node_is_one_the_executor_bound():
    placement = ResourcePlacement(nodes=(_hostname(),), cores=((0, 1),))

    assert _bound_cores(placement) == (0, 1)


def test_an_unnamed_single_node_placement_is_one_the_executor_bound():
    """What a machine with no node names gives, and what tests build."""
    placement = ResourcePlacement(nodes=(), cores=((0, 1),))

    assert _bound_cores(placement) == (0, 1)


def test_a_placement_on_another_node_is_not_bound_here():
    placement = ResourcePlacement(nodes=('somewhere-else',), cores=((0, 1),))

    assert _bound_cores(placement) is None


def test_a_placement_spanning_nodes_is_not_bound():
    """Such a step is confined by its launcher, and affinity says nothing."""
    placement = ResourcePlacement(nodes=('a', 'b'), cores=((0,), (0,)))

    assert _bound_cores(placement) is None


def test_a_process_that_has_its_cores_is_not_reported(tmp_path):
    mine = sorted(os.sched_getaffinity(0))
    placement = ResourcePlacement(nodes=(), cores=(tuple(mine),))
    step = _step(tmp_path, placement)

    check_confinement(step, _logger())

    assert not os.path.exists(_mismatch_file(step))


def test_a_process_without_the_cores_it_was_given_is_reported(tmp_path):
    """The executor's binding silently failing is what this catches."""
    mine = sorted(os.sched_getaffinity(0))
    if len(mine) < 2:
        pytest.skip('need two cores to place a step on one of them')
    placement = ResourcePlacement(nodes=(), cores=((mine[0],),))
    step = _step(tmp_path, placement)
    logger = _logger()

    check_confinement(step, logger)

    assert os.path.exists(_mismatch_file(step))
    report = open(_mismatch_file(step)).read()
    assert 'was given 1 cores' in report
    assert f'is allowed {len(mine)}' in report
    assert any(
        'does not describe how it ran' in line for line in logger.warnings
    )


def test_a_step_with_no_placement_is_not_checked(tmp_path):
    """Every step of a serial run, which must be left exactly as it was."""
    step = _step(tmp_path, None)

    check_confinement(step, _logger())

    assert not os.path.exists(_mismatch_file(step))


def test_a_marker_from_an_earlier_run_does_not_describe_this_one(tmp_path):
    """A rerun that is fine must not be reported with the last run's fault."""
    mine = sorted(os.sched_getaffinity(0))
    placement = ResourcePlacement(nodes=(), cores=(tuple(mine),))
    step = _step(tmp_path, placement)
    with open(_mismatch_file(step), 'w') as handle:
        handle.write('from the run before')

    check_confinement(step, _logger())

    assert not os.path.exists(_mismatch_file(step))


def test_a_launch_that_stayed_in_its_placement_is_confirmed(tmp_path):
    """The whole path: render through mache, launch, read the ranks back."""
    mine = sorted(os.sched_getaffinity(0))
    if len(mine) < 2:
        pytest.skip('need two cores')
    launcher = _script(tmp_path, 'launcher.sh', LAUNCHER)
    system = _system(launcher, len(mine))
    if system.placement_support is PlacementSupport.NONE:
        pytest.skip('no placement mechanism here (taskset is missing)')

    placement = ResourcePlacement(nodes=(), cores=(tuple(mine[:2]),))
    step = _step(tmp_path, placement, ntasks=2, system=system)
    logger = _logger()

    assert _check_launch(step, placement, logger) == []
    assert any('within its placement' in line for line in logger.messages)


def test_a_launch_that_escaped_its_placement_is_reported(tmp_path):
    """A machine that has stopped honoring the arguments it is given."""
    mine = sorted(os.sched_getaffinity(0))
    if len(mine) < 4:
        pytest.skip('need four cores to escape a placement of two')
    everything = ','.join(str(core) for core in mine)
    launcher = _script(
        tmp_path, 'wide.sh', WIDENING_LAUNCHER.format(cores=everything)
    )
    system = _system(launcher, len(mine))
    if system.placement_support is PlacementSupport.NONE:
        pytest.skip('no placement mechanism here (taskset is missing)')

    placement = ResourcePlacement(nodes=(), cores=(tuple(mine[:2]),))
    step = _step(tmp_path, placement, ntasks=2, system=system)

    problems = _check_launch(step, placement, _logger())

    assert len(problems) == 1
    assert 'was given 2' in problems[0]


def test_a_probe_that_could_not_run_is_not_a_mismatch(tmp_path):
    """A launcher hiccup must not be recorded as a placement failure."""
    launcher = _script(tmp_path, 'broken.sh', FAILING_LAUNCHER)
    system = _system(launcher, 4)
    placement = ResourcePlacement(nodes=(), cores=((0, 1),))
    step = _step(tmp_path, placement, ntasks=2, system=system)
    logger = _logger()

    assert _check_launch(step, placement, logger) == []
    assert any('not checked' in line for line in logger.warnings)


def test_a_rank_on_a_node_the_placement_does_not_name_is_reported():
    placement = ResourcePlacement(
        nodes=('nodeA', 'nodeB'), cores=((0, 1), (0, 1))
    )
    seen = {'nodeA': _seen({0, 1}), 'nodeC': _seen({0, 1})}

    problems = _compare(placement, seen, _logger())

    assert any('nodeC' in problem for problem in problems)


def test_ranks_within_a_multi_node_placement_are_confirmed():
    placement = ResourcePlacement(
        nodes=('nodeA', 'nodeB'), cores=((0, 1), (4, 5))
    )
    seen = {'nodeA': _seen({0, 1}), 'nodeB': _seen({4, 5})}

    assert _compare(placement, seen, _logger()) == []


def test_cores_are_compared_against_the_node_they_were_given_on():
    """Core numbers are node-local, so the same number means two things."""
    placement = ResourcePlacement(
        nodes=('nodeA', 'nodeB'), cores=((0, 1), (4, 5))
    )
    seen = {'nodeA': _seen({0, 1}), 'nodeB': _seen({0, 1})}

    problems = _compare(placement, seen, _logger())

    assert len(problems) == 1
    assert 'On nodeB' in problems[0]


def test_the_check_never_fails_the_step_it_is_checking(tmp_path):
    """A diagnostic that can fail the work it reports on is worse than none."""
    placement = ResourcePlacement(nodes=(), cores=((0, 1),))
    # no parallel system on the component and a launch to check, so the
    # rendering the probe needs cannot happen at all
    step = _step(tmp_path, placement, ntasks=2, system=None)
    step.component = None
    logger = _logger()

    check_confinement(step, logger)

    assert not os.path.exists(_mismatch_file(step))
    assert any('the check itself failed' in line for line in logger.warnings)


# --- where the scheduler reserves by count and chooses the cores itself

SCHEDULER = PlacementSupport.SCHEDULER


def test_a_scheduler_machine_is_held_to_the_count_not_the_cores():
    """
    Perlmutter reported thirty steps for running on the right number of
    the wrong cores.  `--exact` promises a count and srun picks which,
    so particular numbers were never promised there.
    """
    placement = ResourcePlacement(nodes=('nid1',), cores=((4, 10, 25),))
    seen = {'nid1': _seen({3, 25, 39})}

    assert _compare(placement, seen, _logger(), support=SCHEDULER) == []


def _perlmutter_cpu(monkeypatch):
    """256 ids, siblings 128 apart, 128 cores."""
    fake_topology(monkeypatch, [(cpu, cpu + 128) for cpu in range(128)])


def test_a_scheduler_launch_given_part_of_a_node_may_not_see_more(
    monkeypatch,
):
    """
    The escape the check exists for looks the same on every machine: a
    step given a few cores and allowed many.  Holding only the count must
    still see it.
    """
    _perlmutter_cpu(monkeypatch)
    placement = ResourcePlacement(nodes=('nid1',), cores=((4, 10, 25),))
    seen = {'nid1': _seen(range(128))}

    problems = _compare(placement, seen, _logger(), support=SCHEDULER)

    assert len(problems) == 1
    assert 'allowed 128 cores' in problems[0]
    assert 'was given 3' in problems[0]


def test_a_scheduler_launch_given_a_whole_node_may_see_its_threads(
    monkeypatch,
):
    """
    Perlmutter's nine other lines: a launch given all 128 of a node's
    cores was allowed 256 ids, which are those cores and their siblings.
    """
    _perlmutter_cpu(monkeypatch)
    placement = ResourcePlacement(nodes=('nid1',), cores=(tuple(range(128)),))
    seen = {'nid1': _seen(range(256))}

    assert _compare(placement, seen, _logger(), support=SCHEDULER) == []


def test_half_a_node_seeing_the_whole_node_is_still_a_mismatch(monkeypatch):
    """
    Twice the ids is only threads when they are the given cores' own.  A
    launch given 64 of 128 cores and allowed all 128 has escaped, though
    the ratio is the same as the whole-node case.
    """
    _perlmutter_cpu(monkeypatch)
    placement = ResourcePlacement(nodes=('nid1',), cores=(tuple(range(64)),))
    seen = {'nid1': _seen(range(128))}

    problems = _compare(placement, seen, _logger(), support=SCHEDULER)

    assert len(problems) == 1
    assert 'allowed 128 cores (128 hardware threads)' in problems[0]


def test_a_launch_allowed_its_cores_and_their_siblings_is_within(monkeypatch):
    """
    A rank allowed both threads of each of its cores has those cores and
    nothing more, however the ids are numbered.
    """
    _perlmutter_cpu(monkeypatch)
    placement = ResourcePlacement(nodes=('nid1',), cores=(tuple(range(64)),))
    seen = {'nid1': _seen(set(range(64)) | set(range(128, 192)))}

    assert _compare(placement, seen, _logger(), support=SCHEDULER) == []


def test_a_binding_machine_is_still_held_to_the_cores():
    """Where the placement named the cores, the count is not enough."""
    placement = ResourcePlacement(nodes=('nid1',), cores=((4, 10, 25),))
    seen = {'nid1': _seen({3, 25, 39})}

    problems = _compare(
        placement, seen, _logger(), support=PlacementSupport.CPU_BINDING
    )

    assert len(problems) == 1


# --- GPUs


def test_a_step_given_no_gpus_is_not_asked_about_devices():
    placement = ResourcePlacement(nodes=('nid1',), cores=((0, 1),), gpus=0)
    seen = {'nid1': _seen({0, 1}, {'0', '1', '2', '3'})}

    assert _compare(placement, seen, _logger()) == []


def test_no_rank_reporting_a_device_is_not_a_pass():
    """
    pm-gpu ran 63 GPU steps and none was asked what it could see.  A
    step given GPUs whose ranks report none is said to be unchecked.
    """
    placement = ResourcePlacement(
        nodes=('nid1',), cores=((0, 1),), gpus=2, gpu_ids=(0, 1)
    )
    seen = {'nid1': _seen({0, 1})}
    logger = _logger()

    assert _compare(placement, seen, logger) == []
    assert any('GPUs not checked' in line for line in logger.warnings)


def test_a_single_node_launch_is_held_to_the_devices_it_was_named():
    placement = ResourcePlacement(
        nodes=('nid1',), cores=((0, 1),), gpus=2, gpu_ids=(0, 1)
    )
    seen = {'nid1': _seen({0, 1}, {'0', '1'})}

    assert _compare(placement, seen, _logger()) == []


def test_a_launch_seeing_a_device_it_was_not_given_is_reported():
    placement = ResourcePlacement(
        nodes=('nid1',), cores=((0, 1),), gpus=2, gpu_ids=(0, 1)
    )
    seen = {'nid1': _seen({0, 1}, {'0', '1', '2', '3'})}

    problems = _compare(placement, seen, _logger())

    assert len(problems) == 1
    assert 'device(s) 2,3' in problems[0]


def test_fewer_devices_than_given_is_reported_but_not_a_mismatch():
    """
    A launcher may number each rank's devices from zero, so four ranks
    with a GPU each can all report device 0.  That cannot be told from
    a rank really given one, so it is logged and not held against.
    """
    placement = ResourcePlacement(
        nodes=('nid1',), cores=(tuple(range(4)),), gpus=4, gpu_ids=(0, 1, 2, 3)
    )
    seen = {'nid1': _seen(range(4), {'0'})}
    logger = _logger()

    assert _compare(placement, seen, logger) == []
    assert any('see device(s) 0' in line for line in logger.messages)


def test_a_spanning_launch_is_held_to_its_share_of_devices_per_node():
    """
    A launch spanning nodes names no devices -- indices are node-local and
    its count is a total -- so each node is held to its share.
    """
    placement = ResourcePlacement(
        nodes=('nid1', 'nid2'), cores=((0, 1), (0, 1)), gpus=4
    )
    within = {
        'nid1': _seen({0, 1}, {'0', '1'}),
        'nid2': _seen({0, 1}, {'2', '3'}),
    }
    beyond = {
        'nid1': _seen({0, 1}, {'0', '1', '2'}),
        'nid2': _seen({0, 1}, {'3'}),
    }

    assert _compare(placement, within, _logger()) == []
    problems = _compare(placement, beyond, _logger())
    assert len(problems) == 1
    assert 'On nid1' in problems[0]
