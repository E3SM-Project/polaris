"""
Checking that a placed step got what it was given.

The scheduler's accounting only describes a run if the machine honors it.
Nothing here can make that true and nothing here tries: a step that was
given four cores and can see sixty-four is reported and then left alone.
Correcting it would hide the thing worth knowing, which is that this
machine no longer confines work the way Polaris believes it does.

That belief is the fragile part.  Which arguments confine a launch is a
property of a site's scheduler configuration rather than of any software
version, so it can change with no release note and no error.  A run would
simply get slower, every step seeing the whole allocation and nothing in
the log to say so.  This is the check that makes that visible, and it earns
its cost only by running on every machine on every run.

What it reads depends on how the step was confined, because the two ways of
confining a step are unrelated mechanisms.

A step that is not launched does its work in the process the executor
started, and the executor confined that process with ``sched_setaffinity``.
Asking the process what it is allowed costs a system call.

A step that launches hands its placement to a launcher, and the affinity of
the process holding the launcher's client says nothing about where the ranks
went.  That is measured rather than assumed: on Chrysalis a locally bound
step's ``srun`` tasks used the whole allocation.  The only way to learn where
the ranks went is to ask them, so this launches the step's own placement once
more with a payload that reports what each rank was allowed.

The probe is the step's real launch in every respect but the payload: same
placement, same task and thread counts, rendered by the same mache call.  A
probe rendered differently would be checking something other than the launch
it stands in for.

A probe that cannot run is reported as *not checked*.  A launcher hiccup is
not evidence of a placement mismatch, and recording it as one would train
whoever reads these reports to ignore them.

What the ranks' answer is held against depends on what the machine
promised.  Where the launcher binds cores explicitly -- Slurm before 20.11,
PALS -- the placement names the cores and the ranks must be on those.
Where the scheduler reserves resources -- Slurm 20.11 and later, with
``--exact`` -- it promises a *count* and picks the cores itself, so holding
the ranks to particular numbers reports every launch: measured on
Perlmutter, where thirty steps were reported for running on the right
number of the wrong cores.  There the count is what is checked, in
physical cores: a launch given a whole node is allowed that node's
hardware threads too, which are twice the ids and the same cores, and the
kernel's topology says which ids are which.

GPUs are asked about the same way, through the visible-devices variable
the machine's vendor uses.  The ranks report what they can see and that is
held against what the placement gave; more devices than given is a
mismatch, fewer is only reported, since a launcher may renumber a rank's
devices from zero and a rank that sees one device numbered zero says
nothing about how many its neighbours see.

Which devices a step is held to depends on who chose them.  Where the
placement names them -- PALS, where nothing else assigns GPUs -- the ranks
are held to those.  Where Slurm reserves GPUs by count it picks which, so
the pool names none and each node is held to its share.  Holding them to
the pool's names reported steps on Frontier that had exactly what they
asked for: Slurm gave one devices 4-7 where the pool had counted 0-3.

What the ranks can read was measured, and differs by vendor.  On Frontier
``ROCR_VISIBLE_DEVICES`` holds the node's own indices -- eight concurrent
one-GPU launches on one node read 0 through 7, one each (job 5515624) --
so a report there says which devices by number.  On Perlmutter
``CUDA_VISIBLE_DEVICES`` is renumbered per launch: four concurrent one-GPU
launches on one node each read ``0`` while holding four distinct devices
(job 58471743).  So there the check can only ever catch a step seeing more
than it was given, and telling the devices apart would mean reading their
UUIDs through the vendor's tool, which is a different probe.  On both
machines the devices concurrent launches were given were disjoint.
"""

import os
import socket
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from mache.parallel import PlacementSupport

from polaris.run.topology import physical_cores

# written in a step's work directory when the check found a mismatch, so the
# scheduler can say so without reading the step's whole log
PLACEMENT_MISMATCH_LOG = 'polaris_placement_mismatch.log'

# what each rank of the probe prints.  Looked for anywhere in a line, since
# some launchers label the output they collect.
MARKER = 'POLARIS_CONFINEMENT'

# the variables through which each vendor tells a process which of a
# node's GPUs it may use, in the order they are looked for.  A rank reports
# the first one that is set, and '-' where none is.
DEVICE_VARIABLES = (
    'CUDA_VISIBLE_DEVICES',
    'ROCR_VISIBLE_DEVICES',
    'ZE_AFFINITY_MASK',
)

# the probe payload: one line per rank saying where it is, what cores it may
# use, and what devices it can see
PROBE = (
    'import os, socket; '
    f'devices = next((os.environ[name] for name in {DEVICE_VARIABLES!r} '
    "if os.environ.get(name)), '-'); "
    f"print('{MARKER}', socket.gethostname().split('.')[0], "
    "','.join(str(core) for core in sorted(os.sched_getaffinity(0))), "
    'devices, flush=True)'
)

