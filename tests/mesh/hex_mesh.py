"""
A small hexagonal-lattice mesh for testing cell-connectivity code.

The lattice uses odd-row-offset coordinates, so every interior cell has six
neighbors in angular order (east, north-east, north-west, west, south-west,
south-east).  Consecutive neighbors in that order share a vertex with each
other and with the cell, which is what the active-vertex tests depend on.
"""

import numpy as np
import xarray as xr

# neighbor offsets in angular order for even and odd rows
_EVEN = [(1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1)]
_ODD = [(1, 0), (1, 1), (0, 1), (-1, 0), (0, -1), (1, -1)]


def hex_mesh(n_cols, n_rows, lat_of_row=None):
    """
    Build a hexagonal-lattice mesh dataset.

    Parameters
    ----------
    n_cols : int
        The number of cells in each row

    n_rows : int
        The number of rows

    lat_of_row : callable, optional
        A function of the row index returning the latitude in degrees of
        the cells in that row.  The default puts every cell at 60 degrees
        north, which is poleward of the usual sea-ice threshold.

    Returns
    -------
    ds_mesh : xarray.Dataset
        A mesh with ``cellsOnCell``, ``nEdgesOnCell``, ``latCell`` and
        ``lonCell``
    """
    if lat_of_row is None:

        def lat_of_row(row):
            return 60.0

    n_cells = n_cols * n_rows

    def index(col, row):
        if 0 <= col < n_cols and 0 <= row < n_rows:
            return col + row * n_cols
        return -1

    cells_on_cell = np.zeros((n_cells, 6), dtype=int)
    lat_cell = np.zeros(n_cells)
    for row in range(n_rows):
        offsets = _ODD if row % 2 else _EVEN
        for col in range(n_cols):
            cell = index(col, row)
            lat_cell[cell] = lat_of_row(row)
            for local, (d_col, d_row) in enumerate(offsets):
                # cellsOnCell is 1-based, with 0 meaning no neighbor
                neighbor = index(col + d_col, row + d_row)
                cells_on_cell[cell, local] = neighbor + 1

    return xr.Dataset(
        data_vars=dict(
            cellsOnCell=(('nCells', 'maxEdges'), cells_on_cell),
            nEdgesOnCell=('nCells', np.full(n_cells, 6, dtype=int)),
            latCell=('nCells', np.radians(lat_cell)),
            lonCell=('nCells', np.zeros(n_cells)),
        )
    )


def cell_index(n_cols, col, row):
    """
    The cell index of a lattice position, matching :py:func:`hex_mesh`.
    """
    return col + row * n_cols
