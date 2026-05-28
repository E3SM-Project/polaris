import numpy as np
import xarray as xr

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.feature_masks import ComputeOceanFeatureMasksStep


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
