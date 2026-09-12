"""
Unit tests for pseudothickness_from_ds().

All tests are self-contained: no file I/O, no full Polaris step framework.
A minimal ConfigParser and xarray.Dataset are constructed in each test.
"""

from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.vertical.diagnostics import (
    depth_from_thickness,
    get_z_mid_and_interface,
    location_for_field,
    pseudothickness_from_ds,
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
