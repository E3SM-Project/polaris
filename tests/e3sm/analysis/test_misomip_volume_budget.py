import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    compute_daily_volume_budget,
)

REF_DENSITY = 1026.0
AREA = 1.0e6
DV_EDGE = 1000.0
THICKNESS = 10.0


def _mesh():
    """Four cells in a row, with the last two tidally forced, and an edge
    on the domain's boundary beside the last"""
    ds_init = xr.Dataset()
    ds_init['areaCell'] = ('nCells', np.full(4, AREA))
    ds_init['cellsOnEdge'] = (
        ('nEdges', 'TWO'),
        np.array([[1, 2], [2, 3], [3, 4], [4, 0]]),
    )
    ds_init['dvEdge'] = ('nEdges', np.full(4, DV_EDGE))
    tidal_mask = xr.DataArray(
        np.array([False, False, True, True]), dims='nCells'
    )
    return ds_init, tidal_mask


def _means(starts, ends, velocity_into_domain=0.01, pressure=None):
    """Daily means with melt in the first cell, flow from the tidally
    forced cells into the others across the second edge, and flow between
    the tidally forced cells and through the boundary that must not count"""
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
    velocity = np.zeros((count, 4, 2))
    # positive is from the first cell of the edge to the second, so
    # negative on the second edge is from the tidally forced cell 3
    # to cell 2
    velocity[:, 1, :] = -velocity_into_domain
    velocity[:, 2, :] = 5.0
    velocity[:, 3, :] = 7.0
    ds['normalVelocity'] = (('Time', 'nEdges', 'nVertLevels'), velocity)
    ds['layerThickness'] = (
        ('Time', 'nCells', 'nVertLevels'),
        np.full((count, 4, 2), THICKNESS),
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
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [5.0e12, 5.0e12 + 3.0e7]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
    )
    np.testing.assert_allclose(ds.dayStart, [0.0, 1.0])
    np.testing.assert_allclose(ds.dayEnd, [1.0, 2.0])
    np.testing.assert_allclose(ds.volumeChange, [np.nan, 3.0e7])


def test_melt_and_frazil_are_volumes_at_the_reference_density():
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [0.0, 0.0]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
    )
    expected = 86400.0 * AREA * (1.0e-5 - 4 * 1.0e-7) / REF_DENSITY
    np.testing.assert_allclose(ds.meltAndFrazilVolume, [expected, expected])


def test_only_edges_out_of_the_tidally_forced_cells_carry_their_inflow():
    """Flow between the tidally forced cells and through the domain's
    boundary is left out"""
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS, velocity_into_domain=0.01),
        _stats(ENDS, [0.0, 0.0]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
    )
    expected = 86400.0 * 0.01 * THICKNESS * DV_EDGE * 2
    np.testing.assert_allclose(ds.tidalForcingInflow, [expected, expected])


def _means_with_tidal_tendency():
    """Daily means with flow in from the tidally forced cells and their
    tidal tendency"""
    ds_means = _means(STARTS, ENDS, velocity_into_domain=0.01)
    tendency = np.zeros((2, 4, 2))
    tendency[:, 2:, :] = 1.0e-9
    ds_means['tidalLayerThicknessTendency'] = (
        ('Time', 'nCells', 'nVertLevels'),
        tendency,
    )
    return ds_means


def test_the_tidal_tendency_replaces_the_transport_estimate():
    """The tendency of a thickness source is exact, so it is used even
    where the transport could be estimated"""
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means_with_tidal_tendency(),
        _stats(ENDS, [0.0, 0.0]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
        'thickness_source',
    )
    expected = 86400.0 * 1.0e-9 * AREA * 4
    np.testing.assert_allclose(ds.tidalForcingInflow, [expected, expected])
    assert ds.tidalForcingInflow.long_name == (
        'volume added by the tidal forcing'
    )


def test_direct_tidal_forcing_uses_the_transport_estimate():
    """Forcing that sets the thickness directly leaves the tendency at
    zero, so the transport is estimated instead"""
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means_with_tidal_tendency(),
        _stats(ENDS, [0.0, 0.0]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
        'direct',
    )
    expected = 86400.0 * 0.01 * THICKNESS * DV_EDGE * 2
    np.testing.assert_allclose(ds.tidalForcingInflow, [expected, expected])
    assert ds.tidalForcingInflow.long_name == (
        'transport in from the tidally forced cells'
    )


def test_without_tidal_forcing_there_is_no_inflow_term():
    ds_init, _ = _mesh()
    ds = compute_daily_volume_budget(
        _means(STARTS, ENDS),
        _stats(ENDS, [0.0, 0.0]),
        ds_init,
        REF_DENSITY,
    )
    assert 'tidalForcingInflow' not in ds


def test_the_load_changes_only_between_days_that_follow_each_other():
    starts = STARTS + ['0001-01-05_00:30:00']
    ends = ENDS + ['0001-01-06_00:00:00']
    pressure = [1.0e5, 3.0e5, 4.0e5]
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means(starts, ends, pressure=pressure),
        _stats(ends, [0.0, 0.0, 0.0]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
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
    ds_init, tidal_mask = _mesh()
    ds = compute_daily_volume_budget(
        _means(starts, ends),
        _stats(ENDS, [0.0, 2.0e7]),
        ds_init,
        REF_DENSITY,
        tidal_mask,
    )
    assert ds.sizes['Time'] == 2
    assert ds.volumeChange.values[1] == pytest.approx(2.0e7)
