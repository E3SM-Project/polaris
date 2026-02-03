import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import (
    pressure_and_spec_vol_from_state_at_geom_height,
    pseudothickness_from_pressure,
)


def pseudothickness_from_ds(ds, config):
    if 'temperature' not in ds.keys() or 'salinity' not in ds.keys():
        print(
            'PseudoThickness is not present in the '
            'initial condition and T,S are not present '
            'to compute it'
        )
        return

    surface_pressure = config.getfloat('vertical_grid', 'surface_pressure')
    rho0 = config.getfloat('vertical_grid', 'rho0')

    p_interface, _, _ = pressure_and_spec_vol_from_state_at_geom_height(
        config,
        ds.layerThickness,
        ds.temperature,
        ds.salinity,
        surface_pressure * xr.ones_like(ds.ssh),
        iter_count=1,
    )

    pseudothickness = pseudothickness_from_pressure(p_interface, rho0)

    return pseudothickness


def depth_from_thickness(ds):
    """
    Compute the depth of the midpoint of each layer from `layerThickness`. It
    is assumed that the `layerThickness` of invalid levels is 0. If
    `ssh` is present in the dataset, depths will be offset by `ssh`. If
    `bottomDepth` is present in the dataset, the location of the bottom of the
    bottommost vertical level will be compared with `bottomDepth`.

    Parameters
    ----------
    ds: xarray.Dataset
        An ocean dataset containing `layerThickness` and optionally `ssh`
        and `bottomDepth`

    Returns
    -------
    z_mid : xarray.DataArray
        The location in meters from the sea surface of the midpoint of each
        layer (level), positive upward
    """
    # TODO when Omega supports these variables, just fetch them
    # if 'zMid' in ds.keys():
    #    z_mid = ds['zMid']
    # elif 'layerThickness' in ds.keys():

    if 'layerThickness' not in ds.keys():
        raise ValueError(
            'Could not reconstruct zMid, zinterface: '
            'Could not find layerThickness in dataset'
        )
    if 'Time' in ds.dims:
        print('Time dimension present in dataset; using first time index')
        ds = ds.isel(Time=0)
    if 'nCells' not in ds.sizes and 'nVertLevels' not in ds.sizes:
        raise ValueError('nCells, and nVertLevels must be dimensions of ds')
    if 'ssh' in ds.keys():
        ssh = ds.ssh.isel(nVertLevels=0).values
    # TODO remove this because it could lead to errors
    else:
        ssh = np.zeros((ds.sizes['nCells']))
    if 'nVertLevelsP1' in ds.dims:
        nz = ds.sizes['nVertLevelsP1']
    else:
        nz = ds.sizes['nVertLevels'] + 1

    # mask out thickness where vertical index exceeds maxLevelCell
    layer_thickness = ds.layerThickness
    if 'maxLevelCell' in ds.keys():
        max_level_cell = ds.maxLevelCell
    else:
        max_level_cell = xr.DataArray(nz * np.ones_like(ssh), dims=('nCells'))
    z_idx = xr.DataArray(
        np.tile(
            np.arange(1, ds.sizes['nVertLevels'] + 1),
            (ds.sizes['nCells'], 1),
        ),
        dims=('nCells', 'nVertLevels'),
    )
    layer_thickness = layer_thickness.where(z_idx <= max_level_cell, np.nan)
    z_int_array = np.zeros((ds.sizes['nCells'], nz))
    z_int_array[:, 0] = ssh
    z_int_array[:, 1:] = np.add(
        -layer_thickness.cumsum(dim='nVertLevels', skipna=False).values,
        ssh[:, np.newaxis],
    )
    z_interface = xr.DataArray(
        z_int_array,
        dims=('nCells', 'nVertLevelsP1'),
    )
    z_mid = xr.DataArray(
        z_int_array[:, :-1] - 0.5 * layer_thickness,
        dims=('nCells', 'nVertLevels'),
    )
    if 'bottomDepth' in ds.keys():
        z_bed_infer = z_interface.isel(nVertLevelsP1=-1)
        z_bed_data = ds.bottomDepth
        cell_diff = (z_bed_infer - z_bed_data).values
        if np.max(np.abs(cell_diff)) > 1.0e-3:
            print(
                'The maximum discrepancy between bottom_depth and the lower'
                f'boundary of z_interface is {np.max(np.abs(cell_diff))}'
            )
    return z_mid
