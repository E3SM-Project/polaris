"""
Helpers for adding density fields to an initial-state dataset.
"""


def add_density_from_specvol(ds):
    """
    Add an in-situ ``Density`` field computed from ``SpecVol`` to ``ds``.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing ``SpecVol``.

    Returns
    -------
    xarray.Dataset
        Dataset with ``Density`` added.
    """
    ds['Density'] = 1.0 / ds['SpecVol']
    ds.Density.attrs['long_name'] = 'in-situ density'
    ds.Density.attrs['units'] = 'kg m-3'
    return ds
