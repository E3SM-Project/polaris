import numpy as np

from polaris.mesh.connectivity import (
    connected_to_seeds,
    count_active_edges,
    has_active_vertex,
    transport_link_mask,
)


def check_cull_mask_consistency(
    ocean_cull_mask,
    ocean_no_cavities_cull_mask,
    land_cull_mask,
    land_ice_mask,
    convention,
    logger,
    max_cells=20,
):
    """
    Check that the cull masks describe a consistent set of domains.

    The cull masks are expected to satisfy four invariants, and a fifth
    that applies only to the ``calving_front`` Antarctic boundary
    convention:

    1. The ocean without ice-shelf cavities is a subset of the ocean.
       Never the reverse.
    2. The land is exactly the complement of the ocean without cavities,
       so every cell on the globe is owned by exactly one of the two.
    3. The land-ice mask is zero at every cell the ocean without cavities
       retains.  Equivalently, the ice-shelf cavity cells of the ocean
       mesh are exactly the cells the ocean retains and the ocean without
       cavities does not.
    4. Critical land blockages and critical ocean passages are applied
       identically to the ocean and to the ocean without cavities.  This
       is enforced by construction in
       :py:meth:`polaris.tasks.e3sm.init.topo.cull.CullMaskStep.refine_ocean_cull_mask`
       rather than checked here.
    5. The two ocean domains differ only by ice-shelf cavities: every cell
       in the ocean but not in the ocean without cavities carries land ice.
    6. Under ``calving_front`` no cell of the ocean carries land ice, since
       that convention ends the ocean at the calving front.

    Invariants 1, 5 and 6 together mean the two ocean domains are identical
    under ``calving_front``, without that equality having to be asserted
    directly: the cells they could differ by all carry land ice, and under
    that convention the ocean has none.

    The grid criteria that decide which cells are usable at all -- two
    active edges per ocean cell, an active vertex per sea-ice cell where sea
    ice forms -- are checked separately by
    :py:func:`check_land_locked_criteria`, which needs the mesh.

    Parameters
    ----------
    ocean_cull_mask : xarray.DataArray or numpy.ndarray
        The ocean cull mask on base-mesh cells (1 where cells are culled,
        0 where they are kept as ocean/sea-ice)

    ocean_no_cavities_cull_mask : xarray.DataArray or numpy.ndarray
        The cull mask for the ocean without ice-shelf cavities

    land_cull_mask : xarray.DataArray or numpy.ndarray
        The land cull mask

    land_ice_mask : xarray.DataArray or numpy.ndarray
        The Antarctic land-ice mask (1 where land ice is present)

    convention : str
        The Antarctic boundary convention the masks were built with, from
        ``spherical_mesh.antarctic_boundary_convention``

    logger : logging.Logger
        The logger for summary output

    max_cells : int, optional
        The maximum number of offending cell indices to report per
        invariant

    Raises
    ------
    ValueError
        If any of the invariants is violated
    """
    ocean = np.asarray(ocean_cull_mask) == 0
    no_cavities = np.asarray(ocean_no_cavities_cull_mask) == 0
    land = np.asarray(land_cull_mask) == 0
    land_ice = np.asarray(land_ice_mask) > 0

    problems: list[str] = []

    _add_problem(
        problems,
        mask=no_cavities & ~ocean,
        message=(
            'cells are in the ocean without ice-shelf cavities but not in '
            'the ocean'
        ),
        max_cells=max_cells,
    )

    _add_problem(
        problems,
        mask=land != ~no_cavities,
        message=(
            'cells where the land is not the complement of the ocean '
            'without ice-shelf cavities'
        ),
        max_cells=max_cells,
    )

    _add_problem(
        problems,
        mask=land_ice & no_cavities,
        message=(
            'cells are flagged as land ice but are retained by the ocean '
            'without ice-shelf cavities'
        ),
        max_cells=max_cells,
    )

    _add_problem(
        problems,
        mask=ocean & ~no_cavities & ~land_ice,
        message=(
            'cells are in the ocean but not in the ocean without ice-shelf '
            'cavities, yet carry no land ice, so the two domains differ by '
            'something other than a cavity'
        ),
        max_cells=max_cells,
    )

    if convention == 'calving_front':
        _add_problem(
            problems,
            mask=ocean & land_ice,
            message=(
                f'cells in the ocean carry land ice, but the {convention} '
                'convention leaves no ice-shelf cavities in the ocean'
            ),
            max_cells=max_cells,
        )

    counts = (
        f'ocean {int(ocean.sum())}, '
        f'ocean without cavities {int(no_cavities.sum())}, '
        f'land {int(land.sum())}, '
        f'land ice {int(land_ice.sum())} '
        f'of {ocean.size} base-mesh cells'
    )

    if problems:
        message = (
            'The cull masks are not consistent with each other '
            f'({convention} convention; {counts}):\n' + '\n'.join(problems)
        )
        logger.error(message)
        raise ValueError(message)

    logger.info(f'Cull mask consistency check passed: {counts}.')


