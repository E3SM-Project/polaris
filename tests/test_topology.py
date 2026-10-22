"""
Tests for reading which CPU ids are the same physical core.

Polaris places one rank or thread per physical core and leaves the sibling
thread idle.  That needs the kernel's word on which ids share a core; the
numbering alone does not say, and a machine that interleaved siblings would
otherwise put two ranks on one core with no error.
"""

from polaris.run.topology import (
    _parse_list,
    one_thread_per_core,
    physical_cores,
    thread_siblings,
    with_siblings,
)


def fake_topology(monkeypatch, groups):
    """
    Give the kernel's answer for tests: each group is the ids of one core.

    An id in no group is its own core, which is what the kernel says of an
    id it has no topology for.
    """
    known = {cpu: tuple(sorted(group)) for group in groups for cpu in group}
    monkeypatch.setattr(
        'polaris.run.topology._read_siblings',
        lambda cpu: known.get(cpu, (cpu,)),
    )


def test_the_kernels_list_formats_are_all_read():
    assert _parse_list('0,64\n') == (0, 64)
    assert _parse_list('0-1') == (0, 1)
    assert _parse_list('0-1,64-65') == (0, 1, 64, 65)
    assert _parse_list('7') == (7,)
    assert _parse_list('') == ()


def test_siblings_are_looked_up_per_id(monkeypatch):
    fake_topology(monkeypatch, [(0, 64), (1, 65)])

    assert thread_siblings([0, 1, 2]) == {0: (0, 64), 1: (1, 65), 2: (2,)}


def test_one_thread_per_core_keeps_the_lowest_of_each(monkeypatch):
    """Perlmutter CPU: 256 ids, siblings 128 apart, 128 cores."""
    fake_topology(monkeypatch, [(cpu, cpu + 128) for cpu in range(128)])

    assert one_thread_per_core(range(256)) == list(range(128))


def test_an_interleaved_numbering_is_still_one_per_core(monkeypatch):
    """
    Nothing promises thread 0 of every core comes first.  A machine that
    numbers siblings next to each other must not be read as twice the
    cores.
    """
    fake_topology(monkeypatch, [(0, 1), (2, 3), (4, 5)])

    assert one_thread_per_core(range(6)) == [0, 2, 4]


def test_a_partial_set_keeps_only_the_cores_it_touches(monkeypatch):
    fake_topology(monkeypatch, [(cpu, cpu + 4) for cpu in range(4)])

    # ids 1 and 5 are one core; 2 alone is another
    assert one_thread_per_core({1, 5, 2}) == [1, 2]
    assert physical_cores({1, 5, 2}) == 2


def test_with_siblings_completes_every_core(monkeypatch):
    fake_topology(monkeypatch, [(cpu, cpu + 4) for cpu in range(4)])

    assert with_siblings({1, 2}) == [1, 2, 5, 6]


def test_a_node_without_topology_files_has_no_siblings(monkeypatch):
    """A container or unusual kernel: every id is its own core."""
    monkeypatch.setattr('polaris.run.topology.SYSFS_CPU', '/nonexistent')

    assert one_thread_per_core(range(4)) == [0, 1, 2, 3]
    assert physical_cores(range(4)) == 4
