"""
What the allocation actually holds, read at the start of a run.

The scheduler packs particular nodes, so it has to know what those nodes
have rather than what a machine's configuration says nodes usually have.
Cores and GPUs come from the configuration, since that is where placement
gets them and they do not vary.  Memory is read from the nodes themselves,
because it does vary and because over-admitting memory kills a job rather
than merely slowing it.

Measured on Chrysalis, job 1283361, which is what the rule below is built
on.  A node there has 257155 MiB of hardware and reports 239633 MiB as
available; Slurm advertises 253000, which is exactly what the machine's
configuration carries.  So the configured figure is not a rough estimate to
be improved on -- it is the site's own number -- but it is about 5.6% above
what a job can actually get, because the kernel, the daemons and
unreclaimable cache have taken their share before any step starts.  Only a
reading taken on the node sees that.
"""

import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from mache.parallel import PlacementSupport, ResourcePlacement

from polaris.parallel import get_memory_per_node

# read on each node, one line per fact, so that a machine which cannot
# answer one of them simply omits it
_PROBE = r'''
import os
import socket

print('host=%s' % socket.gethostname().split('.')[0])

info = {}
try:
    with open('/proc/meminfo') as handle:
        for line in handle:
            key, _, rest = line.partition(':')
            parts = rest.split()
            if parts:
                info[key] = parts[0]
except OSError:
    pass
for key in ('MemTotal', 'MemAvailable'):
    if key in info:
        print('%s=%s' % (key.lower(), info[key]))


def cgroup_limit():
    """The memory this process may use, in bytes, or None if unlimited."""
    unified = os.path.exists('/sys/fs/cgroup/cgroup.controllers')
    relative = ''
    try:
        with open('/proc/self/cgroup') as handle:
            for line in handle:
                fields = line.strip().split(':')
                if len(fields) != 3:
                    continue
                if unified and fields[0] == '0':
                    relative = fields[2]
                elif not unified and 'memory' in fields[1].split(','):
                    relative = fields[2]
    except OSError:
        pass
    if unified:
        names = ['/sys/fs/cgroup%s/memory.max' % relative]
    else:
        names = ['/sys/fs/cgroup/memory%s/memory.limit_in_bytes' % relative]
    for name in names:
        try:
            with open(name) as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value in ('', 'max'):
            return None
        try:
            limit = int(value)
        except ValueError:
            return None
        # a cgroup with no limit set carries a number near the largest a
        # signed 64-bit integer holds rather than saying so
        if limit >= 2**62:
            return None
        return limit
    return None


limit = cgroup_limit()
if limit is not None:
    print('cgroup_limit=%d' % limit)
'''


@dataclass(frozen=True)
class NodeResources:
    """
    What one node of the allocation holds.

    Attributes
    ----------
    name : str
        The node's hostname, which is how a placement names it.

    cores : int
        The cores a launch may use on it.

    gpus : int
        The GPUs it has.

    memory : int or None
        The memory in MiB to credit it with, or ``None`` where nothing
        could say.

    memory_source : str
        Which figure ``memory`` came from: ``'cgroup'`` where the site
        holds a job to one, ``'available'`` where the node reported what it
        had left, or ``'config'`` where neither could be read and the
        machine's configured figure was used.

    memory_total : int or None
        The node's hardware memory in MiB, for the log rather than for
        packing.  A node well below its neighbours here is a node with
        something wrong.

    memory_configured : int or None
        What the machine's configuration says a node has, in MiB, so that a
        disagreement is visible.
    """

    name: str
    cores: int
    gpus: int
    memory: Optional[int]
    memory_source: str
    memory_total: Optional[int]
    memory_configured: Optional[int]


def read_allocation(component, logger) -> List[NodeResources]:
    """
    Read what each node of this allocation holds, and report it.

    One launch, one rank per node, at the start of a run.  It is also the
    first thing on any machine to render a placement across several nodes,
    so a machine that cannot honor one says so here rather than partway
    through a suite.

    Parameters
    ----------
    component : polaris.Component
        The component whose parallel system describes this allocation

    logger : logging.Logger
        Where the reading is reported

    Returns
    -------
    nodes : list of polaris.run.allocation.NodeResources
        One entry per node, in the order the batch system lists them
    """
    parallel_system = component.parallel_system
    if parallel_system is None:
        raise ValueError(
            f'Parallel system has not been set for component {component.name}'
        )

    configured = get_memory_per_node(parallel_system)
    names = parallel_system.node_names
    if not names:
        # nothing names the nodes, which is a login node or a machine with
        # no allocation to describe.  One node, and only the configuration
        # to go on.
        names = ['']

    cores_per_node = parallel_system.cores_per_node or 0
    gpus_per_node = parallel_system.gpus_per_node or 0

    readings = _read_nodes(parallel_system, names, logger)

    nodes = [
        _credit(
            name, readings.get(name), cores_per_node, gpus_per_node, configured
        )
        for name in names
    ]
    silent = [name for name in names if name not in readings]
    if silent and readings:
        # some nodes answered and some did not, which is worth more than a
        # line saying the quiet ones fell back: a launch that reaches only
        # part of its allocation is a placement problem rather than a
        # memory one, and the raw output is what tells them apart
        logger.warning(
            f'{len(silent)} of {len(names)} node(s) did not report their '
            f'memory and fall back to the configured figure: {silent}'
        )
    _report(nodes, logger)
    return nodes


