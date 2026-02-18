import numpy as np
import xarray as xr

from polaris.ocean.vertical.sigma import (
    init_sigma_vertical_coord as init_sigma_vertical_coord,
)
from polaris.ocean.vertical.sigma import (
    update_sigma_layer_thickness as update_sigma_layer_thickness,
)
from polaris.ocean.vertical.zlevel import (
    init_z_level_vertical_coord as init_z_level_vertical_coord,
)
from polaris.ocean.vertical.zlevel import (
    update_z_level_layer_thickness as update_z_level_layer_thickness,
)
from polaris.ocean.vertical.zstar import (
    init_z_star_vertical_coord as init_z_star_vertical_coord,
)
from polaris.ocean.vertical.zstar import (
    update_z_star_layer_thickness as update_z_star_layer_thickness,
)


def init_vertical_coord(config, ds):
    """
    Create a vertical coordinate based on the config options in the
    ``vertical_grid`` section and the ``bottomDepth`` and ``ssh`` variables of
    the mesh data set.

    The following new variables will be added to the data set:

      * ``minLevelCell`` - the index of the top valid layer

      * ``maxLevelCell`` - the index of the bottom valid layer

      * ``cellMask`` - a mask of where cells are valid

      * ``layerThickness`` - the thickness of each layer

      * ``restingThickness`` - the thickness of each layer stretched as if
        ``ssh = 0``

      * ``zMid`` - the elevation of the midpoint of each layer

    So far, all supported coordinates make use of a 1D reference vertical grid.
    The following variables associated with that field are also added to the
    mesh:

      * ``refTopDepth`` - the positive-down depth of the top of each ref. level

      * ``refZMid`` - the positive-down depth of the middle of each ref. level

      * ``refBottomDepth`` - the positive-down depth of the bottom of each ref.
        level

      * ``refInterfaces`` - the positive-down depth of the interfaces between
        ref. levels (with ``nVertLevels`` + 1 elements).

      * ``vertCoordMovementWeights`` - the weights (all ones) for coordinate
        movement

    There is considerable redundancy between these variables but each is
    sometimes convenient.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid

    ds : xarray.Dataset
        A data set containing ``bottomDepth`` and ``ssh`` variables used to
        construct the vertical coordinate
    """

    for var in ['bottomDepth', 'ssh']:
        if var not in ds:
            raise ValueError(f'{var} must be added to ds before this call.')

    if 'Time' in ds.ssh.dims:
        # drop it for now, we'll add it back at the end
        ds['ssh'] = ds.ssh.isel(Time=0)

    coord_type = config.get('vertical_grid', 'coord_type')

    if coord_type == 'z-level':
        init_z_level_vertical_coord(config, ds)
    elif coord_type == 'z-star' or coord_type == 'z-tilde':
        init_z_star_vertical_coord(config, ds)
    elif coord_type == 'sigma':
        init_sigma_vertical_coord(config, ds)
    elif coord_type == 'haney-number':
        raise ValueError('Haney Number coordinate not yet supported.')
    else:
        raise ValueError(f'Unknown coordinate type {coord_type}')

    # recompute the cell mask since min/max indices may have changed
    ds['cellMask'] = _compute_cell_mask(
        ds.minLevelCell, ds.maxLevelCell, ds.sizes['nVertLevels']
    )

    # mask layerThickness and restingThickness
    ds['layerThickness'] = ds.layerThickness.where(ds.cellMask)
    ds['restingThickness'] = ds.restingThickness.where(ds.cellMask)

    # add (back) Time dimension
    ds['ssh'] = ds.ssh.expand_dims(dim='Time', axis=0)
    ds['layerThickness'] = ds.layerThickness.expand_dims(dim='Time', axis=0)
    ds['restingThickness'] = ds.restingThickness.expand_dims(
        dim='Time', axis=0
    )

    ds['zInterface'], ds['zMid'] = compute_zint_zmid_from_layer_thickness(
        layer_thickness=ds.layerThickness,
        bottom_depth=ds.bottomDepth,
        min_level_cell=ds.minLevelCell,
        max_level_cell=ds.maxLevelCell,
    )

    # fortran 1-based indexing
    ds['minLevelCell'] = ds.minLevelCell + 1
    ds['maxLevelCell'] = ds.maxLevelCell + 1


