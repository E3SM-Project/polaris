"""
Run several placed launches at once and read back where they landed.

Every other placement test checks what a command *says*. This one checks
what it *does*: it builds disjoint placements, renders each through mache,
starts them together, and has each report the cores it was actually allowed.

It needs no allocation and no batch system. A single-node launcher confines a
launch with ordinary process affinity, which is enough to exercise the whole
path on any Linux machine, so this guards against a rendering regression on
every commit rather than on whoever remembers to run something inside a job.

It is deliberately self-contained: no import from ``utils/placement_check``,
which is a temporary harness that will be removed from this branch's history.
This is the part of it worth keeping.
"""

import os
import subprocess

import pytest
from mache.parallel import PlacementSupport, ResourcePlacement
from mache.parallel.single_node import SingleNodeSystem

from polaris.config import PolarisConfigParser

# each launch gets this many cores, and sleeps this long so that genuine
# overlap between them is unambiguous
CORES_PER_SLOT = 2
SLEEP_SECONDS = 2

# stands in for mpirun: takes the `-n N -c M` mache renders and runs the
# payload once.  It is not a launcher -- the placement under test is the
# `taskset` prefix mache puts in front of it.
LAUNCHER = """#!/bin/sh
shift 4
exec "$@"
"""

# records the cores it was allowed and when it ran, one file per slot, so
# that concurrent writers cannot interleave
PAYLOAD = """#!/bin/sh
start=$(date +%s.%N)
cpus=$(awk '/Cpus_allowed_list/ {print $2}' /proc/self/status)
sleep "$2"
end=$(date +%s.%N)
printf 'cpus=%s\\nstart=%s\\nend=%s\\n' "$cpus" "$start" "$end" > "$1"
"""


def test_placed_launches_run_at_once_on_the_cores_they_were_given(tmp_path):
    """The whole path: build, render, launch together, read back."""
    usable = sorted(os.sched_getaffinity(0))
    if len(usable) < 2 * CORES_PER_SLOT:
        pytest.skip(f'need {2 * CORES_PER_SLOT} cores, have {len(usable)}')
    slots = min(4, len(usable) // CORES_PER_SLOT)

    launcher = _script(tmp_path, 'launcher.sh', LAUNCHER)
    payload = _script(tmp_path, 'payload.sh', PAYLOAD)
    system = _single_node_system(launcher, len(usable))
    if system.placement_support is PlacementSupport.NONE:
        pytest.skip('no placement mechanism here (taskset is missing)')

    placements = [
        ResourcePlacement(
            nodes=(),
            cores=tuple(
                usable[slot * CORES_PER_SLOT : (slot + 1) * CORES_PER_SLOT]
            ),
            gpus=0,
        )
        for slot in range(slots)
    ]

    processes = []
    for slot, placement in enumerate(placements):
        command = system.get_parallel_command(
            args=[
                payload,
                str(tmp_path / f'slot{slot}.kv'),
                f'{SLEEP_SECONDS}',
            ],
            ntasks=1,
            cpus_per_task=CORES_PER_SLOT,
            placement=placement,
        )
        assert command[0] == 'taskset', command
        processes.append(subprocess.Popen(command))

    for process in processes:
        assert process.wait(timeout=60 + SLEEP_SECONDS) == 0

    runs = [_read(tmp_path / f'slot{slot}.kv') for slot in range(slots)]

    # every launch was confined to exactly the cores it was placed on.  A
    # single-node launcher binds explicitly, so this is the exact set and
    # not merely the right number of them.
    for placement, run in zip(placements, runs, strict=True):
        assert run['cores'] == set(placement.cores)

    # and they really did run at the same time, which is what makes the
    # disjointness above mean anything
    assert _peak_concurrency(runs) == slots
    seen: set[int] = set()
    for run in runs:
        assert seen.isdisjoint(run['cores'])
        seen |= run['cores']


def _single_node_system(launcher, cores_per_node):
    """Build mache's real single-node system, with a stand-in launcher."""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('polaris.machines', 'default.cfg')
    config.set('parallel', 'parallel_executable', launcher, user=True)
    config.set('parallel', 'cores_per_node', f'{cores_per_node}', user=True)
    config.combine()
    return SingleNodeSystem(config.combined)


def _script(tmp_path, name, body):
    """Write an executable script and return its path."""
    path = tmp_path / name
    path.write_text(body)
    path.chmod(0o755)
    return str(path)


def _read(path):
    """Read one launch's record: the cores it saw and when it ran."""
    values = dict(
        line.split('=', 1)
        for line in path.read_text().splitlines()
        if '=' in line
    )
    cores: set[int] = set()
    for chunk in values['cpus'].split(','):
        if '-' in chunk:
            low, _, high = chunk.partition('-')
            cores.update(range(int(low), int(high) + 1))
        elif chunk:
            cores.add(int(chunk))
    return {
        'cores': cores,
        'start': float(values['start']),
        'end': float(values['end']),
    }


def _peak_concurrency(runs):
    """The largest number of launches running at any one instant."""
    events = []
    for run in runs:
        events.append((run['start'], 1))
        events.append((run['end'], -1))
    events.sort()
    current = 0
    peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak
