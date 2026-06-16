import os
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr
from geometric_features import FeatureCollection

from polaris.component import Component
from polaris.config import PolarisConfigParser
from polaris.step import Step
from polaris.tasks.mesh.spherical.feature_masks import (
    ComputeFeatureMasksStep,
)
from polaris.tasks.mesh.spherical.feature_masks import (
    compute as compute_module,
)
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    compute_feature_masks,
    get_feature_masks_filename,
    get_feature_object_type,
    get_mask_types,
)
from polaris.tasks.mesh.spherical.feature_masks.steps import (
    get_feature_mask_steps,
)


def test_get_feature_object_type_region():
    fc_mask = _feature_collection('region')

    assert get_feature_object_type(fc_mask) == 'region'


def test_get_feature_object_type_transect():
    fc_mask = _feature_collection('transect')

    assert get_feature_object_type(fc_mask) == 'transect'


def test_get_feature_object_type_mixed_raises():
    fc_mask = FeatureCollection()
    fc_mask.add_feature(_feature('region', 'Region', _polygon()))
    fc_mask.add_feature(
        _feature('transect', 'Transect', _line_string(), component='ocean')
    )

    with pytest.raises(ValueError, match='single object type'):
        get_feature_object_type(fc_mask)


def test_get_mask_types_defaults():
    assert get_mask_types('default', 'region') == ('cell', 'vertex')
    assert get_mask_types('default', 'transect') == (
        'cell',
        'edge',
        'vertex',
    )


def test_get_mask_types_validates():
    with pytest.raises(ValueError, match='Invalid mask type'):
        get_mask_types('cell bad', 'region')


def test_compute_feature_masks_rejects_region_edge_sign():
    fc_mask = _feature_collection('region')
    ds_mesh = xr.Dataset()

    with pytest.raises(ValueError, match='only valid for transect'):
        compute_feature_masks(
            ds_mesh=ds_mesh,
            fc_mask=fc_mask,
            feature_object_type='region',
            mask_types=('cell',),
            logger=None,
            pool=None,
            chunk_size=1000,
            show_progress=False,
            subdivision_threshold=30.0,
            subdivision_resolution=None,
            add_edge_sign=True,
        )


def test_compute_feature_masks_rejects_transect_edge_sign_without_edge():
    fc_mask = _feature_collection('transect')
    ds_mesh = xr.Dataset()

    with pytest.raises(ValueError, match='requires edge'):
        compute_feature_masks(
            ds_mesh=ds_mesh,
            fc_mask=fc_mask,
            feature_object_type='transect',
            mask_types=('cell',),
            logger=None,
            pool=None,
            chunk_size=1000,
            show_progress=False,
            subdivision_threshold=30.0,
            subdivision_resolution=None,
            add_edge_sign=True,
        )


def test_feature_masks_filename():
    filename = get_feature_masks_filename(
        mesh_name='QU240', prefix='oceanBasins', date='20240830'
    )

    assert filename == 'QU240_oceanBasins20240830.nc'


def test_get_feature_mask_steps_sets_shared_config():
    component = Component(name='mesh')
    mesh_step = Step(
        component=component,
        name='base_mesh',
        subdir='spherical/qu/base_mesh/240km',
    )

    steps, config = get_feature_mask_steps(
        mesh_name='QU240',
        mask_group='Ocean Basins',
        mesh_step=mesh_step,
        mesh_filename='base_mesh.nc',
        component=component,
    )

    step = steps['feature_masks']
    assert isinstance(step, ComputeFeatureMasksStep)
    assert step.mesh_step is mesh_step
    assert step.mesh_filename == 'base_mesh.nc'
    assert config.get('feature_masks', 'mesh_name') == 'QU240'
    assert config.get('feature_masks', 'mask_group') == 'Ocean Basins'
    assert config.get('feature_masks', 'mesh_filename') == 'base_mesh.nc'
    assert step.subdir == (
        'spherical/feature_masks/QU240/oceanBasins20240830/compute'
    )


def test_step_setup_configurable_input(tmp_path):
    mesh_filename = tmp_path / 'mesh.nc'
    mesh_filename.touch()
    step = _configured_step(mesh_filename=str(mesh_filename))

    step.setup()

    assert step.input_data[0]['filename'] == 'mesh.nc'
    assert step.input_data[0]['target'] == str(mesh_filename)
    assert 'QU240_oceanBasins20240830.nc' in step.outputs
    assert 'oceanBasins20240830.geojson' in step.outputs
    assert step.cpus_per_task == 1
    assert step.min_cpus_per_task == 1


def test_step_setup_allows_missing_configurable_options():
    component = Component(name='mesh')
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.mesh.spherical.feature_masks',
        'feature_masks.cfg',
    )
    config.set('feature_masks', 'cpus_per_task', '1')
    config.set('feature_masks', 'min_cpus_per_task', '1')
    step = ComputeFeatureMasksStep(
        component=component,
        subdir='spherical/feature_masks/configurable/compute',
    )
    step.config = config

    step.setup()

    assert step.input_data == []
    assert step.outputs == []
    assert step.cpus_per_task == 1
    assert step.min_cpus_per_task == 1


def test_step_runtime_setup_requires_configurable_options(tmp_path):
    step = _missing_config_step(tmp_path)

    with pytest.raises(
        ValueError, match=r'\[feature_masks\] mesh_filename must be provided'
    ):
        step.runtime_setup()


