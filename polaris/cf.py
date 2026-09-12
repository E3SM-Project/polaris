"""
CF metadata for the netCDF files Polaris writes
"""

import importlib.resources as imp_res
import re
from functools import lru_cache
from typing import Dict, Mapping

import xarray as xr
from ruamel.yaml import YAML

#: The version of the CF conventions that Polaris writes.  It matches the
#: version Omega writes and is the newest that the CF checker validates.
CF_VERSION = '1.8'

# a CF entry in a ``Conventions`` attribute, such as ``CF-1.8``
_CF_ENTRY = re.compile(r'^CF-\d+\.\d+$')


def add_cf_conventions(ds: xr.Dataset) -> xr.Dataset:
    """
    Add ``CF-<version>`` to the ``Conventions`` global attribute of a dataset
    that has no CF entry.  Any other conventions already listed (``MPAS``
    from the MPAS-Tools mesh converter and cell culler) are kept, since the
    attribute lists every convention a file follows.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset about to be written

    Returns
    -------
    ds : xarray.Dataset
        A shallow copy of the dataset with the ``Conventions`` attribute set
    """
    ds = ds.copy()
    existing = str(ds.attrs.get('Conventions', ''))
    entries = [entry for entry in re.split(r'[\s,]+', existing) if entry]
    if not any(_CF_ENTRY.match(entry) for entry in entries):
        entries.insert(0, f'CF-{CF_VERSION}')
    ds.attrs['Conventions'] = ' '.join(entries)
    return ds


def add_var_attrs(
    ds: xr.Dataset, var_attrs: Mapping[str, Mapping[str, str]]
) -> xr.Dataset:
    """
    Fill in attributes (``units``, ``long_name``, ...) for the variables of
    a dataset from a table, without changing any attribute a variable
    already has.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset about to be written

    var_attrs : dict
        The attributes to add to each variable, keyed by variable name.
        Variables not in the dataset are ignored.

    Returns
    -------
    ds : xarray.Dataset
        A shallow copy of the dataset with the attributes added
    """
    ds = ds.copy()
    for name, attrs in var_attrs.items():
        if name not in ds.variables:
            continue
        for attr, value in attrs.items():
            if attr not in ds[name].attrs:
                ds[name].attrs[attr] = value
    return ds


@lru_cache
def read_var_attrs(package: str, filename: str) -> Dict[str, Dict[str, str]]:
    """
    Read a table of variable attributes from a YAML file in a package.  The
    file maps each variable name to its attributes:

    .. code-block:: yaml

        xCell:
          long_name: x coordinate of cell centers
          units: m

    Parameters
    ----------
    package : str
        The package containing the file, such as ``polaris.mesh``

    filename : str
        The name of the YAML file

    Returns
    -------
    var_attrs : dict
        The attributes of each variable, keyed by variable name
    """
    text = imp_res.files(package).joinpath(filename).read_text()
    yaml = YAML(typ='safe')
    var_attrs = yaml.load(text)
    return {
        name: {attr: str(value) for attr, value in attrs.items()}
        for name, attrs in var_attrs.items()
    }
