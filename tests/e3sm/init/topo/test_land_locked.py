import logging

import numpy as np
import pytest

from polaris.tasks.e3sm.init.topo.cull.land_locked import (
    remove_land_locked_cells,
    remove_ocean_land_locked_cells,
)
from tests.mesh.hex_mesh import cell_index, hex_mesh

N_COLS = 9
N_ROWS = 9
THRESHOLD = 43.0

LOGGER = logging.getLogger('test_land_locked')

# a corridor one cell wide running north from the southern block to the
# northern one.  Its interior cells have an active edge to the north and one
# to the south, which are not adjacent in the cell's edge ordering, so they
# have two active edges and no active vertex.
CORRIDOR_COL = 4
CORRIDOR_ROWS = [3, 4, 5, 6]
INTERIOR = [cell_index(N_COLS, CORRIDOR_COL, row) for row in [4, 5]]


def test_dead_end_is_removed_from_the_ocean():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    ocean = _block(rows=range(0, 5))
    dead_end = cell_index(N_COLS, 4, 6)
    ocean[dead_end] = True

    refined = remove_ocean_land_locked_cells(
        ds_mesh, ocean, _seeds(cell_index(N_COLS, 4, 0))
    )

    assert not refined[dead_end]
    assert refined[cell_index(N_COLS, 4, 2)]


def test_removal_cascades_along_a_chain():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    ocean = _block(rows=range(0, 3))
    # a corridor hanging off the block, open at the top
    for row in CORRIDOR_ROWS:
        ocean[cell_index(N_COLS, CORRIDOR_COL, row)] = True

    refined = remove_ocean_land_locked_cells(
        ds_mesh, ocean, _seeds(cell_index(N_COLS, 4, 0))
    )

    # the topmost cell is a dead end, and each one below becomes one in turn
    for row in [6, 5, 4]:
        assert not refined[cell_index(N_COLS, CORRIDOR_COL, row)]
    # the cascade stops at the cell that still touches the block on two
    # sides, which is all the C-grid ocean needs
    assert refined[cell_index(N_COLS, CORRIDOR_COL, 3)]
    assert refined[_block(rows=range(0, 3))].all()


def test_disconnected_region_is_removed_from_the_ocean():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    ocean = np.logical_or(_block(rows=range(0, 3)), _block(rows=range(6, 9)))

    refined = remove_ocean_land_locked_cells(
        ds_mesh, ocean, _seeds(cell_index(N_COLS, 4, 0))
    )

    assert refined[_block(rows=range(0, 3))].all()
    assert not refined[_block(rows=range(6, 9))].any()


def test_vertex_criterion_removes_a_corridor_poleward():
    ds_mesh = hex_mesh(N_COLS, N_ROWS, lat_of_row=_split_lat)
    ocean = _corridor_between_blocks()

    refined_ocean, refined_no_cav = remove_land_locked_cells(
        ds_mesh=ds_mesh,
        ocean_mask=ocean,
        no_cavities_mask=ocean.copy(),
        land_ice_mask=np.zeros(N_COLS * N_ROWS, dtype=bool),
        ocean_seed_mask=_seeds(cell_index(N_COLS, 4, 0)),
        latitude_threshold=THRESHOLD,
        logger=LOGGER,
    )

    # with no land ice the two domains must come out identical
    np.testing.assert_array_equal(refined_ocean, refined_no_cav)
    # the corridor has no usable velocity vertex, so sea ice cannot pass
    for cell in INTERIOR:
        assert not refined_ocean[cell]
    # and the northern block, cut off by its removal, goes with it
    assert not refined_ocean[_block(rows=range(7, 9))].any()
    assert refined_ocean[_block(rows=range(0, 3))].all()


def test_the_same_corridor_survives_equatorward():
    # the whole lattice equatorward of the threshold, where no ice forms
    ds_mesh = hex_mesh(N_COLS, N_ROWS, lat_of_row=lambda row: 20.0)
    ocean = _corridor_between_blocks()

    refined_ocean, _ = remove_land_locked_cells(
        ds_mesh=ds_mesh,
        ocean_mask=ocean,
        no_cavities_mask=ocean.copy(),
        land_ice_mask=np.zeros(N_COLS * N_ROWS, dtype=bool),
        ocean_seed_mask=_seeds(cell_index(N_COLS, 4, 0)),
        latitude_threshold=THRESHOLD,
        logger=LOGGER,
    )

    for cell in INTERIOR:
        assert refined_ocean[cell]
    assert refined_ocean[_block(rows=range(7, 9))].all()


def test_a_cavity_may_differ_between_the_domains():
    ds_mesh = hex_mesh(N_COLS, N_ROWS, lat_of_row=_split_lat)
    ocean = _block(rows=range(0, 5))
    land_ice = np.zeros(N_COLS * N_ROWS, dtype=bool)
    cavity = cell_index(N_COLS, 4, 4)
    land_ice[cavity] = True
    no_cavities = np.logical_and(ocean, ~land_ice)

    refined_ocean, refined_no_cav = remove_land_locked_cells(
        ds_mesh=ds_mesh,
        ocean_mask=ocean,
        no_cavities_mask=no_cavities,
        land_ice_mask=land_ice,
        ocean_seed_mask=_seeds(cell_index(N_COLS, 4, 0)),
        latitude_threshold=THRESHOLD,
        logger=LOGGER,
    )

    assert refined_ocean[cavity]
    assert not refined_no_cav[cavity]
    # the domains differ only there
    assert np.logical_xor(refined_ocean, refined_no_cav).sum() == 1


def test_no_equatorward_cells_raises():
    ds_mesh = hex_mesh(N_COLS, N_ROWS, lat_of_row=lambda row: 60.0)
    ocean = _block(rows=range(0, 5))

    with pytest.raises(ValueError, match='no cells equatorward'):
        remove_land_locked_cells(
            ds_mesh=ds_mesh,
            ocean_mask=ocean,
            no_cavities_mask=ocean.copy(),
            land_ice_mask=np.zeros(N_COLS * N_ROWS, dtype=bool),
            ocean_seed_mask=_seeds(cell_index(N_COLS, 4, 0)),
            latitude_threshold=THRESHOLD,
            logger=LOGGER,
        )


def test_failure_to_converge_raises():
    ds_mesh = hex_mesh(N_COLS, N_ROWS, lat_of_row=_split_lat)
    ocean = _corridor_between_blocks()

    with pytest.raises(ValueError, match='did not converge'):
        remove_land_locked_cells(
            ds_mesh=ds_mesh,
            ocean_mask=ocean,
            no_cavities_mask=ocean.copy(),
            land_ice_mask=np.zeros(N_COLS * N_ROWS, dtype=bool),
            ocean_seed_mask=_seeds(cell_index(N_COLS, 4, 0)),
            latitude_threshold=THRESHOLD,
            logger=LOGGER,
            max_iterations=1,
        )


def _split_lat(row):
    """Rows 0 and 1 equatorward of the threshold, the rest poleward."""
    return 20.0 if row < 2 else 60.0


def _corridor_between_blocks():
    """
    A southern block and a northern one, joined by a corridor one cell wide.
    """
    mask = np.logical_or(_block(rows=range(0, 3)), _block(rows=range(7, 9)))
    for row in CORRIDOR_ROWS:
        mask[cell_index(N_COLS, CORRIDOR_COL, row)] = True
    return mask


def _block(rows, cols=range(N_COLS)):
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    for col in cols:
        for row in rows:
            mask[cell_index(N_COLS, col, row)] = True
    return mask


def _seeds(*cells):
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    for cell in cells:
        mask[cell] = True
    return mask
