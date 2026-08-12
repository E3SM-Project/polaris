"""
Which core counts a mesh's graph gets partitioned into, and which of them are
still to build.

:py:func:`get_core_list` is ported essentially verbatim from Compass'
``files_for_e3sm/graph_partition.py``.  It is a pure function of a cell count
and two bounds, so unlike in Compass it gets real unit tests.
"""

import os

import numpy as np


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
