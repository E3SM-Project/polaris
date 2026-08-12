import ast
import inspect
import logging

import numpy as np
import pytest
import xarray as xr
from geometric_features.aggregation import get_aggregator_by_name

from polaris.component import Component
from polaris.config import PolarisConfigParser
from polaris.tasks.mesh.spherical.feature_masks import (
    ComputeFeatureMasksStep,
)
from polaris.tasks.mesh.spherical.feature_masks import moc as moc_module
from polaris.tasks.mesh.spherical.feature_masks.moc import (
    MOC_MASK_GROUP,
    MOC_PREFIX,
    add_moc_transects,
    moc_masks_filename,
)

_TEST_LOGGER = logging.getLogger('test_moc')


def test_moc_masks_filename():
    filename = moc_masks_filename(mesh_name='QU240', date='20210623')

    assert filename == 'QU240_mocBasinsAndTransects20210623.nc'
    assert MOC_PREFIX in filename
    assert MOC_MASK_GROUP == 'MOC Basins'


def test_add_moc_transects_appends_transects(monkeypatch):
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
        moc_module,
        'add_moc_southern_boundary_transects',
        fake_add_transects,
    )

    result = add_moc_transects(ds_masks, ds_mesh, logger=_TEST_LOGGER)

    assert len(calls) == 1
    assert calls[0][0] is ds_masks
    assert calls[0][1] is ds_mesh
    assert 'transectEdgeMasks' in result


def test_add_moc_transects_drops_problematic_vars(monkeypatch):
    ds_mesh = xr.Dataset()
    ds_masks = xr.Dataset({'regionCellMasks': (('nCells',), np.ones(2))})
    ds_with_extras = ds_masks.copy()
    ds_with_extras['history'] = xr.DataArray('some history')
    ds_with_extras['constituents'] = xr.DataArray('some string')

    monkeypatch.setattr(
        moc_module,
        'add_moc_southern_boundary_transects',
        lambda ds, ds_mesh, logger=None: ds_with_extras,
    )

    result = add_moc_transects(ds_masks, ds_mesh, logger=_TEST_LOGGER)

    assert 'history' not in result
    assert 'constituents' not in result
    assert 'regionCellMasks' in result


@pytest.mark.parametrize('present_var', ['history', 'constituents'])
def test_add_moc_transects_tolerates_missing_problematic_vars(
    monkeypatch, present_var
):
    ds_mesh = xr.Dataset()
    ds_masks = xr.Dataset({'regionCellMasks': (('nCells',), np.ones(2))})
    # only one of the two problematic vars is present
    ds_one_extra = ds_masks.copy()
    ds_one_extra[present_var] = xr.DataArray('value')

    monkeypatch.setattr(
        moc_module,
        'add_moc_southern_boundary_transects',
        lambda ds, ds_mesh, logger=None: ds_one_extra,
    )

    result = add_moc_transects(ds_masks, ds_mesh, logger=_TEST_LOGGER)

    assert present_var not in result
    assert 'regionCellMasks' in result


def test_moc_module_does_not_depend_on_the_ocean_packages():
    # the leaf-module property that lets other components reuse the helpers;
    # importing polaris.tasks anything pulls in every component, so check the
    # module's own imports rather than sys.modules
    tree = ast.parse(inspect.getsource(moc_module))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    forbidden = [
        name
        for name in imported
        if name == 'polaris.ocean'
        or name.startswith('polaris.ocean.')
        or name == 'polaris.tasks.ocean'
        or name.startswith('polaris.tasks.ocean.')
    ]

    assert forbidden == []


def test_moc_helpers_work_without_an_ocean_config_section(tmp_path):
    # a step in another component, whose config has no [ocean] section, can
    # subclass the model-neutral step and reuse the MOC helpers
    mesh_filename = tmp_path / 'mesh.nc'
    mesh_filename.touch()

    component = Component(name='e3sm/init')
    config = PolarisConfigParser()
    config.add_from_package(
        'polaris.tasks.mesh.spherical.feature_masks',
        'feature_masks.cfg',
    )
    config.set('feature_masks', 'mesh_filename', str(mesh_filename))
    config.set('feature_masks', 'mesh_name', 'QU240')
    config.set('feature_masks', 'mask_group', MOC_MASK_GROUP)
    config.set('feature_masks', 'cpus_per_task', '1')
    config.set('feature_masks', 'min_cpus_per_task', '1')

    step = _MocMasksStep(
        component=component,
        subdir='moc_masks',
    )
    step.config = config

    step.setup()

    assert not config.has_section('ocean')
    _, _, date = get_aggregator_by_name(MOC_MASK_GROUP)
    assert step.output_filename == moc_masks_filename('QU240', date)
    assert step.output_filename in step.outputs


class _MocMasksStep(ComputeFeatureMasksStep):
    """
    A stand-in for a MOC mask step in a component other than the ocean.
    """

    def _set_output_filenames(self, mesh_name, mask_group):
        super()._set_output_filenames(mesh_name, mask_group)
        _, _, date = get_aggregator_by_name(mask_group)
        self.output_filename = moc_masks_filename(mesh_name, date)

    def _post_process_masks(self, ds_masks, ds_mesh, mask_group):
        return add_moc_transects(ds_masks, ds_mesh, logger=self.logger)