def update_layer_thickness(config, ds):
    """
    Update the layer thicknesses in ds after the vertical coordinate has
    already been initialized based on the ``bottomDepth`` and ``ssh``
    variables of the mesh data set.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid

    ds : xarray.Dataset
        A data set containing ``bottomDepth`` and ``ssh`` variables used to
        construct the vertical coordinate
    """

    for var in ['bottomDepth', 'ssh']:
        if var not in ds:
            raise ValueError(f'{var} must be added to ds before this call.')

    if 'Time' in ds.ssh.dims:
        # drop it for now, we'll add it back at the end
        ds['ssh'] = ds.ssh.isel(Time=0)

    coord_type = config.get('vertical_grid', 'coord_type')

    if coord_type == 'z-level':
        update_z_level_layer_thickness(config, ds)
    elif coord_type == 'z-star' or coord_type == 'z-tilde':
        update_z_star_layer_thickness(config, ds)
    elif coord_type == 'sigma':
        update_sigma_layer_thickness(config, ds)
    elif coord_type == 'haney-number':
        raise ValueError('Haney Number coordinate not yet supported.')
    else:
        raise ValueError(f'Unknown coordinate type {coord_type}')

    # add (back) Time dimension
    ds['ssh'] = ds.ssh.expand_dims(dim='Time', axis=0)
    ds['layerThickness'] = ds.layerThickness.expand_dims(dim='Time', axis=0)


def compute_zint_zmid_from_layer_thickness(
    layer_thickness: xr.DataArray,
    bottom_depth: xr.DataArray,
    min_level_cell: xr.DataArray,
    max_level_cell: xr.DataArray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute height z at layer interfaces and midpoints given layer thicknesses
    and bottom depth.

    Parameters
    ----------
    layer_thickness : xarray.DataArray
        The layer thickness of each layer.

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor.

    min_level_cell : xarray.DataArray
        The zero-based minimum vertical index from each column.

    max_level_cell : xarray.DataArray
        The zero-based maximum vertical index from each column.

    Returns
    -------
    z_interface : xarray.DataArray
        The elevation of layer interfaces.

    z_mid : xarray.DataArray
        The elevation of layer midpoints.
    """

    n_vert_levels = layer_thickness.sizes['nVertLevels']

    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mask_mid = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    )

    dz = layer_thickness.where(mask_mid, 0.0)
    dz_rev = dz.isel(nVertLevels=slice(None, None, -1))
    sum_from_level = dz_rev.cumsum(dim='nVertLevels').isel(
        nVertLevels=slice(None, None, -1)
    )

    z_bot = (
        xr.zeros_like(layer_thickness.isel(nVertLevels=0, drop=True))
        - bottom_depth
    )
    z_interface_top = z_bot + sum_from_level
    z_interface = z_interface_top.pad(nVertLevels=(0, 1), mode='constant')
    z_interface[dict(nVertLevels=n_vert_levels)] = z_bot
    z_interface = z_interface.rename({'nVertLevels': 'nVertLevelsP1'})

    z_index_p1 = xr.DataArray(
        np.arange(n_vert_levels + 1), dims=['nVertLevelsP1']
    )
    mask_interface = np.logical_and(
        z_index_p1 >= min_level_cell,
        z_index_p1 - 1 <= max_level_cell,
    )
    z_interface = z_interface.where(mask_interface)

    z_interface_upper = z_interface.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    z_interface_lower = z_interface.isel(nVertLevelsP1=slice(1, None)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    z_mid = (0.5 * (z_interface_upper + z_interface_lower)).where(mask_mid)

    dims = list(layer_thickness.dims)
    interface_dims = [dim for dim in dims if dim != 'nVertLevels']
    interface_dims.append('nVertLevelsP1')
    z_interface = z_interface.transpose(*interface_dims)
    z_mid = z_mid.transpose(*dims)

    return z_interface, z_mid


def _compute_cell_mask(minLevelCell, maxLevelCell, nVertLevels):
    z_index = xr.DataArray(np.arange(nVertLevels), dims=['nVertLevels'])
    return np.logical_and(
        z_index >= minLevelCell, z_index <= maxLevelCell
    ).transpose('nCells', 'nVertLevels')
