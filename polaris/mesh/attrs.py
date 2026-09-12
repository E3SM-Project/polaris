"""
Metadata for the variables of an MPAS mesh
"""

import xarray as xr

from polaris.cf import add_var_attrs, read_var_attrs


def add_mesh_var_attrs(ds: xr.Dataset) -> xr.Dataset:
    """
    Fill in the ``units`` and ``long_name`` attributes of the MPAS mesh
    variables in a dataset, for those that do not already have them.  The
    MPAS-Tools mesh creation, conversion and culling tools write none, so
    this makes a mesh file self-describing before it is written.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS mesh variables (with MPAS-Ocean names)

    Returns
    -------
    ds : xarray.Dataset
        A shallow copy of the dataset with the attributes added
    """
    return add_var_attrs(ds, read_var_attrs('polaris.mesh', 'attrs.yaml'))
