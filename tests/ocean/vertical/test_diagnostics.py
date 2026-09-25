"""
Unit tests for pseudothickness_from_ds().

All tests are self-contained: no file I/O, no full Polaris step framework.
A minimal ConfigParser and xarray.Dataset are constructed in each test.
"""

from configparser import ConfigParser

import gsw
import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.vertical.diagnostics import (
    depth_from_thickness,
    get_z_mid_and_interface,
    location_for_field,
    pseudothickness_from_ds,
    spec_vol_from_ds,
    vert_pseudo_velocity_from_ds,
    vert_velocity_top_from_ds,
    vertical_coord_from_location,
)


def _make_config(eos_type='teos-10'):
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'eos_type', eos_type)
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'pseudothickness_iter_count', '10')
    return config


def _make_ds(surface_pressure=None):
    data_vars: dict = dict(
        restingThickness=(('Time', 'nCells', 'nVertLevels'), [[[10.0, 10.0]]]),
        temperature=(('Time', 'nCells', 'nVertLevels'), [[[3.0, 3.0]]]),
        salinity=(('Time', 'nCells', 'nVertLevels'), [[[35.0, 35.0]]]),
    )
    if surface_pressure is not None:
        data_vars['SurfacePressure'] = ('nCells', [surface_pressure])
    return xr.Dataset(data_vars=data_vars)


def test_raises_without_a_surface_pressure():
    """Rather than invent a surface pressure, which cannot be right for both
    callers, the missing field is reported."""
    with pytest.raises(ValueError, match='requires SurfacePressure'):
        pseudothickness_from_ds(
            _make_ds(),
            config=_make_config(),
            src_var_name='restingThickness',
        )


def test_no_surface_pressure_needed_when_given_explicitly():
    pseudothickness, _ = pseudothickness_from_ds(
        _make_ds(),
        config=_make_config(),
        src_var_name='restingThickness',
        surf_pressure=0.0,
    )
    assert pseudothickness is not None


def test_explicit_surface_pressure_overrides_the_dataset():
    """Resting thicknesses are defined at zero surface pressure, so they must
    not depend on a surface pressure the dataset happens to carry."""
    config = _make_config()
    with_pressure, _ = pseudothickness_from_ds(
        _make_ds(surface_pressure=101325.0),
        config=config,
        src_var_name='restingThickness',
        surf_pressure=0.0,
    )
    without_pressure, _ = pseudothickness_from_ds(
        _make_ds(),
        config=config,
        src_var_name='restingThickness',
        surf_pressure=0.0,
    )
    np.testing.assert_allclose(with_pressure.values, without_pressure.values)


def test_dataset_surface_pressure_is_used_by_default():
    """A surface pressure in the dataset alters the result through the
    pressure dependence of the equation of state."""
    config = _make_config()
    at_zero, _ = pseudothickness_from_ds(
        _make_ds(surface_pressure=101325.0),
        config=config,
        src_var_name='restingThickness',
        surf_pressure=0.0,
    )
    from_ds, _ = pseudothickness_from_ds(
        _make_ds(surface_pressure=101325.0),
        config=config,
        src_var_name='restingThickness',
    )
    assert not np.allclose(at_zero.values, from_ds.values)


def _make_vert_coord_ds(var_name, with_time=None):
    """A dataset with a single vertical coordinate field on ``nCells``,
    ``nVertLevels``, and optionally ``Time`` of the given length."""
    values: list = [[0.0, -1.0], [0.0, -2.0]]
    dims: tuple = ('nCells', 'nVertLevels')
    if with_time is not None:
        values = [values] * with_time
        dims = ('Time',) + dims
    return xr.Dataset(data_vars={var_name: (dims, values)})


@pytest.mark.parametrize(
    'location, var_name',
    [
        ('cell-center', 'zMid'),
        ('cell-interfaces', 'GeomZInterface'),
        ('cell-top', 'zTop'),
    ],
)
def test_vertical_coord_from_location(location, var_name):
    ds = _make_vert_coord_ds(var_name)
    coord = vertical_coord_from_location(ds, location)
    assert set(coord.dims) == {'nCells', 'nVertLevels'}
    np.testing.assert_allclose(coord.values, [[0.0, -1.0], [0.0, -2.0]])


