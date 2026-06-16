"""
P-star vertical coordinate construction for Omega.

The p-star coordinate is a specific ALE variant of Omega's z-tilde
(pseudo-height) coordinate system.  It stores a set of reference
pseudo-thicknesses ``RefPseudoThickness`` — the pseudo-thicknesses the layers
would have if the sea-surface pressure were zero — together with
``VertCoordMovementWeights`` that control how changes in total column mass are
distributed across layers.  At runtime, Omega's
``VertCoord::computeTargetThickness()`` adjusts each layer's
pseudo-thickness from its reference value proportionally to the total column
pressure difference and the layer's movement weight.

Pseudo-height is defined as :math:`\\tilde{z} = -p / (\\rho_0 g)`, where
:math:`p` is sea gauge pressure, :math:`\\rho_0` is a reference seawater
density, and :math:`g` is gravitational acceleration.
"""

import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.vertical import compute_zint_zmid_from_layer_thickness
from polaris.ocean.vertical.grid_1d import generate_1d_grid

__all__ = ['init_pstar_vertical_coord']

Gravity = get_constant('standard_acceleration_of_gravity')
RhoSw = get_constant('seawater_density_reference')


def init_pstar_vertical_coord(config, ds):
    """
    Create a p-star vertical coordinate based on the config options in the
    ``vertical_grid`` section and the ``BottomPressure`` and
    ``SurfacePressure`` variables of the mesh dataset.

    ``RefPseudoThickness`` is the pseudo-thickness each layer would have at
    zero ``SurfacePressure``; it is set by clipping the reference 1-D grid
    at the snapped ``BottomPressure / (rho0 * g)``.  ``PseudoThickness`` is
    then scaled from ``RefPseudoThickness`` by
    ``(BottomPressure - SurfacePressure) / BottomPressure``, the p-star
    analogue of z-star's ``layerThickness = restingThickness *
    (ssh + bottomDepth) / bottomDepth``.

    The following new variables are added to ``ds``:

    * ``minLevelCell`` — index of the topmost valid layer (1-based; always
      1, since non-zero top levels are not supported)
    * ``maxLevelCell`` — index of the bottommost valid layer (1-based)
    * ``cellMask`` — boolean mask of valid layers
    * ``RefPseudoThickness`` — reference pseudo-thickness (no Time dim)
    * ``PseudoThickness`` — pseudo-thickness scaled by surface pressure
    * ``ZTildeInterface`` — pseudo-height at layer interfaces
    * ``ZTildeMid`` — pseudo-height at layer midpoints
    * ``vertCoordMovementWeights`` — weights for coordinate movement (all 1)

    ``BottomPressure`` in ``ds`` is updated to the post-snap value.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options with parameters used to construct the vertical
        grid.

    ds : xarray.Dataset
        Dataset containing ``BottomPressure`` and ``SurfacePressure``
        variables (both in Pa with dimension ``nCells``) used to construct
        the vertical coordinate.  Also requires ``nVertLevels`` to be a
        dimension of ``ds``.
    """
    interfaces = generate_1d_grid(config=config)
    ref_pseudo_depth_top = xr.DataArray(interfaces[:-1], dims=['nVertLevels'])
    ref_pseudo_depth_bot = xr.DataArray(interfaces[1:], dims=['nVertLevels'])

    ds['vertCoordMovementWeights'] = xr.ones_like(ref_pseudo_depth_bot)

    min_vert_levels = config.getint('vertical_grid', 'min_vert_levels')
    min_layer_thickness = config.getfloat(
        'vertical_grid', 'min_layer_thickness'
    )

    # pseudo_bottom_depth is defined at zero SurfacePressure: it sets the
    # boundaries of RefPseudoThickness.
    pseudo_bottom_depth = ds.BottomPressure / (RhoSw * Gravity)

    if 'Time' in pseudo_bottom_depth.dims:
        pseudo_bottom_depth = pseudo_bottom_depth.isel(Time=0)

    min_level_cell, max_level_cell = _compute_min_max_level_cell(
        ref_pseudo_depth_top,
        pseudo_bottom_depth,
        min_vert_levels,
        min_layer_thickness,
    )

    pseudo_bottom_depth, max_level_cell = _alter_pseudo_column_thickness(
        config, pseudo_bottom_depth, ref_pseudo_depth_bot, max_level_cell
    )

    # Update BottomPressure after partial-cell snap.  The resting depth
    # (SurfacePressure = 0) determines the snap; SurfacePressure then scales
    # the layers uniformly, analogous to ssh in z-star.
    ds['BottomPressure'] = pseudo_bottom_depth * (RhoSw * Gravity)

    # Resting pseudo-thicknesses (as if SurfacePressure = 0), then scale by
    # (BottomPressure - SurfacePressure) / BottomPressure to account for the
    # surface pressure squashing the column — the p-star analogue of z-star's
    # layerThickness = restingThickness * (ssh + bottomDepth) / bottomDepth.
    ref_pseudo_thickness = _compute_ref_pseudo_thickness(
        ref_pseudo_depth_top,
        ref_pseudo_depth_bot,
        pseudo_bottom_depth,
        min_level_cell,
        max_level_cell,
    )

    scale = xr.where(
        ds.BottomPressure > 0,
        (ds.BottomPressure - ds.SurfacePressure) / ds.BottomPressure,
        1.0,
    )

    cell_mask = _compute_cell_mask(
        min_level_cell, max_level_cell, ds.sizes['nVertLevels']
    )
    ds['cellMask'] = cell_mask

    ref_pseudo_thickness = ref_pseudo_thickness.where(cell_mask)
    ds['RefPseudoThickness'] = ref_pseudo_thickness.copy()

    pseudo_thickness = (ref_pseudo_thickness * scale).where(cell_mask)
    pseudo_thickness = pseudo_thickness.expand_dims(dim='Time', axis=0)

    # add Time dimension to PseudoThickness but not RefPseudoThickness
    ds['PseudoThickness'] = pseudo_thickness

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
    pseudo_bottom_depth,
    min_vert_levels,
    min_layer_thickness,
):
    """
    Compute zero-based ``minLevelCell`` and ``maxLevelCell`` indices for the
    given reference grid and pseudo-bottom depth.
    """
    valid = pseudo_bottom_depth >= min_layer_thickness * min_vert_levels

    above_bot_mask = (ref_pseudo_depth_top < pseudo_bottom_depth).transpose(
        'nCells', 'nVertLevels'
    )
    cell_mask = np.logical_and(above_bot_mask, valid)

    # non-zero top index (e.g. ice-shelf cavities) is not supported
    min_level_cell = xr.zeros_like(pseudo_bottom_depth).astype(int)
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
    config, pseudo_bottom_depth, ref_pseudo_depth_bot, max_level_cell
):
    """
    Apply full or partial bottom-cell snapping to ``pseudo_bottom_depth``.
    """
    section = config['vertical_grid']
    partial_cell_type = 'none'
    min_pc_fraction = 0.0
    if config.has_option('vertical_grid', 'partial_cell_type'):
        partial_cell_type = section.get('partial_cell_type').lower()
        min_pc_fraction = section.getfloat('min_pc_fraction')

    if partial_cell_type == 'full':
        pseudo_bottom_depth = _compute_full_cells_pseudo_depth(
            ref_pseudo_depth_bot, max_level_cell
        )
    elif partial_cell_type == 'partial':
        pseudo_bottom_depth, max_level_cell = _snap_partial_cells(
            pseudo_bottom_depth,
            ref_pseudo_depth_bot,
            max_level_cell,
            min_pc_fraction,
        )
    elif partial_cell_type != 'none':
        raise ValueError(f'Unexpected partial cell type {partial_cell_type}')

    return pseudo_bottom_depth, max_level_cell


