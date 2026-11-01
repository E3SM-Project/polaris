"""
Unit tests for the ocean heat content kernel.

The columns are synthetic, so the answer is one that can be written down: a
constant temperature over a known mass is that temperature times that mass
times the specific heat capacity in the Physical Constants Dictionary.  What
is checked beyond that is what the kernel does at the edges of a column,
since a mass-weighted sum over a partly valid column is where a diagnostic
like this goes wrong quietly.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.heat_content import heat_content

CP = get_constant('seawater_specific_heat_capacity_reference')
N_LEVELS = 4


def column(temperature, weights):
    """One column, as the data arrays the kernel takes"""
    dims = ('nCells', 'nVertLevels')
    return (
        xr.DataArray(np.array([temperature]), dims=dims),
        xr.DataArray(np.array([weights]), dims=dims),
    )


def test_a_constant_temperature_over_a_known_mass():
    """The one case where the answer can be written down."""
    temperature, weights = column([10.0] * N_LEVELS, [1.0e5] * N_LEVELS)
    da = heat_content(temperature, weights)
    assert da.values[0] == pytest.approx(CP * 10.0 * 4.0e5)


def test_each_layer_is_weighted_by_its_own_mass():
    temperature, weights = column(
        [10.0, 5.0, 2.0, 1.0], [1.0e5, 2.0e5, 3.0e5, 4.0e5]
    )
    da = heat_content(temperature, weights)
    expected = CP * (10.0 * 1e5 + 5.0 * 2e5 + 2.0 * 3e5 + 1.0 * 4e5)
    assert da.values[0] == pytest.approx(expected)


def test_a_layer_that_weighs_nothing_contributes_nothing():
    """Which is what lets the same kernel serve a range that covers part of
    the column."""
    temperature, weights = column(
        [10.0, 10.0, 10.0, 10.0], [1.0e5, 1.0e5, 0.0, 0.0]
    )
    da = heat_content(temperature, weights)
    assert da.values[0] == pytest.approx(CP * 10.0 * 2.0e5)


def test_a_temperature_that_was_never_written_cannot_reach_the_sum():
    """Below the seafloor a model may write a fill value, which arrives as
    NaN.  It weighs nothing, so it must not make the whole column NaN."""
    temperature, weights = column(
        [10.0, 10.0, np.nan, np.nan], [1.0e5, 1.0e5, 0.0, 0.0]
    )
    da = heat_content(temperature, weights)
    assert da.values[0] == pytest.approx(CP * 10.0 * 2.0e5)


def test_a_column_with_no_mass_is_masked_rather_than_zero():
    """Land, or a column whose seafloor lies above the range.  A global sum
    is unaffected by the mask and a map shows a hole."""
    temperature, weights = column([10.0] * N_LEVELS, [0.0] * N_LEVELS)
    da = heat_content(temperature, weights)
    assert np.isnan(da.values[0])


def test_a_missing_temperature_where_there_is_mass_is_not_hidden():
    """Masking is for a column with nothing in it, not for a column whose
    temperature is missing where it should not be."""
    temperature, weights = column(
        [10.0, np.nan, 10.0, 10.0], [1.0e5] * N_LEVELS
    )
    da = heat_content(temperature, weights)
    assert np.isnan(da.values[0])


def test_the_vertical_dimension_is_gone_and_the_units_are_labeled():
    temperature, weights = column([10.0] * N_LEVELS, [1.0e5] * N_LEVELS)
    da = heat_content(temperature, weights)
    assert 'nVertLevels' not in da.dims
    assert da.dims == ('nCells',)
    assert da.attrs['units'] == 'J m-2'
    assert da.name == 'heat_content'


def test_a_time_dimension_survives():
    """The maps integrate one season at a time and the time series a month at
    a time, so a leading dimension has to come through."""
    dims = ('Time', 'nCells', 'nVertLevels')
    shape = (2, 3, N_LEVELS)
    temperature = xr.DataArray(np.full(shape, 10.0), dims=dims)
    weights = xr.DataArray(np.full(shape, 1.0e5), dims=dims)
    da = heat_content(temperature, weights)
    assert da.dims == ('Time', 'nCells')
    np.testing.assert_allclose(da.values, CP * 10.0 * 4.0e5)
