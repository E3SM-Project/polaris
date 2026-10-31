"""
Unit tests for updating the layer thickness after a change in SSH, as SSH
adjustment does when it adjusts SSH rather than the land-ice pressure.
"""

from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.ocean.vertical import init_vertical_coord, update_layer_thickness

VERT_LEVELS = 10
MAX_BOTTOM_DEPTH = 720.0


def _make_config(coord_type):
    config = ConfigParser()
    config.add_section('vertical_grid')
    config.set('vertical_grid', 'grid_type', 'uniform')
    config.set('vertical_grid', 'vert_levels', str(VERT_LEVELS))
    config.set('vertical_grid', 'bottom_depth', str(MAX_BOTTOM_DEPTH))
    config.set('vertical_grid', 'coord_type', coord_type)
    config.set('vertical_grid', 'partial_cell_type', 'None')
    config.set('vertical_grid', 'min_pc_fraction', '0.1')
    config.set('vertical_grid', 'min_vert_levels', '3')
    config.set('vertical_grid', 'min_layer_thickness', '0.0')
    return config


def _make_ds(config, ssh):
    """An ice-shelf-like set of columns with a sloping bed"""
    ds = xr.Dataset()
    ds['bottomDepth'] = xr.DataArray(
        np.linspace(300.0, MAX_BOTTOM_DEPTH, ssh.size), dims=['nCells']
    )
    ds['ssh'] = xr.DataArray(ssh, dims=['nCells'])
    init_vertical_coord(config, ds)
    return ds


@pytest.mark.parametrize('coord_type', ['z-star', 'sigma'])
def test_update_matches_init_with_new_ssh(coord_type):
    """
    Updating the SSH of an initialized coordinate must give the coordinate
    initialized with that SSH from the start
    """
    config = _make_config(coord_type)
    old_ssh = np.linspace(-250.0, 0.0, 8)
    new_ssh = old_ssh - np.linspace(20.0, 0.5, 8)

    ds = _make_ds(config, old_ssh)
    ds['ssh'] = xr.DataArray(new_ssh, dims=['nCells']).expand_dims(
        dim='Time', axis=0
    )
    update_layer_thickness(config, ds)

    ds_expected = _make_ds(config, new_ssh)

    for var in [
        'ssh',
        'layerThickness',
        'zMid',
        'GeomZInterface',
        'minLevelCell',
        'maxLevelCell',
        'restingThickness',
    ]:
        assert ds[var].dims == ds_expected[var].dims, var
        np.testing.assert_allclose(
            ds[var].values, ds_expected[var].values, err_msg=var
        )


def test_update_keeps_column_thickness():
    """The layers must fill the column from the bed to the new SSH"""
    config = _make_config('z-star')
    ds = _make_ds(config, np.linspace(-250.0, 0.0, 8))
    new_ssh = np.linspace(-270.0, 0.2, 8)
    ds['ssh'] = xr.DataArray(new_ssh, dims=['nCells'])
    update_layer_thickness(config, ds)

    column = ds.layerThickness.isel(Time=0).sum(dim='nVertLevels')
    np.testing.assert_allclose(column.values, new_ssh + ds.bottomDepth.values)
    assert (ds.layerThickness.isel(Time=0, nVertLevels=0) > 0.0).all()
