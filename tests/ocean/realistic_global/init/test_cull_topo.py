import numpy as np
import xarray as xr

from polaris.tasks.ocean.realistic_global.init.cull_topo import (
    cull_topography,
)


def test_cull_topography_carries_the_land_ice_mask():
    ds_topo = xr.Dataset(
        {
            'base_elevation': ('nCells', [-100.0, -200.0, 50.0, -300.0]),
            'ice_thickness': ('nCells', [0.0, 500.0, 900.0, 800.0]),
            'scalar': ((), 1.0),
        }
    )
    ds_masks = xr.Dataset({'landIceMask': ('nCells', [0, 1, 1, 1])})
    # the culled mesh keeps base cells 3, 0 and 1, in that order
    cell_map = np.array([3, 0, 1])

    ds_out = cull_topography(ds_topo, ds_masks, cell_map)

    np.testing.assert_array_equal(
        ds_out.base_elevation.values, [-300.0, -100.0, -200.0]
    )
    np.testing.assert_array_equal(
        ds_out.ice_thickness.values, [800.0, 0.0, 500.0]
    )
    np.testing.assert_array_equal(ds_out.landIceMask.values, [1, 0, 1])
    # fields without an nCells dimension are not carried over
    assert 'scalar' not in ds_out
