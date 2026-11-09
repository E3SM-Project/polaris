"""
Unit tests for the Galewsky et al. (2004) jet, its balanced height and its
height perturbation.  These need no mesh and no model.
"""

import numpy as np
import pytest

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.tasks.ocean.galewsky_jet.initial_state import (
    balanced_height,
    get_jet_params,
    height_perturbation,
    jet_velocity,
    streamfunction,
)

U_MAX = 80.0
PHI0 = np.pi / 7.0
PHI1 = 0.5 * np.pi - PHI0
JET = dict(u_max=U_MAX, phi0=PHI0, phi1=PHI1)
PERTURBATION = dict(
    h_hat=120.0, alpha=1.0 / 3.0, beta=1.0 / 15.0, phi2=0.25 * np.pi
)


def test_jet_peaks_at_45n():
    lat = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 180001)
    u = jet_velocity(lat, **JET)
    assert u.max() == pytest.approx(U_MAX, rel=1e-8)
    assert np.rad2deg(lat[np.argmax(u)]) == pytest.approx(45.0, abs=1e-3)


def test_jet_is_zero_outside():
    lat = np.deg2rad(np.array([-90.0, -45.0, 0.0, 25.0, 65.0, 80.0, 90.0]))
    assert np.all(jet_velocity(lat, **JET) == 0.0)


def test_balanced_height_mean_and_range():
    lat = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 20001)
    h = balanced_height(lat, h_mean=10000.0, **JET)
    weight = np.cos(lat)
    mean = np.trapezoid(h * weight, lat) / np.trapezoid(weight, lat)
    assert mean == pytest.approx(10000.0, abs=1e-3)
    # the range Galewsky et al. (2004) show in their Fig. 1b
    assert h.min() == pytest.approx(9071.3, abs=1.0)
    assert h.max() == pytest.approx(10158.2, abs=1.0)


def test_balanced_height_is_in_gradient_wind_balance():
    """
    g dh/dphi = -a u (f + u tan(phi) / a), GSP04 eq. 3 in differential form
    """
    radius = get_constant('mean_radius')
    gravity = get_constant('standard_acceleration_of_gravity')
    omega = get_constant('angular_velocity')

    lat = np.deg2rad(np.linspace(30.0, 60.0, 31))
    dlat = 1e-5
    h_plus = balanced_height(lat + dlat, h_mean=10000.0, **JET)
    h_minus = balanced_height(lat - dlat, h_mean=10000.0, **JET)
    lhs = gravity * (h_plus - h_minus) / (2.0 * dlat)

    u = jet_velocity(lat, **JET)
    coriolis = 2.0 * omega * np.sin(lat)
    rhs = -radius * u * (coriolis + u * np.tan(lat) / radius)
    atol = 1e-3 * np.abs(rhs).max()
    np.testing.assert_allclose(lhs, rhs, rtol=1e-3, atol=atol)


def test_streamfunction_gives_jet():
    """
    u = -(1/a) dpsi/dphi
    """
    radius = get_constant('mean_radius')
    lat = np.deg2rad(np.linspace(-80.0, 80.0, 161))
    dlat = 1e-5
    psi_plus = streamfunction(lat + dlat, **JET)
    psi_minus = streamfunction(lat - dlat, **JET)
    u = -(psi_plus - psi_minus) / (2.0 * dlat * radius)
    # the streamfunction is interpolated linearly from the quadrature grid,
    # so this difference across a fraction of a grid interval is only
    # accurate to about 1e-4
    np.testing.assert_allclose(
        u, jet_velocity(lat, **JET), rtol=1e-3, atol=1e-3
    )


def test_perturbation_peak_and_location():
    lon = np.deg2rad(np.linspace(-180.0, 179.5, 720))
    lat = np.deg2rad(np.linspace(-89.5, 89.5, 359))
    lon, lat = np.meshgrid(lon, lat)
    h_prime = height_perturbation(lon, lat, **PERTURBATION)
    index = np.unravel_index(np.argmax(h_prime), h_prime.shape)
    assert np.rad2deg(lon[index]) == pytest.approx(0.0, abs=0.5)
    assert np.rad2deg(lat[index]) == pytest.approx(45.0, abs=0.5)
    # the peak is h_hat cos(45 deg)
    peak = 120.0 * np.cos(0.25 * np.pi)
    assert h_prime.max() == pytest.approx(peak, rel=1e-3)


def test_perturbation_wraps_in_longitude():
    lat = np.deg2rad(45.0)
    kwargs = PERTURBATION
    for lon in [0.1, -0.2, 3.0]:
        assert height_perturbation(
            lon + 2.0 * np.pi, lat, **kwargs
        ) == pytest.approx(height_perturbation(lon, lat, **kwargs))
    # negligible on the far side of the globe
    assert height_perturbation(np.pi, lat, **kwargs) < 1e-30


def test_jet_params_from_config():
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.galewsky_jet', 'galewsky_jet.cfg'
    )
    params = get_jet_params(config)
    assert params['phi0'] == pytest.approx(np.pi / 7.0)
    assert params['phi1'] == pytest.approx(0.5 * np.pi - np.pi / 7.0)
    assert params['phi2'] == pytest.approx(0.25 * np.pi)
    assert params['alpha'] == pytest.approx(1.0 / 3.0)
    assert params['beta'] == pytest.approx(1.0 / 15.0)
    assert params['u_max'] == 80.0
    assert params['h_hat'] == 120.0
    assert params['h_mean'] == 10000.0
