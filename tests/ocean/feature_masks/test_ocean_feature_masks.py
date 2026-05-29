import logging

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.feature_masks import ComputeOceanFeatureMasksStep
from polaris.tasks.ocean.feature_masks import compute as ocean_compute_module

_TEST_LOGGER = logging.getLogger('test_ocean_feature_masks')


def test_ocean_feature_masks_step_is_ocean_io_step():
    from polaris.ocean.model.ocean_io_step import OceanIOStep

    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )

    assert isinstance(step, OceanIOStep)


def test_ocean_feature_masks_opens_omega_mesh(tmp_path):
    filename = tmp_path / 'omega_mesh.nc'
    xr.Dataset(
        coords={'NCells': np.arange(2)},
        data_vars={
            'LatCell': ('NCells', np.array([0.0, 1.0])),
            'LonCell': ('NCells', np.array([0.0, 1.0])),
        },
    ).to_netcdf(filename)

    component = Ocean()
    component.model = 'omega'
    component.mpaso_to_omega_dim_map = {'nCells': 'NCells'}
    component.mpaso_to_omega_var_map = {
        'latCell': 'LatCell',
        'lonCell': 'LonCell',
    }
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )

    ds_mesh = step._open_mesh_dataset(filename)

    assert 'nCells' in ds_mesh.dims
    assert 'latCell' in ds_mesh
    assert 'lonCell' in ds_mesh


def test_ocean_feature_masks_writes_omega_mask(tmp_path):
    filename = tmp_path / 'omega_mask.nc'
    component = Ocean()
    component.model = 'omega'
    component.mpaso_to_omega_dim_map = {
        'nCells': 'NCells',
        'nRegions': 'NRegions',
    }
    component.mpaso_to_omega_var_map = {
        'regionCellMasks': 'RegionCellMasks',
        'regionNames': 'RegionNames',
    }
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )
    ds_masks = xr.Dataset(
        data_vars={
            'regionCellMasks': (
                ('nCells', 'nRegions'),
                np.ones((2, 1), dtype=np.int32),
            ),
            'regionNames': ('nRegions', ['Test Region']),
        }
    )

    step._write_mask_dataset(ds_masks, filename)

    ds_native = xr.open_dataset(filename)
    assert 'NCells' in ds_native.dims
    assert 'NRegions' in ds_native.dims
    assert 'RegionCellMasks' in ds_native
    assert 'RegionNames' in ds_native


def test_set_output_filenames_moc_basins():
    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )

    step._set_output_filenames(mesh_name='QU240', mask_group='MOC Basins')

    assert step.output_filename is not None
    assert step.geojson_filename is not None
    assert 'mocBasinsAndTransects' in step.output_filename
    assert step.output_filename.startswith('QU240_mocBasinsAndTransects')
    assert step.output_filename.endswith('.nc')
    assert step.geojson_filename.startswith('mocBasins')
    assert 'AndTransects' not in step.geojson_filename


def test_set_output_filenames_non_moc_uses_normal_naming():
    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )

    step._set_output_filenames(mesh_name='QU240', mask_group='Ocean Basins')

    assert step.output_filename is not None
    assert 'mocBasinsAndTransects' not in step.output_filename
    assert step.output_filename.startswith('QU240_oceanBasins')


def test_post_process_masks_moc_calls_transects(monkeypatch):
    ds_mesh = xr.Dataset({'nCells': np.arange(2)})
    ds_masks = xr.Dataset(
        {'regionCellMasks': (('nCells', 'nRegions'), np.ones((2, 1)))}
    )
    ds_combined = ds_masks.copy()
    ds_combined['transectEdgeMasks'] = (
        ('nEdges', 'nTransects'),
        np.ones((3, 1)),
    )

    calls = []

    def fake_add_transects(ds_mask, ds_mesh_arg, logger=None):
        calls.append((ds_mask, ds_mesh_arg))
        return ds_combined

    monkeypatch.setattr(
        ocean_compute_module,
        'add_moc_southern_boundary_transects',
        fake_add_transects,
    )

    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )
    step.logger = _TEST_LOGGER

    result = step._post_process_masks(ds_masks, ds_mesh, 'MOC Basins')

    assert len(calls) == 1
    assert 'transectEdgeMasks' in result


def test_post_process_masks_drops_problematic_vars(monkeypatch):
    ds_mesh = xr.Dataset()
    ds_masks = xr.Dataset({'regionCellMasks': (('nCells',), np.ones(2))})
    ds_with_extras = ds_masks.copy()
    ds_with_extras['history'] = xr.DataArray('some history')
    ds_with_extras['constituents'] = xr.DataArray('some string')

    monkeypatch.setattr(
        ocean_compute_module,
        'add_moc_southern_boundary_transects',
        lambda ds, ds_mesh, logger=None: ds_with_extras,
    )

    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )
    step.logger = _TEST_LOGGER

    result = step._post_process_masks(ds_masks, ds_mesh, 'MOC Basins')

    assert 'history' not in result
    assert 'constituents' not in result
    assert 'regionCellMasks' in result


def test_post_process_masks_non_moc_is_noop(monkeypatch):
    called = []
    monkeypatch.setattr(
        ocean_compute_module,
        'add_moc_southern_boundary_transects',
        lambda *a, **kw: called.append(True),
    )

    ds_mesh = xr.Dataset()
    ds_masks = xr.Dataset({'regionCellMasks': (('nCells',), np.ones(2))})

    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )
    step.logger = _TEST_LOGGER

    result = step._post_process_masks(ds_masks, ds_mesh, 'Ocean Basins')

    assert called == []
    assert result is ds_masks


@pytest.mark.parametrize('missing_var', ['history', 'constituents'])
def test_post_process_masks_tolerates_missing_problematic_vars(
    monkeypatch, missing_var
):
    ds_mesh = xr.Dataset()
    ds_masks = xr.Dataset({'regionCellMasks': (('nCells',), np.ones(2))})
    # only one of the two problematic vars is present
    ds_one_extra = ds_masks.copy()
    ds_one_extra[missing_var] = xr.DataArray('value')

    monkeypatch.setattr(
        ocean_compute_module,
        'add_moc_southern_boundary_transects',
        lambda ds, ds_mesh, logger=None: ds_one_extra,
    )

    component = Ocean()
    step = ComputeOceanFeatureMasksStep(
        component=component,
        subdir='feature_masks/configurable/compute',
    )
    step.logger = _TEST_LOGGER

    result = step._post_process_masks(ds_masks, ds_mesh, 'MOC Basins')

    assert missing_var not in result
