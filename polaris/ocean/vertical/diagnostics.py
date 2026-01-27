import numpy as np
import xarray as xr


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
        The location in meters from the sea surface of the midpoing of each
        layer (level), positive upward
    """
    # TODO when Omega supports these variables, just fetch them
    # if 'zMid' in ds.keys():
    #    z_mid = ds['zMid']
    # elif 'layerThickness' in ds.keys():

    if 'layerThickness' in ds.keys():
        if 'Time' in ds.dims:
            print('Time dimension present in datasetusing first time index')
            ds = ds.isel(Time=0)
        if 'nCells' not in ds.sizes and 'nVertLevels' not in ds.sizes:
            raise ValueError(
                'nCells, and nVertLevels must be dimensions of ds'
            )
        if 'ssh' in ds.keys():
            ssh = ds.ssh.isel(nVertLevels=0).values
        # TODO remove this because it could lead to errors
        else:
            ssh = np.zeros((ds.sizes['nCells']))

        if 'nVertLevelsP1' in ds.dims:
            z_interface = xr.DataArray(
                np.zeros((ds.sizes['nCells'], ds.sizes['nVertLevelsP1'])),
                dims=('nCells', 'nVertLevelsP1'),
            )
        else:
            z_interface = xr.DataArray(
                np.zeros((ds.sizes['nCells'], ds.sizes['nVertLevels'] + 1)),
                dims=('nCells', 'nVertLevelsP1'),
            )
        z_interface[:, 0] = ssh
        for z_index in range(1, ds.sizes['nVertLevels'] + 1):
            z_interface[:, z_index] = ssh + (
                -ds['layerThickness']
                .isel(nVertLevels=slice(0, z_index))
                .sum(dim='nVertLevels')
            )
        if 'bottomDepth' in ds.keys():
            z_bed_infer = (
                z_interface.isel(nVertLevelsP1=-1).mean(dim='nCells').values
            )
            z_bed_data = ds.bottomDepth.mean(dim='nCells').values
            if abs(z_bed_infer - z_bed_data) > 1.0e-3:
                print(f'bottom_depth from ds = {z_bed_data}')
                print(f'bottom_depth from z_interface = {z_bed_infer}')
        z_mid = z_interface[:, :-1] - 0.5 * ds['layerThickness']
    else:
        raise ValueError(
            'Could not reconstruct zMid, zinterface: '
            'Could not find layerThickness in dataset'
        )
    return z_mid
