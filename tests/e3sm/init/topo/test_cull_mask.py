import logging

import numpy as np
import xarray as xr

from polaris.tasks.e3sm.init.topo.cull.mask import CullMaskStep


def test_antarctic_land_ice_ownership_includes_southern_non_ocean_cells():
    ds_topo = _topo_dataset(
        ocean_frac=[1.0, 0.0, 0.0],
        land_frac=[0.0, 1.0, 1.0],
        ice_frac=[0.2, 0.0, 0.0],
        grounded_mask=[0.0, 0.0, 0.0],
        base_elevation=[-100.0, 100.0, 100.0],
    )
    ocean_cull_mask = xr.DataArray([False, True, True], dims=('nCells',))
    lat_cell = xr.DataArray([-80.0, -75.0, -40.0], dims=('nCells',))

    land_ice = CullMaskStep._antarctic_land_ice_ownership(
        ds_topo=ds_topo,
        ocean_cull_mask=ocean_cull_mask,
        lat_cell=lat_cell,
        land_ice_max_latitude=-60.0,
        land_ice_min_fraction=0.01,
    )

    np.testing.assert_array_equal(land_ice.values, [True, True, False])


def test_apply_critical_transects_without_transect_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    step = _cull_mask_step()

    cull_mask = xr.DataArray([True, True, False, False], dims=('nCells',))
    result = step._apply_critical_transects(
        cull_mask=cull_mask, mask_name='test mask'
    )

    np.testing.assert_array_equal(result.values, [True, True, False, False])


def test_apply_critical_transects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_transect_mask('critical_land_transects_mask.nc', [0, 0, 1, 0])
    _write_transect_mask('critical_ocean_transects_mask.nc', [1, 0, 0, 1])
    step = _cull_mask_step()

    # cells 0 and 1 are culled from the ocean, cells 2 and 3 are kept
    cull_mask = xr.DataArray([True, True, False, False], dims=('nCells',))
    result = step._apply_critical_transects(
        cull_mask=cull_mask, mask_name='test mask'
    )

    # cell 0 is rescued by an ocean passage, cell 2 is culled by a land
    # blockage, and cell 3 was already kept
    np.testing.assert_array_equal(result.values, [False, True, True, False])


def test_apply_critical_transects_cannot_add_cells_missing_from_ocean(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _write_transect_mask('critical_ocean_transects_mask.nc', [1, 1, 0, 0])
    step = _cull_mask_step()

    # the ocean itself does not retain cell 1, so the passage must not add
    # it back to the ocean without ice-shelf cavities
    ocean_cull_mask = xr.DataArray([False, True, True, True], dims=('nCells',))
    cull_mask = xr.DataArray([True, True, True, False], dims=('nCells',))
    result = step._apply_critical_transects(
        cull_mask=cull_mask,
        mask_name='test mask',
        ocean_cull_mask=ocean_cull_mask,
    )

    np.testing.assert_array_equal(result.values, [False, True, True, False])


def _cull_mask_step():
    step = CullMaskStep.__new__(CullMaskStep)
    step.logger = logging.getLogger('test_cull_mask')
    return step


def _write_transect_mask(filename, cell_mask):
    ds = xr.Dataset()
    ds['regionCellMasks'] = xr.DataArray(
        np.asarray(cell_mask, dtype=np.int32).reshape(-1, 1),
        dims=('nCells', 'nRegions'),
    )
    ds.to_netcdf(filename)


def _topo_dataset(
    ocean_frac,
    land_frac,
    ice_frac,
    grounded_mask,
    base_elevation,
):
    return xr.Dataset(
        data_vars=dict(
            ocean_frac=('nCells', np.asarray(ocean_frac, dtype=float)),
            land_frac=('nCells', np.asarray(land_frac, dtype=float)),
            ice_frac=('nCells', np.asarray(ice_frac, dtype=float)),
            grounded_mask=(
                'nCells',
                np.asarray(grounded_mask, dtype=float),
            ),
            base_elevation=(
                'nCells',
                np.asarray(base_elevation, dtype=float),
            ),
        )
    )
