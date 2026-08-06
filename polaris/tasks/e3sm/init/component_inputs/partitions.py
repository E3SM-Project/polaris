"""
Which core counts a mesh's graph gets partitioned into.

Ported essentially verbatim from Compass'
``files_for_e3sm/graph_partition.py``.  It is a pure function of a cell count
and two bounds, so unlike in Compass it gets real unit tests.
"""

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
