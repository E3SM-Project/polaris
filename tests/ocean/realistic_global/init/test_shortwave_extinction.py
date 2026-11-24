from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.init.jra55_map import Jra55MapStep
from polaris.tasks.ocean.realistic_global.init.remap_jra55 import (
    check_no_missing_cells,
)
from polaris.tasks.ocean.realistic_global.init.remap_shortwave_extinction import (  # noqa: E501
    EXTINCTION_VAR_NAMES,
    OMEGA_VAR_NAMES,
    SHORTWAVE_EXTINCTION_COEFFS_FILENAME,
    RemapShortwaveExtinctionStep,
    _normalize_coefficients,
)
from polaris.tasks.ocean.realistic_global.init.shortwave_extinction_map import (  # noqa: E501
    ShortwaveExtinctionMapStep,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)


class _FakeComponent:
    name = 'ocean'


class _FakeStep:
    path = 'fake/step'


def _get_init_config(mesh_name):
    config = PolarisConfigParser()
    config.add_from_package('polaris.remap', 'mapping.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.init',
        'init.cfg',
    )
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


def _make_map_step(mesh_name='icos240km'):
    step = ShortwaveExtinctionMapStep(
        component=_FakeComponent(),
        subdir=f'{mesh_name}/shortwave_extinction_map',
        cull_mesh_step=_FakeStep(),
        extinction_step=_FakeStep(),
        mesh_name=mesh_name,
    )
    step.config = _get_init_config(mesh_name)
    return step


@pytest.mark.parametrize('method', ['conserve', 'bilinear'])
def test_mapping_command_uses_configured_method(method, monkeypatch, tmp_path):
    step = _make_map_step()
    step.config.set('shortwave_extinction', 'method', method)
    step.config.set('mapping', 'map_tool', 'esmf')
    step.work_dir = str(tmp_path)
    monkeypatch.chdir(tmp_path)
    step.remapper.src_descriptor = SimpleNamespace(
        mesh_name='source', regional=False, to_scrip=lambda *args: None
    )
    step.remapper.dst_descriptor = SimpleNamespace(
        mesh_name='destination',
        regional=False,
        to_scrip=lambda *args, **kwargs: None,
    )

    step.runtime_setup()

    args = step.args[0]
    assert args[0] == 'ESMF_RegridWeightGen'
    assert args[args.index('--method') + 1] == method
    suffix = 'aave' if method == 'conserve' else 'bilin'
    assert step.remapper.map_filename.endswith(f'_esmf{suffix}.nc')


def test_unsupported_mapping_method_is_rejected():
    step = _make_map_step()
    step.config.set('shortwave_extinction', 'method', 'invalid')
    with pytest.raises(ValueError, match='Unsupported shortwave extinction'):
        step.runtime_setup()


def test_task_count_has_a_floor_from_the_source():
    """
    The 9.3 million cell source sets the cost of the weights, so even a
    coarse mesh gets many tasks rather than the one its size would suggest.
    """
    step = _make_map_step('icos240km')
    step._update_ntasks()
    section = step.config['shortwave_extinction']
    assert step.ntasks == section.getint('ntasks')
    assert step.min_tasks == section.getint('min_tasks')


def test_task_count_still_scales_with_a_large_mesh():
    step = _make_map_step('u-oi6to18-lr12p5')
    step._update_ntasks()
    section = step.config['shortwave_extinction']
    assert step.ntasks > section.getint('ntasks')
    assert step.min_tasks > section.getint('min_tasks')


def test_wind_stress_stays_bilinear():
    step = Jra55MapStep(
        component=_FakeComponent(),
        subdir='icos240km/jra55_map',
        stress_step=_FakeStep(),
        cull_mesh_step=_FakeStep(),
        mesh_name='icos240km',
    )
    assert step.remapper.method == 'bilinear'


def test_remap_output_keeps_only_the_coefficients_on_cells():
    ds_raw = xr.Dataset(
        {
            'ExtinctionCoeffRed': ('ncol', np.full(3, 0.23)),
            'ExtinctionCoeffBlue': ('ncol', np.full(3, 0.04)),
            'area': ('ncol', np.ones(3)),
        }
    )
    ds_out = RemapShortwaveExtinctionStep._postprocess_remapped_output(ds_raw)
    assert list(ds_out.data_vars) == EXTINCTION_VAR_NAMES
    assert ds_out.ExtinctionCoeffRed.dims == ('nCells',)


