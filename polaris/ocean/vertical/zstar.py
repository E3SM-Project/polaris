import numpy
import xarray

from polaris.ocean.vertical.grid_1d import add_1d_grid
from polaris.ocean.vertical.partial_cells import alter_bottom_depth
from polaris.ocean.vertical.zlevel import (
    compute_min_max_level_cell,
    compute_z_level_layer_thickness,
)


def init_z_star_vertical_coord(config, ds):
    """
    Create a z-star vertical coordinate based on the config options in the
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

    restingSSH = xarray.zeros_like(ds.bottomDepth)
    min_vert_levels = config.getint('vertical_grid', 'min_vert_levels')
    min_layer_thickness = config.getfloat(
        'vertical_grid', 'min_layer_thickness'
    )
    ds['minLevelCell'], ds['maxLevelCell'], ds['cellMask'] = (
        compute_min_max_level_cell(
            ds.refTopDepth,
            ds.refBottomDepth,
            restingSSH,
            ds.bottomDepth,
            min_vert_levels=min_vert_levels,
            min_layer_thickness=min_layer_thickness,
        )
    )

    ds['bottomDepth'], ds['maxLevelCell'] = alter_bottom_depth(
        config, ds.bottomDepth, ds.refBottomDepth, ds.maxLevelCell
    )

    ds['restingThickness'] = compute_z_level_layer_thickness(
        ds.refTopDepth,
        ds.refBottomDepth,
        restingSSH,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )

    ds['layerThickness'] = _compute_z_star_layer_thickness(
        ds.restingThickness,
        ds.ssh,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )


def update_z_star_layer_thickness(config, ds):
    """
    Update the z-star vertical coordinate layer thicknesses based on the
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
    ds['layerThickness'] = _compute_z_star_layer_thickness(
        ds.restingThickness,
        ds.ssh,
        ds.bottomDepth,
        ds.minLevelCell,
        ds.maxLevelCell,
    )


def _compute_z_star_layer_thickness(
    resting_thickness,
    ssh,
    bottom_depth,
    min_level_cell,
    max_level_cell,
):
    """
    Compute z-star layer thickness by stretching restingThickness based on ssh
    and bottomDepth

    Parameters
    ----------
    resting_thickness : xarray.DataArray
        The thickness of z-star layers when ssh = 0

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

    n_vert_levels = resting_thickness.sizes['nVertLevels']
    z_index = xarray.DataArray(
        numpy.arange(n_vert_levels), dims=['nVertLevels']
    )
    mask = numpy.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')

    layer_stretch = (ssh + bottom_depth) / resting_thickness.sum(
        dim='nVertLevels'
    )
    layer_thickness = layer_stretch * resting_thickness

    return layer_thickness.where(mask, 0.0)
