import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.analysis.misomip.ice_sheet import get_lines_range
from polaris.tasks.e3sm.analysis.misomip.plots import (
    get_color_norm,
    get_color_range,
    get_map_mask,
    get_range_mask,
)
from polaris.viz.time_series import Series

#: Five cells: fully floating, half floating, floating but holding only the
#: film, grounded and open ocean
FLOATING = xr.DataArray([1.0, 0.5, 0.3, 0.0, 0.0], dims='nCells')
LAND_ICE = xr.DataArray([1.0, 1.0, 1.0, 1.0, 0.0], dims='nCells')
FILM = xr.DataArray([0, 0, 1, 1, 0], dims='nCells')


def _geometry(with_film=True):
    ds = xr.Dataset()
    ds['landIceFloatingFraction'] = FLOATING
    ds['landIceFraction'] = LAND_ICE
    if with_film:
        ds['filmColumn'] = FILM
    return ds


def _config(**ranges):
    config = PolarisConfigParser()
    config.add_section('misomip_analysis_color_ranges')
    for option, value in ranges.items():
        config.set('misomip_analysis_color_ranges', option, value)
    return config


@pytest.mark.parametrize(
    'where, expected',
    [
        ('floating', [True, True, True, False, False]),
        ('open', [False, False, False, False, True]),
    ],
)
def test_maps_show_the_film(where, expected):
    """A column that holds only the film is drawn like any other"""
    mask = get_map_mask(_geometry(), where)
    np.testing.assert_array_equal(mask.values, expected)


def test_a_map_of_everywhere_has_no_mask():
    assert get_map_mask(_geometry(), 'all') is None


def test_an_unknown_place_raises():
    with pytest.raises(ValueError, match='Unexpected place'):
        get_map_mask(_geometry(), 'cavity')


def test_the_film_does_not_count_toward_a_range():
    """Under floating ice, the floating cell that holds only the film is
    left out"""
    ds = _geometry()
    counted = get_range_mask(ds, get_map_mask(ds, 'floating'))
    np.testing.assert_array_equal(
        counted.values, [True, True, False, False, False]
    )


def test_without_a_film_mask_the_film_is_under_grounded_ice():
    """The initial condition has no film mask, so the film is the columns
    under grounded ice"""
    counted = get_range_mask(_geometry(with_film=False))
    np.testing.assert_array_equal(
        counted.values, [True, True, True, False, True]
    )


def test_a_configured_range_serves_every_field_that_shares_it():
    """The bottom temperature uses the temperature's range, whatever the
    data"""
    config = _config(temperature='-2.5, 1.0')
    field = xr.DataArray([5.0, 6.0], dims='nCells')
    assert get_color_range(config, 'temperature') == (-2.5, 1.0)
    assert get_color_range(config, 'temperatureBottom', field) == (-2.5, 1.0)


def test_a_blank_range_comes_from_the_cells_that_count():
    """The fresh film does not stretch the salinity's range"""
    config = _config(salinity='')
    field = xr.DataArray([34.0, 34.5, 0.0, 0.0, 34.6], dims='nCells')
    counted = get_range_mask(_geometry())
    vmin, vmax = get_color_range(config, 'salinity', field, counted)
    assert (vmin, vmax) == pytest.approx((34.0, 34.6))


def test_a_blank_range_of_a_velocity_is_centered_on_zero():
    config = _config(boundary_layer_velocity='')
    field = xr.DataArray([0.1, -0.3, 2.0, 0.0, 0.05], dims='nCells')
    counted = get_range_mask(
        _geometry(), get_map_mask(_geometry(), 'floating')
    )
    vmin, vmax = get_color_range(config, 'uBoundaryLayer', field, counted)
    assert (vmin, vmax) == pytest.approx((-0.3, 0.3))


def test_no_config_and_no_field_leave_the_range_to_the_plot():
    assert get_color_range(_config(), 'meltRate') == (None, None)


def test_salinity_s_uneven_bins_serve_its_maps_and_sections():
    """The bottom salinity uses salinity's bins, coarse where the film is
    fresh and fine in the cavity's range"""
    config = _config(
        salinity_bounds='0.0, 30.0, 34.0, 34.5, 34.8',
        salinity_ticks='0.0, 34.0, 34.8',
    )
    for name in ['salinity', 'salinityBottom']:
        norm, ticks = get_color_norm(config, name, 'viridis')
        np.testing.assert_array_equal(
            norm.boundaries, [0.0, 30.0, 34.0, 34.5, 34.8]
        )
        assert norm.extend == 'both'
        assert ticks == [0.0, 34.0, 34.8]


def test_without_bounds_a_field_has_no_norm():
    config = _config(temperature_bounds='')
    assert get_color_norm(config, 'temperature', 'viridis') == (None, None)
    assert get_color_norm(config, 'meltRate', 'viridis') == (None, None)


def test_the_runs_set_the_y_range_not_the_ensemble():
    """Values after the end of the axis are left out, and the range is
    padded by a tenth of its size"""
    lines = [
        Series(np.array([0.0, 1.0, 5.0]), np.array([10.0, 12.0, 100.0]), 'a'),
        Series(np.array([0.0, 1.0]), np.array([11.0, np.nan]), 'b'),
    ]
    assert get_lines_range(lines, end_year=2.0) == pytest.approx((9.8, 12.2))


def test_constant_runs_still_get_a_y_range():
    lines = [Series(np.array([0.0, 1.0]), np.array([5.0, 5.0]), 'a')]
    assert get_lines_range(lines, end_year=1.0) == pytest.approx((4.5, 5.5))
