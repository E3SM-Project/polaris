"""
Helpers for adding density fields to an initial-state dataset.
"""

from polaris.attrs import set_attrs


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
    set_attrs(ds.Density, long_name='in-situ density', units='kg m-3')
    return ds
