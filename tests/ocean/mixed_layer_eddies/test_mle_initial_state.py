import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.mixed_layer_eddies.init import (
    compute_background_salinity,
    compute_density_anomaly,
    read_itp77_salinity,
)


@pytest.fixture(scope='module')
def config():
    """The config options of the mixed-layer eddies tasks"""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.mixed_layer_eddies', 'mixed_layer_eddies.cfg'
    )
    return config


def test_itp77_profile_is_read_deepest_first():
    z, salinity = read_itp77_salinity()
    assert z.size == 149
    assert np.all(np.diff(z) > 0.0)
    assert z[0] == pytest.approx(-151.36, abs=0.01)
    # a fresh surface layer over the halocline
    assert salinity[-1] < salinity[0]


def test_background_is_constant_above_the_mixed_layer_base():
    z_profile, salinity_profile = read_itp77_salinity()
    z = np.array([0.0, -10.0, -29.0, -30.0, -60.0, -152.0])
    salinity = compute_background_salinity(
        z, z_profile, salinity_profile, ml_depth=30.0
    )
    at_base = np.interp(-30.0, z_profile, salinity_profile)
    np.testing.assert_allclose(salinity[:4], at_base)
    assert salinity[4] == pytest.approx(
        np.interp(-60.0, z_profile, salinity_profile)
    )
    # below the deepest point, the profile is held at its deepest value
    assert salinity[5] == pytest.approx(salinity_profile[0])


def test_background_keeps_data_array_dims():
    z_profile, salinity_profile = read_itp77_salinity()
    z = xr.DataArray([[-5.0, -50.0]], dims=('nCells', 'nVertLevels'))
    salinity = compute_background_salinity(
        z, z_profile, salinity_profile, ml_depth=30.0
    )
    assert isinstance(salinity, xr.DataArray)
    assert salinity.dims == ('nCells', 'nVertLevels')


def test_fronts_are_periodic_and_centered(config):
    y_period = 200.0e3
    y = xr.DataArray(np.linspace(0.0, y_period, 9), dims=('nCells',))
    z = xr.DataArray([-1.0], dims=('nVertLevels',))
    anomaly = compute_density_anomaly(config, y, z, y_period).isel(
        nVertLevels=0
    )
    # periodic: the same at both ends of the domain
    np.testing.assert_allclose(
        anomaly.isel(nCells=0), anomaly.isel(nCells=-1), atol=1e-12
    )
    # the front at L_y / 2 has density increasing with y
    center = anomaly.isel(nCells=4)
    assert float(anomaly.isel(nCells=5)) > float(center)
    # Delta rho_y Y_S - Delta rho_z, with Y_S = 0 at the front
    assert float(center) == pytest.approx(-1.5, rel=1e-4)


def test_anomaly_tapers_at_the_mixed_layer_base(config):
    y_period = 200.0e3
    y = xr.DataArray([0.5 * y_period], dims=('nCells',))
    z = xr.DataArray([0.0, -30.0, -60.0], dims=('nVertLevels',))
    anomaly = compute_density_anomaly(config, y, z, y_period)
    anomaly = anomaly.isel(nCells=0).values
    # full offset at the surface, half at H_m, none well below
    assert anomaly[0] == pytest.approx(-1.5, rel=1e-4)
    assert anomaly[1] == pytest.approx(-0.75, rel=1e-6)
    assert abs(anomaly[2]) < 1e-4
