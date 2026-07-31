import gsw
import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.ocean.eos import convert_tracers


def _make_tracer_ds():
    """A 2-cell, 2-layer dataset whose second cell has an invalid bottom
    layer."""
    temperature = np.array([[[10.0, 12.0], [20.0, np.nan]]])
    salinity = np.array([[[35.0, 35.2], [34.8, np.nan]]])
    pressure = np.array([[[1.0e5, 2.0e6], [1.0e5, 2.0e6]]])
    return xr.Dataset(
        data_vars=dict(
            temperature=(('Time', 'nCells', 'nVertLevels'), temperature),
            salinity=(('Time', 'nCells', 'nVertLevels'), salinity),
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

    ds_out = convert_tracers(
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

    assert_allclose(ds_out.temperature.values[valid], expected_pt)
    assert_allclose(ds_out.salinity.values[valid], expected_sp)
    assert ds_out.temperature.dims == ds.temperature.dims
    assert ds_out.temperature.attrs['long_name'] == 'potential temperature'
    assert ds_out.temperature.attrs['units'] == 'degC'
    assert ds_out.salinity.attrs['long_name'] == 'practical salinity'
    assert ds_out.salinity.attrs['units'] == 'PSU'


def test_convert_tracers_to_mpas_ocean_per_cell_location():
    ds = _make_tracer_ds()
    sa = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = np.array([0.0, 180.0])
    lat = np.array([-60.0, 30.0])

    ds_out = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=lon,
        lat=lat,
    )

    # each cell is converted at its own location
    for cell in range(2):
        expected_sp = gsw.SP_from_SA(
            sa[0, cell, 0], p_dbar[0, cell, 0], lon[cell], lat[cell]
        )
        assert_allclose(ds_out.salinity.values[0, cell, 0], expected_sp)


def test_convert_tracers_to_teos10():
    ds = _make_tracer_ds()
    pt = ds.temperature.values.copy()
    sp = ds.salinity.values.copy()
    p_dbar = ds.pressure.values.copy() / 1e4
    lon = 10.0
    lat = -20.0

    ds_out = convert_tracers(
        ds,
        source='mpas-ocean',
        target='teos-10',
        pressure=ds.pressure,
        lon=lon,
        lat=lat,
    )

    valid = np.isfinite(pt)
    expected_sa = gsw.SA_from_SP(sp[valid], p_dbar[valid], lon, lat)
    expected_ct = gsw.CT_from_pt(expected_sa, pt[valid])

    assert_allclose(ds_out.salinity.values[valid], expected_sa)
    assert_allclose(ds_out.temperature.values[valid], expected_ct)
    assert ds_out.temperature.attrs['long_name'] == 'conservative temperature'
    assert ds_out.salinity.attrs['long_name'] == 'absolute salinity'
    assert ds_out.salinity.attrs['units'] == 'g kg-1'


def test_convert_tracers_round_trip():
    ds = _make_tracer_ds()

    ds_mpaso = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )
    ds_back = convert_tracers(
        ds_mpaso,
        source='mpas-ocean',
        target='teos-10',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    valid = np.isfinite(ds.temperature.values)
    assert_allclose(
        ds_back.temperature.values[valid],
        ds.temperature.values[valid],
        rtol=1e-10,
        atol=1e-10,
    )
    assert_allclose(
        ds_back.salinity.values[valid],
        ds.salinity.values[valid],
        rtol=1e-10,
        atol=1e-10,
    )


def test_convert_tracers_same_convention_is_a_no_op():
    ds = _make_tracer_ds()

    ds_out = convert_tracers(
        ds,
        source='teos-10',
        target='teos-10',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    assert ds_out is ds


def test_convert_tracers_does_not_modify_input():
    ds = _make_tracer_ds()
    ct = ds.temperature.values.copy()
    sa = ds.salinity.values.copy()

    convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    assert_allclose(ds.temperature.values, ct)
    assert_allclose(ds.salinity.values, sa)


def test_convert_tracers_preserves_invalid_cells():
    ds = _make_tracer_ds()
    invalid = ~np.isfinite(ds.temperature.values)

    ds_out = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    # below-bottom cells stay NaN and valid neighbors stay finite
    assert np.isnan(ds_out.temperature.values[invalid]).all()
    assert np.isnan(ds_out.salinity.values[invalid]).all()
    assert np.isfinite(ds_out.temperature.values[~invalid]).all()
    assert np.isfinite(ds_out.salinity.values[~invalid]).all()


def test_convert_tracers_without_time_dimension():
    ds = _make_tracer_ds()
    ds_no_time = ds.isel(Time=0)

    ds_out = convert_tracers(
        ds_no_time,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds_no_time.pressure,
        lon=0.0,
        lat=0.0,
    )
    ds_with_time = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    assert ds_out.temperature.dims == ('nCells', 'nVertLevels')
    assert_allclose(
        ds_out.salinity.values, ds_with_time.salinity.values[0], equal_nan=True
    )


def test_convert_tracers_with_transposed_dimensions():
    ds = _make_tracer_ds()
    ds_transposed = ds.transpose('Time', 'nVertLevels', 'nCells')
    lon = np.array([0.0, 180.0])
    lat = np.array([-60.0, 30.0])

    ds_out = convert_tracers(
        ds_transposed,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds_transposed.pressure,
        lon=lon,
        lat=lat,
    )
    ds_expected = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=lon,
        lat=lat,
    )

    assert ds_out.salinity.dims == ('Time', 'nVertLevels', 'nCells')
    assert_allclose(
        ds_out.salinity.transpose('Time', 'nCells', 'nVertLevels').values,
        ds_expected.salinity.values,
        equal_nan=True,
    )


def test_convert_tracers_with_tracer_pairs():
    ds = _make_tracer_ds()
    ds['temperatureSurfaceRestoringValue'] = ds.temperature.isel(nVertLevels=0)
    ds['salinitySurfaceRestoringValue'] = ds.salinity.isel(nVertLevels=0)

    ds_out = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure.isel(nVertLevels=0),
        lon=0.0,
        lat=0.0,
        tracer_pairs=(
            (
                'temperatureSurfaceRestoringValue',
                'salinitySurfaceRestoringValue',
            ),
        ),
    )

    ds_full = convert_tracers(
        ds,
        source='teos-10',
        target='mpas-ocean',
        pressure=ds.pressure,
        lon=0.0,
        lat=0.0,
    )

    assert_allclose(
        ds_out.salinitySurfaceRestoringValue.values,
        ds_full.salinity.values[:, :, 0],
        equal_nan=True,
    )
    # the 3D tracers are untouched
    assert_allclose(
        ds_out.temperature.values, ds.temperature.values, equal_nan=True
    )


def test_convert_tracers_raises_on_unknown_convention():
    ds = _make_tracer_ds()

    with pytest.raises(ValueError, match='Unknown tracer convention'):
        convert_tracers(
            ds,
            source='teos-10',
            target='eos-80',
            pressure=ds.pressure,
            lon=0.0,
            lat=0.0,
        )


def test_convert_tracers_raises_on_missing_tracer():
    ds = _make_tracer_ds().drop_vars('salinity')

    with pytest.raises(ValueError, match='salinity'):
        convert_tracers(
            ds,
            source='teos-10',
            target='mpas-ocean',
            pressure=ds.pressure,
            lon=0.0,
            lat=0.0,
        )
