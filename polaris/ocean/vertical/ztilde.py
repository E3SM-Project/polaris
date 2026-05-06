"""
Conversions between Omega pseudo-height and pressure.

Omega's vertical coordinate is pseudo-height
    z_tilde = -p / (RhoSw * g)
with z_tilde positive upward. Here, ``p`` is sea pressure in Pascals (Pa),
``RhoSw`` is a reference density (kg m^-3), and ``g`` is gravitational
acceleration as defined by ``polaris.constants`` via the Physical Constants
Dictionary.
"""

import logging

import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.eos import compute_specvol
from polaris.ocean.vertical import compute_zint_zmid_from_layer_thickness
from polaris.ocean.vertical.grid_1d import generate_1d_grid

__all__ = [
    'z_tilde_from_pressure',
    'pseudothickness_from_pressure',
    'pressure_from_z_tilde',
    'pressure_and_spec_vol_from_state_at_geom_height',
    'pressure_from_geom_thickness',
]

Gravity = get_constant('standard_acceleration_of_gravity')
RhoSw = get_constant('seawater_density_reference')


def pseudothickness_from_pressure(
    p: xr.DataArray,
) -> xr.DataArray:
    """
    Convert sea pressure to pseudo-thickness.

    z_tilde = -p / (RhoSw * g)

    Parameters
    ----------
    p : xarray.DataArray
        Sea pressure in Pascals (Pa) at layer interfaces.

    Returns
    -------
    xarray.DataArray
        Pseudo-thickness at layer mid-points with dimensions NCells by
        NVertLayers (one less layer than ``p``) (units: m).
    """

    p_top = p.isel(nVertLevelsP1=slice(0, -1))
    p_bot = p.isel(nVertLevelsP1=slice(1, None))
    dims = list(p.dims)
    dims = [item.replace('nVertLevelsP1', 'nVertLevels') for item in dims]
    h = xr.DataArray(
        (p_bot - p_top) / (RhoSw * Gravity),
        dims=tuple(dims),
    )
    return h.assign_attrs(
        {
            'long_name': 'pseudo-thickness',
            'units': 'm',
            'note': 'h_tilde = -dp / (RhoSw * g)',
        }
    )


def z_tilde_from_pressure(p: xr.DataArray) -> xr.DataArray:
    """
    Convert sea pressure to pseudo-height.

    z_tilde = -p / (RhoSw * g)

    Parameters
    ----------
    p : xarray.DataArray
        Sea pressure in Pascals (Pa).

    Returns
    -------
    xarray.DataArray
        Pseudo-height with the same shape and coords as ``p`` (units: m).
    """

    z = -(p) / (RhoSw * Gravity)
    return z.assign_attrs(
        {
            'long_name': 'pseudo-height',
            'units': 'm',
            'note': 'z_tilde = -p / (RhoSw * g)',
        }
    )


def pressure_from_z_tilde(z_tilde: xr.DataArray) -> xr.DataArray:
    """
    Convert pseudo-height to sea pressure.

    p = -z_tilde * (RhoSw * g)

    Parameters
    ----------
    z_tilde : xarray.DataArray
        Pseudo-height in meters (m), positive upward.

    Returns
    -------
    xarray.DataArray
        Sea pressure with the same shape and coords as ``z_tilde`` (Pa).
    """

    p = -(z_tilde) * (RhoSw * Gravity)
    return p.assign_attrs(
        {
            'long_name': 'sea pressure',
            'units': 'Pa',
            'note': 'p = -RhoSw * g * z_tilde',
        }
    )


