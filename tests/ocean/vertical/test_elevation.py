"""
Unit tests for the vertical reductions that pick a layer by index.

The columns are synthetic and their geometry is known, so what is checked is
that ``minLevelCell`` and ``maxLevelCell`` are respected: an ice-shelf cavity
whose topmost valid layer is not the topmost layer of the grid, a column
whose seafloor is above the bottom of the grid, and land.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical.elevation import (
    apply_vertical_reduction,
    get_valid_level_range,
    parse_vertical_reduction,
)

N_LEVELS = 6

# one column per case: a full-depth column, an ice-shelf cavity whose top
# three layers are in the ice, a shallow column, and a land column
MIN_LEVEL_CELL = [0, 3, 0, 0]
MAX_LEVEL_CELL = [5, 5, 2, -1]
LAND = 3


@pytest.fixture
def columns():
    """A field whose value is the layer index plus 100 times the cell, so
    that a value says which layer of which column it came from."""
    cells = np.arange(len(MIN_LEVEL_CELL))[:, None]
    levels = np.arange(N_LEVELS)[None, :]
    return xr.Dataset(
        dict(
            field=(('nCells', 'nVertLevels'), 100.0 * cells + levels),
            minLevelCell=('nCells', np.array(MIN_LEVEL_CELL)),
            maxLevelCell=('nCells', np.array(MAX_LEVEL_CELL)),
        )
    )


def test_top_is_the_topmost_valid_layer(columns):
    """Including under an ice-shelf cavity, where it is not layer zero."""
    values = _reduce(columns, 'top')
    assert values[0] == 0.0
    assert values[1] == 100.0 + 3
    assert values[2] == 200.0
    assert np.isnan(values[LAND])


def test_bottom_is_the_bottommost_valid_layer(columns):
    """Including where the seafloor is above the bottom of the grid."""
    values = _reduce(columns, 'bottom')
    assert values[0] == 5.0
    assert values[1] == 100.0 + 5
    assert values[2] == 200.0 + 2
    assert np.isnan(values[LAND])


def test_a_fixed_index_returns_that_index(columns):
    values = _reduce(columns, 'k1')
    assert values[0] == 1.0
    assert values[2] == 200.0 + 1


def test_a_fixed_index_is_masked_above_the_topmost_valid_layer(columns):
    """In the cavity column, layer 1 is in the ice."""
    values = _reduce(columns, 'k1')
    assert np.isnan(values[1])


def test_a_fixed_index_is_masked_below_the_seafloor(columns):
    """In the shallow column, layer 4 is below the seafloor."""
    values = _reduce(columns, 'k4')
    assert np.isnan(values[2])
    assert values[0] == 4.0


def test_land_is_masked_for_every_reduction(columns):
    for spec in ('top', 'bottom', 'k0', 'k5'):
        assert np.isnan(_reduce(columns, spec)[LAND])


def test_the_vertical_dimension_is_gone(columns):
    da_map = _reduce(columns, 'top', raw=True)
    assert 'nVertLevels' not in da_map.dims
    assert da_map.dims == ('nCells',)


def test_a_time_dimension_survives(columns):
    """Maps are made from a climatology, which has a length-one time axis."""
    ds = columns.copy()
    ds['field'] = ds.field.expand_dims(dim='time', axis=0)
    da_map = apply_vertical_reduction(
        ds.field,
        parse_vertical_reduction('top'),
        min_level_cell=ds.minLevelCell,
        max_level_cell=ds.maxLevelCell,
    )
    assert da_map.dims == ('time', 'nCells')


def test_the_reductions_parse():
    assert parse_vertical_reduction('top').kind == 'top'
    assert parse_vertical_reduction('BOTTOM').kind == 'bottom'
    assert parse_vertical_reduction(' k10 ').level == 10
    assert parse_vertical_reduction('k10').label == 'k10'
    assert parse_vertical_reduction('-100.0').elevation == -100.0
    assert parse_vertical_reduction('-100.0').label == '-100m'


def test_something_that_is_neither_is_reported():
    with pytest.raises(ValueError, match='not a vertical reduction'):
        parse_vertical_reduction('surface')
    with pytest.raises(ValueError, match='not a vertical index'):
        parse_vertical_reduction('k-1')


def test_interpolating_to_an_elevation_is_not_implemented_yet(columns):
    with pytest.raises(NotImplementedError, match='vertical geometry'):
        _reduce(columns, '-100.0')


def _reduce(ds, spec, raw=False):
    """Apply a reduction given by its config spelling"""
    da_map = apply_vertical_reduction(
        ds.field,
        parse_vertical_reduction(spec),
        min_level_cell=ds.minLevelCell,
        max_level_cell=ds.maxLevelCell,
    )
    return da_map if raw else da_map.values


def test_the_valid_level_range_is_converted_from_one_based_indices():
    """Both models write minLevelCell and maxLevelCell the way MPAS-Ocean's
    Fortran indexes them."""
    ds = xr.Dataset(
        dict(
            minLevelCell=('nCells', np.array([1, 4])),
            maxLevelCell=('nCells', np.array([6, 6])),
        )
    )
    min_level_cell, max_level_cell = get_valid_level_range(ds)
    np.testing.assert_array_equal(min_level_cell.values, [0, 3])
    np.testing.assert_array_equal(max_level_cell.values, [5, 5])


def test_a_column_with_no_cavities_starts_at_the_top_of_the_grid():
    """A simulation without ice-shelf cavities need not write
    minLevelCell."""
    ds = xr.Dataset(dict(maxLevelCell=('nCells', np.array([6, 3]))))
    min_level_cell, max_level_cell = get_valid_level_range(ds)
    np.testing.assert_array_equal(min_level_cell.values, [0, 0])
    np.testing.assert_array_equal(max_level_cell.values, [5, 2])


def test_a_column_with_no_seafloor_is_reported():
    with pytest.raises(ValueError, match='no maxLevelCell'):
        get_valid_level_range(xr.Dataset())
