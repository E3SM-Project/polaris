"""
Which core counts a mesh's graph gets partitioned into, which of them are
still to build, and building them.

:py:func:`get_core_list` is ported essentially verbatim from Compass'
``files_for_e3sm/graph_partition.py``.  It is a pure function of a cell count
and two bounds, so unlike in Compass it gets real unit tests.

:py:func:`build_partitions` runs ``gpmetis`` once per core count, several at a
time.  Each call is serial, but a mesh needs hundreds of them, and on the
finest unified mesh they add up to most of a day on one core.
"""

import multiprocessing
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import NamedTuple

import numpy as np

#: The file every ``gpmetis`` report is appended to.  There are hundreds of
#: them, and in the step's log they would bury everything else.
GPMETIS_LOG = 'gpmetis.log'


class RegionGraph(NamedTuple):
    """
    A graph file to partition, and which of a mesh's cells it covers.

    Attributes
    ----------
    filename : str
        The graph file, in the format ``gpmetis`` reads.

    cells : numpy.ndarray or None
        The index in the full mesh of each vertex in the graph, or ``None`` if
        the graph is the whole mesh.
    """

    filename: str
    cells: np.ndarray | None = None


#: The regions a worker process partitions, set when it starts.
_worker_regions: list[RegionGraph] = []


def get_core_list(ncells, max_cells_per_core=30000, min_cells_per_core=2):
    """
    A fairly exhaustive list of core counts to partition a mesh into.

    The list is not every integer in range.  It keeps counts that factor well
    for a decomposition, plus whole-node counts for the node sizes E3SM
    machines actually have, plus a few counts that divide the ne30 atmosphere
    mesh, since a run is usually laid out around those.

    Parameters
    ----------
    ncells : int
        The number of cells in the mesh.

    max_cells_per_core : float, optional
        The approximate maximum number of cells per core, which sets the
        smallest partition created.

    min_cells_per_core : float, optional
        The approximate minimum number of cells per core, which sets the
        largest partition created.

    Returns
    -------
    numpy.ndarray
        The core counts, in increasing order.
    """
    min_graph_size = max(2, int(ncells / max_cells_per_core))
    max_graph_size = int(ncells / min_cells_per_core)

    node_sizes = [16, 24, 30, 32, 36, 44, 52, 56, 64, 84, 96, 112, 128, 256]
    max_nodes = 20

    special_core_counts = [3, 9, 15, 21, 225, 675, 1350]

    max_nodes_approx = 100
    special_approx_cores = [675, 1350, 2700, 5400]

    cores = set()
    if ncells < max_cells_per_core:
        cores.add(1)

    for candidate in range(min_graph_size, max_graph_size):
        factors = _prime_factors(candidate)
        twos = np.count_nonzero(factors == 2)
        fives = np.count_nonzero(factors == 5)
        gt_five = np.count_nonzero(factors > 5)
        big_factor = factors.max()
        if twos > 0 and fives <= twos and gt_five <= 1 and big_factor <= 7:
            cores.add(candidate)
        # small odd multiples of 3 and a few that correspond to divisors of
        # the ne30 (30x30x6=5400) size
        elif candidate in special_core_counts:
            cores.add(candidate)

    # add node counts from 1 to max_nodes even if they're weird primes
    for node_size in node_sizes:
        for node_count in range(1, max_nodes + 1):
            core_count = node_size * node_count
            if min_graph_size <= core_count <= max_graph_size:
                cores.add(core_count)

    # add even node counts if they are close to some especially desirable core
    # counts for the ne30 atmosphere mesh (also used for MPAS-Seaice)
    for node_size in node_sizes:
        for node_count in range(1, max_nodes_approx + 1):
            core_count = node_size * node_count
            for approx in special_approx_cores:
                lower = max(approx - 2 * node_size, min_graph_size)
                upper = min(approx + 2 * node_size, max_graph_size)
                if lower <= core_count <= upper:
                    cores.add(core_count)

    return np.array(sorted(cores))


def read_graph_cell_count(graph_filename):
    """
    The number of cells a METIS graph file describes.

    Read from the header rather than by counting lines, which overcounts by
    the header itself.

    Parameters
    ----------
    graph_filename : str
        The path to the graph file.

    Returns
    -------
    int
        The number of cells (vertices) in the graph.
    """
    with open(graph_filename) as graph_file:
        header = graph_file.readline()
    return int(header.split()[0])


