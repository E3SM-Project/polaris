"""
The MISMIP+ diagnostics, computed from the flotation criterion with the
protocol's densities
"""

from polaris.landice import diagnostics
from polaris.landice.mismip_plus.geometry import (
    DOMAIN_WIDTH,
    ICE_DENSITY,
    OCEAN_DENSITY,
)


def thickness_above_flotation(thickness, bed):
    """
    Compute the thickness above flotation with the MISMIP+ densities

    Parameters
    ----------
    thickness : xarray.DataArray
        The ice thickness in m

    bed : xarray.DataArray
        The bed elevation in m, relative to sea level

    Returns
    -------
    haf : xarray.DataArray
        The thickness above flotation in m, positive where ice is grounded
    """
    return diagnostics.thickness_above_flotation(
        thickness, bed, ICE_DENSITY, OCEAN_DENSITY
    )


def compute_diagnostics(ds, ds_mesh=None):
    """
    Compute the ice volume, volume above flotation, grounded area and
    centerline grounding line of MISMIP+

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``thickness`` and ``bedTopography``, with or without a
        ``Time`` dimension

    ds_mesh : xarray.Dataset, optional
        A dataset with ``areaCell``, ``xCell``, ``yCell`` and ``dcEdge``, by
        default ``ds``

    Returns
    -------
    ds_diag : xarray.Dataset
        The diagnostics ``iceVolume`` (m^3), ``iceVAF`` (m^3),
        ``groundedArea`` (m^2) and ``xGL`` (m), the position at which the
        grounding line crosses the centerline, with the same ``Time``
        dimension as ``ds``
    """
    if ds_mesh is None:
        ds_mesh = ds
    ds_diag = diagnostics.compute_volume_and_area(
        ds.thickness,
        ds.bedTopography,
        ds_mesh.areaCell,
        ICE_DENSITY,
        OCEAN_DENSITY,
    )
    haf = thickness_above_flotation(ds.thickness, ds.bedTopography)
    ds_diag['xGL'] = diagnostics.grounding_line_on_row(
        haf, ds_mesh, y=0.5 * DOMAIN_WIDTH
    )
    ds_diag['xGL'].attrs['units'] = 'm'
    return ds_diag
