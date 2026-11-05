import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    compute_daily_volume_budget,
)

REF_DENSITY = 1026.0
AREA = 1.0e6
TENDENCY = 1.0e-9


def _mesh():
    """Four cells, the last two tidally forced"""
    ds_init = xr.Dataset()
    ds_init['areaCell'] = ('nCells', np.full(4, AREA))
    return ds_init


def _means(starts, ends, pressure=None, tendency=False):
    """Daily means with melt in the first cell, frazil everywhere and, if
    asked, a tidal tendency in the two tidally forced cells"""
    count = len(ends)
    ds = xr.Dataset()
    ds['xtime_startDaily'] = ('Time', np.array(starts))
    ds['xtime_endDaily'] = ('Time', np.array(ends))
    melt = np.zeros((count, 4))
    melt[:, 0] = 1.0e-5
    ds['landIceFreshwaterFlux'] = (('Time', 'nCells'), melt)
    ds['frazilIceFreshwaterFlux'] = (
        ('Time', 'nCells'),
        np.full((count, 4), -1.0e-7),
    )
    if tendency:
        values = np.zeros((count, 4, 2))
        values[:, 2:, :] = TENDENCY
        ds['tidalLayerThicknessTendency'] = (
            ('Time', 'nCells', 'nVertLevels'),
            values,
        )
    if pressure is not None:
        ds['landIcePressure'] = (
            ('Time', 'nCells'),
            np.outer(pressure, [1.0, 0.0, 0.0, 0.0]),
        )
    return ds


def _stats(times, volumes):
    ds = xr.Dataset()
    ds['xtime'] = ('Time', np.array(times))
    ds['volumeCellGlobal'] = ('Time', np.array(volumes))
    return ds


STARTS = ['0001-01-01_00:30:00', '0001-01-02_00:30:00']
ENDS = ['0001-01-02_00:00:00', '0001-01-03_00:00:00']


def test_a_day_s_volume_change_needs_the_volume_at_both_its_ends():
    """A segment writes no statistics at its start, so its first day has
    no change"""
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [5.0e12, 5.0e12 + 3.0e7]),
        _mesh(),
        REF_DENSITY,
    )
    np.testing.assert_allclose(ds.dayStart, [0.0, 1.0])
    np.testing.assert_allclose(ds.dayEnd, [1.0, 2.0])
    np.testing.assert_allclose(ds.volumeChange, [np.nan, 3.0e7])


def test_melt_and_frazil_are_volumes_at_the_reference_density():
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
    )
    expected = 86400.0 * AREA * (1.0e-5 - 4 * 1.0e-7) / REF_DENSITY
    np.testing.assert_allclose(ds.meltAndFrazilVolume, [expected, expected])


def test_the_tidal_tendency_of_a_thickness_source_is_its_term():
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS, tendency=True),
        _stats(ENDS, [0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
        'thickness_source',
    )
    expected = 86400.0 * TENDENCY * AREA * 4
    np.testing.assert_allclose(ds.tidalForcingInflow, [expected, expected])
    assert ds.tidalForcingInflow.long_name == (
        'volume added by the tidal forcing'
    )
    assert ds.attrs['tidal_forcing_type'] == 'thickness_source'


def test_a_day_without_the_tidal_tendency_has_no_term():
    """Before a run writes the tendency, its days have no term rather than
    none added"""
    ds_means = _means(STARTS, ENDS, tendency=True)
    values = ds_means.tidalLayerThicknessTendency.values.copy()
    values[0] = np.nan
    ds_means['tidalLayerThicknessTendency'] = (
        ('Time', 'nCells', 'nVertLevels'),
        values,
    )
    ds = compute_daily_volume_budget(
        ds_means,
        _stats(ENDS, [0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
        'thickness_source',
    )
    expected = 86400.0 * TENDENCY * AREA * 4
    np.testing.assert_allclose(ds.tidalForcingInflow, [np.nan, expected])


def test_direct_tidal_forcing_has_no_term():
    """Forcing that sets the thickness directly leaves the tendency at
    zero, so the budget has no tidal term"""
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS, tendency=True),
        _stats(ENDS, [0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
        'direct',
    )
    assert 'tidalForcingInflow' not in ds
    assert ds.attrs['tidal_forcing_type'] == 'direct'


def test_without_tidal_forcing_there_is_no_tidal_term():
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
    )
    assert 'tidalForcingInflow' not in ds
    assert ds.attrs['tidal_forcing_type'] == 'none'


def test_the_load_changes_only_between_days_that_follow_each_other():
    starts = STARTS + ['0001-01-05_00:30:00']
    ends = ENDS + ['0001-01-06_00:00:00']
    pressure = [1.0e5, 3.0e5, 4.0e5]
    ds = compute_daily_volume_budget(
        _means(starts, ends, pressure=pressure),
        _stats(ends, [0.0, 0.0, 0.0]),
        _mesh(),
        REF_DENSITY,
    )
    gravity = get_constant('standard_acceleration_of_gravity')
    load = AREA * np.array(pressure) / (REF_DENSITY * gravity)
    np.testing.assert_allclose(ds.landIceLoad, load)
    np.testing.assert_allclose(
        ds.landIceLoadChange, [np.nan, load[1] - load[0], np.nan]
    )


def test_a_day_run_again_is_counted_once():
    starts = STARTS + [STARTS[1]]
    ends = ENDS + [ENDS[1]]
    ds = compute_daily_volume_budget(
        _means(starts, ends),
        _stats(ENDS, [0.0, 2.0e7]),
        _mesh(),
        REF_DENSITY,
    )
    assert ds.sizes['Time'] == 2
    assert ds.volumeChange.values[1] == pytest.approx(2.0e7)
