import numpy as np

from polaris.constants import get_constant


def compute_land_ice_pressure_from_thickness(
    land_ice_thickness, modify_mask, land_ice_density
):
    """
    Compute the pressure from an overlying ice shelf from ice thickness

    Parameters
    ----------
    land_ice_thickness: xarray.DataArray
        The ice thickness

    modify_mask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can deviate from 0

    land_ice_density : float
        A reference density for land ice

    Returns
    -------
    land_ice_pressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean
    """
    gravity = get_constant('standard_acceleration_of_gravity')
    land_ice_pressure = modify_mask * np.maximum(
        land_ice_density * gravity * land_ice_thickness, 0.0
    )
    return land_ice_pressure


def compute_land_ice_pressure_from_draft(
    land_ice_draft, modify_mask, ref_density=None
):
    """
    Compute the pressure from an overlying ice shelf from ice draft

    Parameters
    ----------
    land_ice_draft : xarray.DataArray
        The ice draft (sea surface height)

    modify_mask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can deviate from 0

    ref_density : float, optional
        A reference density for seawater displaced by the ice shelf

    Returns
    -------
    land_ice_pressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean
    """
    gravity = get_constant('standard_acceleration_of_gravity')
    if ref_density is None:
        ref_density = get_constant('seawater_density_reference')
    land_ice_pressure = modify_mask * np.maximum(
        -ref_density * gravity * land_ice_draft, 0.0
    )
    return land_ice_pressure
