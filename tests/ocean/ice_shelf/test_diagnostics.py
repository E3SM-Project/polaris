import numpy as np
import pytest
import xarray as xr

from polaris.mpas.time_series_stats import rename_time_series_stats
from polaris.ocean.ice_shelf.diagnostics import (
    compute_melt_diagnostics,
    compute_melt_rate_by_draft,
    compute_thin_film_diagnostics,
)

#: Four cells: fully floating, half floating, grounded and open ocean
AREA = xr.DataArray([1.0e6, 2.0e6, 3.0e6, 4.0e6], dims='nCells')
FLOATING = xr.DataArray([1.0, 0.5, 0.0, 0.0], dims='nCells')
LAND_ICE = xr.DataArray([1.0, 1.0, 1.0, 0.0], dims='nCells')
DRAFT = xr.DataArray([-400.0, -150.0, -50.0, 0.0], dims='nCells')


def _fluxes(times=1):
    """Fluxes per unit cell area, the same at every time but scaled by the
    time index plus one, so a Time dimension is checked to be kept"""
    scale = xr.DataArray(np.arange(1.0, times + 1.0), dims='Time')
    ds = xr.Dataset()
    ds['landIceFreshwaterFlux'] = scale * xr.DataArray(
        [1.0e-3, 2.0e-3, 0.0, 0.0], dims='nCells'
    )
    ds['landIceBoundaryLayerTemperature'] = xr.DataArray(
        [1.0, 2.0, 0.0, 0.0], dims='nCells'
    )
    ds['landIceInterfaceTemperature'] = xr.DataArray(
        [-2.0, -2.0, 0.0, 0.0], dims='nCells'
    )
    ds['landIceBoundaryLayerSalinity'] = xr.DataArray(
        [34.0, 34.0, 0.0, 0.0], dims='nCells'
    )
    ds['landIceInterfaceSalinity'] = xr.DataArray(
        [30.0, 32.0, 0.0, 0.0], dims='nCells'
    )
    ds['landIceFrictionVelocity'] = xr.DataArray(
        [0.01, 0.02, 0.0, 0.0], dims='nCells'
    )
    return ds


def test_melt_is_averaged_over_the_floating_area():
    """The half-floating cell melts over half its area, so it counts with
    half its area in the mean."""
    ds_diag = compute_melt_diagnostics(
        AREA, _fluxes(times=2), FLOATING, draft=DRAFT
    )

    # 1e-3 * 1e6 + 2e-3 * 2e6 kg s-1, doubled at the second time
    np.testing.assert_allclose(ds_diag.totalMeltFlux, [5.0e3, 1.0e4])
    assert float(ds_diag.floatingArea) == 2.0e6
    # 5 m3 s-1 of freshwater over 2e6 m2 of floating ice
    np.testing.assert_allclose(ds_diag.meanMeltRate, [2.5e-6, 5.0e-6])
    # the drivers are weighted by floating area: 1e6 m2 of each cell
    assert float(ds_diag.meanThermalDriving) == 3.5
    assert float(ds_diag.meanHalineDriving) == 3.0
    assert float(ds_diag.meanFrictionVelocity) == pytest.approx(0.015)
    # only the first cell is deeper than 300 m
    np.testing.assert_allclose(ds_diag.meanMeltRateDeep, [1.0e-6, 2.0e-6])


def test_melt_is_binned_by_draft():
    ds_bins = compute_melt_rate_by_draft(
        AREA,
        _fluxes().landIceFreshwaterFlux.isel(Time=0),
        FLOATING,
        DRAFT,
        bin_width=100.0,
    )

    np.testing.assert_allclose(ds_bins.draft, [-350.0, -250.0, -150.0, -50.0])
    melt = ds_bins.meanMeltRate.values
    assert melt[0] == pytest.approx(1.0e-6)
    assert np.isnan(melt[1])
    # 4 m3 s-1 over the 1e6 m2 of the half-floating cell
    assert melt[2] == pytest.approx(4.0e-6)
    # the grounded cell's bin has no floating ice
    assert np.isnan(melt[3])


def test_a_thin_film_is_dry_under_grounded_ice_only():
    """Two layers of 1 mm make a column under 4 mm dry.  The grounded cell
    is dry; the open-ocean cell is as thin but is not under ice."""
    ssh = xr.DataArray([-300.0, -100.0, -49.999, 0.1], dims='nCells')
    bottom_depth = xr.DataArray([500.0, 200.0, 50.0, -0.0985], dims='nCells')
    levels = xr.DataArray([10, 10, 2, 2], dims='nCells')

    ds_diag = compute_thin_film_diagnostics(
        AREA, ssh, bottom_depth, levels, LAND_ICE, FLOATING, 1.0e-3
    )

    assert float(ds_diag.dryAreaUnderGroundedIce) == 3.0e6
    assert float(ds_diag.openOceanMeanSsh) == pytest.approx(0.1)


def test_monthly_means_take_the_names_of_their_fields():
    ds = xr.Dataset()
    ds['timeMonthly_avg_ssh'] = xr.DataArray([0.0], dims='nCells')
    ds['timeMonthly_avg_activeTracers_temperature'] = xr.DataArray(
        [1.0], dims='nCells'
    )
    ds['xtime_startMonthly'] = xr.DataArray([b'0001-01-01'], dims='Time')

    ds = rename_time_series_stats(ds)

    assert sorted(ds.data_vars) == ['ssh', 'temperature', 'xtime_startMonthly']


def test_monthly_means_that_would_collide_raise():
    ds = xr.Dataset()
    ds['timeMonthly_avg_activeTracers_temperature'] = xr.DataArray([1.0])
    ds['timeMonthly_avg_temperature'] = xr.DataArray([1.0])

    with pytest.raises(ValueError, match='collide'):
        rename_time_series_stats(ds)
