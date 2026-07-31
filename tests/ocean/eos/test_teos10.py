import gsw
import numpy as np
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.eos import convert_tracers


def _make_tracer_ds():
    ct = np.array([[[10.0, 12.0], [20.0, np.nan]]])
    sa = np.array([[[35.0, 35.2], [34.8, np.nan]]])
    pressure = np.array([[[1.0e5, 2.0e6], [1.0e5, 2.0e6]]])
    return xr.Dataset(
        data_vars=dict(
            temperature=(('Time', 'nCells', 'nVertLevels'), ct),
            salinity=(('Time', 'nCells', 'nVertLevels'), sa),
            pressure=(('Time', 'nCells', 'nVertLevels'), pressure),
        )
    )


def test_convert_tracers_to_mpas_ocean_nominal_location():
    ds = _make_tracer_ds()
    ct = ds.temperature.values.copy()
    sa = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = 0.0
    lat = 0.0

    ds = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=lon,
        lat=lat,
    )

    valid = np.isfinite(ct)
    expected_pt = gsw.pt_from_CT(sa[valid], ct[valid])
    expected_sp = gsw.SP_from_SA(sa[valid], p_dbar[valid], lon, lat)

    assert_allclose(ds.temperature.values[valid], expected_pt)
    assert_allclose(ds.salinity.values[valid], expected_sp)
    # invalid (below-bottom) values stay NaN
    assert np.isnan(ds.temperature.values[~valid]).all()
    assert np.isnan(ds.salinity.values[~valid]).all()
    assert ds.temperature.attrs['long_name'] == 'potential temperature'
    assert ds.salinity.attrs['units'] == 'PSU'


def test_convert_tracers_to_mpas_ocean_per_cell_location():
    ds = _make_tracer_ds()
    sa = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = np.array([0.0, 180.0])
    lat = np.array([-60.0, 30.0])

    ds = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=lon,
        lat=lat,
    )

    # check a single valid (cell, level) against a direct gsw call
    expected_sp = gsw.SP_from_SA(sa[0, 1, 0], p_dbar[0, 1, 0], lon[1], lat[1])
    assert_allclose(ds.salinity.values[0, 1, 0], expected_sp)
