"""
Helpers for adding layer-thickness fields to an initial-state dataset.
"""


def layer_thickness_from_geom_interfaces(ds):
    """
    Compute ``restingThickness`` and ``layerThickness`` from geometric
    interface heights in ``ds``.

    Both fields equal the geometric layer thickness (appropriate for a
    quiescent initialisation).  Layers below the seafloor are zeroed
    out using ``cellMask``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing ``GeomZInterface`` and ``cellMask``, for
        example produced by
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
    layer_thick.attrs['long_name'] = 'layer thickness'
    layer_thick.attrs['units'] = 'm'

    ds['restingThickness'] = layer_thick
    ds.restingThickness.attrs['long_name'] = 'resting layer thickness'
    ds.restingThickness.attrs['units'] = 'm'

    ds['layerThickness'] = layer_thick
    return ds