def _read_nodes(parallel_system, names, logger) -> Dict[str, Dict[str, int]]:
    """
    Ask every node what memory a job may use on it.

    A failure here is not fatal: the run falls back to the configured
    figure, which is what Polaris used before anything asked.  It is
    reported loudly, because the fallback is exactly the over-crediting the
    reading exists to correct.
    """
    if not parallel_system.mpi_allowed:
        logger.info(
            'Not asking the nodes about memory: this is not an allocation.'
        )
        return {}

    if parallel_system.placement_support is PlacementSupport.NONE:
        logger.warning(
            'This machine cannot confine a launch, so the nodes cannot be '
            'asked about memory one at a time. Using the configured figure.'
        )
        return {}

    placement = ResourcePlacement(
        nodes=tuple(name for name in names if name != ''),
        cores=tuple((0,) for _ in names),
        gpus=0,
    )
    command = parallel_system.get_parallel_command(
        args=[sys.executable, '-c', _PROBE],
        ntasks=len(names),
        cpus_per_task=1,
        placement=placement,
    )
    try:
        process = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
    except OSError as exception:
        logger.warning(
            f'Could not ask the nodes about memory ({exception}). Using the '
            f'configured figure.'
        )
        return {}

    if process.returncode != 0:
        logger.warning(
            f'Asking the nodes about memory failed with exit code '
            f'{process.returncode}. Using the configured figure.\n'
            f'{process.stderr.strip()}'
        )
        return {}

    readings = _parse(process.stdout)
    if len(readings) != len(names):
        # keep what the nodes actually said, since a reading that is wrong
        # or missing cannot be diagnosed from the summary alone
        logger.debug(f'the nodes answered:\n{process.stdout}')
    return readings


def _parse(output: str) -> Dict[str, Dict[str, int]]:
    """
    Group the probe's ``key=value`` lines by the node that printed them.

    Launchers label output in their own ways and some interleave it, so the
    ``host`` line starts a node's record and everything after it belongs to
    that node until the next one.
    """
    readings: Dict[str, Dict[str, int]] = {}
    current: Optional[str] = None
    for line in output.splitlines():
        # a launcher may prefix each line with a rank label
        _, _, tail = line.rpartition(' ')
        key, sep, value = (tail or line).strip().partition('=')
        if sep != '=':
            continue
        if key == 'host':
            current = value
            readings.setdefault(current, {})
            continue
        if current is None:
            continue
        try:
            readings[current][key] = int(value)
        except ValueError:
            continue
    return readings


def _credit(
    name, reading, cores_per_node, gpus_per_node, configured
) -> NodeResources:
    """
    Decide what one node is credited with, from what it reported.

    The cgroup limit is what the kernel will kill against, so it wins where
    a site sets one.  Otherwise what the node says is still available is
    the closest thing to what a job may use.  Where both are known the
    smaller is taken: a cgroup limit above what the node actually has free
    is not a promise the node can keep.
    """
    reading = reading or {}
    # /proc/meminfo is in KiB, the cgroup limit in bytes, and everything
    # Polaris and mache say about memory is in MiB
    available = reading.get('memavailable')
    available = None if available is None else available // 1024
    total = reading.get('memtotal')
    total = None if total is None else total // 1024
    limit = reading.get('cgroup_limit')
    limit = None if limit is None else limit // (1024 * 1024)

    candidates = {'cgroup': limit, 'available': available}
    known = {
        source: value
        for source, value in candidates.items()
        if value is not None
    }
    if known:
        source = min(known, key=lambda key: known[key])
        memory = known[source]
    else:
        source = 'config'
        memory = configured

    return NodeResources(
        name=name,
        cores=cores_per_node,
        gpus=gpus_per_node,
        memory=memory,
        memory_source=source,
        memory_total=total,
        memory_configured=configured,
    )


def _report(nodes: List[NodeResources], logger) -> None:
    """
    Log what each node was credited with, and what it disagreed with.

    This is the standing record the design asks for, and it is what makes a
    machine's answer available without anyone running a probe: every
    concurrent run reports it.
    """
    logger.info('')
    logger.info('Allocation:')
    for node in nodes:
        name = node.name or 'this node'
        memory = 'unknown' if node.memory is None else f'{node.memory} MiB'
        logger.info(
            f'  {name}: {node.cores} cores, {node.gpus} gpus, '
            f'{memory} ({node.memory_source})'
        )
        if node.memory_total is not None:
            logger.info(f'      hardware: {node.memory_total} MiB')
        if node.memory_configured is not None:
            logger.info(f'      configured: {node.memory_configured} MiB')

    _warn_about_odd_nodes(nodes, logger)


def _warn_about_odd_nodes(nodes: List[NodeResources], logger) -> None:
    """Say when one node is much smaller than the rest, or than the config."""
    credited = [node.memory for node in nodes if node.memory is not None]
    if len(credited) > 1:
        smallest, largest = min(credited), max(credited)
        if largest > 0 and (largest - smallest) / largest > 0.05:
            logger.warning(
                f'The nodes of this allocation do not hold the same memory: '
                f"{smallest} MiB to {largest} MiB. Packing uses each node's "
                f'own figure, so this is handled, but a node far below its '
                f'neighbours may have something wrong with it.'
            )

    for node in nodes:
        configured = node.memory_configured
        if configured is None or node.memory is None:
            continue
        if node.memory_source == 'config':
            continue
        if node.memory < configured:
            logger.info(
                f'  {node.name or "this node"} credits '
                f"{configured - node.memory} MiB less than the machine's "
                f'configured {configured} MiB, which is what a job does not '
                f'get to use.'
            )
