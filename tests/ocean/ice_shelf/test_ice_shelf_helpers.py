from configparser import ConfigParser
from importlib import resources

import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.constants import get_constant
from polaris.ocean.ice_shelf import (
    compute_freezing_temperature,
    compute_land_ice_draft_from_pressure,
    compute_land_ice_pressure_from_draft,
    compute_land_ice_pressure_from_thickness,
)


def _read_freeze_config(model='mpas-ocean'):
    """Read the freezing-point config options shipped with polaris."""
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    text = (
        resources.files('polaris.ocean.ice_shelf')
        .joinpath('freeze.cfg')
        .read_text()
    )
    config.read_string(text)
    return config


def test_pressure_from_draft():
    gravity = get_constant('standard_acceleration_of_gravity')
    draft = xr.DataArray(np.array([-100.0, -10.0, 0.0, 5.0]))
    mask = xr.DataArray(np.array([1, 0, 1, 1]))
    pressure = compute_land_ice_pressure_from_draft(
        draft, mask, ref_density=1028.0
    )
    expected = np.array([1028.0 * gravity * 100.0, 0.0, 0.0, 0.0])
    assert_allclose(pressure.values, expected)


def test_pressure_from_draft_default_density():
    gravity = get_constant('standard_acceleration_of_gravity')
    rho_sw = get_constant('seawater_density_reference')
    draft = xr.DataArray(np.array([-200.0]))
    pressure = compute_land_ice_pressure_from_draft(draft, 1)
    assert_allclose(pressure.values, [rho_sw * gravity * 200.0])


def test_pressure_from_thickness():
    gravity = get_constant('standard_acceleration_of_gravity')
    thickness = xr.DataArray(np.array([500.0, 0.0, 300.0]))
    mask = xr.DataArray(np.array([1, 1, 0]))
    pressure = compute_land_ice_pressure_from_thickness(
        thickness, mask, land_ice_density=918.0
    )
    assert_allclose(pressure.values, [918.0 * gravity * 500.0, 0.0, 0.0])


def test_floating_ice_pressure_is_consistent():
    """Floating ice in hydrostatic balance gives the same pressure from its
    thickness and from its draft"""
    rho_ice = 918.0
    rho_sw = 1028.0
    thickness = xr.DataArray(np.array([100.0, 600.0]))
    draft = -rho_ice / rho_sw * thickness
    from_thickness = compute_land_ice_pressure_from_thickness(
        thickness, 1, land_ice_density=rho_ice
    )
    from_draft = compute_land_ice_pressure_from_draft(
        draft, 1, ref_density=rho_sw
    )
    assert_allclose(from_thickness.values, from_draft.values)


def test_draft_from_pressure_inverts_pressure_from_draft():
    draft = xr.DataArray(np.array([-500.0, -20.0, 0.0]))
    pressure = compute_land_ice_pressure_from_draft(
        draft, 1, ref_density=1028.0
    )
    recovered = compute_land_ice_draft_from_pressure(
        pressure, pressure > 0.0, ref_density=1028.0
    )
    assert_allclose(recovered.values, draft.values)


def test_freeze_config_matches_mpas_ocean_defaults():
    """The coefficients match MPAS-Ocean's defaults for
    config_land_ice_cavity_freezing_temperature_coeff_*"""
    section = _read_freeze_config()['ice_shelf_freeze']
    assert section.getfloat('mpas_ocean_coeff_0') == 6.22e-2
    assert section.getfloat('mpas_ocean_coeff_S') == -5.63e-2
    assert section.getfloat('mpas_ocean_coeff_p') == -7.43e-8
    assert section.getfloat('mpas_ocean_coeff_pS') == -1.74e-10


def test_freezing_temperature():
    config = _read_freeze_config()
    salinity = xr.DataArray(np.array([0.0, 34.0, 34.0]))
    pressure = xr.DataArray(np.array([0.0, 0.0, 5.0e6]))
    freezing = compute_freezing_temperature(config, salinity, pressure)
    expected = (
        6.22e-2
        - 5.63e-2 * salinity.values
        - 7.43e-8 * pressure.values
        - 1.74e-10 * pressure.values * salinity.values
    )
    assert_allclose(freezing.values, expected)
    # freezing point decreases with salinity and pressure
    assert freezing.values[1] < freezing.values[0]
    assert freezing.values[2] < freezing.values[1]


def test_freezing_temperature_not_supported_for_omega():
    config = _read_freeze_config(model='omega')
    salinity = xr.DataArray(np.array([34.0]))
    pressure = xr.DataArray(np.array([1.0e6]))
    with pytest.raises(NotImplementedError):
        compute_freezing_temperature(config, salinity, pressure)
