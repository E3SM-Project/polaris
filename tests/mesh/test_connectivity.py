import numpy as np

from polaris.mesh.connectivity import (
    active_edge_masks,
    connected_to_seeds,
    count_active_edges,
    has_active_vertex,
    seed_mask_from_points,
    transport_link_mask,
)
from tests.mesh.hex_mesh import cell_index, hex_mesh

N_COLS = 7
N_ROWS = 7
CENTER = cell_index(N_COLS, 3, 2)


def test_interior_cell_has_six_active_edges():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.ones(N_COLS * N_ROWS, dtype=bool)

    assert count_active_edges(ds_mesh, mask)[CENTER] == 6
    assert has_active_vertex(ds_mesh, mask)[CENTER]


def test_dead_end_has_one_active_edge_and_no_vertex():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    # the center and a single neighbor, which is the east one
    mask[CENTER] = True
    mask[ds_mesh.cellsOnCell.values[CENTER, 0] - 1] = True

    assert count_active_edges(ds_mesh, mask)[CENTER] == 1
    assert not has_active_vertex(ds_mesh, mask)[CENTER]


def test_two_opposite_edges_satisfy_the_edge_test_but_not_the_vertex_test():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    neighbors = ds_mesh.cellsOnCell.values[CENTER] - 1
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    # east and west, which are local edges 0 and 3, so not adjacent
    mask[CENTER] = True
    mask[neighbors[0]] = True
    mask[neighbors[3]] = True

    assert count_active_edges(ds_mesh, mask)[CENTER] == 2
    assert not has_active_vertex(ds_mesh, mask)[CENTER]


def test_two_adjacent_edges_satisfy_both_tests():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    neighbors = ds_mesh.cellsOnCell.values[CENTER] - 1
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    # east and north-east, which are local edges 0 and 1
    mask[CENTER] = True
    mask[neighbors[0]] = True
    mask[neighbors[1]] = True

    assert count_active_edges(ds_mesh, mask)[CENTER] == 2
    assert has_active_vertex(ds_mesh, mask)[CENTER]


def test_transport_links_need_an_active_vertex():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    neighbors = ds_mesh.cellsOnCell.values[CENTER] - 1
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    mask[CENTER] = True
    mask[neighbors[0]] = True
    mask[neighbors[3]] = True

    active, _, _ = active_edge_masks(ds_mesh, mask)
    link = transport_link_mask(ds_mesh, mask)

    # both edges are active, but neither has an active vertex
    assert active[CENTER].sum() == 2
    assert link[CENTER].sum() == 0


def test_links_require_both_cells_in_the_domain():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.ones(N_COLS * N_ROWS, dtype=bool)
    # two cells separated by a removed cell must not be joined through it
    mask[cell_index(N_COLS, 3, 3)] = False

    seeds = np.zeros(N_COLS * N_ROWS, dtype=bool)
    seeds[CENTER] = True
    connected = connected_to_seeds(ds_mesh, mask, seeds)

    assert not connected[cell_index(N_COLS, 3, 3)]


def test_connectivity_over_plain_and_transport_graphs_differ():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    # a row of cells: edge-connected, but the joining edges have no active
    # vertex because there is nothing above or below them
    for col in range(N_COLS):
        mask[cell_index(N_COLS, col, 3)] = True
    seeds = np.zeros(N_COLS * N_ROWS, dtype=bool)
    seeds[cell_index(N_COLS, 0, 3)] = True

    plain = connected_to_seeds(ds_mesh, mask, seeds)
    transport = connected_to_seeds(
        ds_mesh, mask, seeds, link_mask=transport_link_mask(ds_mesh, mask)
    )

    assert plain[mask].all()
    assert not transport[cell_index(N_COLS, N_COLS - 1, 3)]


def test_disconnected_region_is_dropped_by_both_graphs():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.zeros(N_COLS * N_ROWS, dtype=bool)
    for col in range(3):
        for row in range(3):
            mask[cell_index(N_COLS, col, row)] = True
    island = cell_index(N_COLS, 6, 6)
    mask[island] = True

    seeds = np.zeros(N_COLS * N_ROWS, dtype=bool)
    seeds[cell_index(N_COLS, 0, 0)] = True

    assert not connected_to_seeds(ds_mesh, mask, seeds)[island]


def test_no_seeds_gives_nothing_connected():
    ds_mesh = hex_mesh(N_COLS, N_ROWS)
    mask = np.ones(N_COLS * N_ROWS, dtype=bool)
    seeds = np.zeros(N_COLS * N_ROWS, dtype=bool)

    assert not connected_to_seeds(ds_mesh, mask, seeds).any()


def test_seed_mask_picks_the_nearest_cell():
    ds_mesh = hex_mesh(3, 3, lat_of_row=lambda row: -60.0 + 30.0 * row)
    seeds = seed_mask_from_points(ds_mesh, [0.0], [-58.0])

    # the first row sits at -60, closer to -58 than the second row at -30
    assert seeds[:3].any()
    assert not seeds[3:].any()
