import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.diagnostics import vert_velocity_top_from_ds
from polaris.tasks.ocean import Ocean

# a velocity that differs between interfaces, so a mismatch in where
# SpecVol is interpolated to would show up
VERT_VELOCITY_TOP = np.array(
    [[[0.0, 1.0e-4, -2.0e-4, 5.0e-5, 0.0]] * 3],
)


def _make_component():
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    return component


def _make_config():
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.set('ocean', 'eos_type', 'linear')
    return config


def _make_state_ds():
    """A state with layers of unequal thickness and a temperature that
    varies with depth, so SpecVol does too"""
    dims = ('Time', 'nCells', 'nVertLevels')
    ds = xr.Dataset()
    ds['layerThickness'] = (
        dims,
        np.broadcast_to([10.0, 20.0, 40.0, 80.0], (1, 3, 4)),
    )
    ds['temperature'] = (
        dims,
        np.broadcast_to([20.0, 12.0, 6.0, 2.0], (1, 3, 4)),
    )
    ds['salinity'] = (dims, np.full((1, 3, 4), 35.0))
    ds['SurfacePressure'] = (('Time', 'nCells'), np.zeros((1, 3)))
    ds['vertVelocityTop'] = (
        ('Time', 'nCells', 'nVertLevelsP1'),
        VERT_VELOCITY_TOP,
    )
    return ds


@pytest.mark.parametrize('already_present', [None, 'PseudoThickness'])
def test_write_adds_vertical_pseudo_velocity(tmp_path, already_present):
    """VerticalPseudoVelocity is written on interfaces whether or not the
    layerThickness pass added SpecVol first (#815, #816)."""
    ds = _make_state_ds()
    if already_present is not None:
        ds[already_present] = ds.layerThickness
    filename = str(tmp_path / 'state.nc')

    _make_component().write_model_dataset(ds, filename, _make_config())

    ds_out = xr.open_dataset(filename)
    assert ds_out.VerticalPseudoVelocity.dims == (
        'time',
        'NCells',
        'NVertLayersP1',
    )


def test_write_adds_total_vertical_pseudo_velocity(tmp_path):
    """vertAleTransportTop is converted the same way as vertVelocityTop."""
    ds = _make_state_ds().rename({'vertVelocityTop': 'vertAleTransportTop'})
    filename = str(tmp_path / 'state.nc')

    _make_component().write_model_dataset(ds, filename, _make_config())

    ds_out = xr.open_dataset(filename)
    assert 'VerticalPseudoVelocity' not in ds_out
    assert ds_out.TotalVerticalPseudoVelocity.dims == (
        'time',
        'NCells',
        'NVertLayersP1',
    )


def test_vertical_pseudo_velocity_round_trip(tmp_path):
    """Writing vertVelocityTop and reading it back with
    vert_velocity_top_from_ds() recovers it."""
    component = _make_component()
    config = _make_config()
    filename = str(tmp_path / 'state.nc')

    component.write_model_dataset(_make_state_ds(), filename, config)
    ds = component.open_model_dataset(filename, config)
    ds = ds.drop_vars('vertVelocityTop')

    assert np.ptp(ds.SpecVol.values) > 0.0
    assert_allclose(
        vert_velocity_top_from_ds(ds).values, VERT_VELOCITY_TOP, atol=1e-20
    )


def test_write_raises_without_spec_vol(tmp_path):
    """A vertical velocity that cannot be converted is an error, not left
    under its MPAS-Ocean name."""
    ds = _make_state_ds().drop_vars(['temperature', 'salinity'])
    filename = str(tmp_path / 'state.nc')

    with pytest.raises(ValueError, match='requires SpecVol'):
        _make_component().write_model_dataset(ds, filename, _make_config())