# a probe is the step's own launch, so one that has not answered in this long
# is not going to.  Waiting longer would spend the step's wall clock learning
# nothing.
PROBE_SECONDS = 120


def check_confinement(step, logger) -> None:
    """
    Check that a placed step received what it was given, and say so when it
    did not.

    Does nothing for a step with no placement, which is every step of a
    serial run.

    Parameters
    ----------
    step : polaris.Step
        The step about to run, with its resources already constrained to its
        placement

    logger : logging.Logger
        The step's logger, which is where the finding goes
    """
    # a marker left by an earlier run of this step describes that run and
    # not this one, and the scheduler cannot tell the two apart
    try:
        os.remove(os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG))
    except OSError:
        pass

    placement = step.placement
    if placement is None:
        return

    if step.hands_out_work:
        # its own process is not bound to its cores; each piece of its work
        # is, by the resident that forks it
        logger.info(
            'placement: this step hands out its work, and each piece is '
            'bound to its core by the resident that forks it'
        )
        return

    try:
        problems = list(_check_affinity(placement, logger))
        if step.ntasks > 1:
            problems.extend(_check_launch(step, placement, logger))
    except Exception as exception:  # noqa: BLE001
        # deliberately everything.  This is a diagnostic, and a diagnostic
        # that can fail the work it is reporting on is worse than no
        # diagnostic: whoever hits it loses a run to a check they did not
        # ask for and cannot see the point of.
        logger.warning(
            f'placement: not checked; the check itself failed: {exception!r}'
        )
        return

    if problems:
        _record(step, problems, logger)


def _check_affinity(placement, logger) -> List[str]:
    """Ask this process what cores it is allowed, where it was bound."""
    promised = _bound_cores(placement)
    if promised is None:
        logger.info(
            f'placement: this process is not bound; the step is placed on '
            f'{len(placement.cores)} nodes and its launcher confines it'
        )
        return []

    if not hasattr(os, 'sched_getaffinity'):
        logger.info('placement: this platform cannot report core affinity')
        return []

    allowed = set(os.sched_getaffinity(0))
    if allowed == set(promised):
        logger.info(
            f'placement: this process has the {len(promised)} cores it was '
            f'given'
        )
        return []

    return [
        f'This process was given {len(promised)} cores '
        f'({_ranges(promised)}) but is allowed {len(allowed)} '
        f'({_ranges(allowed)}).'
    ]


def _bound_cores(placement) -> Optional[Tuple[int, ...]]:
    """
    The cores the executor bound this process to, or ``None`` if it did not.

    Mirrors the executor's own rule: only a step whose whole placement is on
    the node the scheduler is running on gets bound, because affinity is the
    only mechanism available here and it reaches no further than this node.
    """
    if len(placement.cores) != 1:
        return None
    if placement.nodes and placement.nodes[0].split('.')[0] != _hostname():
        return None
    return tuple(placement.cores[0]) or None


