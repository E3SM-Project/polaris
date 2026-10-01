from mpas_tools.ocean.moc import add_moc_southern_boundary_transects

from polaris.tasks.mesh.spherical.feature_masks.compute import (
    get_feature_masks_filename,
)

#: The geometric_features aggregation these helpers apply to
MOC_MASK_GROUP = 'MOC Basins'

#: The filename prefix E3SM already uses for the staged file, as in
#: oRRS18to6v3_mocBasinsAndTransects20210623.nc
MOC_PREFIX = 'mocBasinsAndTransects'


def moc_masks_filename(mesh_name, date):
    """
    Get the filename for a MOC basin-and-transect mask file.

    Parameters
    ----------
    mesh_name : str
        The mesh name for output filenames and metadata

    date : str
        The date stamp for the ``'MOC Basins'`` aggregation

    Returns
    -------
    filename : str
        The mask filename
    """
    return get_feature_masks_filename(
        mesh_name=mesh_name, prefix=MOC_PREFIX, date=date
    )


def add_moc_transects(ds_masks, ds_mesh, logger):
    """
    Append the southern-boundary transects to MOC basin masks, and drop the
    string variables that are incompatible with CDF5.

    Parameters
    ----------
    ds_masks : xarray.Dataset
        The MOC basin region masks

    ds_mesh : xarray.Dataset
        A standard MPAS mesh dataset

    logger : logging.Logger
        Logger for progress output

    Returns
    -------
    ds_masks : xarray.Dataset
        The masks with southern-boundary transects appended
    """
    ds_masks = add_moc_southern_boundary_transects(
        ds_masks, ds_mesh, logger=logger
    )
    to_drop = [v for v in ['history', 'constituents'] if v in ds_masks]
    if to_drop:
        ds_masks = ds_masks.drop_vars(to_drop)
    return ds_masks
