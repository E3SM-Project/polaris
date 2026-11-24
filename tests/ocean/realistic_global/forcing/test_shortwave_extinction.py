import netCDF4
import numpy as np
import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.forcing.shortwave_extinction import (
    ShortwaveExtinctionProductStep,
)
from polaris.tasks.ocean.realistic_global.forcing.shortwave_extinction.product import (  # noqa: E501
    compute_extinction,
)


def _write_month(path, lat, lon, log_chl):
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('lat', len(lat))
        ds.createDimension('lon', len(lon))
        ds.createVariable('lat', 'f8', ('lat',))[:] = lat
        ds.createVariable('lon', 'f8', ('lon',))[:] = lon
        chl = ds.createVariable(
            'Chl_a', 'f8', ('lat', 'lon'), fill_value=-9999.0
        )
        chl.scalling = 'log10'
        chl[:] = log_chl


def _write_climatology(tmp_path, lat, lon, months=None):
    template = str(tmp_path / 'chl_{month:02d}.nc')
    if months is None:
        months = {}
    for month in range(1, 13):
        values = months.get(month, np.full((len(lat), len(lon)), -9999.0))
        _write_month(template.format(month=month), lat, lon, values)
    return template


def _files(template):
    return [template.format(month=month) for month in range(1, 13)]


def _run(template, max_chl=10.0, fill_chl=0.1):
    return compute_extinction(
        _files(template), max_chl=max_chl, fill_chl=fill_chl
    )


def _expected_field(north, south, k0, a, exponent):
    fill = k0 + a * 0.2**exponent
    south_values = k0 + a * np.array([9.0, 1.0]) ** exponent
    north_values = k0 + a * np.array([1.0, 9.0]) ** exponent
    capped_values = k0 + a * np.array([10.0, 1.0]) ** exponent
    return np.array(
        [
            [np.dot(south, south_values), fill, fill],
            [np.dot(north, north_values), np.dot(north, capped_values), fill],
            [fill, k0 + a * 8.0**exponent, fill],
        ]
    )


def test_product_weighting_cap_missing_and_metadata(tmp_path):
    lat = [90.0, 60.0, -60.0]
    lon = [10.0, 20.0, 30.0]
    jan = np.array(
        [
            [np.log10(4.0), np.log10(2.0), -9999.0],
            [0.0, 2.0, np.nan],
            [np.log10(9.0), -9999.0, np.inf],
        ]
    )
    june = np.array(
        [
            [-9999.0, np.log10(8.0), -9999.0],
            [np.log10(9.0), 0.0, -9999.0],
            [0.0, -9999.0, -np.inf],
        ]
    )
    template = _write_climatology(tmp_path, lat, lon, {1: jan, 6: june})
    ds = _run(template, max_chl=10.0, fill_chl=0.2)

    # Monthly mean daily TOA insolation from the Spencer formulation, W m-2.
    # These are independent reference values for January and June at +/-60.
    north = np.array([40.474122663219, 471.939262101058])
    south = np.array([473.459167812056, 24.909711258990])
    north /= north.sum()
    south /= south.sum()

    assert set(ds.variables) == {
        'lat',
        'lon',
        'ExtinctionCoeffRed',
        'ExtinctionCoeffBlue',
        'ChlorophyllWeighted',
        'nValidMonths',
        'filled',
    }
    # latitude is written ascending
    np.testing.assert_array_equal(ds['lat'], lat[::-1])
    np.testing.assert_array_equal(ds['lon'], lon)
    expected = {
        'ExtinctionCoeffRed': _expected_field(
            north, south, 0.225, 0.037, 0.629
        ),
        'ExtinctionCoeffBlue': _expected_field(
            north, south, 0.0232, 0.074, 0.674
        ),
        'ChlorophyllWeighted': _expected_field(north, south, 0.0, 1.0, 1.0),
    }
    for name, values in expected.items():
        assert ds[name].dims == ('lat', 'lon')
        np.testing.assert_allclose(ds[name], values, rtol=1e-6)
    np.testing.assert_array_equal(
        ds['nValidMonths'], [[2, 0, 0], [2, 2, 0], [1, 2, 0]]
    )
    np.testing.assert_array_equal(
        ds['filled'], [[0, 1, 1], [0, 0, 1], [1, 0, 1]]
    )
    assert ds['ExtinctionCoeffRed'].attrs['units'] == 'm-1'
    assert ds['ExtinctionCoeffBlue'].attrs['units'] == 'm-1'
    assert 'capped at 10.0' in ds.attrs['method']
    assert 'filled with Chl = 0.2' in ds.attrs['method']
    assert 'Manizza' in ds.attrs['references']


def test_all_missing_is_filled(tmp_path):
    template = _write_climatology(tmp_path, [-30.0, 30.0], [0.0, 90.0])
    ds = _run(template, fill_chl=0.0)
    np.testing.assert_array_equal(ds['filled'], np.ones((2, 2)))
    np.testing.assert_array_equal(ds['nValidMonths'], np.zeros((2, 2)))
    np.testing.assert_allclose(ds['ChlorophyllWeighted'], 0.0)
    np.testing.assert_allclose(ds['ExtinctionCoeffRed'], 0.225)
    np.testing.assert_allclose(ds['ExtinctionCoeffBlue'], 0.0232)


@pytest.mark.parametrize('coordinate', ['lat', 'lon'])
@pytest.mark.parametrize('change', ['shift', 'reverse', 'size'])
def test_monthly_grid_mismatch_rejected(tmp_path, coordinate, change):
    lat = np.array([-60.0, 0.0, 60.0])
    lon = np.array([10.0, 20.0, 30.0])
    template = _write_climatology(tmp_path, lat, lon)
    changed = (lat if coordinate == 'lat' else lon).copy()
    if change == 'shift':
        changed += 0.5
    elif change == 'reverse':
        changed = changed[::-1]
    else:
        changed = changed[:-1]
    if coordinate == 'lat':
        lat = changed
    else:
        lon = changed
    _write_month(
        template.format(month=7), lat, lon, np.zeros((len(lat), len(lon)))
    )
    with pytest.raises(ValueError, match='(?i)grid|lat|lon|coord'):
        _run(template)


@pytest.mark.parametrize('coordinate', ['lat', 'lon'])
@pytest.mark.parametrize(
    'values',
    [
        [0.0, 0.0, 1.0],
        [0.0, 2.0, 1.0],
        [0.0, np.nan, 2.0],
        [0.0, np.inf, 2.0],
    ],
    ids=['duplicate', 'nonmonotonic', 'nan', 'inf'],
)
def test_invalid_coordinates_rejected(tmp_path, coordinate, values):
    lat = values if coordinate == 'lat' else [-30.0, 0.0, 30.0]
    lon = values if coordinate == 'lon' else [10.0, 20.0, 30.0]
    template = _write_climatology(tmp_path, lat, lon)
    with pytest.raises(ValueError, match='(?i)grid|lat|lon|coord'):
        _run(template)


def test_the_step_downloads_the_twelve_monthly_files():
    class _Component:
        name = 'ocean'

    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forcing.shortwave_extinction',
        'shortwave_extinction.cfg',
    )
    step = ShortwaveExtinctionProductStep(
        component=_Component(), subdir='extinction_product'
    )
    step.config = config
    step.setup()

    urls = sorted(d['url'] for d in step.input_data if d['url'])
    assert len(urls) == 12
    assert urls[0].endswith('/GMIS_A_CHLA_01.nc')
    assert urls[-1].endswith('/GMIS_A_CHLA_12.nc')
