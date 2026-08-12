from configparser import ConfigParser

import xarray as xr

from polaris.ocean.vertical.grid_1d import REF_COORD_VARS, add_1d_grid


def _make_config(vert_levels=4, bottom_depth=100.0):
    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', str(vert_levels))
    config.set('vertical_grid', 'bottom_depth', str(bottom_depth))
    return config


def test_ref_coord_vars_matches_add_1d_grid():
    """REF_COORD_VARS must stay in sync with what add_1d_grid writes."""
    config = _make_config()
    ds = xr.Dataset()
    add_1d_grid(config, ds)
    assert set(REF_COORD_VARS) == set(ds.data_vars)
