"""
Tests for reading what the allocation's nodes actually hold.

The rule under test came from a measurement rather than from argument: on
Chrysalis a node has 257155 MiB of hardware, reports 239633 MiB available,
and is advertised by Slurm as 253000, which is exactly what the machine's
config says.  So the configured figure is the site's own number and is
still about 5.6% above what a job can really use.  These check that the
reading is preferred, that the safest of the readings wins, and that a
machine which cannot answer falls back rather than failing.
"""

import logging

import pytest
from mache.parallel import PlacementSupport

from polaris import Component
from polaris.run.allocation import _parse, read_allocation

# what a Chrysalis compute node reported in job 1283361
CHRYSALIS_TOTAL_KB = 263327076
CHRYSALIS_AVAILABLE_KB = 245383912
CHRYSALIS_CONFIGURED_MIB = 253000


class _FakeSystem:
    """A parallel system that answers a probe without running one."""

    def __init__(self, names, stdout='', returncode=0, mpi_allowed=True):
        self.node_names = names
        self.mpi_allowed = mpi_allowed
        self.cores_per_node = 64
        self.gpus_per_node = 0
        self.memory_per_node = CHRYSALIS_CONFIGURED_MIB
        self.placement_support = PlacementSupport.CPU_BINDING
        self.commands = []
        self.placements = []
        self._stdout = stdout
        self._returncode = returncode

    def get_config_int(self, key, default=0):
        return default

    def get_parallel_command(
        self, args, ntasks, cpus_per_task=0, gpus_per_task=0, placement=None
    ):
        self.commands.append(dict(ntasks=ntasks, cpus_per_task=cpus_per_task))
        self.placements.append(placement)
        return ['probe']


def _component(system):
    component = Component(name='ocean')
    component.parallel_system = system
    return component


def _run(monkeypatch, system):
    """Read the allocation with the probe's output faked."""

    class _Process:
        returncode = system._returncode
        stdout = system._stdout
        stderr = ''

    monkeypatch.setattr(
        'polaris.run.allocation.subprocess.run',
        lambda *args, **kwargs: _Process(),
    )
    return read_allocation(_component(system), logging.getLogger('test'))


def test_a_node_is_credited_with_what_it_says_is_available(monkeypatch):
    """The measured case: less than the site advertises, and that matters."""
    system = _FakeSystem(
        ['chr-0495'],
        stdout=(
            f'host=chr-0495\n'
            f'memtotal={CHRYSALIS_TOTAL_KB}\n'
            f'memavailable={CHRYSALIS_AVAILABLE_KB}\n'
        ),
    )

    nodes = _run(monkeypatch, system)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.memory == CHRYSALIS_AVAILABLE_KB // 1024
    assert node.memory_source == 'available'
    assert node.memory_total == CHRYSALIS_TOTAL_KB // 1024
    assert node.memory_configured == CHRYSALIS_CONFIGURED_MIB
    # the point of reading: the configured figure is higher than what a job
    # can actually get
    assert node.memory < node.memory_configured


def test_a_cgroup_limit_wins_when_it_is_the_smaller(monkeypatch):
    """It is what the kernel will kill against."""
    system = _FakeSystem(
        ['nid001'],
        stdout=(
            'host=nid001\n'
            'memtotal=524288000\n'
            'memavailable=500000000\n'
            f'cgroup_limit={200 * 1024 * 1024 * 1024}\n'
        ),
    )

    nodes = _run(monkeypatch, system)

    assert nodes[0].memory == 200 * 1024
    assert nodes[0].memory_source == 'cgroup'


def test_what_is_available_wins_when_a_cgroup_promises_more(monkeypatch):
    """A limit above what the node has free is not a promise it can keep."""
    system = _FakeSystem(
        ['nid001'],
        stdout=(
            'host=nid001\n'
            'memavailable=104857600\n'
            f'cgroup_limit={200 * 1024 * 1024 * 1024}\n'
        ),
    )

    nodes = _run(monkeypatch, system)

    assert nodes[0].memory == 100 * 1024
    assert nodes[0].memory_source == 'available'