def test_vertical_coord_from_location_unsupported_location():
    ds = _make_vert_coord_ds('zMid')
    with pytest.raises(ValueError, match='Unsupported variable location'):
        vertical_coord_from_location(ds, 'cell-bottom')


def test_vertical_coord_from_location_missing_field():
    ds = _make_vert_coord_ds('zMid')
    with pytest.raises(ValueError, match='GeomZInterface'):
        vertical_coord_from_location(ds, 'cell-interfaces')


def test_vertical_coord_from_location_retains_time_of_length_one():
    ds = _make_vert_coord_ds('zMid', with_time=1)
    coord = vertical_coord_from_location(ds, 'cell-center')
    assert set(coord.dims) == {'Time', 'nCells', 'nVertLevels'}
    assert coord.sizes['Time'] == 1


def test_vertical_coord_from_location_rejects_multiple_times():
    """A dataset carrying more than one time cannot be reduced to a single
    vertical coordinate without picking a time, which is left to the
    caller."""
    ds = _make_vert_coord_ds('zMid', with_time=2)
    with pytest.raises(ValueError, match='Time dimension'):
        vertical_coord_from_location(ds, 'cell-center')


def test_location_for_field_interfaces():
    var = xr.DataArray(np.zeros(3), dims=('nVertLevelsP1',))
    assert location_for_field(var) == 'cell-interfaces'


def test_location_for_field_layer_top():
    """BruntVaisalaFreqTop is listed in variables.yaml as an MPAS-Ocean
    field written at the top of each layer despite being on
    nVertLevels."""
    var = xr.DataArray(np.zeros(3), dims=('nVertLevels',))
    location = location_for_field(var, 'BruntVaisalaFreqTop')
    assert location == 'cell-top'


def test_location_for_field_defaults_to_cell_center():
    var = xr.DataArray(np.zeros(3), dims=('nVertLevels',))
    assert location_for_field(var, 'temperature') == 'cell-center'
    assert location_for_field(var) == 'cell-center'


def _make_reconstruction_datasets():
    ds = xr.Dataset(
        data_vars=dict(
            layerThickness=(('nCells', 'nVertLevels'), [[10.0, 10.0]]),
        )
    )
    ds_vert = xr.Dataset(
        data_vars=dict(
            bottomDepth=('nCells', [20.0]),
            minLevelCell=('nCells', [1]),
            maxLevelCell=('nCells', [2]),
        )
    )
    return ds, ds_vert


def test_get_z_mid_and_interface_reconstruct():
    ds, ds_vert = _make_reconstruction_datasets()
    with pytest.raises(ValueError, match='no zMid, GeomZInterface'):
        get_z_mid_and_interface(ds, allow_reconstruct=False)

    with pytest.raises(
        ValueError, match='without the vertical coordinate dataset'
    ):
        get_z_mid_and_interface(ds, allow_reconstruct=True, ds_vert=None)

    z_mid, z_interface = get_z_mid_and_interface(
        ds, allow_reconstruct=True, ds_vert=ds_vert
    )
    np.testing.assert_allclose(z_interface.values, [[0.0, -10.0, -20.0]])
    np.testing.assert_allclose(z_mid.values, [[-5.0, -15.0]])


def test_depth_from_thickness_with_ds_vert():
    ds, ds_vert = _make_reconstruction_datasets()
    with pytest.raises(
        ValueError, match='without the vertical coordinate dataset'
    ):
        depth_from_thickness(ds, ds_vert=None)

    z_mid = depth_from_thickness(ds, ds_vert=ds_vert)
    np.testing.assert_allclose(z_mid.values, [[-5.0, -15.0]])


