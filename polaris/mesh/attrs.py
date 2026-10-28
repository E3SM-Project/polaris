"""
Metadata for the variables of an MPAS mesh
"""

import xarray as xr
from mpas_tools.mesh.attrs import get_mesh_var_attrs

from polaris.cf import add_var_attrs
from polaris.mesh.info import is_spherical


def add_mesh_var_attrs(ds: xr.Dataset) -> xr.Dataset:
    """
    Fill in the ``units``, ``long_name`` and ``standard_name`` attributes of
    the MPAS mesh variables in a dataset, for those that do not already have
    them, from the table in :py:mod:`mpas_tools.mesh.attrs`.

    The MPAS-Tools mesh tools write these attributes themselves, but mesh
    variables that Polaris adds to other datasets may not have them.
    Latitude and longitude variables get a ``standard_name`` only if the
    dataset's ``on_a_sphere`` attribute is ``YES``.  Unlike
    :py:func:`mpas_tools.mesh.attrs.add_mesh_attrs()`, no attribute is
    removed, so a dataset that does not carry ``on_a_sphere`` keeps the
    standard names its mesh variables came with.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS mesh variables (with MPAS-Ocean names)

    Returns
    -------
    ds : xarray.Dataset
        A shallow copy of the dataset with the attributes added
    """
    on_a_sphere = is_spherical(ds, default=False)
    return add_var_attrs(ds, get_mesh_var_attrs(on_a_sphere))
