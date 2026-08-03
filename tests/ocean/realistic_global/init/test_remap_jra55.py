import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.remap_jra55 import (
    fill_missing_from_nearest,
)


def _cells_along_a_line(n_cells):
    """
    Cell centres strung out along the x axis, so "nearest" is unambiguous.
    """
    xyz = np.zeros((n_cells, 3))
    xyz[:, 0] = np.arange(n_cells, dtype=float)
    return xyz


def _dataset(taux, tauy):
    return xr.Dataset(
        {
            'taux': ('nCells', np.asarray(taux, dtype=float)),
            'tauy': ('nCells', np.asarray(tauy, dtype=float)),
        }
    )


def test_no_missing_values_is_a_no_op():
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
    ds_out, n_filled = fill_missing_from_nearest(
        ds=ds,
        var_names=['taux', 'tauy'],
        cell_xyz=_cells_along_a_line(3),
        max_fill_fraction=1.0e-4,
        min_allowed_fill=16,
    )
    assert n_filled == 0
    np.testing.assert_allclose(ds_out.taux.values, [1.0, 2.0, 3.0])


def test_missing_cells_take_their_nearest_neighbour():
    ds = _dataset([1.0, 2.0, np.nan, 4.0], [-1.0, -2.0, np.nan, -4.0])
    ds_out, n_filled = fill_missing_from_nearest(
        ds=ds,
        var_names=['taux', 'tauy'],
        cell_xyz=np.array(
            [[0.0, 0, 0], [1.0, 0, 0], [1.1, 0, 0], [5.0, 0, 0]]
        ),
        max_fill_fraction=1.0e-4,
        min_allowed_fill=16,
    )
    assert n_filled == 1
    # cell 2 is closest to cell 1
    assert ds_out.taux.values[2] == pytest.approx(2.0)
    assert ds_out.tauy.values[2] == pytest.approx(-2.0)


def test_components_are_filled_from_the_same_donor():
    """
    A cell is missing if *any* component is, so the filled vector stays
    physical rather than mixing components from different donors.
    """
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, np.nan, -3.0])
    ds_out, n_filled = fill_missing_from_nearest(
        ds=ds,
        var_names=['taux', 'tauy'],
        cell_xyz=np.array([[0.0, 0, 0], [0.9, 0, 0], [5.0, 0, 0]]),
        max_fill_fraction=1.0e-4,
        min_allowed_fill=16,
    )
    assert n_filled == 1
    # taux at cell 1 was finite, but is replaced along with tauy so both
    # come from cell 0
    assert ds_out.taux.values[1] == pytest.approx(1.0)
    assert ds_out.tauy.values[1] == pytest.approx(-1.0)


def test_implausibly_many_missing_cells_raises():
    """
    The expected gap is the small polar cap.  A large missing count means
    something other than the pole is wrong and must not be filled silently.
    """
    n_cells = 1000
    taux = np.ones(n_cells)
    taux[: n_cells // 2] = np.nan
    ds = _dataset(taux, np.ones(n_cells))
    with pytest.raises(ValueError, match='refusing to fill'):
        fill_missing_from_nearest(
            ds=ds,
            var_names=['taux', 'tauy'],
            cell_xyz=_cells_along_a_line(n_cells),
            max_fill_fraction=1.0e-4,
            min_allowed_fill=16,
        )


def test_small_meshes_are_allowed_the_absolute_floor():
    """
    On a coarse mesh the fraction test would trip on a single legitimately
    filled polar cell, so a small absolute number is always allowed.
    """
    n_cells = 100
    taux = np.ones(n_cells)
    taux[0] = np.nan
    ds = _dataset(taux, np.ones(n_cells))
    _, n_filled = fill_missing_from_nearest(
        ds=ds,
        var_names=['taux', 'tauy'],
        cell_xyz=_cells_along_a_line(n_cells),
        max_fill_fraction=1.0e-4,
        min_allowed_fill=16,
    )
    assert n_filled == 1
