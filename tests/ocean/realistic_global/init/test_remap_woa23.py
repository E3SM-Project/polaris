import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.remap_woa23 import (
    RemapWoa23Step,
    _estimate_cell_count,
)


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


# -----------------------------------------------------------------------
# _estimate_cell_count
# -----------------------------------------------------------------------


def test_estimate_cell_count_icos_base_mesh():
    count = _estimate_cell_count('icos240km')
    # formula: 6e8 / 240**2 ≈ 10417
    assert count is not None
    assert count == pytest.approx(6e8 / 240**2, rel=1e-6)


def test_estimate_cell_count_qu_base_mesh():
    count = _estimate_cell_count('qu30km')
    # formula: 6e8 / 30**2 ≈ 666667
    assert count is not None
    assert count == pytest.approx(6e8 / 30**2, rel=1e-6)


def test_estimate_cell_count_unified_mesh_returns_int_or_none():
    """Unified meshes with approximate_cell_count set return a positive int."""
    count = _estimate_cell_count('u.oi240.lr240')
    assert count is not None
    assert count > 0


def test_estimate_cell_count_unknown_mesh():
    count = _estimate_cell_count('nonexistent_mesh_xyz')
    assert count is None