def test_vertical_coord_from_location_reconstruct():
    ds, ds_vert = _make_reconstruction_datasets()
    with pytest.raises(
        ValueError, match='without the vertical coordinate dataset'
    ):
        vertical_coord_from_location(
            ds, 'cell-center', allow_reconstruct=True, ds_vert=None
        )

    z_center = vertical_coord_from_location(
        ds, 'cell-center', allow_reconstruct=True, ds_vert=ds_vert
    )
    np.testing.assert_allclose(z_center.values, [[-5.0, -15.0]])

    z_inter = vertical_coord_from_location(
        ds, 'cell-interfaces', allow_reconstruct=True, ds_vert=ds_vert
    )
    np.testing.assert_allclose(z_inter.values, [[0.0, -10.0, -20.0]])

    z_top = vertical_coord_from_location(
        ds, 'cell-top', allow_reconstruct=True, ds_vert=ds_vert
    )
    np.testing.assert_allclose(z_top.values, [[0.0, -10.0]])


def test_reconstruct_from_omega_state():
    rho_sw = get_constant('seawater_density_reference')
    spec_vol = 1.0 / rho_sw
    ds = xr.Dataset(
        data_vars=dict(
            SpecVol=(('nCells', 'nVertLevels'), [[spec_vol, spec_vol]]),
            PseudoThickness=(('nCells', 'nVertLevels'), [[10.0, 10.0]]),
        )
    )
    ds_vert = xr.Dataset(
        data_vars=dict(
            bottomDepth=('nCells', [20.0]),
        )
    )
    z_mid, z_interface = get_z_mid_and_interface(
        ds, allow_reconstruct=True, ds_vert=ds_vert
    )
    np.testing.assert_allclose(z_interface.values, [[0.0, -10.0, -20.0]])
    np.testing.assert_allclose(z_mid.values, [[-5.0, -15.0]])


def test_reconstruct_missing_bottom_depth():
    ds = xr.Dataset(
        data_vars=dict(
            layerThickness=(('nCells', 'nVertLevels'), [[10.0, 10.0]]),
        )
    )
    ds_vert = xr.Dataset()
    with pytest.raises(ValueError, match='bottomDepth is not present'):
        get_z_mid_and_interface(ds, allow_reconstruct=True, ds_vert=ds_vert)


def _make_omega_state_ds(with_pseudothickness=True):
    """An Omega state with MPAS-Ocean names and no SpecVol"""
    cell_dims = ('Time', 'nCells', 'nVertLevels')
    data_vars: dict = dict(
        temperature=(cell_dims, [[[10.0, 5.0, 2.0]]]),
        salinity=(cell_dims, [[[34.0, 34.5, 35.0]]]),
        SurfacePressure=(('Time', 'nCells'), [[1.0e4]]),
    )
    if with_pseudothickness:
        data_vars['PseudoThickness'] = (cell_dims, [[[10.0, 100.0, 1000.0]]])
    return xr.Dataset(data_vars=data_vars)


def test_spec_vol_from_pseudothickness():
    """The pressure a pseudo-thickness implies is used directly, with no
    geometric thickness or iteration."""
    rho_sw = get_constant('seawater_density_reference')
    gravity = get_constant('standard_acceleration_of_gravity')
    ds = _make_omega_state_ds()

    spec_vol = spec_vol_from_ds(ds, _make_config())

    h_tilde = np.array([10.0, 100.0, 1000.0])
    p_top = 1.0e4 + rho_sw * gravity * (np.cumsum(h_tilde) - h_tilde)
    p_mid = p_top + 0.5 * rho_sw * gravity * h_tilde
    expected = gsw.specvol(
        ds.salinity.values[0, 0], ds.temperature.values[0, 0], p_mid / 1.0e4
    )
    assert spec_vol.dims == ds.temperature.dims
    np.testing.assert_allclose(spec_vol.values[0, 0], expected, rtol=1e-12)


def test_spec_vol_from_geom_thickness_matches_pseudothickness():
    """Without a pseudo-thickness, the iteration from the geometric
    thickness finds the same specific volume."""
    rho_sw = get_constant('seawater_density_reference')
    config = _make_config()
    ds = _make_omega_state_ds()
    spec_vol = spec_vol_from_ds(ds, config)

    ds_geom = _make_omega_state_ds(with_pseudothickness=False)
    ds_geom['layerThickness'] = rho_sw * spec_vol * ds.PseudoThickness
    spec_vol_geom = spec_vol_from_ds(ds_geom, config)

    np.testing.assert_allclose(spec_vol_geom.values, spec_vol.values, 1e-12)