def partitions_to_build(cores, basename, ncells):
    """
    The core counts from ``cores`` that still need a partition file.

    Partitioning a large mesh takes hours -- most of a day on the finest
    unified mesh -- so a step that is interrupted has to be able to pick up
    where it stopped rather than start over.

    A file is only taken as finished when it has one line per cell, which is
    what ``gpmetis`` writes.  Existence alone is not enough: a job killed at
    its walltime leaves a partition truncated part-way through, and trusting
    that would hand E3SM a partition covering some of the mesh.  The one-piece
    partition is the exception, being deliberately empty.

    Parameters
    ----------
    cores : iterable of int
        The core counts the step means to partition into.

    basename : str
        The partition filenames without the ``.part.<n>`` suffix.

    ncells : int
        The number of cells each complete partition file describes.

    Returns
    -------
    list of int
        The core counts still to build, in the order given.
    """
    return [
        int(ncores)
        for ncores in cores
        if not _is_complete_partition(
            f'{basename}.part.{ncores}', int(ncores), ncells
        )
    ]


def build_partitions(regions, cores, basename, ncells, process_count, logger):
    """
    Write the partition file for each core count, several at a time.

    Each region's graph is partitioned into ``n`` pieces on its own, and piece
    ``i`` of every region goes to core ``i``, so every core gets a share of
    every region.  With one region covering the whole mesh, that is a plain
    partition of the mesh's graph.

    Each partition is written under another name and renamed once it is
    complete, so a job killed at its walltime cannot leave a truncated file
    under the name E3SM reads.

    Parameters
    ----------
    regions : list of RegionGraph
        The graphs to partition, one per region.

    cores : iterable of int
        The core counts to build a partition file for.

    basename : str
        The partition filenames without the ``.part.<n>`` suffix.

    ncells : int
        The number of cells in the full mesh.

    process_count : int
        The most ``gpmetis`` processes to run at once.

    logger : logging.Logger
        The logger to report progress to.
    """
    cores = [int(ncores) for ncores in cores]
    if 1 in cores:
        # gpmetis will not make a one-piece partition, and an empty file is
        # what MPAS reads as "every cell on one task"
        with open(f'{basename}.part.1', 'w'):
            pass
        cores.remove(1)

    # the largest partitions take longest, so starting them first keeps the
    # last few from running on alone
    cores.sort(reverse=True)

    results = _build_all(regions, cores, basename, ncells, process_count)
    with open(GPMETIS_LOG, 'a') as gpmetis_log:
        for index, (ncores, elapsed, reports) in enumerate(results):
            gpmetis_log.write(''.join(reports))
            gpmetis_log.flush()
            logger.info(
                f'  {ncores} pieces in {elapsed:.0f} s '
                f'({index + 1} of {len(cores)})'
            )


def get_region_graph(cells_on_cell, n_edges_on_cell, in_region):
    """
    The graph of a region's cells, keeping only the edges between them.

    This is the graph ``MpasCellCuller.x`` writes for a mesh culled to the
    region, without culling the mesh: the cells keep their order, and so does
    each cell's list of neighbors.

    Parameters
    ----------
    cells_on_cell : numpy.ndarray
        The mesh's one-based ``cellsOnCell``.

    n_edges_on_cell : numpy.ndarray
        The mesh's ``nEdgesOnCell``.

    in_region : numpy.ndarray
        Whether each cell is in the region.

    Returns
    -------
    cells : numpy.ndarray
        The index in the mesh of each cell in the region.

    xadj : numpy.ndarray
        Where each cell's neighbors start in ``adjncy``, with one more entry
        than there are cells.

    adjncy : numpy.ndarray
        Each cell's neighbors in the region, by their zero-based index among
        the region's cells.
    """
    ncells, max_edges = cells_on_cell.shape
    in_region = np.asarray(in_region, dtype=bool)
    cells = np.flatnonzero(in_region)

    neighbors = cells_on_cell[cells].astype(np.int64) - 1
    is_neighbor = (
        np.arange(max_edges) < n_edges_on_cell[cells, np.newaxis]
    ) & ((neighbors >= 0) & (neighbors < ncells))
    is_neighbor[is_neighbor] = in_region[neighbors[is_neighbor]]

    region_index = np.full(ncells, -1, dtype=np.int64)
    region_index[cells] = np.arange(len(cells))

    xadj = np.zeros(len(cells) + 1, dtype=np.int64)
    np.cumsum(np.count_nonzero(is_neighbor, axis=1), out=xadj[1:])
    adjncy = region_index[neighbors[is_neighbor]]
    return cells, xadj, adjncy


def write_graph(filename, xadj, adjncy):
    """
    Write a graph in the format ``gpmetis`` reads.

    Parameters
    ----------
    filename : str
        The file to write.

    xadj : numpy.ndarray
        Where each vertex's neighbors start in ``adjncy``, with one more entry
        than there are vertices.

    adjncy : numpy.ndarray
        Each vertex's zero-based neighbors, one vertex after another.  Every
        edge appears once from each end.
    """
    bounds = np.asarray(xadj).tolist()
    neighbors = [str(vertex + 1) for vertex in np.asarray(adjncy).tolist()]
    with open(filename, 'w') as handle:
        handle.write(f'{len(bounds) - 1} {len(neighbors) // 2}\n')
        for start, end in zip(bounds[:-1], bounds[1:], strict=True):
            handle.write(' '.join(neighbors[start:end]))
            handle.write('\n')


