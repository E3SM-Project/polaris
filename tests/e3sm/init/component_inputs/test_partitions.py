import numpy as np

from polaris.tasks.e3sm.init.component_inputs.partitions import (
    get_region_graph,
    read_graph_cell_count,
    write_graph,
)


def test_a_region_graph_keeps_only_the_edges_inside_it():
    """
    Three cells cut from a loop of six are a line, not a loop: the edges to
    the cells outside go with them.
    """
    cells_on_cell, n_edges_on_cell = _ring(6)
    in_region = np.array([True, True, True, False, False, False])

    cells, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    np.testing.assert_array_equal(cells, [0, 1, 2])
    np.testing.assert_array_equal(xadj, [0, 1, 3, 4])
    np.testing.assert_array_equal(adjncy, [1, 0, 2, 1])


def test_a_region_graph_numbers_cells_within_the_region():
    """
    The graph's vertices are the region's cells in mesh order, so a vertex
    number is a position in ``cells``, not an index in the mesh.
    """
    cells_on_cell, n_edges_on_cell = _ring(6)
    in_region = np.array([False, False, False, True, True, True])

    cells, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    np.testing.assert_array_equal(cells, [3, 4, 5])
    np.testing.assert_array_equal(xadj, [0, 1, 3, 4])
    np.testing.assert_array_equal(adjncy, [1, 0, 2, 1])


def test_a_region_graph_ignores_missing_and_unused_neighbors():
    """
    A 0 is a neighbor that is not there, and a slot past ``nEdgesOnCell`` is
    not a neighbor at all, even when it holds a cell index.
    """
    cells_on_cell, n_edges_on_cell = _grid(3, 3)

    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, np.ones(9, dtype=bool)
    )

    # 4 corners with 2 neighbors, 4 edge cells with 3, the center with 4
    np.testing.assert_array_equal(np.diff(xadj), [2, 3, 2, 3, 4, 3, 2, 3, 2])
    assert len(adjncy) == 2 * 12


def test_every_edge_of_a_region_graph_appears_from_both_ends():
    """
    gpmetis requires it, and a region cut at random is where a one-sided
    filter on neighbors would break it.
    """
    cells_on_cell, n_edges_on_cell = _grid(12, 10)
    in_region = np.random.default_rng(seed=0).random(120) < 0.6

    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, in_region
    )

    vertex = np.repeat(np.arange(len(xadj) - 1), np.diff(xadj))
    edges = set(zip(vertex.tolist(), adjncy.tolist(), strict=True))
    assert edges == {(b, a) for a, b in edges}


def test_a_written_graph_has_the_header_gpmetis_expects(tmp_path):
    """
    The vertex count, then the edge count with each edge counted once, then
    one line per vertex of one-based neighbors.
    """
    cells_on_cell, n_edges_on_cell = _ring(4)
    _, xadj, adjncy = get_region_graph(
        cells_on_cell, n_edges_on_cell, np.ones(4, dtype=bool)
    )

    filename = str(tmp_path / 'graph.info')
    write_graph(filename, xadj, adjncy)

    with open(filename) as graph_file:
        lines = graph_file.read().splitlines()
    assert lines == ['4 4', '4 2', '1 3', '2 4', '3 1']
    assert read_graph_cell_count(filename) == 4


def _grid(nx, ny):
    """
    A rectangular mesh of square cells, as ``cellsOnCell`` and
    ``nEdgesOnCell``.

    Neighbors off the edge of the grid are 0, as in a culled MPAS mesh, and
    the slots past ``nEdgesOnCell`` hold a real cell index, so that a graph
    that read either would come out wrong rather than by luck right.
    """
    ncells = nx * ny
    index = np.arange(ncells).reshape(ny, nx)
    cells_on_cell = np.ones((ncells, 6), dtype=np.int32)
    for column, (dy, dx) in enumerate([(0, 1), (1, 0), (0, -1), (-1, 0)]):
        y, x = np.divmod(np.arange(ncells), nx)
        y, x = y + dy, x + dx
        inside = (x >= 0) & (x < nx) & (y >= 0) & (y < ny)
        neighbor = np.zeros(ncells, dtype=np.int32)
        neighbor[inside] = index[y[inside], x[inside]] + 1
        cells_on_cell[:, column] = neighbor
    n_edges_on_cell = np.full(ncells, 4, dtype=np.int32)
    return cells_on_cell, n_edges_on_cell


def _ring(ncells):
    """
    Cells in a loop, each with the one before and the one after it.
    """
    cell = np.arange(ncells)
    cells_on_cell = np.zeros((ncells, 3), dtype=np.int32)
    cells_on_cell[:, 0] = (cell - 1) % ncells + 1
    cells_on_cell[:, 1] = (cell + 1) % ncells + 1
    return cells_on_cell, np.full(ncells, 2, dtype=np.int32)
