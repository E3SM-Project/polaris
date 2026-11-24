import numpy
import xarray

from polaris.ocean.vertical.grid_1d import add_1d_grid
from polaris.ocean.vertical.partial_cells import alter_bottom_depth, alter_ssh


def init_z_level_vertical_coord(config, ds):
    """
    Create a z-level vertical coordinate based on the config options in the
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
    add_1d_grid(config, ds)

    ds['vertCoordMovementWeights'] = xarray.ones_like(ds.refBottomDepth)

    ds['minLevelCell'], ds['maxLevelCell'], ds['cellMask'] = (
        compute_min_max_level_cell(
            ds.refTopDepth, ds.refBottomDepth, ds.ssh, ds.bottomDepth
        )
    )

    ds['bottomDepth'], ds['maxLevelCell'] = alter_bottom_depth(
        config, ds.bottomDepth, ds.refBottomDepth, ds.maxLevelCell
    )

    ds['ssh'], ds['minLevelCell'] = alter_ssh(
        config, ds.ssh, ds.refBottomDepth, ds.minLevelCell
    )

    ds['layerThickness'] = compute_z_level_layer_thickness(
        ds.refTopDepth,
        ds.refBottomDepth,
        ds.ssh,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )

    ds['restingThickness'] = compute_z_level_resting_thickness(
        ds.layerThickness,
        ds.ssh,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )


def update_z_level_layer_thickness(config, ds):
    """
    Update the z-level vertical coordinate layer thicknesses based on the
    ``bottomDepth`` and ``ssh`` variables of the mesh data set.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid

    ds : xarray.Dataset
        A data set containing ``bottomDepth`` and ``ssh`` variables used to
        construct the vertical coordinate
    """
    ds['layerThickness'] = compute_z_level_layer_thickness(
        ds.refTopDepth,
        ds.refBottomDepth,
        ds.ssh,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )


def compute_min_max_level_cell(
    ref_top_depth,
    ref_bottom_depth,
    ssh,
    bottom_depth,
    min_vert_levels=None,
    min_layer_thickness=None,
):
    """
    Compute ``minLevelCell`` and ``maxLevelCell`` indices as well as a cell
    mask for the given reference grid and top and bottom topography.

    Parameters
    ----------
    ref_top_depth : xarray.DataArray
        A 1D array of positive-down depths of the top of each z level

    ref_bottom_depth : xarray.DataArray
        A 1D array of positive-down depths of the bottom of each z level

    ssh : xarray.DataArray
        The sea surface height

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor


    Returns
    -------
    minLevelCell : xarray.DataArray
        The zero-based index of the top valid level

    maxLevelCell : xarray.DataArray
        The zero-based index of the bottom valid level

    cellMask : xarray.DataArray
        A boolean mask of where there are valid cells
    """
    if min_layer_thickness is not None:
        valid = bottom_depth + min_layer_thickness * min_vert_levels >= -ssh
    else:
        valid = bottom_depth > -ssh

    aboveTopMask = (ref_bottom_depth <= -ssh).transpose(
        'nCells', 'nVertLevels'
    )
    aboveBottomMask = (ref_top_depth < bottom_depth).transpose(
        'nCells', 'nVertLevels'
    )
    aboveBottomMask = numpy.logical_and(aboveBottomMask, valid)

    minLevelCell = (aboveTopMask.sum(dim='nVertLevels')).where(valid, 0)
    maxLevelCell = (aboveBottomMask.sum(dim='nVertLevels') - 1).where(valid, 0)
    if min_vert_levels is not None:
        maxLevelCell = numpy.maximum(
            maxLevelCell, minLevelCell + min_vert_levels - 1
        )
    cellMask = numpy.logical_and(
        numpy.logical_not(aboveTopMask), aboveBottomMask
    )
    cellMask = numpy.logical_and(cellMask, valid)

    return minLevelCell, maxLevelCell, cellMask


def compute_z_level_layer_thickness(
    ref_top_depth,
    ref_bottom_depth,
    ssh,
    bottom_depth,
    min_level_cell,
    max_level_cell,
):
    """
    Compute z-level layer thickness from ssh and bottomDepth

    Parameters
    ----------
    ref_top_depth : xarray.DataArray
        A 1D array of positive-down depths of the top of each z level

    ref_bottom_depth : xarray.DataArray
        A 1D array of positive-down depths of the bottom of each z level

    ssh : xarray.DataArray
        The sea surface height

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor

    min_level_cell : xarray.DataArray
        The zero-based index of the top valid level

    max_level_cell : xarray.DataArray
        The zero-based index of the bottom valid level

    Returns
    -------
    layerThickness : xarray.DataArray
        The thickness of each layer (level)
    """

    n_vert_levels = ref_bottom_depth.sizes['nVertLevels']
    z_index = xarray.DataArray(
        numpy.arange(n_vert_levels), dims=['nVertLevels']
    )
    mask = numpy.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')

    z_top = xarray.where(ssh < -ref_top_depth, ssh, -ref_top_depth)
    z_bot = xarray.where(
        -bottom_depth > -ref_bottom_depth,
        -bottom_depth,
        -ref_bottom_depth,
    )
    thickness = (z_top - z_bot).transpose('nCells', 'nVertLevels')

    return thickness.where(mask, 0.0)


def compute_z_level_resting_thickness(
    layer_thickness,
    ssh,
    bottom_depth,
    min_level_cell,
    max_level_cell,
):
    """
    Compute z-level resting thickness by "unstretching" layerThickness
    based on ssh and bottomDepth

    Parameters
    ----------
    layer_thickness : xarray.DataArray
        The thickness of each layer (level)

    ssh : xarray.DataArray
        The sea surface height

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor

    min_level_cell : xarray.DataArray
        The zero-based index of the top valid level

    max_level_cell : xarray.DataArray
        The zero-based index of the bottom valid level

    Returns
    -------
    restingThickness : xarray.DataArray
        The thickness of z-star layers when ssh = 0
    """

    n_vert_levels = layer_thickness.sizes['nVertLevels']
    z_index = xarray.DataArray(
        numpy.arange(n_vert_levels), dims=['nVertLevels']
    )
    mask = numpy.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')

    layer_stretch = bottom_depth / (ssh + bottom_depth)
    resting_thickness = layer_stretch * layer_thickness

    return resting_thickness.where(mask, 0.0)
