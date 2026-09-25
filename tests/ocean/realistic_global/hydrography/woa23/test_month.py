"""
Tests for building the WOA23 product for a configured month.
"""

import os

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.hydrography.woa23 import (
    extrapolate,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23.month import (
    get_month_abbreviation,
    get_woa23_month,
)
from polaris.tasks.ocean.realistic_global.hydrography.woa23.steps import (
    get_woa23_steps,
)
from polaris.tasks.ocean.realistic_global.init.remap_woa23 import (
    RemapWoa23Step,
)
from polaris.tasks.ocean.realistic_global.init.woa23_map import Woa23MapStep
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)


@pytest.mark.parametrize('month', [0, 13])
def test_month_outside_1_to_12_is_rejected(month):
    _, steps = _get_steps(month)

    with pytest.raises(ValueError, match='between 1 and 12'):
        get_woa23_month(steps['woa23_combine'].config)


def test_month_abbreviations():
    assert get_month_abbreviation(1) == 'jan'
    assert get_month_abbreviation(10) == 'oct'
    assert get_month_abbreviation(12) == 'dec'


def test_combine_reads_the_configured_month():
    _, steps = _get_steps(10)
    step = steps['woa23_combine']

    step.setup()

    targets = {entry['filename']: entry['target'] for entry in step.input_data}
    assert targets == {
        'woa_temp_ann.nc': 'woa23_decav91C0_t00_04.nc',
        'woa_temp_oct.nc': 'woa23_decav91C0_t10_04.nc',
        'woa_salin_ann.nc': 'woa23_decav91C0_s00_04.nc',
        'woa_salin_oct.nc': 'woa23_decav91C0_s10_04.nc',
    }
    assert step.outputs == ['woa_combined_oct.nc']


def test_downstream_steps_use_the_month_in_filenames():
    _, steps = _get_steps(10)
    combine_step = steps['woa23_combine']
    extrapolate_step = steps['woa23_extrapolate']
    viz_step = steps['woa23_viz']

    extrapolate_step.setup()
    viz_step.setup()

    assert _work_dir_targets(extrapolate_step)['woa.nc'] == (
        f'{combine_step.path}/woa_combined_oct.nc'
    )
    assert extrapolate_step.outputs == ['woa23_decav_0.25_oct_extrap.nc']
    assert _work_dir_targets(viz_step)['woa.nc'] == (
        f'{extrapolate_step.path}/woa23_decav_0.25_oct_extrap.nc'
    )


def test_init_steps_use_the_month_in_filenames():
    component, steps = _get_steps(10)
    extrapolate_step = steps['woa23_extrapolate']
    expected = f'{extrapolate_step.path}/woa23_decav_0.25_oct_extrap.nc'

    map_step = Woa23MapStep(
        component=component,
        subdir='icos240km/woa23_map',
        extrapolate_step=extrapolate_step,
        cull_mesh_step=_FakeStep(),
        mesh_name='icos240km',
    )
    map_step.config = _get_init_config('icos240km')
    remap_step = RemapWoa23Step(
        component=component,
        subdir='icos240km/remap_woa23',
        extrapolate_step=extrapolate_step,
        woa23_map_step=map_step,
    )

    map_step.setup()
    remap_step.setup()

    assert _work_dir_targets(map_step)['woa23_extrap.nc'] == expected
    assert _work_dir_targets(remap_step)['woa23_extrap.nc'] == expected


@pytest.mark.parametrize('step_name', ['woa23_combine', 'woa23_extrapolate'])
def test_january_is_in_the_cache(step_name):
    component, steps = _get_steps(1)
    step = steps[step_name]

    step.setup()

    for output in step.outputs:
        assert os.path.join(step.path, output) in component.cached_files


def test_cached_step_for_a_month_without_an_entry_fails(tmp_path):
    component, steps = _get_steps(10)
    step = steps['woa23_extrapolate']
    # a cache with only January in it
    component.cached_files = {
        f'{step.path}/woa23_decav_0.25_jan_extrap.nc': 'jan.nc',
    }
    step.cached = True
    step.setup()
    step.work_dir = str(tmp_path)
    step.base_work_dir = str(tmp_path)

    with pytest.raises(ValueError, match='has not been added to the cache'):
        step.process_inputs_and_outputs()


def test_extrapolated_product_is_single_precision_with_month(
    tmp_path, monkeypatch
):
    _, steps = _get_steps(10)
    step = steps['woa23_extrapolate']
    monkeypatch.chdir(tmp_path)
    _write_dataset('woa_extrap.nc', dtype=np.float64)

    step._write_product(in_filename='woa_extrap.nc')

    with xr.open_dataset('woa23_decav_0.25_oct_extrap.nc') as ds:
        assert ds.ct_an.dtype == np.float32
        assert ds.sa_an.dtype == np.float32
        assert ds.attrs['month'] == 10


def test_extrapolation_loads_single_precision_as_double(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_dataset('woa.nc', dtype=np.float32)

    ds = extrapolate._load_in_double_precision('woa.nc')

    assert ds.ct_an.dtype == np.float64
    assert ds.sa_an.dtype == np.float64


def _write_dataset(filename, dtype):
    """Write a small WOA-like dataset with a missing value."""
    ct = np.array([[[1.0, np.nan], [3.0, 4.0]]], dtype=dtype)
    sa = np.array([[[34.0, np.nan], [35.0, 36.0]]], dtype=dtype)
    ds = xr.Dataset(
        data_vars={
            'ct_an': (('depth', 'lat', 'lon'), ct),
            'sa_an': (('depth', 'lat', 'lon'), sa),
        },
        coords={
            'depth': ('depth', np.array([0.0])),
            'lat': ('lat', np.array([-45.0, 10.0])),
            'lon': ('lon', np.array([20.0, 160.0])),
        },
    )
    ds.to_netcdf(filename)


def _get_steps(month):
    """Get the WOA23 steps with the month set in their shared config."""
    component = Ocean()
    steps, config = get_woa23_steps(component=component, include_viz=True)
    config.set('woa23', 'month', str(month))
    return component, steps


class _FakeStep:
    path = 'fake/step'


def _get_init_config(mesh_name):
    """Build the config of a realistic global init step."""
    config = PolarisConfigParser()
    config.add_from_package('polaris.remap', 'mapping.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


def _work_dir_targets(step):
    return {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    }
