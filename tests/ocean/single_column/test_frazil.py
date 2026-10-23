import logging

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.eos.linear import compute_linear_ct_freezing
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.single_column.frazil import Frazil
from polaris.tasks.ocean.single_column.frazil.melting_short import (
    FrazilMeltingShort,
)
from polaris.tasks.ocean.single_column.frazil.one_layer import FrazilOneLayer


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
@pytest.mark.parametrize('case', ['freezing', 'melting', 'one_layer', 'short'])
def test_frazil_eos(model, case, monkeypatch):
    task = _make_task(model, case)
    expected = 'linear' if model == 'mpas-ocean' else 'teos-10'
    assert task.config.get('ocean', 'eos_type') == expected

    # Isolate the single-column overrides from mesh and stream setup.
    monkeypatch.setattr(
        OceanModelStep, 'dynamic_model_config', lambda self, at_setup: None
    )
    for step in task._frazil_type_steps.values():
        assert step.update_eos
        step.config = task.config
        step.update_namelist_eos()
        step.dynamic_model_config(at_setup=True)
        eos_types = [
            entry['options']['config_eos_type']
            for entry in step.model_config_data
            if 'options' in entry and 'config_eos_type' in entry['options']
        ]
        assert eos_types
        assert all(eos == expected for eos in eos_types)


@pytest.mark.parametrize('dsdz', [0.01, 0.0, -0.01])
def test_freezing_temperature_is_uniform_above_freezing(dsdz):
    task = _make_task('mpas-ocean', 'freezing')
    task.config.set('single_column_frazil', 'dsdz', str(dsdz))
    temperature, salinity = _initial_tracers(task)
    freezing = compute_linear_ct_freezing(salinity)
    offset = task.config.getfloat(
        'single_column_frazil', 'temperature_above_freezing'
    )
    np.testing.assert_allclose(
        temperature, float(np.max(freezing)) + offset, rtol=0.0, atol=1e-14
    )
    assert bool((temperature > freezing).all())
    assert float((temperature - freezing).min()) == pytest.approx(offset)


def test_omega_freezing_temperature_is_unchanged():
    task = _make_task('omega', 'freezing')
    temperature, _ = _initial_tracers(task)
    np.testing.assert_allclose(
        temperature,
        task.config.getfloat('single_column_frazil', 'temperature_freezing'),
    )


def test_one_layer_still_starts_at_freezing():
    task = _make_task('mpas-ocean', 'one_layer')
    temperature, salinity = _initial_tracers(task)
    np.testing.assert_allclose(
        temperature, compute_linear_ct_freezing(salinity)
    )


def test_short_bottom_layer_still_starts_supercooled():
    task = _make_task('mpas-ocean', 'short')
    temperature, salinity = _initial_tracers(task)
    supercooling = task.config.getfloat(
        'single_column_frazil_melting', 'supercooling_delta_temperature'
    )
    np.testing.assert_allclose(
        temperature.isel(nVertLevels=-1),
        compute_linear_ct_freezing(salinity.isel(nVertLevels=-1))
        - supercooling,
    )


@pytest.mark.parametrize('offset', ['0.0', '-0.001', 'nan', 'inf'])
def test_invalid_freezing_temperature_offset(offset):
    task = _make_task('mpas-ocean', 'freezing')
    task.config.set(
        'single_column_frazil', 'temperature_above_freezing', offset
    )
    with pytest.raises(ValueError, match='finite and positive'):
        _initial_tracers(task)


def _make_task(model, case):
    component = Ocean()
    component.model = model
    subdir = f'column/frazil/{case}'
    task: Frazil | FrazilOneLayer | FrazilMeltingShort
    if case == 'one_layer':
        task = FrazilOneLayer(component, subdir)
    elif case == 'short':
        task = FrazilMeltingShort(component, subdir, 'short', 'warm.cfg')
    else:
        task = Frazil(component, subdir, case)
    task.config.set('ocean', 'model', model)
    task.configure()
    return task


def _initial_tracers(task):
    step = task.steps['init']
    step.logger = logging.getLogger('frazil_init')
    ds = xr.Dataset(
        {
            'refZMid': ('nVertLevels', [-2.0, -6.0, -10.0]),
            'layerThickness': (
                ('Time', 'nCells', 'nVertLevels'),
                np.full((1, 2, 3), 4.0),
            ),
        }
    )
    x_cell = xr.DataArray([0.0, 1.0], dims='nCells')
    return step._compute_temperature_salinity(task.config, ds, x_cell)
