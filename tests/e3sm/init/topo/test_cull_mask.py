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
