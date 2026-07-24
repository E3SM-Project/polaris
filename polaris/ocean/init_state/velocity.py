"""
Helpers for adding velocity fields to an initial-state dataset.
"""

import numpy as np
import xarray as xr


def add_quiescent_normal_velocity(ds, ds_mesh):
    """
    Add a quiescent ``normalVelocity`` field (all zeros) to ``ds``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset to add the field to, with an ``nVertLevels`` dimension.

    ds_mesh : xarray.Dataset
        Horizontal mesh dataset, used to determine ``nEdges``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``normalVelocity`` added.
    """
    nedges = ds_mesh.sizes['nEdges']
    nlevels = ds.sizes['nVertLevels']
    ds['normalVelocity'] = xr.DataArray(
        data=np.zeros((1, nedges, nlevels), dtype=float),
        dims=['Time', 'nEdges', 'nVertLevels'],
        attrs={'long_name': 'normal velocity', 'units': 'm s-1'},
    )
    return ds
