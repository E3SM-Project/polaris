"""
Unit tests for the vertical reductions that need no vertical geometry: the
ones that pick a layer by index, and the weights of the whole column.

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
    elevation_range_weights,
    get_valid_level_range,
    is_whole_column,
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
            # a distinct mass per layer and per column, so that a weight can
            # only be right by coming from the layer it belongs to
            layer_mass=(
                ('nCells', 'nVertLevels'),
                1000.0 + 10.0 * levels + 1.0 * cells,
            ),
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


def test_an_elevation_range_parses_into_its_bounds():
    """A bound is either a keyword, which resolves per column, or a fixed
    elevation."""
    whole = parse_vertical_reduction('top:bottom')
    assert whole.kind == 'range'
    assert (whole.z_top, whole.z_bot) == (np.inf, -np.inf)

    upper = parse_vertical_reduction('top:-700.0')
    assert (upper.z_top, upper.z_bot) == (np.inf, -700.0)

    middle = parse_vertical_reduction(' -700.0 : -2000.0 ')
    assert (middle.z_top, middle.z_bot) == (-700.0, -2000.0)

    abyss = parse_vertical_reduction('-2000.0:BOTTOM')
    assert (abyss.z_top, abyss.z_bot) == (-2000.0, -np.inf)


def test_a_range_is_labeled_by_both_of_its_bounds():
    """The label names a file, so the elevations are spelled the way a
    single elevation is, and joined by _to_ rather than by a hyphen, which
    the negative elevations already use."""
    assert parse_vertical_reduction('top:bottom').label == 'top_to_bottom'
    assert parse_vertical_reduction('top:-700.0').label == 'top_to_-700m'
    assert (
        parse_vertical_reduction('-2000.0:bottom').label == '-2000m_to_bottom'
    )


def test_a_range_that_does_not_descend_is_reported():
    with pytest.raises(ValueError, match='does not descend'):
        parse_vertical_reduction('-700.0:-100.0')
    with pytest.raises(ValueError, match='does not descend'):
        parse_vertical_reduction('-700.0:-700.0')


def test_a_bound_on_the_wrong_end_is_reported():
    """ "top" is the free surface and "bottom" the seafloor, so neither can
    stand in for the other end of the range."""
    with pytest.raises(ValueError, match='is not the top'):
        parse_vertical_reduction('bottom:top')
    with pytest.raises(ValueError, match='is not the bottom'):
        parse_vertical_reduction('top:seafloor')


def test_something_that_is_not_a_range_is_reported():
    with pytest.raises(ValueError, match='not an elevation range'):
        parse_vertical_reduction('top:-700.0:-2000.0')


def test_only_the_whole_column_is_the_whole_column():
    assert is_whole_column(parse_vertical_reduction('top:bottom'))
    assert not is_whole_column(parse_vertical_reduction('top:-700.0'))
    assert not is_whole_column(parse_vertical_reduction('top'))


def test_the_whole_column_weighs_every_valid_layer_and_nothing_else(columns):
    """No geometry is read: every valid layer is whole, so its weight is its
    whole mass, and every other layer weighs nothing."""
    weights = _whole_column_weights(columns)
    layer_mass = columns.layer_mass.values
    np.testing.assert_allclose(weights[0], layer_mass[0])
    np.testing.assert_allclose(
        weights[1], [0.0, 0.0, 0.0] + list(layer_mass[1, 3:])
    )
    np.testing.assert_allclose(
        weights[2], list(layer_mass[2, :3]) + [0.0, 0.0, 0.0]
    )
    np.testing.assert_allclose(weights[LAND], np.zeros(N_LEVELS))


def test_the_whole_column_weights_are_a_mass_per_unit_area(columns):
    weights = elevation_range_weights(
        None,
        columns.layer_mass,
        columns.minLevelCell,
        columns.maxLevelCell,
        np.inf,
        -np.inf,
    )
    assert weights.attrs['units'] == 'kg m-2'


def test_a_layer_with_no_mass_written_still_weighs_nothing(columns):
    """A model may write anything below the seafloor, including a fill value
    that arrives as NaN, and it must not reach the sum."""
    levels = xr.DataArray(np.arange(N_LEVELS), dims='nVertLevels')
    layer_mass = columns.layer_mass.where(levels <= columns.maxLevelCell)
    weights = elevation_range_weights(
        None,
        layer_mass,
        columns.minLevelCell,
        columns.maxLevelCell,
        np.inf,
        -np.inf,
    )
    assert np.all(np.isfinite(weights.values))
    np.testing.assert_allclose(weights.values[LAND], np.zeros(N_LEVELS))


def test_a_range_with_a_finite_bound_is_not_implemented_yet(columns):
    with pytest.raises(NotImplementedError, match='vertical geometry'):
        elevation_range_weights(
            None,
            columns.layer_mass,
            columns.minLevelCell,
            columns.maxLevelCell,
            np.inf,
            -700.0,
        )


def test_a_range_is_not_a_slice(columns):
    """A range is a weighted integral, so it does not go through the entry
    point that picks a layer."""
    with pytest.raises(ValueError, match='not a slice'):
        apply_vertical_reduction(
            columns.field,
            parse_vertical_reduction('top:bottom'),
            min_level_cell=columns.minLevelCell,
            max_level_cell=columns.maxLevelCell,
        )


def _whole_column_weights(ds):
    """The weights of the whole column, as an array"""
    return elevation_range_weights(
        None,
        ds.layer_mass,
        ds.minLevelCell,
        ds.maxLevelCell,
        np.inf,
        -np.inf,
    ).values
