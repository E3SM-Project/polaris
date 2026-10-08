import logging
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.isomip_plus.forward import Forward
from polaris.tasks.ocean.isomip_plus.init import Init
from polaris.tasks.ocean.isomip_plus.xtime import get_record_times


def _get_config():
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.ocean.isomip_plus', 'isomip_plus.cfg'
    )
    config.set('vertical_grid', 'coord_type', 'z-star')
    return config


def _get_init_step(config) -> Any:
    """A stand-in for the init step with the attributes its methods use"""
    step: Any = SimpleNamespace(
        config=config, logger=logging.getLogger('test_wetting_drying')
    )
    step._draft_from_pressure = lambda pressure: Init._draft_from_pressure(
        step, pressure
    )
    return step


def _xtime(dates):
    return np.array([date.ljust(64) for date in dates], dtype='S64')


def test_get_record_times_bytes_and_str():
    dates = [
        '0001-01-01_00:00:00',
        '0001-01-01_06:00:00',
        '0001-01-05_00:00:00',
    ]
    expected = [0.0, 6 * 3600.0, 4 * 86400.0]
    assert_allclose(get_record_times(_xtime(dates)), expected)
    assert_allclose(get_record_times(np.array(dates)), expected)


def test_forcing_interval_from_records(tmp_path):
    ds = xr.Dataset()
    ds['xtime'] = (
        'Time',
        _xtime(
            [
                '0001-01-01_00:00:00',
                '0001-01-01_06:00:00',
                '0001-01-01_12:00:00',
            ]
        ),
    )
    ds.to_netcdf(tmp_path / 'land_ice_forcing.nc')
    step: Any = SimpleNamespace(work_dir=str(tmp_path))
    assert Forward._get_forcing_interval(step, at_setup=True) == 'none'
    interval = Forward._get_forcing_interval(step, at_setup=False)
    assert interval == '0000_06:00:00.000'


def test_forcing_interval_must_be_even(tmp_path):
    ds = xr.Dataset()
    ds['xtime'] = (
        'Time',
        _xtime(
            [
                '0001-01-01_00:00:00',
                '0001-01-01_06:00:00',
                '0001-01-02_00:00:00',
            ]
        ),
    )
    ds.to_netcdf(tmp_path / 'land_ice_forcing.nc')
    step: Any = SimpleNamespace(work_dir=str(tmp_path))
    with pytest.raises(ValueError, match='evenly spaced'):
        Forward._get_forcing_interval(step, at_setup=False)


@pytest.mark.parametrize('thin_film', [True, False])
def test_tidal_input_mask(tmp_path, monkeypatch, thin_film):
    """Only tasks with a thin film hold SSH at zero in the restoring region,
    which lies between 790 and 800 km"""
    config = _get_config()
    step = _get_init_step(config)
    step.experiment = 'drying'
    step.thin_film = thin_film
    step._get_profiles = lambda ds, profile: Init._get_profiles(
        step, ds, profile
    )
    ds = xr.Dataset()
    ds['xIsomipCell'] = ('nCells', [700e3, 790e3, 800e3])
    ds['zMid'] = (('Time', 'nCells', 'nVertLevels'), -np.ones((1, 3, 2)))
    monkeypatch.chdir(tmp_path)
    Init._write_forcing(step, ds)
    ds_forcing = xr.open_dataset('forcing.nc')
    if thin_film:
        assert_allclose(ds_forcing.tidalInputMask.values, [0.0, 1.0, 1.0])
    else:
        assert 'tidalInputMask' not in ds_forcing


def test_thicken_thin_film():
    """A grounded cell gets the thin-film thickness in each active layer,
    while a cell with a thick column is unchanged"""
    config = _get_config()
    layer_thickness = config.getfloat(
        'isomip_plus', 'thin_film_layer_thickness'
    )
    ds = xr.Dataset()
    ds['bottomDepth'] = ('nCells', [400.0, 400.0])
    # the first cell has a provisional one-layer film
    ds['ssh'] = ('nCells', [-400.0 + layer_thickness, -100.0])
    init_vertical_coord(config, ds)
    level_count = (ds.maxLevelCell - ds.minLevelCell + 1).values
    assert level_count[0] > 1
    thick_column = ds.layerThickness.isel(Time=0, nCells=1).sum().values

    step = _get_init_step(config)
    Init._thicken_thin_film(step, ds)

    column = ds.layerThickness.isel(Time=0).sum(dim='nVertLevels').values
    assert_allclose(column[0], layer_thickness * level_count[0])
    assert_allclose(column[1], thick_column)
    assert_allclose(ds.ssh.isel(Time=0).values, -400.0 + column)
    assert_allclose(ds.landIceDraft.values, ds.ssh.values)
