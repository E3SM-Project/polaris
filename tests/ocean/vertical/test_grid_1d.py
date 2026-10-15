from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical.grid_1d import (
    REF_COORD_VARS,
    add_1d_grid,
    generate_1d_grid,
)


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


def test_json_grid_without_bottom_depth_is_used_whole():
    """A json-based grid with no bottom depth keeps all of its levels."""
    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', '80layerE3SMv1')

    interfaces = generate_1d_grid(config)

    assert interfaces.size == 81
    assert interfaces[0] == 0.0
    assert np.all(np.diff(interfaces) > 0.0)


def test_json_grid_is_chopped_at_bottom_depth():
    """A json-based grid with a bottom depth ends at the nearest interface."""
    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', '80layerE3SMv1')
    full = generate_1d_grid(config)
    config.set('vertical_grid', 'bottom_depth', '1000.0')

    interfaces = generate_1d_grid(config)

    nearest_index = np.abs(full - 1000.0).argmin()
    assert interfaces.size == nearest_index + 1
    assert interfaces[-1] == pytest.approx(1000.0)
    assert interfaces[:-1] == pytest.approx(full[:nearest_index])