def test_remap_writes_omega_file_without_lat_lon(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ds = xr.Dataset(
        {var: ('ncol', np.full(3, 0.1)) for var in EXTINCTION_VAR_NAMES},
        coords={
            'lat': ('ncol', [-30.0, 0.0, 30.0]),
            'lon': ('ncol', [0.0, 90.0, 180.0]),
        },
    )
    ds.lat.attrs = {'units': 'degrees_north', 'bounds': 'lat_vertices'}
    ds.lon.attrs = {'units': 'degrees_east', 'bounds': 'lon_vertices'}
    ds.to_netcdf('shortwave_extinction_on_mesh_raw.nc')
    ds[EXTINCTION_VAR_NAMES].to_netcdf('shortwave_extinction.nc')
    xr.Dataset(
        {
            'frac_b': ('ncol', np.ones(3)),
            'yc_b': ('ncol', [-30.0, 0.0, 30.0]),
            'xc_b': ('ncol', [0.0, 90.0, 180.0]),
        }
    ).to_netcdf('map.nc')

    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    step = RemapShortwaveExtinctionStep(
        component=component,
        subdir='remap',
        extinction_map_step=_make_map_step(),
    )
    ncremap = Mock()
    step.dependencies['extinction_map'] = SimpleNamespace(
        remapper=SimpleNamespace(map_filename='map.nc', ncremap=ncremap)
    )
    step.config = _get_init_config('icos240km')
    step.run()
    assert ncremap.call_args.kwargs['overwrite'] is True

    # Omega's names, on its cell dimension, in the file its stream reads
    with xr.open_dataset(SHORTWAVE_EXTINCTION_COEFFS_FILENAME) as ds_out:
        assert ds_out.attrs['Conventions'] == 'CF-1.8'
        assert not {'lat', 'lon'} & set(ds_out.variables)
        for name in OMEGA_VAR_NAMES.values():
            assert ds_out[name].dims == ('NCells',)
            np.testing.assert_allclose(ds_out[name], 0.1)
        assert not set(EXTINCTION_VAR_NAMES) & set(ds_out)
    assert SHORTWAVE_EXTINCTION_COEFFS_FILENAME in step.cf_check_files


def _coefficients(n_cells):
    return xr.Dataset(
        {
            'ExtinctionCoeffRed': ('nCells', np.full(n_cells, 0.2)),
            'ExtinctionCoeffBlue': ('nCells', np.full(n_cells, 0.04)),
        }
    )


def test_coefficients_are_normalized_by_coverage():
    n_cells = 200
    frac_b = np.ones(n_cells)
    frac_b[0] = 0.999
    frac_b[1] = 1.00001
    ds = _coefficients(n_cells)
    ds['ExtinctionCoeffRed'][:2] *= frac_b[:2]
    out = _normalize_coefficients(ds, frac_b)
    np.testing.assert_allclose(out.ExtinctionCoeffRed, 0.2)


@pytest.mark.parametrize('frac_b_value', [0.0, 0.5, np.nan])
def test_poorly_covered_cell_fails(frac_b_value):
    frac_b = np.ones(200)
    frac_b[3] = frac_b_value
    with pytest.raises(ValueError, match='1 of 200 cells'):
        _normalize_coefficients(_coefficients(200), frac_b)


@pytest.mark.parametrize('bad_value', [-0.1, 0.0, np.nan])
def test_bad_coefficient_fails(bad_value):
    ds = _coefficients(200)
    ds['ExtinctionCoeffBlue'][5] = bad_value
    with pytest.raises(ValueError, match='1 of 200 cells'):
        _normalize_coefficients(ds, np.ones(200))


@pytest.mark.parametrize('coverage', [np.nan, np.inf, -np.inf])
def test_nonfinite_coverage_is_rejected(coverage):
    ds = xr.Dataset({var: ('nCells', [0.1]) for var in EXTINCTION_VAR_NAMES})
    with pytest.raises(ValueError, match='1 of 1 cells'):
        check_no_missing_cells(ds, EXTINCTION_VAR_NAMES, np.array([coverage]))
