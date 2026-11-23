"""
Conversion of the layer indices of each cell between the MPAS-Ocean and Omega
conventions

MPAS-Ocean's ``minLevelCell`` and ``maxLevelCell`` are one-based (Fortran)
indices of the top and bottom active layers of each cell, while Omega's
``MinLayerCell`` and ``MaxLayerCell`` are zero-based (C++) indices, in files
as well as in the model.  Polaris works with the MPAS-Ocean convention, so
the indices are shifted whenever these variables are renamed between the two
models' names.
"""

# MPAS-Ocean names of the one-based layer indices
MPASO_LAYER_INDEX_VARS = ['minLevelCell', 'maxLevelCell']

# Omega names of the same, zero-based, layer indices
OMEGA_LAYER_INDEX_VARS = ['MinLayerCell', 'MaxLayerCell']


def layer_indices_to_omega(ds):
    """
    Convert any one-based MPAS-Ocean layer indices (``minLevelCell`` and
    ``maxLevelCell``) in a dataset to zero-based indices, as Omega expects,
    before the variables are renamed to their Omega names

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with MPAS-Ocean variable names

    Returns
    -------
    ds : xarray.Dataset
        The dataset with the layer indices reduced by 1
    """
    return _shift_layer_indices(ds, MPASO_LAYER_INDEX_VARS, -1)


def layer_indices_from_omega(ds):
    """
    Convert any zero-based Omega layer indices (``MinLayerCell`` and
    ``MaxLayerCell``) in a dataset to the one-based indices of MPAS-Ocean,
    before the variables are renamed to their MPAS-Ocean names

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with Omega variable names

    Returns
    -------
    ds : xarray.Dataset
        The dataset with the layer indices increased by 1
    """
    return _shift_layer_indices(ds, OMEGA_LAYER_INDEX_VARS, 1)


def _shift_layer_indices(ds, var_names, offset):
    """
    Add an offset to the given variables if they are in the dataset, keeping
    their data type and attributes
    """
    shifted = {}
    for name in var_names:
        if name in ds:
            da = ds[name]
            shifted[name] = (
                (da + offset).astype(da.dtype).assign_attrs(da.attrs)
            )
    if shifted:
        ds = ds.assign(shifted)
    return ds
