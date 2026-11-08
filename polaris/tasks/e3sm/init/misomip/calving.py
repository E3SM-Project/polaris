"""
MALI's flotation test and the protocol's calving, on MALI's cells

Ice thinner than 100 m that floats is calved, as is ice beyond the MISMIP+
calving front (Asay-Davis et al. 2016, Sects. 2.1 and 3.1.2).
"""

import numpy as np

from polaris.landice.mismip_plus.geometry import (
    CALVING_X,
    ICE_DENSITY,
    OCEAN_DENSITY,
)

#: The thickness in m of floating ice below which it is calved
CALVING_THICKNESS = 100.0


def get_floating_mask(
    thickness,
    bed_topography,
    ice_density=ICE_DENSITY,
    ocean_density=OCEAN_DENSITY,
    sea_level=0.0,
):
    """
    Get where ice floats by MALI's flotation test, in which ice exactly at
    flotation floats

    Parameters
    ----------
    thickness : numpy.ndarray
        The ice thickness in m

    bed_topography : numpy.ndarray
        The bed elevation in m

    ice_density : float, optional
        The density of ice in kg m^-3

    ocean_density : float, optional
        The density of seawater in kg m^-3

    sea_level : float, optional
        The sea level in m

    Returns
    -------
    floating : numpy.ndarray
        Whether there is floating ice
    """
    thickness = np.asarray(thickness)
    return np.logical_and(
        thickness > 0.0,
        ice_density / ocean_density * thickness
        <= sea_level - np.asarray(bed_topography),
    )


def get_grounded_mask(
    thickness,
    bed_topography,
    ice_density=ICE_DENSITY,
    ocean_density=OCEAN_DENSITY,
    sea_level=0.0,
):
    """
    Get where there is ice that is not floating by MALI's flotation test

    Parameters
    ----------
    thickness : numpy.ndarray
        The ice thickness in m

    bed_topography : numpy.ndarray
        The bed elevation in m

    ice_density : float, optional
        The density of ice in kg m^-3

    ocean_density : float, optional
        The density of seawater in kg m^-3

    sea_level : float, optional
        The sea level in m

    Returns
    -------
    grounded : numpy.ndarray
        Whether there is grounded ice
    """
    floating = get_floating_mask(
        thickness, bed_topography, ice_density, ocean_density, sea_level
    )
    has_ice = np.asarray(thickness) > 0.0
    return np.logical_and(has_ice, np.logical_not(floating))


def calve(
    thickness,
    bed_topography,
    x_cell,
    calving_thickness=CALVING_THICKNESS,
    calving_x=CALVING_X,
    ice_density=ICE_DENSITY,
    ocean_density=OCEAN_DENSITY,
):
    """
    Remove floating ice thinner than the calving thickness and all ice
    beyond the calving front

    Parameters
    ----------
    thickness : numpy.ndarray
        The ice thickness in m on MALI's cells.  A leading time dimension is
        allowed.

    bed_topography : numpy.ndarray
        The bed elevation in m on MALI's cells

    x_cell : numpy.ndarray
        The x coordinate in m of MALI's cells

    calving_thickness : float, optional
        The thickness in m below which floating ice is calved

    calving_x : float, optional
        The x coordinate in m beyond which ice is calved

    ice_density : float, optional
        The density of ice in kg m^-3

    ocean_density : float, optional
        The density of seawater in kg m^-3

    Returns
    -------
    thickness : numpy.ndarray
        The calved thickness
    """
    thickness = np.asarray(thickness)
    floating = get_floating_mask(
        thickness, bed_topography, ice_density, ocean_density
    )
    calved = np.logical_or(
        np.logical_and(floating, thickness < calving_thickness),
        np.asarray(x_cell) > calving_x,
    )
    return np.where(calved, 0.0, thickness)
