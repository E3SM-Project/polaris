import logging
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import xarray as xr
from numpy.testing import assert_allclose

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.isomip_plus.forward import Forward
from polaris.tasks.ocean.isomip_plus.init import PROFILES, Init
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
        config=config,
        logger=logging.getLogger('test_wetting_drying'),
        gravity=None,
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
    assert Forward.get_forcing_interval(step, at_setup=True) == 'none'
    interval = Forward.get_forcing_interval(step, at_setup=False)
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
        Forward.get_forcing_interval(step, at_setup=False)


def test_tidal_input_mask(tmp_path, monkeypatch):
    """The outflow holds SSH at zero in the restoring region, which lies
    between 790 and 800 km"""
    config = _get_config()
    step = _get_init_step(config)
    step.experiment = 'drying'
    step.profiles = PROFILES['drying']
    step._get_profiles = lambda ds, profile: Init._get_profiles(
        step, ds, profile
    )
    ds = xr.Dataset()
    ds['xIsomipCell'] = ('nCells', [700e3, 790e3, 800e3])
    ds['zMid'] = (('Time', 'nCells', 'nVertLevels'), -np.ones((1, 3, 2)))
    monkeypatch.chdir(tmp_path)
    Init._write_forcing(step, ds)
    ds_forcing = xr.open_dataset('forcing.nc')
    assert_allclose(ds_forcing.tidalInputMask.values, [0.0, 1.0, 1.0])


def test_set_ssh_from_bed():
    """Grounded cells get the thin-film thickness in each active layer above
    the bed that partial cells leave, raised in one cell and deepened in the
    other, while a floating cell with a thick column keeps its draft"""
    config = _get_config()
    layer_thickness = config.getfloat(
        'isomip_plus', 'thin_film_layer_thickness'
    )
    step = _get_init_step(config)
    step.thin_film = True
    step._get_ssh_from_bed = lambda pressure, bottom_depth, level_count=1: (
        Init._get_ssh_from_bed(step, pressure, bottom_depth, level_count)
    )
    density = config.getfloat('isomip_plus', 'ocean_density')
    gravity = get_constant('standard_acceleration_of_gravity')
    # the two grounded cells have ice heavier than floatation at the bed;
    # the third cell floats with its draft at 100 m
    pressure = density * gravity * np.array([500.0, 500.0, 100.0])
    ds = xr.Dataset()
    ds['landIcePressure'] = (('Time', 'nCells'), pressure[np.newaxis, :])
    # with 20 m layers, partial cells raise the first bed to 400 m and
    # deepen the second to 402 m
    ds['bottomDepth'] = ('nCells', [400.5, 401.5, 400.0])
    ds['ssh'] = step._get_ssh_from_bed(
        ds.landIcePressure.isel(Time=0), ds.bottomDepth
    )
    init_vertical_coord(config, ds)
    assert_allclose(ds.bottomDepth.values, [400.0, 402.0, 400.0])

    Init._set_ssh_from_bed(step, ds)

    level_count = (ds.maxLevelCell - ds.minLevelCell + 1).values
    column = ds.layerThickness.isel(Time=0).sum(dim='nVertLevels').values
    assert_allclose(ds.thinFilmMask.values, [1, 1, 0])
    assert_allclose(column[:2], layer_thickness * level_count[:2])
    assert_allclose(ds.ssh.isel(Time=0).values[2], -100.0)
    assert_allclose(
        ds.ssh.isel(Time=0).values, -ds.bottomDepth.values + column
    )
    assert_allclose(ds.landIceDraft.values, ds.ssh.values)
