import numpy as np


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
    5. Under ``calving_front`` the ocean and the ocean without cavities
       are identical, so the ocean and the land partition the base mesh.
       Under that convention ``ocean_frac`` and ``ice_frac`` are averages
       of disjoint source-resolution sets, so ``ice_frac > 0.5`` implies
       ``ocean_frac < 0.5`` and every land-ice cell is already outside
       the ocean on the fraction test alone.

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

    if convention == 'calving_front':
        _add_problem(
            problems,
            mask=ocean != no_cavities,
            message=(
                'cells differ between the ocean and the ocean without '
                f'ice-shelf cavities, but the {convention} convention '
                'leaves no ice-shelf cavities for them to differ by'
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
