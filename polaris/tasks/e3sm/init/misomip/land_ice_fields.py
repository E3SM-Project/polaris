"""
The ocean's land-ice fields, as E3SM's coupler delivers them from MALI

This reproduces three pieces of FAnSSIE's E3SM: the ice-shelf fields that
MALI exports to the coupler, the coupler's unnormalized mapping of them with
the glc-to-ocean map, and the normalization MPAS-Ocean applies when it
imports land-ice geometry.
"""

import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from scipy.sparse import csr_matrix

from polaris.landice.mismip_plus.geometry import ICE_DENSITY, OCEAN_DENSITY
from polaris.tasks.e3sm.init.misomip.calving import (
    get_floating_mask,
    get_grounded_mask,
)

#: E3SM's gravitational acceleration in m s^-2
GRAVITY = constants['SHR_CONST_G']

#: The fields MALI exports for ice-shelf coupling
EXPORT_FIELDS = [
    'below_sea_level_mask',
    'lithop',
    'icemask_floating',
    'icemask_grounded',
]


def compute_mali_export(
    thickness,
    bed_topography,
    ice_density=ICE_DENSITY,
    ocean_density=OCEAN_DENSITY,
    gravity=GRAVITY,
    sea_level=0.0,
):
    """
    Compute the ice-shelf fields that MALI exports to the coupler

    Every field is masked where the bed is above sea level, where there can
    be no ocean.

    Parameters
    ----------
    thickness : numpy.ndarray
        The ice thickness in m on MALI's cells.  A leading time dimension is
        allowed.

    bed_topography : numpy.ndarray
        The bed elevation in m on MALI's cells

    ice_density : float, optional
        The density of ice in kg m^-3

    ocean_density : float, optional
        The density of seawater in kg m^-3, for MALI's flotation test

    gravity : float, optional
        The gravitational acceleration in m s^-2

    sea_level : float, optional
        The sea level in m

    Returns
    -------
    export : dict of str to numpy.ndarray
        The fields in :py:data:`EXPORT_FIELDS`: the below-sea-level mask
        :math:`m`, the pressure :math:`m \\rho_i g H`, and :math:`m` times
        MALI's floating and grounded masks
    """
    thickness = np.asarray(thickness, dtype=float)
    below = (np.asarray(bed_topography) <= sea_level).astype(float)
    floating = get_floating_mask(
        thickness, bed_topography, ice_density, ocean_density, sea_level
    )
    grounded = get_grounded_mask(
        thickness, bed_topography, ice_density, ocean_density, sea_level
    )
    below = np.broadcast_to(below, thickness.shape)
    return {
        'below_sea_level_mask': below.copy(),
        'lithop': below * thickness * ice_density * gravity,
        'icemask_floating': below * floating,
        'icemask_grounded': below * grounded,
    }


def read_map(filename):
    """
    Read a map in SCRIP format as a sparse matrix

    Parameters
    ----------
    filename : str
        The map file

    Returns
    -------
    matrix : scipy.sparse.csr_matrix
        The weights, with a row for each destination cell and a column for
        each source cell
    """
    with xr.open_dataset(filename) as ds:
        shape = (ds.sizes['n_b'], ds.sizes['n_a'])
        matrix = csr_matrix(
            (ds.S.values, (ds.row.values - 1, ds.col.values - 1)),
            shape=shape,
        )
    return matrix


def apply_map(matrix, field):
    """
    Map a field as E3SM's coupler maps MALI's ice-shelf fields, without
    normalizing

    Parameters
    ----------
    matrix : scipy.sparse.csr_matrix
        The weights, from :py:func:`read_map`

    field : numpy.ndarray
        The field on the source cells.  A leading time dimension is allowed.

    Returns
    -------
    mapped : numpy.ndarray
        The field on the destination cells
    """
    field = np.asarray(field, dtype=float)
    return np.asarray(matrix @ field.T).T


def import_geometry(mapped):
    """
    Normalize the mapped fields as MPAS-Ocean does when it imports land-ice
    geometry

    Parameters
    ----------
    mapped : dict of str to numpy.ndarray
        MALI's exports on the ocean's cells, from :py:func:`apply_map`

    Returns
    -------
    fields : dict of str to numpy.ndarray
        ``landIcePressure``, ``landIceFraction``, ``landIceFloatingFraction``
        and ``landIceGroundedFraction``, the difference of the two fractions.
        All are zero where no part of a cell is below sea level in MALI.
    """
    below = mapped['below_sea_level_mask']
    has_ocean = below > 0.0
    denominator = np.where(has_ocean, below, 1.0)
    pressure = np.where(has_ocean, mapped['lithop'] / denominator, 0.0)
    floating = mapped['icemask_floating']
    floating_fraction = np.where(
        has_ocean, np.minimum(floating / denominator, 1.0), 0.0
    )
    land_ice_fraction = np.where(
        has_ocean,
        np.minimum((floating + mapped['icemask_grounded']) / denominator, 1.0),
        0.0,
    )
    return {
        'landIcePressure': pressure,
        'landIceFraction': land_ice_fraction,
        'landIceFloatingFraction': floating_fraction,
        'landIceGroundedFraction': land_ice_fraction - floating_fraction,
    }
