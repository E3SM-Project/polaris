import numpy as np
import xarray as xr

from polaris.ocean.model.layer_indices import (
    layer_indices_from_omega,
    layer_indices_to_omega,
)
from polaris.tasks.ocean import Ocean

MIN_LEVEL_CELL = np.array([1, 1, 2], dtype=np.int32)
MAX_LEVEL_CELL = np.array([4, 3, 4], dtype=np.int32)


def _make_component():
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    return component


def _make_mpaso_ds():
    """MPAS-Ocean (one-based) layer indices for 3 cells with 4 levels"""
    ds = xr.Dataset()
    ds['minLevelCell'] = ('nCells', MIN_LEVEL_CELL)
    ds['maxLevelCell'] = ('nCells', MAX_LEVEL_CELL)
    ds.maxLevelCell.attrs['long_name'] = 'bottom level'
    return ds


def test_layer_indices_to_omega_are_zero_based():
    ds = layer_indices_to_omega(_make_mpaso_ds())
    np.testing.assert_array_equal(ds.minLevelCell, MIN_LEVEL_CELL - 1)
    np.testing.assert_array_equal(ds.maxLevelCell, MAX_LEVEL_CELL - 1)
    assert ds.maxLevelCell.dtype == np.int32
    assert ds.maxLevelCell.attrs['long_name'] == 'bottom level'


def test_layer_indices_from_omega_are_one_based():
    ds = _make_mpaso_ds().rename(
        {'minLevelCell': 'MinLayerCell', 'maxLevelCell': 'MaxLayerCell'}
    )
    ds = layer_indices_from_omega(ds)
    np.testing.assert_array_equal(ds.MinLayerCell, MIN_LEVEL_CELL + 1)
    np.testing.assert_array_equal(ds.MaxLayerCell, MAX_LEVEL_CELL + 1)


def test_layer_indices_without_index_vars_are_unchanged():
    ds = xr.Dataset({'bottomDepth': ('nCells', np.ones(3))})
    assert layer_indices_to_omega(ds).identical(ds)
    assert layer_indices_from_omega(ds).identical(ds)


def test_map_to_omega_makes_layer_indices_zero_based():
    """Mapping to Omega names also makes the indices zero-based, and
    mapping back restores the MPAS-Ocean names and one-based indices"""
    component = _make_component()
    ds_mpaso = _make_mpaso_ds()

    ds_omega = component.map_to_native_model_vars(ds_mpaso)
    np.testing.assert_array_equal(ds_omega.MinLayerCell, MIN_LEVEL_CELL - 1)
    np.testing.assert_array_equal(ds_omega.MaxLayerCell, MAX_LEVEL_CELL - 1)

    ds_back = component.map_from_native_model_vars(ds_omega)
    np.testing.assert_array_equal(ds_back.minLevelCell, MIN_LEVEL_CELL)
    np.testing.assert_array_equal(ds_back.maxLevelCell, MAX_LEVEL_CELL)

    # the input dataset is not modified in place
    np.testing.assert_array_equal(ds_mpaso.minLevelCell, MIN_LEVEL_CELL)
