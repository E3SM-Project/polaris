import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.forcing.jra55.stress import (
    Jra55StressStep,
    wind_stress,
)

# the outermost two TL319 Gaussian latitudes, from the JRA55-do file
TL319_LAT_OUTER = 89.57008955
TL319_LON_LAST = 359.4375

RHO_AIR = 1.22
MIN_WIND_SPEED = 0.5


def _drag(speed):
    """The Large and Yeager neutral 10-m drag law, written out longhand."""
    return 1e-3 * (2.70 / speed + 0.142 + 0.0764 * speed)


@pytest.mark.parametrize('speed', [1.0, 5.0, 10.0, 20.0])
def test_drag_law_matches_large_and_yeager(speed):
    """
    Stress follows rho * Cd * |U| * U with the Large and Yeager neutral
    10-m drag coefficient.
    """
    taux, tauy = wind_stress(
        u10=np.array([speed]),
        v10=np.array([0.0]),
        rho_air=RHO_AIR,
        min_wind_speed=MIN_WIND_SPEED,
    )
    expected = RHO_AIR * _drag(speed) * speed * speed
    assert taux[0] == pytest.approx(expected)
    assert tauy[0] == pytest.approx(0.0)


def test_low_wind_speed_is_clamped():
    """
    The 2.70/U term diverges as U goes to zero, so the speed used in the
    drag law is clamped from below.  The stress itself still goes to zero,
    because it is proportional to the wind components.
    """
    small = 1e-8
    taux, _ = wind_stress(
        u10=np.array([small]),
        v10=np.array([0.0]),
        rho_air=RHO_AIR,
        min_wind_speed=MIN_WIND_SPEED,
    )
    expected = RHO_AIR * _drag(MIN_WIND_SPEED) * MIN_WIND_SPEED * small
    assert np.isfinite(taux[0])
    assert taux[0] == pytest.approx(expected)

    zero, _ = wind_stress(
        u10=np.array([0.0]),
        v10=np.array([0.0]),
        rho_air=RHO_AIR,
        min_wind_speed=MIN_WIND_SPEED,
    )
    assert zero[0] == pytest.approx(0.0)


def test_stress_of_mean_wind_underestimates_mean_stress():
    """
    This is why the step averages the stress rather than the wind, and why
    it needs the 3-hourly data at all: the drag law is convex, so gusts
    contribute stress that a time-mean wind does not carry.
    """
    rng = np.random.default_rng(0)
    u10 = 8.0 + 6.0 * rng.standard_normal(20000)
    v10 = np.zeros_like(u10)

    taux, _ = wind_stress(
        u10=u10,
        v10=v10,
        rho_air=RHO_AIR,
        min_wind_speed=MIN_WIND_SPEED,
    )
    taux_of_mean, _ = wind_stress(
        u10=np.array([u10.mean()]),
        v10=np.array([0.0]),
        rho_air=RHO_AIR,
        min_wind_speed=MIN_WIND_SPEED,
    )

    assert taux.mean() > taux_of_mean[0]


def _synthetic_source():
    """
    A tiny stand-in for the JRA55-do file, with the real TL319 outermost
    latitude and longitude so the padding test is meaningful.
    """
    lat = np.array([-TL319_LAT_OUTER, 0.0, TL319_LAT_OUTER])
    lon = np.array([0.0, 180.0, TL319_LON_LAST])
    lat_bnds = np.column_stack([lat - 0.25, lat + 0.25])
    lon_bnds = np.column_stack([lon - 0.28125, lon + 0.28125])
    return xr.Dataset(
        {
            'lat_bnds': (('lat', 'bnds'), lat_bnds),
            'lon_bnds': (('lon', 'bnds'), lon_bnds),
        },
        coords={'lat': ('lat', lat), 'lon': ('lon', lon)},
    )


def test_product_is_not_padded():
    """
    The product must keep the native TL319 extent.  Padding a lat-lon source
    so that its corners or centres reach the pole aborts mbtempest, and
    duplicating a longitude column makes the grid overlap itself and breaks
    both map tools.  See remap_bilinear_pole_findings.md.
    """
    ds_source = _synthetic_source()
    shape = (ds_source.sizes['lat'], ds_source.sizes['lon'])
    ds_out = Jra55StressStep._build_dataset(
        ds_u=ds_source,
        taux=np.zeros(shape),
        tauy=np.zeros(shape),
    )

    assert ds_out.lat.values[0] == pytest.approx(-TL319_LAT_OUTER)
    assert ds_out.lat.values[-1] == pytest.approx(TL319_LAT_OUTER)
    assert abs(ds_out.lat.values).max() < 90.0
    assert ds_out.lon.values[-1] == pytest.approx(TL319_LON_LAST)
    assert ds_out.lon.values[-1] < 360.0
    assert ds_out.sizes['lat'] == ds_source.sizes['lat']
    assert ds_out.sizes['lon'] == ds_source.sizes['lon']


def test_bounds_are_carried_through():
    """
    CF bounds are passed on so the product stays correct if pyremap learns
    to honour them.
    """
    ds_source = _synthetic_source()
    shape = (ds_source.sizes['lat'], ds_source.sizes['lon'])
    ds_out = Jra55StressStep._build_dataset(
        ds_u=ds_source,
        taux=np.zeros(shape),
        tauy=np.zeros(shape),
    )
    for name in ['lat_bnds', 'lon_bnds']:
        assert name in ds_out
        np.testing.assert_allclose(ds_out[name].values, ds_source[name].values)


def test_stress_variables_have_units():
    """
    Both models expect N m-2, so the units travel with the product.
    """
    ds_source = _synthetic_source()
    shape = (ds_source.sizes['lat'], ds_source.sizes['lon'])
    ds_out = Jra55StressStep._build_dataset(
        ds_u=ds_source,
        taux=np.ones(shape),
        tauy=np.full(shape, 2.0),
    )
    for name in ['taux', 'tauy']:
        assert ds_out[name].attrs['units'] == 'N m-2'
        assert ds_out[name].dims == ('lat', 'lon')