def check_land_locked_criteria(
    ds_mesh,
    ocean_cull_mask,
    ocean_no_cavities_cull_mask,
    latitude_threshold,
    logger,
    max_cells=20,
):
    """
    Check that no land-locked cells survive in either ocean domain.

    Three post-conditions of removing land-locked cells:

    1. Every cell of either domain has at least two active edges, so that a
       C-grid has a way to move water in and a way to move it out.
    2. Every cell of the ocean without cavities poleward of the sea-ice
       latitude threshold has at least one active vertex, so that a B-grid
       has a velocity point by which ice can leave it.
    3. Every cell of the ocean without cavities can reach the part of that
       domain equatorward of the threshold, where ice melts, over edges
       that carry B-grid flux.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell``, ``nEdgesOnCell`` and ``latCell``

    ocean_cull_mask : xarray.DataArray or numpy.ndarray
        The ocean cull mask on base-mesh cells (1 where cells are culled)

    ocean_no_cavities_cull_mask : xarray.DataArray or numpy.ndarray
        The cull mask for the ocean without ice-shelf cavities

    latitude_threshold : float
        The latitude in degrees poleward of which sea ice can form

    logger : logging.Logger
        The logger for summary output

    max_cells : int, optional
        The maximum number of offending cell indices to report

    Raises
    ------
    ValueError
        If any of the criteria is violated
    """
    ocean = np.asarray(ocean_cull_mask) == 0
    no_cavities = np.asarray(ocean_no_cavities_cull_mask) == 0
    poleward = np.abs(np.degrees(ds_mesh.latCell.values)) >= latitude_threshold

    problems: list[str] = []

    for name, mask in [
        ('the ocean', ocean),
        ('the ocean without ice-shelf cavities', no_cavities),
    ]:
        _add_problem(
            problems,
            mask=mask & (count_active_edges(ds_mesh, mask) < 2),
            message=f'cells of {name} have fewer than two active edges',
            max_cells=max_cells,
        )

    _add_problem(
        problems,
        mask=no_cavities & poleward & ~has_active_vertex(ds_mesh, no_cavities),
        message=(
            'cells of the ocean without ice-shelf cavities poleward of the '
            'sea-ice latitude threshold have no active vertex, so sea ice '
            'there has no velocity point to leave by'
        ),
        max_cells=max_cells,
    )

    seeds = no_cavities & ~poleward
    if seeds.any():
        reachable = connected_to_seeds(
            ds_mesh,
            no_cavities,
            seeds,
            link_mask=transport_link_mask(ds_mesh, no_cavities),
        )
        _add_problem(
            problems,
            mask=no_cavities & ~reachable,
            message=(
                'cells of the ocean without ice-shelf cavities cannot move '
                'sea ice to the equatorward part of the domain, where it '
                'melts'
            ),
            max_cells=max_cells,
        )

    if problems:
        message = (
            'Land-locked cells survive in the culled ocean domains:\n'
            + '\n'.join(problems)
        )
        logger.error(message)
        raise ValueError(message)

    logger.info('Land-locked cell check passed.')


def check_critical_passages(
    ocean_cull_mask,
    ds_transects,
    logger,
    max_cells=10,
):
    """
    Check that no cell on a critical ocean passage was culled from the
    ocean.

    A critical passage exists to keep a strait open that the topography
    alone would close, so a cell removed from one is a passage that the
    mesh cannot support: either it is too coarse to resolve the strait, or
    the transect wanders onto land.  Either way the transect is the thing
    to fix, so the error names it.

    Parameters
    ----------
    ocean_cull_mask : xarray.DataArray or numpy.ndarray
        The final ocean cull mask on base-mesh cells (1 where cells are
        culled, 0 where they are kept)

    ds_transects : xarray.Dataset
        The widened critical ocean transects, with ``transectCellMasks``
        and ``transectNames``

    logger : logging.Logger
        The logger for summary output

    max_cells : int, optional
        The maximum number of offending cell indices to report per transect

    Raises
    ------
    ValueError
        If any critical passage lost a cell
    """
    culled = np.asarray(ocean_cull_mask) > 0
    cell_masks = ds_transects.transectCellMasks.values > 0
    names = [_decode(name) for name in ds_transects.transectNames.values]

    problems: list[str] = []
    for index, name in enumerate(names):
        _add_problem(
            problems,
            mask=culled & cell_masks[:, index],
            message=f'cells culled from the ocean on {name!r}',
            max_cells=max_cells,
        )

    if problems:
        message = (
            'Critical ocean passages lost cells to the removal of '
            'land-locked cells. The mesh cannot keep these passages open, '
            'so the transects need modification in geometric_features (or '
            'the mesh needs more resolution there):\n' + '\n'.join(problems)
        )
        logger.error(message)
        raise ValueError(message)

    logger.info(
        f'Critical ocean passage check passed: {len(names)} transects intact.'
    )


def _decode(name):
    """
    Decode a transect name that may be stored as bytes.
    """
    if isinstance(name, bytes):
        return name.decode()
    return str(name)


def _add_problem(problems, mask, message, max_cells):
    """
    Append a description of the offending cells to ``problems`` if any.
    """
    count = int(np.count_nonzero(mask))
    if count == 0:
        return

    indices = np.nonzero(mask)[0]
    listed = ', '.join(str(index) for index in indices[:max_cells])
    if count > max_cells:
        listed = f'{listed}, ...'
    problems.append(f'  {count} {message}: {listed}')