@pytest.mark.parametrize(
    'drop, match',
    [
        ('SurfacePressure', 'without SurfacePressure'),
        ('PseudoThickness', 'without PseudoThickness or layerThickness'),
    ],
)
def test_spec_vol_from_ds_missing_inputs(drop, match):
    ds = _make_omega_state_ds().drop_vars(drop)
    with pytest.raises(ValueError, match=match):
        spec_vol_from_ds(ds, _make_config())


def _make_vert_velocity_ds():
    """Omega output with a uniform pseudo-velocity and a specific volume
    that differs between layers of unequal thickness"""
    rho_sw = get_constant('seawater_density_reference')
    spec_vol = np.array([1.0, 2.0, 4.0]) / rho_sw
    return xr.Dataset(
        data_vars=dict(
            VerticalPseudoVelocity=(
                ('Time', 'nCells', 'nVertLevelsP1'),
                np.ones((1, 1, 4)),
            ),
            SpecVol=(('Time', 'nCells', 'nVertLevels'), [[spec_vol]]),
            # geometric thicknesses of 10, 10 and 30 m
            PseudoThickness=(
                ('Time', 'nCells', 'nVertLevels'),
                [[[10.0, 5.0, 7.5]]],
            ),
        )
    )


def test_vert_velocity_top_from_ds():
    """SpecVol is interpolated to interfaces in geometric height, and held
    constant above the top and below the bottom layer."""
    ds = _make_vert_velocity_ds()
    vert_velocity_top = vert_velocity_top_from_ds(ds)
    assert vert_velocity_top.dims == ds.VerticalPseudoVelocity.dims
    np.testing.assert_allclose(
        vert_velocity_top.values, [[[1.0, 1.5, 2.5, 4.0]]]
    )


def test_vert_velocity_top_from_ds_invalid_layers():
    """Interfaces next to an invalid layer take the valid layer's value,
    and those between two invalid layers are NaN."""
    ds = _make_vert_velocity_ds()
    ds_vert = xr.Dataset(
        data_vars=dict(
            minLevelCell=('nCells', [1]),
            maxLevelCell=('nCells', [2]),
        )
    )
    vert_velocity_top = vert_velocity_top_from_ds(ds, ds_vert=ds_vert)
    np.testing.assert_allclose(
        vert_velocity_top.values, [[[1.0, 1.5, 2.0, np.nan]]]
    )


def test_vert_pseudo_velocity_from_ds():
    """The inverse of vert_velocity_top_from_ds(), with the dimensions of
    the geometric velocity"""
    ds = _make_vert_velocity_ds()
    ds['vertVelocityTop'] = (
        ('Time', 'nCells', 'nVertLevelsP1'),
        [[[1.0, 1.5, 2.5, 4.0]]],
    )
    pseudo_velocity = vert_pseudo_velocity_from_ds(ds)
    assert pseudo_velocity.dims == ds.vertVelocityTop.dims
    np.testing.assert_allclose(pseudo_velocity.values, np.ones((1, 1, 4)))


@pytest.mark.parametrize('with_ds_vert', [False, True])
def test_vert_pseudo_velocity_round_trip(with_ds_vert):
    """Converting to a pseudo-velocity and back recovers the original
    velocity at every interface next to a valid layer."""
    ds = _make_vert_velocity_ds().drop_vars('VerticalPseudoVelocity')
    velocity = np.array([[[0.0, -2.0e-4, 3.0e-5, 1.0e-4]]])
    ds['vertAleTransportTop'] = (
        ('Time', 'nCells', 'nVertLevelsP1'),
        velocity,
    )
    ds_vert = None
    if with_ds_vert:
        ds_vert = xr.Dataset(
            data_vars=dict(
                minLevelCell=('nCells', [1]),
                maxLevelCell=('nCells', [2]),
            )
        )
        velocity[..., -1] = np.nan
    ds['VerticalPseudoVelocity'] = vert_pseudo_velocity_from_ds(
        ds, src_var_name='vertAleTransportTop', ds_vert=ds_vert
    )
    round_trip = vert_velocity_top_from_ds(ds, ds_vert=ds_vert)
    np.testing.assert_allclose(round_trip.values, velocity)
