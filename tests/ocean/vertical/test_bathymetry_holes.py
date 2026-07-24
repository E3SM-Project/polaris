"""
Unit tests for polaris.ocean.vertical.bathymetry_holes.fill_max_level_holes.

All tests are self-contained: a tiny synthetic connectivity is built in each
test, so no file I/O or Polaris step framework is needed.
"""

import numpy as np

from polaris.ocean.vertical.bathymetry_holes import fill_max_level_holes


def _fill(max_level_cell, cells_on_cell, n_edges_on_cell):
    return fill_max_level_holes(
        max_level_cell=np.array(max_level_cell),
        cells_on_cell=np.array(cells_on_cell),
        n_edges_on_cell=np.array(n_edges_on_cell),
    ).tolist()


def test_single_pit_capped_to_deepest_neighbor():
    """A center cell deeper than all its neighbors is capped at the deepest
    neighbor's level (in one step, regardless of how many levels deeper)."""
    # cell0 (level 8) neighbors cell1 (5) and cell2 (3); 8 > 5 -> cap to 5
    result = _fill(
        max_level_cell=[8, 5, 3],
        cells_on_cell=[[1, 2], [0, -1], [0, -1]],
        n_edges_on_cell=[2, 1, 1],
    )
    assert result == [5, 5, 3]


def test_cell_equal_to_deepest_neighbor_is_not_a_hole():
    """A cell whose level ties its deepest neighbor is not a hole and is left
    unchanged (a hole requires being strictly deeper than every neighbor)."""
    result = _fill(
        max_level_cell=[5, 5, 3],
        cells_on_cell=[[1, 2], [0, -1], [0, -1]],
        n_edges_on_cell=[2, 1, 1],
    )
    assert result == [5, 5, 3]


def test_cell_with_a_deeper_neighbor_is_unchanged():
    """A cell deeper than some but not all neighbors is not a hole; only the
    genuinely isolated pit (cell1 here) is capped."""
    # cell0 (5) has a deeper neighbor cell1 (6), so cell0 is not a hole.
    # cell1 (6) has only neighbor cell0 (5), so cell1 is a pit -> cap to 5.
    result = _fill(
        max_level_cell=[5, 6, 3],
        cells_on_cell=[[1, 2], [0, -1], [0, -1]],
        n_edges_on_cell=[2, 1, 1],
    )
    assert result == [5, 5, 3]


def test_cell_with_no_ocean_neighbors_is_unchanged():
    """A cell surrounded only by land (level 0) has no ocean neighbor to cap
    against and is left as-is."""
    result = _fill(
        max_level_cell=[4, 0, 0],
        cells_on_cell=[[1, 2], [0, -1], [0, -1]],
        n_edges_on_cell=[2, 1, 1],
    )
    assert result == [4, 0, 0]


def test_land_cells_are_never_deepened_or_touched():
    """Land/invalid columns (level 0) stay 0 and never gain levels."""
    result = _fill(
        max_level_cell=[6, 0, 4],
        cells_on_cell=[[1, 2], [0, 2], [0, 1]],
        n_edges_on_cell=[2, 2, 2],
    )
    # cell0 (6) neighbors are cell2 (4) and land cell1 (ignored) -> cap to 4;
    # land cell1 stays 0; cell2 (4) neighbor cell0 (now 4) -> tie, unchanged
    assert result == [4, 0, 4]


def test_already_smooth_field_is_returned_unchanged():
    """A field with no isolated pits is returned untouched."""
    max_level_cell = [3, 4, 4, 3]
    result = _fill(
        max_level_cell=max_level_cell,
        cells_on_cell=[[1, -1], [0, 2], [1, 3], [2, -1]],
        n_edges_on_cell=[1, 2, 2, 1],
    )
    assert result == max_level_cell
