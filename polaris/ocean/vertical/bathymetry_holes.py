"""
Fill isolated bathymetry "holes" in a column layout.

A "hole" is an ocean cell whose bottom level (``maxLevelCell``) is deeper than
that of every one of its horizontal ocean neighbors.  The deepest layers of
such a cell have no neighbor at the same level to exchange with, so they are
effectively inert.  :py:func:`fill_max_level_holes` iteratively caps each
cell's ``maxLevelCell`` at its deepest ocean neighbor until no such holes
remain, mirroring the bathymetry smoothing MPAS-Ocean applies in its init mode.
"""

import numpy as np

__all__ = ['fill_max_level_holes']


def fill_max_level_holes(
    max_level_cell: np.ndarray,
    cells_on_cell: np.ndarray,
    n_edges_on_cell: np.ndarray,
) -> np.ndarray:
    """
    Cap each cell's ``maxLevelCell`` at its deepest ocean neighbor, iterating
    until no cell is deeper than all of its neighbors.

    The operation only ever *reduces* ``maxLevelCell`` (never deepens a
    column), and it leaves land/invalid columns (``maxLevelCell == 0``)
    untouched.

    Parameters
    ----------
    max_level_cell : numpy.ndarray
        1-based index of the bottom valid level for each cell (0 for
        land/invalid columns), shape ``(nCells,)``.

    cells_on_cell : numpy.ndarray
        0-based neighbor cell indices for each cell, shape
        ``(nCells, maxEdges)``.  Entries ``< 0`` mark missing neighbors.

    n_edges_on_cell : numpy.ndarray
        Number of valid edges (neighbors) for each cell, shape ``(nCells,)``.

    Returns
    -------
    numpy.ndarray
        Updated 1-based ``maxLevelCell`` with isolated deep pits removed.
    """
    max_level_cell = np.asarray(max_level_cell).copy()
    cells_on_cell = np.asarray(cells_on_cell)
    n_edges_on_cell = np.asarray(n_edges_on_cell)

    _, max_edges = cells_on_cell.shape
    edge_index = np.arange(max_edges)[np.newaxis, :]
    # neighbor slots that are within nEdgesOnCell and reference a real cell
    valid_slot = (edge_index < n_edges_on_cell[:, np.newaxis]) & (
        cells_on_cell >= 0
    )
    # clamp missing indices to 0 so the fancy-indexing below stays in bounds;
    # such slots are excluded by valid_slot / ocean_neighbor anyway
    neighbor = np.where(valid_slot, cells_on_cell, 0)

    while True:
        neighbor_level = max_level_cell[neighbor]
        # only ocean neighbors (level > 0) in valid slots count
        ocean_neighbor = valid_slot & (neighbor_level > 0)
        deepest_neighbor = np.where(ocean_neighbor, neighbor_level, 0).max(
            axis=1
        )
        has_ocean_neighbor = ocean_neighbor.any(axis=1)

        # cap a cell only if it is an ocean cell with at least one ocean
        # neighbor and is deeper than every one of those neighbors
        needs_cap = (
            (max_level_cell > 0)
            & has_ocean_neighbor
            & (max_level_cell > deepest_neighbor)
        )
        capped = np.where(needs_cap, deepest_neighbor, max_level_cell)

        if np.array_equal(capped, max_level_cell):
            break
        max_level_cell = capped

    return max_level_cell
