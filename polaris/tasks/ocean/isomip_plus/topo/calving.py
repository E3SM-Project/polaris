import numpy as np


def calve_thin_ice(ds, min_ice_thickness, min_floating_fraction=0.1):
    """
    Remove (calve) floating ice thinner than a minimum thickness from ISOMIP+
    input geometry, as required by the ISOMIP+ protocol (Asay-Davis et al.
    2016, Sect. 3.1.2).

    The calculation is independent at each point, so ``ds`` can hold a
    single snapshot or several time records.

    Parameters
    ----------
    ds : xarray.Dataset
        ISOMIP+ input geometry with ``upperSurface``, ``lowerSurface``,
        ``floatingMask``, ``groundedMask`` and ``openOceanMask``

    min_ice_thickness : float
        The thickness (m) below which floating ice is removed

    min_floating_fraction : float, optional
        The floating fraction above which ice is considered for calving

    Returns
    -------
    ds : xarray.Dataset
        A copy of the input geometry in which calved ice has zero surface
        elevation, draft and floating fraction, and the calved area is open
        ocean
    """
    ice_thickness = ds.upperSurface - ds.lowerSurface
    calve = np.logical_and(
        ds.floatingMask > min_floating_fraction,
        ice_thickness < min_ice_thickness,
    )
    keep = np.logical_not(calve)

    ds = ds.copy()
    for var in ['upperSurface', 'lowerSurface', 'floatingMask']:
        ds[var] = ds[var].where(keep, 0.0)
    ds['openOceanMask'] = ds.openOceanMask.where(keep, 1.0 - ds.groundedMask)
    return ds
