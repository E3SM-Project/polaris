import numpy as np

from polaris.mesh.connectivity import (
    active_edge_masks,
    connected_to_seeds,
    transport_link_mask,
)


def remove_ocean_land_locked_cells(ds_mesh, ocean_mask, ocean_seed_mask):
    """
    Refine the ocean domain alone, removing the cells through which a C-grid
    cannot circulate and those that are not connected to the open ocean.

    A cell needs at least two active edges, a way in and a way out.  The two
    need not be adjacent and no condition on vertices applies, because the
    ocean's velocities live at edges.

    This is the ocean half of :py:func:`remove_land_locked_cells` and is used
    on its own where the ocean domain is needed before the land-ice mask
    exists.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    ocean_mask : numpy.ndarray
        A boolean mask on cells, True for the candidate ocean domain

    ocean_seed_mask : numpy.ndarray
        A boolean mask on cells, True at the seed cells for the flood fill

    Returns
    -------
    ocean_mask : numpy.ndarray
        The refined ocean domain
    """
    ocean = np.asarray(ocean_mask).astype(bool).copy()
    seeds = np.asarray(ocean_seed_mask).astype(bool)
    ocean = _enforce_ocean_criteria(ds_mesh, ocean)
    return connected_to_seeds(ds_mesh, ocean, seeds)


def remove_land_locked_cells(
    ds_mesh,
    ocean_mask,
    no_cavities_mask,
    land_ice_mask,
    ocean_seed_mask,
    latitude_threshold,
    logger=None,
    max_iterations=100,
):
    """
    Refine the ocean and ocean-without-cavities domains together, removing
    the cells in which the ocean cannot circulate and those in which sea ice
    would be trapped.

    The two models make different demands on the mesh.  MPAS-Ocean and Omega
    are C-grids with velocities at edges, so an ocean cell needs at least two
    active edges: a way in and a way out.  MPAS-Seaice is a B-grid with
    velocities at vertices, so a sea-ice cell needs at least one active
    vertex, or ice drifting into it has no velocity point to leave by.  The
    vertex criterion is the stronger of the two and applies only where sea
    ice can form.

    The two domains are refined together rather than in sequence, because
    removing a cell from one can strand a cell in the other.  Each pass only
    ever removes cells, so the alternation terminates.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell``, ``nEdgesOnCell`` and ``latCell``

    ocean_mask : numpy.ndarray
        A boolean mask on cells, True for the candidate ocean domain

    no_cavities_mask : numpy.ndarray
        A boolean mask on cells, True for the candidate ocean domain without
        ice-shelf cavities

    land_ice_mask : numpy.ndarray
        A boolean mask on cells, True where land ice is present.  Used to
        decide which cells may legitimately be in ``ocean`` but not in
        ``ocean_no_cavities``

    ocean_seed_mask : numpy.ndarray
        A boolean mask on cells, True at the seed cells for the ocean flood
        fill

    latitude_threshold : float
        The latitude in degrees poleward of which sea ice can form

    logger : logging.Logger, optional
        A logger for per-iteration counts

    max_iterations : int, optional
        The maximum number of alternations before giving up

    Returns
    -------
    ocean_mask : numpy.ndarray
        The refined ocean domain

    no_cavities_mask : numpy.ndarray
        The refined ocean domain without ice-shelf cavities

    Raises
    ------
    ValueError
        If the sea-ice domain has no cells equatorward of the latitude
        threshold to seed its flood fill, or if the alternation fails to
        converge
    """
    ocean = np.asarray(ocean_mask).astype(bool).copy()
    no_cavities = np.asarray(no_cavities_mask).astype(bool).copy()
    land_ice = np.asarray(land_ice_mask).astype(bool)
    seeds = np.asarray(ocean_seed_mask).astype(bool)

    lat_cell = np.degrees(ds_mesh.latCell.values)
    poleward = np.abs(lat_cell) >= latitude_threshold

    for iteration in range(max_iterations):
        n_ocean = int(ocean.sum())
        n_no_cavities = int(no_cavities.sum())

        # the ocean needs two active edges per cell and has to be contiguous
        ocean = remove_ocean_land_locked_cells(ds_mesh, ocean, seeds)

        # nothing survives without cavities that the ocean has dropped
        no_cavities = np.logical_and(no_cavities, ocean)

        # sea ice needs an active vertex where it can form, two active edges
        # everywhere, and a way to drift to where it melts
        no_cavities = _enforce_sea_ice_criteria(ds_mesh, no_cavities, poleward)
        no_cavities = _transport_connected(
            ds_mesh, no_cavities, poleward, latitude_threshold
        )

        # the two domains may differ only by ice-shelf cavities, so a cell
        # the sea ice cannot use is only kept if it is under land ice
        stranded = ocean & ~no_cavities & ~land_ice
        ocean = np.logical_and(ocean, ~stranded)

        removed_ocean = n_ocean - int(ocean.sum())
        removed_no_cavities = n_no_cavities - int(no_cavities.sum())
        if logger is not None:
            logger.info(
                f'  land-locked pass {iteration + 1}: removed '
                f'{removed_ocean} ocean and {removed_no_cavities} '
                f'no-cavities cells'
            )
        if removed_ocean == 0 and removed_no_cavities == 0:
            return ocean, no_cavities

    raise ValueError(
        f'Removing land-locked cells did not converge in {max_iterations} '
        f'alternations of the ocean and sea-ice passes.'
    )


def _enforce_ocean_criteria(ds_mesh, mask):
    """
    Remove cells with fewer than two active edges, repeating until none are
    left, since removing one cell can take a neighbor below two.
    """
    while True:
        active, _, _ = active_edge_masks(ds_mesh, mask)
        too_few = np.logical_and(mask, active.sum(axis=1) < 2)
        if not too_few.any():
            return mask
        mask = np.logical_and(mask, ~too_few)


def _enforce_sea_ice_criteria(ds_mesh, mask, poleward):
    """
    Remove cells with fewer than two active edges, and cells poleward of the
    sea-ice latitude threshold with no active vertex, repeating until none
    are left.
    """
    while True:
        active, active_next, _ = active_edge_masks(ds_mesh, mask)
        too_few = active.sum(axis=1) < 2
        no_vertex = np.logical_and(
            poleward, ~np.logical_and(active, active_next).any(axis=1)
        )
        bad = np.logical_and(mask, np.logical_or(too_few, no_vertex))
        if not bad.any():
            return mask
        mask = np.logical_and(mask, ~bad)


def _transport_connected(ds_mesh, mask, poleward, latitude_threshold):
    """
    Remove cells from which sea ice cannot drift to the equatorward part of
    the domain, where it melts.

    The fill is seeded from the domain equatorward of the latitude
    threshold.  Those cells form no ice and so cannot be removed by this
    criterion; making them the seeds is what keeps a transport-isolated
    basin such as the Mediterranean, which straddles or lies equatorward of
    the threshold, from being removed wholesale.
    """
    seeds = np.logical_and(mask, ~poleward)
    if not seeds.any():
        raise ValueError(
            f'The ocean without ice-shelf cavities has no cells equatorward '
            f'of the sea-ice latitude threshold ({latitude_threshold} '
            f'degrees), so the sea-ice transport flood fill has no seeds. '
            f'Check sea_ice_latitude_threshold.'
        )

    link_mask = transport_link_mask(ds_mesh, mask)
    return connected_to_seeds(ds_mesh, mask, seeds, link_mask=link_mask)