def test_each_node_is_credited_from_its_own_reading(monkeypatch):
    """Aurora's nodes differ, which is the case this exists for."""
    system = _FakeSystem(
        ['x1', 'x2'],
        stdout=(
            'host=x1\nmemavailable=1162240000\n'
            'host=x2\nmemavailable=1031168000\n'
        ),
    )

    nodes = _run(monkeypatch, system)

    assert [node.name for node in nodes] == ['x1', 'x2']
    assert nodes[0].memory == 1162240000 // 1024
    assert nodes[1].memory == 1031168000 // 1024
    assert nodes[0].memory != nodes[1].memory


def test_the_nodes_are_asked_one_rank_each(monkeypatch):
    """One rank per node, each placed on the node it is asking about."""
    system = _FakeSystem(
        ['x1', 'x2', 'x3'],
        stdout='host=x1\nhost=x2\nhost=x3\n',
    )

    _run(monkeypatch, system)

    assert system.commands[-1]['ntasks'] == 3
    placement = system.placements[-1]
    assert placement.nodes == ('x1', 'x2', 'x3')
    assert placement.total_cores == 3


def test_a_failed_probe_falls_back_to_the_configured_figure(monkeypatch):
    """A run that cannot ask still runs, on what Polaris used before."""
    system = _FakeSystem(['x1'], stdout='', returncode=1)

    nodes = _run(monkeypatch, system)

    assert nodes[0].memory == CHRYSALIS_CONFIGURED_MIB
    assert nodes[0].memory_source == 'config'


def test_a_login_system_is_not_asked(monkeypatch):
    """There is no allocation to ask about."""
    system = _FakeSystem(None, mpi_allowed=False)

    nodes = _run(monkeypatch, system)

    assert system.commands == []
    assert len(nodes) == 1
    assert nodes[0].memory_source == 'config'


def test_a_machine_that_cannot_place_is_not_asked(monkeypatch):
    """Without placement the ranks cannot be put one per node."""
    system = _FakeSystem(['x1', 'x2'], stdout='')
    system.placement_support = PlacementSupport.NONE

    nodes = _run(monkeypatch, system)

    assert system.commands == []
    assert [node.memory_source for node in nodes] == ['config', 'config']


def test_a_node_that_did_not_answer_falls_back_on_its_own(monkeypatch):
    """One silent node does not cost the others their readings."""
    system = _FakeSystem(
        ['x1', 'x2'], stdout='host=x1\nmemavailable=104857600\n'
    )

    nodes = _run(monkeypatch, system)

    assert nodes[0].memory_source == 'available'
    assert nodes[1].memory_source == 'config'


def test_output_is_grouped_by_the_node_that_printed_it():
    """Launchers label lines with a rank, and mache's srun does."""
    output = (
        '0: host=x1\n0: memavailable=1000\n1: host=x2\n1: memavailable=2000\n'
    )

    assert _parse(output) == {
        'x1': {'memavailable': 1000},
        'x2': {'memavailable': 2000},
    }


def test_nodes_that_differ_are_reported(monkeypatch, caplog):
    """Handled by packing, and still worth saying out loud."""
    system = _FakeSystem(
        ['x1', 'x2'],
        stdout=(
            'host=x1\nmemavailable=1162240000\n'
            'host=x2\nmemavailable=524288000\n'
        ),
    )

    with caplog.at_level(logging.WARNING):
        _run(monkeypatch, system)

    assert 'do not hold the same memory' in caplog.text


def test_a_component_without_a_parallel_system_says_so():
    component = Component(name='ocean')
    with pytest.raises(ValueError, match='Parallel system has not been set'):
        read_allocation(component, logging.getLogger('test'))