def pressure_from_geom_thickness(
    surf_pressure: xr.DataArray,
    geom_layer_thickness: xr.DataArray,
    spec_vol: xr.DataArray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the pressure at layer interfaces and midpoints given surface
    pressure, geometric layer thicknesses, and specific volume. This
    calculation assumes a constant specific volume within each layer.

    Parameters
    ----------
    surf_pressure : xarray.DataArray
        The surface pressure at the top of the water column.

    geom_layer_thickness : xarray.DataArray
        The geometric thickness of each layer, set to zero for invalid layers.

    spec_vol : xarray.DataArray
        The specific volume at each layer.

    Returns
    -------
    p_interface : xarray.DataArray
        The pressure at layer interfaces.

    p_mid : xarray.DataArray
        The pressure at layer midpoints.
    """

    dp = Gravity / spec_vol * geom_layer_thickness

    p_interface = dp.cumsum(dim='nVertLevels').pad(
        nVertLevels=(1, 0), mode='constant', constant_values=0.0
    )
    p_interface = surf_pressure + p_interface
    p_interface = p_interface.rename({'nVertLevels': 'nVertLevelsP1'})

    p_interface_top = p_interface.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )
    p_mid = p_interface_top + 0.5 * dp

    dims = list(geom_layer_thickness.dims)
    interface_dims = [dim for dim in dims if dim != 'nVertLevels']
    interface_dims.append('nVertLevelsP1')

    p_interface = p_interface.transpose(*interface_dims)
    p_mid = p_mid.transpose(*dims)

    return p_interface, p_mid


def pressure_and_spec_vol_from_state_at_geom_height(
    config: PolarisConfigParser,
    geom_layer_thickness: xr.DataArray,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    surf_pressure: xr.DataArray,
    iter_count: int,
    logger: logging.Logger | None = None,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Compute the pressure at layer interfaces and midpoints, as well as the
    specific volume at midpoints given geometric layer thicknesses,
    temperature and salinity at layer midpoints (i.e. constant in geometric
    height, not pseudo-height), and surface pressure. The solution is found
    iteratively starting from a specific volume calculated from the reference
    density.

    Requires config options needed by
    {py:func}`polaris.ocean.eos.compute_specvol()`.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters defining the equation of state.

    geom_layer_thickness : xarray.DataArray
        The geometric thickness of each layer.

    temperature : xarray.DataArray
        The temperature at layer midpoints.

    salinity : xarray.DataArray
        The salinity at layer midpoints.

    surf_pressure : xarray.DataArray
        The surface pressure at the top of the water column.

    iter_count : int
        The number of iterations to perform.

    logger : logging.Logger, optional
        A logger for logging iteration information.

    Returns
    -------
    p_interface : xarray.DataArray
        The pressure at layer interfaces.

    p_mid : xarray.DataArray
        The pressure at layer midpoints.

    spec_vol : xarray.DataArray
        The specific volume at layer midpoints.
    """

    spec_vol = 1.0 / RhoSw * xr.ones_like(geom_layer_thickness)

    p_interface, p_mid = pressure_from_geom_thickness(
        surf_pressure=surf_pressure,
        geom_layer_thickness=geom_layer_thickness,
        spec_vol=spec_vol,
    )

    prev_spec_vol = spec_vol

    for iter in range(iter_count):
        spec_vol = compute_specvol(
            config=config,
            temperature=temperature,
            salinity=salinity,
            pressure=p_mid,
        )

        if logger is not None:
            delta_spec_vol = spec_vol - prev_spec_vol
            max_delta = np.abs(delta_spec_vol).max().item()
            prev_spec_vol = spec_vol
            logger.info(
                f'Max change in specific volume during EOS iteration {iter}: '
                f'{max_delta:.3e} m3 kg-1'
            )

        p_interface, p_mid = pressure_from_geom_thickness(
            surf_pressure=surf_pressure,
            geom_layer_thickness=geom_layer_thickness,
            spec_vol=spec_vol,
        )

    return p_interface, p_mid, spec_vol


def geom_height_from_pseudo_height(
    geom_z_bot: xr.DataArray,
    h_tilde: xr.DataArray,
    spec_vol: xr.DataArray,
    min_level_cell: np.ndarray,
    max_level_cell: np.ndarray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Sum geometric heights from pseudo-heights and specific volume.

    Parameters
    ----------
    geom_z_bot : xarray.DataArray
        Geometric height at the bathymetry for each water column.

    h_tilde : xarray.DataArray
        Pseudo-thickness of vertical layers, set to zero for invalid layers.

    spec_vol : xarray.DataArray
        Specific volume at midpoints of vertical layers.

    min_level_cell : xarray.DataArray
        Minimum valid zero-based level index for each cell.

    max_level_cell : xarray.DataArray
        Maximum valid zero-based level index for each cell.

    Returns
    -------
    geom_z_inter : xarray.DataArray
        Geometric height at layer interfaces.

    geom_z_mid : xarray.DataArray
        Geometric height at layer midpoints.
    """
    # geometric height starts with geom_z_bot at the bottom
    # and adds up the contributions from each layer above

    n_vert_levels = spec_vol.sizes['nVertLevels']

    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mid_mask = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    )

    geom_thickness = (spec_vol * h_tilde * RhoSw).where(mid_mask, 0.0)

    dz_rev = geom_thickness.isel(nVertLevels=slice(None, None, -1))
    sum_from_level = dz_rev.cumsum(dim='nVertLevels').isel(
        nVertLevels=slice(None, None, -1)
    )

    geom_z_inter_top = geom_z_bot + sum_from_level
    geom_z_inter = geom_z_inter_top.pad(
        nVertLevels=(0, 1), mode='constant', constant_values=0.0
    )
    geom_z_inter[dict(nVertLevels=n_vert_levels)] = geom_z_bot
    geom_z_inter = geom_z_inter.rename({'nVertLevels': 'nVertLevelsP1'})

    z_index_p1 = xr.DataArray(
        np.arange(n_vert_levels + 1), dims=['nVertLevelsP1']
    )
    inter_mask = np.logical_and(
        z_index_p1 >= min_level_cell,
        z_index_p1 <= max_level_cell + 1,
    )
    geom_z_inter = geom_z_inter.where(inter_mask)

    geom_z_inter_lower = geom_z_inter.isel(
        nVertLevelsP1=slice(1, None)
    ).rename({'nVertLevelsP1': 'nVertLevels'})
    geom_z_mid = (geom_z_inter_lower + 0.5 * geom_thickness).where(mid_mask)

    # transpose to match h_tilde.  For geom_z_inter, replace nVertLevels with
    # nVertLevelsP1 at the same index in the list of dimensions
    z_mid_dims = list(h_tilde.dims)
    z_inter_dims = z_mid_dims.copy()
    z_inter_dims[z_mid_dims.index('nVertLevels')] = 'nVertLevelsP1'
    geom_z_inter = geom_z_inter.transpose(*z_inter_dims)
    geom_z_mid = geom_z_mid.transpose(*z_mid_dims)

    return geom_z_inter, geom_z_mid


def get_iter_count_for_eos(config: PolarisConfigParser) -> int:
    """
    Get the number of iterations to perform when adjusting the
    pseudo-bottom-depth to hit the right geometric bottom depth.  Default is
    from the `pseudothickness_iter_count` config option for TEOS-10 and 1 for
    other equations of state.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters defining the equation of state.

    Returns
    -------
    int
        The number of iterations to perform.
    """
    eos_type = config.get('ocean', 'eos_type')
    if eos_type == 'teos-10':
        return config.getint('vertical_grid', 'pseudothickness_iter_count')
    else:
        return 1


def init_z_tilde_vertical_coord(config, ds):
    """
    Create a z-tilde vertical coordinate based on the config options in the
    ``vertical_grid`` section and the ``BottomPressure`` and
    ``SurfacePressure`` variables of the mesh data set.

    The following new variables will be added to the data set:

      * ``minLevelCell`` - the index of the top valid layer

      * ``maxLevelCell`` - the index of the bottom valid layer

      * ``cellMask`` - a mask of where cells are valid

      * ``PseudoThickness`` - the pseudo-thickness of each layer

      * ``RefPseudoThickness`` - the same as pseudo-thickness, used for the
        p* vertical coordinate

      * ``zTildeMid`` - the pseudo height of the midpoint of each layer

      * ``zTildeInterface`` - the pseudo height of the interfaces between
        layers

      * ``vertCoordMovementWeights`` - the weights (all ones) for coordinate
        movement

    Note: since bottom pressure is typically not known at initialization, the
    calling code will likely need to iteratively adjust the bottom pressure
    to obtain the desire geometric bottom depth.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid

    ds : xarray.Dataset
        A data set containing ``bottomDepth`` and ``SurfacePressure`` variables
        used to construct the vertical coordinate
    """

    interfaces = generate_1d_grid(config=config)
    ref_pseudo_depth_top = xr.DataArray(interfaces[:-1], dims=['nVertLevels'])
    ref_pseudo_depth_bot = xr.DataArray(interfaces[1:], dims=['nVertLevels'])

    ds['vertCoordMovementWeights'] = xr.ones_like(ref_pseudo_depth_bot)

    min_vert_levels = config.getint('vertical_grid', 'min_vert_levels')
    min_layer_thickness = config.getfloat(
        'vertical_grid', 'min_layer_thickness'
    )

    pseudo_bottom_depth = ds.BottomPressure / (RhoSw * Gravity)

    pseudo_column_thickness = (ds.BottomPressure - ds.SurfacePressure) / (
        RhoSw * Gravity
    )

    if 'Time' in pseudo_column_thickness.dims:
        pseudo_column_thickness = pseudo_column_thickness.isel(Time=0)

    min_level_cell, max_level_cell = _compute_min_max_level_cell(
        ref_pseudo_depth_top,
        pseudo_column_thickness,
        min_vert_levels,
        min_layer_thickness,
    )

    pseudo_column_thickness, max_level_cell = _alter_pseudo_column_thickness(
        config, pseudo_column_thickness, ref_pseudo_depth_bot, max_level_cell
    )

    pseudo_thickness = _compute_pseudo_thickness(
        ref_pseudo_depth_top,
        ref_pseudo_depth_bot,
        pseudo_column_thickness,
        min_level_cell,
        max_level_cell,
    )

    # recompute the cell mask since min/max indices may have changed
    cell_mask = _compute_cell_mask(
        min_level_cell, max_level_cell, ds.sizes['nVertLevels']
    )
    ds['cellMask'] = cell_mask

    # mask layerThickness and restingThickness
    ds['PseudoThickness'] = pseudo_thickness.where(cell_mask)
    ds['RefPseudoThickness'] = ds.PseudoThickness.copy()

    # add Time dimension
    ds['PseudoThickness'] = ds.PseudoThickness.expand_dims(dim='Time', axis=0)

    ds['ZTildeInterface'], ds['ZTildeMid'] = (
        compute_zint_zmid_from_layer_thickness(
            layer_thickness=pseudo_thickness,
            bottom_depth=pseudo_bottom_depth,
            min_level_cell=min_level_cell,
            max_level_cell=max_level_cell,
        )
    )

    # fortran 1-based indexing
    ds['minLevelCell'] = min_level_cell + 1
    ds['maxLevelCell'] = max_level_cell + 1


def _compute_min_max_level_cell(
    ref_pseudo_depth_top,
    pseudo_column_thickness,
    min_vert_levels,
    min_layer_thickness,
):
    """
    Compute ``minLevelCell`` and ``maxLevelCell`` indices as well as a cell
    mask for the given reference grid and bottom topography.
    """
    valid = pseudo_column_thickness >= min_layer_thickness * min_vert_levels

    above_bot_mask = (
        ref_pseudo_depth_top < pseudo_column_thickness
    ).transpose('nCells', 'nVertLevels')
    cell_mask = np.logical_and(above_bot_mask, valid)

    # nonzero top index isn't supporeted at least for now
    min_level_cell = xr.zeros_like(pseudo_column_thickness).astype(int)
    max_level_cell = (cell_mask.sum(dim='nVertLevels') - 1).where(valid, 0)
    max_level_cell = np.maximum(
        max_level_cell, min_level_cell + min_vert_levels - 1
    )

    return min_level_cell, max_level_cell


def _compute_cell_mask(min_level_cell, max_level_cell, n_vert_levels):
    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    return np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')


def _alter_pseudo_column_thickness(
    config, pseudo_column_thickness, ref_pseudo_depth_bot, max_level_cell
):
    """
    Alter ``pseudo_column_thickness`` and ``max_level_cell`` for full or
    partial bottom cells, if requested
    """
    section = config['vertical_grid']
    partial_cell_type = 'none'
    min_pc_fraction = 0.0
    if config.has_option('vertical_grid', 'partial_cell_type'):
        partial_cell_type = section.get('partial_cell_type').lower()
        min_pc_fraction = section.getfloat('min_pc_fraction')

    if partial_cell_type == 'full':
        pseudo_column_thickness = _compute_full_cells_pseudo_depth(
            ref_pseudo_depth_bot, max_level_cell
        )
    elif partial_cell_type == 'partial':
        pseudo_column_thickness, max_level_cell = (
            _alter_pseudo_column_thickness_for_partial_cells(
                pseudo_column_thickness,
                ref_pseudo_depth_bot,
                max_level_cell,
                min_pc_fraction,
            )
        )
    elif partial_cell_type != 'none':
        raise ValueError(f'Unexpected partial cell type {partial_cell_type}')

    return pseudo_column_thickness, max_level_cell


def _compute_full_cells_pseudo_depth(ref_pseudo_depth_bot, level_index):
    """
    Compute the full cell bottom depth given a level index
    """

    pseudo_depth = ref_pseudo_depth_bot.isel(nVertLevels=level_index).where(
        level_index >= 0, other=0.0
    )
    return pseudo_depth


def _alter_pseudo_column_thickness_for_partial_cells(
    pseudo_column_thickness,
    ref_pseudo_depth_bot,
    max_level_cell,
    min_pc_fraction,
):
    """
    Alter pseudo_column_thickness and max_level_cell for partial cells
    """

    full_bot = _compute_full_cells_pseudo_depth(
        ref_pseudo_depth_bot, max_level_cell
    )

    full_top = _compute_full_cells_pseudo_depth(
        ref_pseudo_depth_bot, max_level_cell - 1
    )

    full_thickness = full_bot - full_top

    pseudo_depth_min_bot = full_bot - (1.0 - min_pc_fraction) * full_thickness

    pseudo_depth_min_bot_mid = 0.5 * (pseudo_depth_min_bot + full_top)

    # where the bottom depth is far too shallow, we're going to fill in the
    # last level
    mask = pseudo_column_thickness < pseudo_depth_min_bot_mid
    max_level_cell = xr.where(mask, max_level_cell - 1, max_level_cell)
    pseudo_column_thickness = xr.where(mask, full_top, pseudo_column_thickness)

    # where the bottom depth only a bit too shallows, we move it deeper
    mask = np.logical_and(
        np.logical_not(mask), pseudo_column_thickness < pseudo_depth_min_bot
    )
    pseudo_column_thickness = xr.where(
        mask, pseudo_depth_min_bot, pseudo_column_thickness
    )

    return pseudo_column_thickness, max_level_cell


def _compute_pseudo_thickness(
    ref_pseudo_depth_top,
    ref_pseudo_depth_bot,
    pseudo_column_thickness,
    min_level_cell,
    max_level_cell,
):
    """
    Compute z-tilde layer thickness by stretching restingThickness based on
    pseudo_column_thickness
    """

    n_vert_levels = ref_pseudo_depth_bot.sizes['nVertLevels']
    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mask = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')

    pseudo_depth_bot = np.minimum(
        pseudo_column_thickness, ref_pseudo_depth_bot
    )
    pseudo_thickness = (pseudo_depth_bot - ref_pseudo_depth_top).transpose(
        'nCells', 'nVertLevels'
    )

    return pseudo_thickness.where(mask, 0.0)
