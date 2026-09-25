"""
Tests for building the WOA23 product for a configured month.
"""

import os

import numpy as np
import pytest
import xarray as xr

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
    get_woa23_topography_step,
)


@pytest.mark.parametrize('month', [0, 13])
def test_month_outside_1_to_12_is_rejected(month):
    _, steps = _get_steps(month)

    with pytest.raises(ValueError, match='between 1 and 12'):
        get_woa23_month(steps['combine'].config)


def test_month_abbreviations():
    assert get_month_abbreviation(1) == 'jan'
    assert get_month_abbreviation(10) == 'oct'
    assert get_month_abbreviation(12) == 'dec'


def test_combine_reads_the_configured_month():
    _, steps = _get_steps(10)
    step = steps['combine']

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
    combine_step = steps['combine']
    extrapolate_step = steps['extrapolate']
    viz_step = steps['viz']

    extrapolate_step.setup()
    viz_step.setup()

    assert _work_dir_targets(extrapolate_step)['woa.nc'] == (
        f'{combine_step.path}/woa_combined_oct.nc'
    )
    assert extrapolate_step.outputs == ['woa23_decav_0.25_oct_extrap.nc']
    assert _work_dir_targets(viz_step)['woa.nc'] == (
        f'{extrapolate_step.path}/woa23_decav_0.25_oct_extrap.nc'
    )


@pytest.mark.parametrize('step_name', ['combine', 'extrapolate'])
def test_january_is_in_the_cache(step_name):
    component, steps = _get_steps(1)
    step = steps[step_name]

    step.setup()

    for output in step.outputs:
        assert os.path.join(step.path, output) in component.cached_files


def test_cached_step_for_a_month_without_an_entry_fails(tmp_path):
    component, steps = _get_steps(10)
    step = steps['extrapolate']
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
    step = steps['extrapolate']
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
    steps, config = get_woa23_steps(
        component=component, combine_topo_step=get_woa23_topography_step()
    )
    config.set('woa23', 'month', str(month))
    return component, steps


def _work_dir_targets(step):
    return {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    }
