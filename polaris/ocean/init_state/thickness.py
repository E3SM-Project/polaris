"""
Helpers for adding layer-thickness fields to an initial-state dataset.
"""

from polaris.attrs import set_attrs


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
    set_attrs(layer_thick, long_name='layer thickness', units='m')

    # ``ds[name] = da`` copies the attributes, so the two fields can share an
    # array and still describe themselves differently.
    ds['restingThickness'] = layer_thick
    set_attrs(
        ds.restingThickness, long_name='resting layer thickness', units='m'
    )

    ds['layerThickness'] = layer_thick
    return ds