def _compute_full_cells_pseudo_depth(ref_pseudo_depth_bot, level_index):
    """
    Return the full-cell pseudo-depth at the bottom of ``level_index``.
    """
    pseudo_depth = ref_pseudo_depth_bot.isel(nVertLevels=level_index).where(
        level_index >= 0, other=0.0
    )
    return pseudo_depth


def _snap_partial_cells(
    pseudo_bottom_depth,
    ref_pseudo_depth_bot,
    max_level_cell,
    min_pc_fraction,
):
    """
    Snap ``pseudo_bottom_depth`` and ``max_level_cell`` for partial cells.
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

    # where the bottom is far too shallow, remove the last level
    mask = pseudo_bottom_depth < pseudo_depth_min_bot_mid
    max_level_cell = xr.where(mask, max_level_cell - 1, max_level_cell)
    pseudo_bottom_depth = xr.where(mask, full_top, pseudo_bottom_depth)

    # where the bottom is only slightly too shallow, snap it deeper
    mask = np.logical_and(
        np.logical_not(mask),
        pseudo_bottom_depth < pseudo_depth_min_bot,
    )
    pseudo_bottom_depth = xr.where(
        mask, pseudo_depth_min_bot, pseudo_bottom_depth
    )

    return pseudo_bottom_depth, max_level_cell


def _compute_ref_pseudo_thickness(
    ref_pseudo_depth_top,
    ref_pseudo_depth_bot,
    pseudo_bottom_depth,
    min_level_cell,
    max_level_cell,
):
    """
    Compute resting p-star pseudo-thicknesses (as if SurfacePressure = 0)
    by clipping reference layers at ``pseudo_bottom_depth``.
    """
    n_vert_levels = ref_pseudo_depth_bot.sizes['nVertLevels']
    z_index = xr.DataArray(np.arange(n_vert_levels), dims=['nVertLevels'])
    mask = np.logical_and(
        z_index >= min_level_cell, z_index <= max_level_cell
    ).transpose('nCells', 'nVertLevels')

    pseudo_depth_bot = np.minimum(pseudo_bottom_depth, ref_pseudo_depth_bot)
    pseudo_thickness = (pseudo_depth_bot - ref_pseudo_depth_top).transpose(
        'nCells', 'nVertLevels'
    )

    return pseudo_thickness.where(mask, 0.0)