def _build_all(regions, cores, basename, ncells, process_count):
    """
    The result of building each partition, in the order they finish.
    """
    if process_count <= 1 or len(cores) <= 1:
        for ncores in cores:
            yield _build_partition(regions, basename, ncells, ncores)
        return

    # forkserver rather than fork, because the step's process may have threads
    # by now.  The server imports this module once and the workers inherit
    # it: importing it means importing every Polaris task, which in dozens of
    # processes at once on a shared file system can take minutes.  (If the
    # server is already running, the workers just import it themselves.)
    context = multiprocessing.get_context('forkserver')
    context.set_forkserver_preload(['__main__', __name__])

    # each worker is handed the regions once, rather than with every task,
    # since the sea-ice regions carry a cell index for every cell in the mesh
    with ProcessPoolExecutor(
        max_workers=min(process_count, len(cores)),
        mp_context=context,
        initializer=_set_worker_regions,
        initargs=(regions,),
    ) as executor:
        futures = [
            executor.submit(_build_partition_in_worker, basename, ncells, n)
            for n in cores
        ]
        try:
            for future in as_completed(futures):
                yield future.result()
        finally:
            # after a failure, start nothing new; partitions already being
            # built are left to finish, so a rerun has them
            for future in futures:
                future.cancel()


def _set_worker_regions(regions):
    """
    Hand a worker process the regions it partitions.
    """
    global _worker_regions
    _worker_regions = regions


def _build_partition_in_worker(basename, ncells, ncores):
    """
    Build one partition file in a worker process.
    """
    return _build_partition(_worker_regions, basename, ncells, ncores)


def _build_partition(regions, basename, ncells, ncores):
    """
    Build the partition file for one core count.
    """
    start = time.monotonic()
    reports = []
    partition = np.zeros(ncells, dtype=np.int64)
    for region in regions:
        pieces, report = _run_gpmetis(region.filename, ncores)
        reports.append(report)
        cells = slice(None) if region.cells is None else region.cells
        partition[cells] = pieces

    incomplete = f'{basename}.incomplete.{ncores}'
    with open(incomplete, 'w') as handle:
        handle.write('\n'.join(map(str, partition.tolist())))
        handle.write('\n')
    os.replace(incomplete, f'{basename}.part.{ncores}')
    return ncores, time.monotonic() - start, reports


def _run_gpmetis(graph_filename, ncores):
    """
    Partition a graph file, returning each vertex's piece and what gpmetis
    printed.
    """
    # gpmetis names its output after its input.  A file left by a killed run
    # must not be read as this run's.
    filename = f'{graph_filename}.part.{ncores}'
    if os.path.exists(filename):
        os.remove(filename)

    args = ['gpmetis', graph_filename, f'{ncores}']
    result = subprocess.run(args, capture_output=True, text=True)
    report = f'$ {" ".join(args)}\n{result.stdout}{result.stderr}\n'
    if result.returncode != 0 or not os.path.exists(filename):
        message = (
            f'gpmetis did not partition {graph_filename} into {ncores} '
            f'pieces:\n{report}'
        )
        if 'idx_t: 32bits' in result.stdout:
            message += (
                'This gpmetis is a 32-bit build, which fails on the largest '
                'meshes.  The 64-bit build comes from Spack, through the '
                'Polaris load script.\n'
            )
        raise RuntimeError(message)

    pieces = np.loadtxt(filename, dtype=np.int64, ndmin=1)
    os.remove(filename)
    return pieces, report


def _is_complete_partition(filename, ncores, ncells):
    """
    Whether a partition file is finished, rather than merely present.
    """
    if not os.path.exists(filename):
        return False
    if ncores == 1:
        # written empty on purpose: MPAS reads that as "every cell on one
        # task", so there are no lines to count
        return True
    return _count_lines(filename) == ncells


def _count_lines(filename):
    """
    Count the lines in a file, in binary chunks so that a partition file with
    millions of lines costs milliseconds.
    """
    count = 0
    with open(filename, 'rb') as handle:
        while chunk := handle.read(1024 * 1024):
            count += chunk.count(b'\n')
    return count


# https://stackoverflow.com/a/22808285
def _prime_factors(n):
    i = 2
    factors = []
    while i * i <= n:
        if n % i:
            i += 1
        else:
            n //= i
            factors.append(i)
    if n > 1:
        factors.append(n)
    return np.array(factors)
