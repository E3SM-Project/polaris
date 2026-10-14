import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.remap_jra55 import (
    check_no_missing_cells,
)


def _dataset(taux, tauy):
    return xr.Dataset(
        {
            'taux': ('nCells', np.asarray(taux, dtype=float)),
            'tauy': ('nCells', np.asarray(tauy, dtype=float)),
        }
    )


def test_fully_covered_cells_pass():
    """
    Bilinear weights cover a cell only to within round-off of one.
    """
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
    frac_b = np.array([1.0, 1.0 - 1.0e-15, 1.0 + 1.0e-15])
    check_no_missing_cells(ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b)


def test_an_uncovered_cell_raises():
    """
    ncremap writes zero to a cell the weights do not reach, so only the
    coverage from the mapping file shows it is missing.
    """
    ds = _dataset([1.0, 0.0, 3.0], [-1.0, 0.0, -3.0])
    frac_b = np.array([1.0, 0.0, 1.0])
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )


def test_a_partly_covered_cell_raises():
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
    frac_b = np.array([1.0, 0.5, 1.0])
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )


def test_a_non_finite_component_raises():
    ds = _dataset([1.0, 2.0, 3.0], [-1.0, np.nan, -3.0])
    frac_b = np.ones(3)
    with pytest.raises(ValueError, match='1 of 3 cells'):
        check_no_missing_cells(
            ds=ds, var_names=['taux', 'tauy'], frac_b=frac_b
        )