def test_step_runtime_setup_updates_outputs(tmp_path):
    step = _missing_config_step(tmp_path)
    step.config.set('feature_masks', 'mesh_filename', 'mesh.nc')
    step.config.set('feature_masks', 'mesh_name', 'QU240')

    step.runtime_setup()

    assert step.output_filename == 'QU240_oceanBasins20240830.nc'
    assert step.geojson_filename == 'oceanBasins20240830.geojson'
    assert step.outputs == [
        os.path.join(str(tmp_path), 'QU240_oceanBasins20240830.nc'),
        os.path.join(str(tmp_path), 'oceanBasins20240830.geojson'),
    ]


def test_step_setup_shared_mesh_input():
    component = Component(name='mesh')
    mesh_step = Step(
        component=component,
        name='base_mesh',
        subdir='spherical/qu/base_mesh/240km',
    )
    step = _configured_step(
        component=component,
        mesh_step=mesh_step,
        mesh_filename='base_mesh.nc',
    )

    step.setup()

    assert step.input_data[0]['work_dir_target'] == os.path.join(
        mesh_step.path, 'base_mesh.nc'
    )


def test_step_run_writes_masks_and_geojson(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xr.Dataset(
        coords={'nCells': np.arange(1)},
        data_vars={
            'lonCell': ('nCells', np.array([0.0])),
            'latCell': ('nCells', np.array([0.0])),
        },
    ).to_netcdf('source_mesh.nc')

    fc_mask = _feature_collection('region')

    def build_mask_feature_collection(mask_group):
        assert mask_group == 'Ocean Basins'
        return fc_mask, 'oceanBasins', '20240830'

    def create_mask_pool(process_count, method):
        assert process_count == 1
        assert method == 'forkserver'
        return None

    def fake_compute_feature_masks(**kwargs):
        assert kwargs['feature_object_type'] == 'region'
        assert kwargs['mask_types'] == ('cell', 'vertex')
        return xr.Dataset(
            data_vars={
                'regionCellMasks': (
                    ('nCells', 'nRegions'),
                    np.ones((1, 1), dtype=np.int32),
                ),
                'regionNames': ('nRegions', ['Test Region']),
            }
        )

    monkeypatch.setattr(
        compute_module,
        'build_mask_feature_collection',
        build_mask_feature_collection,
    )
    monkeypatch.setattr(compute_module, 'create_mask_pool', create_mask_pool)
    monkeypatch.setattr(
        compute_module,
        'compute_feature_masks',
        fake_compute_feature_masks,
    )

    step = _configured_step(mesh_filename='source_mesh.nc')
    step.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    step.cpus_per_task = 1
    step.run()

    assert os.path.exists('QU240_oceanBasins20240830.nc')
    assert os.path.exists('oceanBasins20240830.geojson')
    ds_masks = xr.open_dataset('QU240_oceanBasins20240830.nc')
    assert ds_masks.attrs['mesh_name'] == 'QU240'
    assert ds_masks.attrs['mask_group'] == 'Ocean Basins'
    assert ds_masks.attrs['feature_object_type'] == 'region'
    assert ds_masks.attrs['source_mesh_filename'] == 'source_mesh.nc'
    assert 'regionCellMasks' in ds_masks


def _configured_step(
    component=None,
    mesh_step=None,
    mesh_filename=None,
):
    if component is None:
        component = Component(name='mesh')
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.mesh.spherical.feature_masks',
        'feature_masks.cfg',
    )
    config.set('feature_masks', 'mesh_filename', mesh_filename)
    config.set('feature_masks', 'mesh_name', 'QU240')
    config.set('feature_masks', 'mask_group', 'Ocean Basins')
    config.set('feature_masks', 'cpus_per_task', '1')
    config.set('feature_masks', 'min_cpus_per_task', '1')
    step = ComputeFeatureMasksStep(
        component=component,
        subdir='spherical/feature_masks/configurable/compute',
        mesh_step=mesh_step,
        mesh_filename=mesh_filename if mesh_step is not None else None,
    )
    step.config = config
    return step


def _missing_config_step(work_dir):
    component = Component(name='mesh')
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.mesh.spherical.feature_masks',
        'feature_masks.cfg',
    )
    config.set('feature_masks', 'cpus_per_task', '1')
    config.set('feature_masks', 'min_cpus_per_task', '1')
    step = ComputeFeatureMasksStep(
        component=component,
        subdir='spherical/feature_masks/configurable/compute',
    )
    step.config = config
    step.work_dir = str(work_dir)
    return step


def _feature_collection(object_type):
    geometry = _polygon() if object_type == 'region' else _line_string()
    fc_mask = FeatureCollection()
    fc_mask.add_feature(_feature(object_type, 'Test Feature', geometry))
    return fc_mask


def _feature(object_type, name, geometry, component='ocean'):
    return {
        'type': 'Feature',
        'properties': {
            'name': name,
            'tags': '',
            'object': object_type,
            'component': component,
            'author': 'Polaris',
        },
        'geometry': geometry,
    }


def _polygon():
    return {
        'type': 'Polygon',
        'coordinates': [
            [
                [-1.0, -1.0],
                [1.0, -1.0],
                [1.0, 1.0],
                [-1.0, 1.0],
                [-1.0, -1.0],
            ]
        ],
    }


def _line_string():
    return {
        'type': 'LineString',
        'coordinates': [[-1.0, 0.0], [1.0, 0.0]],
    }
