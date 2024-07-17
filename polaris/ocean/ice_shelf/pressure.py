import numpy as np
from mpas_tools.cime.constants import constants


def compute_land_ice_pressure_from_thickness(land_ice_thickness, modify_mask,
                                             land_ice_density=None):
    """
    Compute the pressure from an overlying ice shelf from ice thickness

    Parameters
    ----------
    land_ice_thickness: xarray.DataArray
        The ice thickness

    modify_mask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can be deviate from 0

    land_ice_density : float, optional
        A reference density for land ice

    Returns
    -------
    land_ice_pressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean
    """
    gravity = constants['SHR_CONST_G']
    if land_ice_density is None:
        land_ice_density = constants['SHR_CONST_RHOICE']
    land_ice_pressure = modify_mask * \
        np.maximum(land_ice_density * gravity * land_ice_thickness, 0.)
    return land_ice_pressure


def compute_land_ice_pressure_from_draft(land_ice_draft, modify_mask,
                                         ref_density=None):
    """
    Compute the pressure from an overlying ice shelf from ice draft

    Parameters
    ----------
    land_ice_draft : xarray.DataArray
        The ice draft (sea surface height)

    modify_mask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can be deviate from 0

    ref_density : float, optional
        A reference density for seawater displaced by the ice shelf

    Returns
    -------
    land_ice_pressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean
    """
    gravity = constants['SHR_CONST_G']
    if ref_density is None:
        ref_density = constants['SHR_CONST_RHOSW']
    land_ice_pressure = \
        modify_mask * np.maximum(-ref_density * gravity * land_ice_draft, 0.)
    return land_ice_pressure


def compute_land_ice_draft_from_pressure(land_ice_pressure, modify_mask,
                                         ref_density=None):
    """
    Compute the ice-shelf draft associated with the pressure from an overlying
    ice shelf

    Parameters
    ----------
    land_ice_pressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean

    modify_mask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can be deviate from 0

    ref_density : float, optional
        A reference density for seawater displaced by the ice shelf

    Returns
    -------
    land_ice_draft : xarray.DataArray
        The ice draft
    """
    gravity = constants['SHR_CONST_G']
    if ref_density is None:
        ref_density = constants['SHR_CONST_RHOSW']
    land_ice_draft = \
        - (modify_mask * land_ice_pressure / (ref_density * gravity))
    return land_ice_draft
