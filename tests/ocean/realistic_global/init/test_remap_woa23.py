import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.remap_woa23 import (
    RemapWoa23Step,
)
from polaris.tasks.ocean.realistic_global.init.woa23_map import Woa23MapStep


class _FakeComponent:
    name = 'ocean'


class _FakeStep:
    path = 'fake/step'


def _make_steps(mesh_name='icos240km'):
    map_step = Woa23MapStep(
        component=_FakeComponent(),
        subdir=f'{mesh_name}/woa23_map',
        extrapolate_step=_FakeStep(),
        cull_mesh_step=_FakeStep(),
        mesh_name=mesh_name,
    )
    remap_step = RemapWoa23Step(
        component=_FakeComponent(),
        subdir=f'{mesh_name}/remap_woa23',
        extrapolate_step=_FakeStep(),
        woa23_map_step=map_step,
    )
    return map_step, remap_step


def test_remap_step_is_serial():
    """
    The MPI work lives in the map step; ncremap here runs in serial.
    """
    _, remap_step = _make_steps()
    assert remap_step.ntasks == 1
    assert remap_step.min_tasks == 1


def test_remap_step_depends_on_map_step():
    """
    The remapper is fetched through the dependency mechanism so that it is
    resolved only after the map step has run.
    """
    map_step, remap_step = _make_steps()
    assert remap_step.dependencies['woa23_map'] is map_step


def test_remap_step_output():
    _, remap_step = _make_steps()
    assert 'woa23_on_mesh.nc' in remap_step.outputs[0]


def _make_raw_ncremap_output(ncol=4, ndepth=3):
    """Return a synthetic dataset resembling raw ncremap output."""
    depths = np.linspace(0.0, 1000.0, ndepth)
    ct_data = np.arange(ncol * ndepth, dtype=float).reshape(ndepth, ncol)
    sa_data = ct_data + 34.0
    return xr.Dataset(
        data_vars={
            'ct_an': (('depth', 'ncol'), ct_data),
            'sa_an': (('depth', 'ncol'), sa_data),
        },
        coords={
            'depth': ('depth', depths),
        },
    )


def test_postprocess_renames_ncol_to_ncells():
    ds_raw = _make_raw_ncremap_output(ncol=4, ndepth=3)
    ds_out = RemapWoa23Step._postprocess_remapped_output(ds_raw)
    assert 'nCells' in ds_out.dims
    assert 'ncol' not in ds_out.dims


def test_postprocess_keeps_only_ct_sa():
    ds_raw = _make_raw_ncremap_output(ncol=4, ndepth=3)
    ds_raw['extra_var'] = xr.DataArray(
        np.zeros((3, 4)), dims=('depth', 'ncol')
    )
    ds_out = RemapWoa23Step._postprocess_remapped_output(ds_raw)
    assert set(ds_out.data_vars) == {'ct_an', 'sa_an'}


def test_postprocess_preserves_depth_coordinate():
    ds_raw = _make_raw_ncremap_output(ncol=4, ndepth=3)
    ds_out = RemapWoa23Step._postprocess_remapped_output(ds_raw)
    assert 'depth' in ds_out.coords
    assert ds_out.coords['depth'].values == pytest.approx([0.0, 500.0, 1000.0])


def test_postprocess_output_shape():
    ncol, ndepth = 6, 5
    ds_raw = _make_raw_ncremap_output(ncol=ncol, ndepth=ndepth)
    ds_out = RemapWoa23Step._postprocess_remapped_output(ds_raw)
    assert ds_out['ct_an'].shape == (ndepth, ncol)
    assert ds_out['sa_an'].shape == (ndepth, ncol)


def test_postprocess_no_ncol_passthrough():
    """If the input already has nCells (not ncol), it should pass through."""
    depths = np.array([0.0, 200.0])
    ds = xr.Dataset(
        data_vars={
            'ct_an': (('depth', 'nCells'), np.ones((2, 3))),
            'sa_an': (('depth', 'nCells'), np.ones((2, 3)) * 34.5),
        },
        coords={'depth': ('depth', depths)},
    )
    ds_out = RemapWoa23Step._postprocess_remapped_output(ds)
    assert 'nCells' in ds_out.dims
    assert 'ncol' not in ds_out.dims
    assert ds_out['ct_an'].shape == (2, 3)
