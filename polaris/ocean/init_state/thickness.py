"""
Helpers for adding layer-thickness fields to an initial-state dataset.
"""

import numpy as np
import xarray as xr

from polaris.attrs import set_attrs


def layer_thickness_from_geom_interfaces(ds):
    r"""
    Compute ``restingThickness`` and ``layerThickness`` from geometric
    interface heights in ``ds``.

    ``layerThickness`` is the geometric layer thickness (appropriate for a
    quiescent initialisation).  ``restingThickness`` is the thickness the
    layer would have at zero sea-surface height, which MPAS-Ocean's z-star
    coordinate requires to sum to ``bottomDepth``:

    .. math::

        h_{rest} = h \frac{H}{H + \eta}

    where :math:`H` is ``bottomDepth`` and :math:`\eta` is ``ssh``.  The two
    are the same where ``ssh`` is zero, or where ``ds`` has no ``ssh`` or
    ``bottomDepth``.  They differ under land ice, whose load depresses the
    sea surface.  Layers below the seafloor are zeroed out using
    ``cellMask``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing ``GeomZInterface`` and ``cellMask``, and
        optionally ``ssh`` and ``bottomDepth``, for example produced by
        :py:class:`polaris.ocean.vertical.pstar_init.PStarInitStep`.

    Returns
    -------
    xarray.Dataset
        Dataset with ``restingThickness`` and ``layerThickness`` added.
    """
    geom_z_inter = ds['GeomZInterface']  # (Time, nCells, nVertLevelsP1)
    layer_thick = (
        geom_z_inter.isel(nVertLevelsP1=slice(None, -1))
        - geom_z_inter.isel(nVertLevelsP1=slice(1, None))
    ).rename({'nVertLevelsP1': 'nVertLevels'})

    cell_mask = ds['cellMask'].astype(bool)
    layer_thick = layer_thick.where(cell_mask, other=0.0)
    set_attrs(layer_thick, long_name='layer thickness', units='m')

    resting_thick = layer_thick
    if 'ssh' in ds and 'bottomDepth' in ds:
        column_thickness = ds.bottomDepth + ds.ssh
        # exactly 1 where ssh is exactly 0, so those columns are unchanged
        stretch = xr.where(
            column_thickness > 0.0, ds.bottomDepth / column_thickness, 1.0
        )
        resting_thick = layer_thick * stretch

    # ``ds[name] = da`` copies the attributes, so the two fields can share an
    # array and still describe themselves differently.
    ds['restingThickness'] = resting_thick
    set_attrs(
        ds.restingThickness, long_name='resting layer thickness', units='m'
    )

    ds['layerThickness'] = layer_thick
    return ds


def apply_min_max_layer_thickness(ds, min_thickness, max_thickness_factor):
    r"""
    Set ``layerThickness`` to the thickness MPAS-Ocean's z-star coordinate
    targets with its minimum and maximum layer thicknesses, as
    ``ocn_ALE_thickness()`` does with ``config_use_min_max_thickness``.

    The z-star target stretches ``restingThickness`` by the sea-surface
    height:

    .. math::

        h_k = h_{rest,k} + \eta \frac{h_{rest,k}}{\sum_k h_{rest,k}}

    A sweep down the column then raises each layer thinner than
    ``min_thickness`` to it, and lowers each thicker than
    ``max_thickness_factor`` times its resting thickness to that, carrying
    the difference to the layers below.  A sweep back up does the same,
    carrying the difference to the layers above, and whatever is left goes
    to the top layer.  A column at least ``min_thickness`` thick in every
    layer keeps its total thickness, and one whose z-star thicknesses are
    within the limits is unchanged.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset with ``restingThickness``, ``ssh``, ``minLevelCell`` and
        ``maxLevelCell``

    min_thickness : float
        The minimum layer thickness (m), MPAS-Ocean's
        ``config_min_thickness``

    max_thickness_factor : float
        The maximum layer thickness as a multiple of the resting thickness,
        MPAS-Ocean's ``config_max_thickness_factor``

    Returns
    -------
    xarray.Dataset
        The dataset with ``layerThickness`` replaced
    """
    resting = ds.restingThickness
    has_time = 'Time' in resting.dims
    if has_time:
        resting = resting.isel(Time=0)
    ssh = ds.ssh
    if 'Time' in ssh.dims:
        ssh = ssh.isel(Time=0)

    rest = resting.transpose('nCells', 'nVertLevels').values
    nlevels = rest.shape[1]
    levels = np.arange(nlevels)[np.newaxis, :]
    k_min = ds.minLevelCell.values[:, np.newaxis] - 1
    k_max = ds.maxLevelCell.values[:, np.newaxis] - 1
    valid = (levels >= k_min) & (levels <= k_max)
    rest = np.where(valid, rest, 0.0)

    rest_sum = rest.sum(axis=1, keepdims=True)
    rest_sum = np.where(rest_sum > 0.0, rest_sum, 1.0)
    target = np.where(
        valid, rest + ssh.values[:, np.newaxis] * rest / rest_sum, 0.0
    )

    prelim = target.copy()
    max_thick = max_thickness_factor * rest
    remainder = np.zeros(rest.shape[0])
    down = np.zeros_like(rest)
    for k in range(nlevels):
        in_column = valid[:, k]
        new = np.maximum(
            min_thickness,
            np.minimum(prelim[:, k] + remainder, max_thick[:, k]),
        )
        change = np.where(in_column, new - prelim[:, k], 0.0)
        down[:, k] = change
        remainder = remainder - change
    prelim = prelim + down

    up = np.zeros_like(rest)
    for k in range(nlevels - 2, -1, -1):
        in_column = valid[:, k] & (k < k_max[:, 0])
        new = np.maximum(
            min_thickness,
            np.minimum(prelim[:, k] + remainder, max_thick[:, k]),
        )
        change = np.where(in_column, new - prelim[:, k], 0.0)
        up[:, k] = change
        remainder = remainder - change
    cells = np.arange(rest.shape[0])
    up[cells, k_min[:, 0]] += remainder

    thickness = np.where(valid, target + down + up, 0.0)
    layer_thick = xr.DataArray(thickness, dims=('nCells', 'nVertLevels'))
    if has_time:
        layer_thick = layer_thick.expand_dims(dim='Time', axis=0)
    layer_thick.attrs = dict(ds.layerThickness.attrs)
    ds['layerThickness'] = layer_thick
    return ds
