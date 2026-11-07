"""
Helpers for adding layer-thickness fields to an initial-state dataset.
"""

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