def _check_launch(step, placement, logger) -> List[str]:
    """Launch the step's own placement and ask the ranks where they landed."""
    system = step.component.parallel_system
    if system is None:
        return []

    gpus = placement.gpus
    command = system.get_parallel_command(
        args=[sys.executable, '-c', PROBE],
        ntasks=step.ntasks,
        cpus_per_task=step.cpus_per_task,
        gpus_per_task=(0 if gpus <= 0 else -(-gpus // step.ntasks)),
        placement=placement,
        memory_cap=None,
    )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PROBE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            f'placement: not checked; the probe launch did not answer in '
            f'{PROBE_SECONDS} s\n  {" ".join(command)}'
        )
        return []
    except OSError as exception:
        logger.warning(
            f'placement: not checked; the probe launch could not start: '
            f'{exception}\n  {" ".join(command)}'
        )
        return []

    if result.returncode != 0:
        logger.warning(
            f'placement: not checked; the probe launch exited '
            f'{result.returncode}\n  {" ".join(command)}\n'
            f'{result.stderr.strip()}'
        )
        return []

    seen = _parse(result.stdout)
    if not seen:
        # one silent probe says little.  On Aurora two steps started in a
        # burst of nineteen on one node went unanswered and the next run
        # answered every one, so this is output lost under load until the
        # same step is silent twice.
        logger.warning(
            'placement: not checked; the probe launch ran but no rank '
            'reported.  One silent probe is usually output lost under '
            'load; the same step silent again is worth chasing'
        )
        return []

    return _compare(
        placement,
        seen,
        logger,
        support=system.placement_support,
        device_names=_device_names(system),
    )


def _device_names(system) -> Optional[List[str]]:
    """
    The names a launch's ranks see for each of a node's GPUs, by index.

    Aurora names a tile ``0.1`` where the placement says index 1, so the
    check has to translate before it compares.  ``None`` where the machine
    has no GPUs to name.
    """
    if not system.gpus_per_node:
        return None
    return system.get_gpu_device_names()


class Report(NamedTuple):
    """What one node's ranks reported, taken together."""

    cores: Set[int]
    devices: Set[str]


def _parse(output: str) -> Dict[str, Report]:
    """Collect what each node's ranks reported, by node."""
    seen: Dict[str, Report] = {}
    for line in output.splitlines():
        if MARKER not in line:
            continue
        fields = line.split(MARKER, 1)[1].split()
        if len(fields) != 3:
            continue
        node, cores, devices = fields
        try:
            reported = {int(core) for core in cores.split(',') if core}
        except ValueError:
            continue
        report = seen.setdefault(node, Report(set(), set()))
        report.cores.update(reported)
        if devices != '-':
            report.devices.update(
                device for device in devices.split(',') if device
            )
    return seen


def _compare(
    placement,
    seen: Dict[str, Report],
    logger,
    support: PlacementSupport = PlacementSupport.CPU_BINDING,
    device_names: Optional[List[str]] = None,
) -> List[str]:
    """Hold what the ranks reported against what the placement promised."""
    promised = _promised(placement)
    problems = []

    if promised:
        strangers = sorted(set(seen) - set(promised))
        if strangers:
            problems.append(
                f'The launch ran on {", ".join(strangers)}, which the '
                f'placement does not name ({", ".join(sorted(promised))}).'
            )
    else:
        # an unnamed single-node placement: every rank is on this node, so
        # whatever they reported is held against the one core list
        promised = {node: set(placement.cores[0]) for node in seen}

    for node in sorted(seen):
        allowed = promised.get(node)
        if allowed is None:
            continue
        problem = _compare_cores(node, seen[node].cores, allowed, support)
        if problem:
            problems.append(problem)

    problems.extend(
        _compare_devices(placement, seen, logger, support, device_names)
    )

    if not problems:
        total = sum(len(report.cores) for report in seen.values())
        what = (
            'cores'
            if support is PlacementSupport.CPU_BINDING
            else 'hardware threads, on no more cores than it was given,'
        )
        logger.info(
            f'placement: the launch used {total} {what} on '
            f'{len(seen)} node(s), all of them within its placement'
        )
    return problems


def _compare_cores(
    node: str,
    reported: Set[int],
    allowed: Set[int],
    support: PlacementSupport,
) -> Optional[str]:
    """
    Say how one node's ranks differ from their placement, if they do.

    Which comparison applies is what the machine promised.  An explicit
    binding names the cores, so the ranks have to be on those.  A scheduler
    that reserves resources promises a count and chooses the cores itself,
    so the count is what is held -- in physical cores, since a rank
    allowed both threads of a core has one core, and a launch given a
    whole node is allowed every thread on it.  A launch given part of a
    node and allowed more cores than that has escaped, on either kind of
    machine, and that is what this exists to see.

    The topology read is this node's.  The ranks may be on another, but
    nodes in an allocation are alike, which is what ``cores_per_node``
    already assumes.
    """
    if support is PlacementSupport.CPU_BINDING:
        if reported - allowed:
            return (
                f'On {node} the launch was allowed {len(reported)} cores '
                f'({_ranges(reported)}) but was given {len(allowed)} '
                f'({_ranges(allowed)}).'
            )
        return None

    cores = physical_cores(reported)
    if cores <= len(allowed):
        return None
    return (
        f'On {node} the launch was allowed {cores} cores '
        f'({len(reported)} hardware threads) but was given {len(allowed)}. '
        f'This machine reserves cores by count and chooses which, so only '
        f'the count is held.'
    )


def _compare_devices(
    placement,
    seen: Dict[str, Report],
    logger,
    support: PlacementSupport = PlacementSupport.CPU_BINDING,
    device_names: Optional[List[str]] = None,
) -> List[str]:
    """
    Hold the devices the ranks saw against the GPUs the placement gave.

    More than given is reported.  Fewer is only logged: a launcher may
    number each rank's devices from zero, so every rank of a four-GPU
    launch may report a single device 0 and the union say one.  That
    cannot be told from a rank that really was given one, and reporting it
    would have every GPU step on such a machine reported.

    The placement names its devices by index and the ranks see the
    machine's names for them, which on Aurora are tiles such as ``1.0``,
    so the indices are translated with ``device_names`` first.  Comparing
    the two as they came reported thirteen correctly placed steps on
    Aurora.

    No rank reporting a device at all, for a step that was given GPUs, is
    said as not checked rather than passed.
    """
    given = placement.gpus
    if given <= 0:
        return []

    reported = {node: report.devices for node, report in seen.items()}
    if not any(reported.values()):
        logger.warning(
            f'placement: GPUs not checked; the step was given {given} but '
            f'no rank reported a visible-devices variable '
            f'({", ".join(DEVICE_VARIABLES)})'
        )
        return []

    for node in sorted(reported):
        logger.info(
            f'placement: on {node} the ranks see device(s) '
            f'{",".join(sorted(reported[node])) or "none"}'
        )

    problems = []
    named = _named_devices(placement, device_names)
    if named is not None and support is PlacementSupport.CPU_BINDING:
        # the placement names its devices and the launcher binds them, so
        # the ranks are held to those.  A scheduler that assigns GPUs picks
        # which itself, so there each node is held to a count, as below.
        for node, devices in sorted(reported.items()):
            wanted = named.get(node, named.get('', set()))
            extra = devices - wanted
            if extra:
                problems.append(
                    f'On {node} the launch can see device(s) '
                    f'{",".join(sorted(extra))} that its placement did not '
                    f'give it ({",".join(sorted(wanted))}).'
                )
        return problems

    # where the scheduler assigns a launch's devices, it is told only how
    # many in total, so each node is held to its share
    nodes = max(len(placement.nodes), 1)
    per_node = -(-given // nodes)
    for node, devices in sorted(reported.items()):
        if len(devices) > per_node:
            problems.append(
                f'On {node} the launch can see {len(devices)} device(s) '
                f'({",".join(sorted(devices))}) but was given {per_node}.'
            )
    return problems


def _named_devices(
    placement, device_names: Optional[List[str]]
) -> Optional[Dict[str, Set[str]]]:
    """
    The device names the placement gives each node, keyed by short node
    name, or by ``''`` for a placement that names no node.
    """
    if placement.gpu_ids is None:
        return None
    per_node = list(placement.gpu_ids)
    if per_node and all(isinstance(entry, int) for entry in per_node):
        # a mache that takes one flat list for the launch
        per_node = [per_node]

    keys = [node.split('.')[0] for node in placement.nodes] or ['']
    return {
        key: {_device_name(index, device_names) for index in node_ids}
        for key, node_ids in zip(keys, per_node, strict=False)
    }


def _device_name(index: int, device_names: Optional[List[str]]) -> str:
    """The machine's name for a node's GPU with this index."""
    if device_names is not None and index < len(device_names):
        return device_names[index]
    return str(index)


def _promised(placement) -> Dict[str, Set[int]]:
    """The cores the placement gives on each node it names."""
    if not placement.nodes:
        return {}
    return {
        node.split('.')[0]: set(cores)
        for node, cores in zip(placement.nodes, placement.cores, strict=False)
    }


def _record(step, problems: List[str], logger) -> None:
    """
    Say what did not match, in the step's log and in a file beside it.

    The file is what lets the scheduler report a mismatch: a step that runs
    at the same time as fourteen others has its own log, and a warning in it
    is easy to never read.
    """
    lines = [
        f'The placement of step {step.path} does not describe how it ran.',
        '',
    ]
    lines.extend(f'  {problem}' for problem in problems)
    lines.extend(
        [
            '',
            'Nothing has been changed. The step ran, and its results are as '
            'good as they ever were;',
            'what is wrong is the accounting, which believes this step is '
            'using less of the machine',
            'than it is. Other steps are being started against that belief.',
        ]
    )
    report = '\n'.join(lines) + '\n'

    logger.warning('')
    logger.warning(report)

    try:
        with open(
            os.path.join(step.work_dir, PLACEMENT_MISMATCH_LOG), 'w'
        ) as handle:
            handle.write(report)
    except OSError:
        # the finding is in the log either way; failing the step over where
        # the copy went would be worse than the mismatch
        pass


def _hostname() -> str:
    """This node's short name, as the allocation lists it."""
    return socket.gethostname().split('.')[0]


def _ranges(cores) -> str:
    """Say a set of core numbers the way a person reads one."""
    cores = sorted(cores)
    if not cores:
        return 'none'
    spans = []
    start = previous = cores[0]
    for core in cores[1:]:
        if core == previous + 1:
            previous = core
            continue
        spans.append((start, previous))
        start = previous = core
    spans.append((start, previous))
    return ','.join(
        f'{first}' if first == last else f'{first}-{last}'
        for first, last in spans
    )
