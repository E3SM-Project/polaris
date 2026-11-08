"""
The E3SM-facing names and paths that are particular to unified meshes.

Paths that any E3SM workflow stages the same way, keyed by E3SM's grid name,
are in :py:mod:`polaris.e3sm.init.inputdata`; the ones here follow from a
unified mesh's short name.  Between the two modules, the layout of the
assembled tree is described in one place rather than scattered across the
steps that write into it.  Like :py:mod:`polaris.e3sm.init.inputdata`, this
module imports no step and opens no file, so the naming rules can be unit
tested without a work directory.
"""

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.inputdata import get_nonempty_option, ocean_dir

#: The culled-mesh regions a SCRIP file is staged for, matching the prefixes
#: the cull step writes.
SCRIP_REGIONS = ('ocean', 'ocean_no_cavities', 'land')

#: The culled-mesh regions whose SCRIP file is also staged beside the ocean
#: products, where the ``ocean`` in the region name is redundant and is
#: dropped from the filename.
OCEAN_SCRIP_REGIONS = ('ocean', 'ocean_no_cavities')

#: The culled-mesh regions whose mesh itself is staged.  ``ocean_no_cavities``
#: is not among them: it exists to build mapping files, and under the
#: ``calving_front`` convention every current unified mesh uses it is identical
#: to ``ocean`` anyway, so staging it would be a second copy of the same mesh.
MESH_REGIONS = ('ocean', 'land')

_UNIFIED_MESH_DIR = 'inputdata/share/meshes/mpas/unified'


def get_mesh_short_name(config: PolarisConfigParser) -> str:
    """
    The E3SM short name of the mesh the files are staged for.

    A Polaris mesh name says how a mesh was built (``u-oi30-lr10``); an E3SM
    short name identifies a released mesh (``u02-oi30-lr10``), and the
    two-digit ID is what distinguishes two meshes built to the same recipe at
    different times.  Only a person can decide a mesh has earned one, so there
    is no default and no autodetection from a restart file's global attributes.

    Unified meshes register theirs as ``[unified_mesh] e3sm_short_name``.
    ``[component_inputs] mesh_short_name`` overrides that when set.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the component-input steps.

    Returns
    -------
    str
        The E3SM short name.

    Raises
    ------
    ValueError
        If neither option is set.
    """
    short_name = get_nonempty_option(
        config, 'component_inputs', 'mesh_short_name'
    )
    if short_name is not None:
        return short_name

    short_name = get_nonempty_option(config, 'unified_mesh', 'e3sm_short_name')
    if short_name is not None:
        return short_name

    raise ValueError(
        'This mesh has no E3SM short name, so the component input files '
        'cannot be named.  Set [component_inputs] mesh_short_name, or '
        'register the mesh by setting [unified_mesh] e3sm_short_name in its '
        'config file.'
    )


def base_mesh_path(short_name: str, creation_date: str) -> str:
    """
    Where the base mesh, carrying the base-to-culled index maps, is staged.

    Under ``share/meshes/mpas/unified/<id>/`` rather than Compass'
    ``share/meshes/mpas/ocean/``: for a unified mesh the base mesh belongs to
    the ocean, sea-ice, land and river components equally, and filing it under
    the ocean would misdescribe it.  The per-mesh subdirectory keeps one
    mesh's files together -- see :py:func:`_mesh_dir`.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to
        :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.
    """
    return f'{_mesh_dir(short_name)}/{short_name}.base.{creation_date}.nc'


def scrip_path(short_name: str, creation_date: str, region: str) -> str:
    """
    Where the SCRIP description of one culled mesh is staged.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    region : str
        The culled-mesh region, one of :py:data:`SCRIP_REGIONS`.

    Returns
    -------
    str
        The path, relative to
        :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.

    Raises
    ------
    ValueError
        If ``region`` is not a region a SCRIP file is staged for.
    """
    if region not in SCRIP_REGIONS:
        raise ValueError(
            f'No SCRIP file is staged for the region {region!r}.  Expected '
            f'one of {", ".join(SCRIP_REGIONS)}.'
        )
    return (
        f'{_mesh_dir(short_name)}/'
        f'{short_name}.{region}.scrip.{creation_date}.nc'
    )


def ocean_scrip_path(short_name: str, creation_date: str, region: str) -> str:
    """
    Where a SCRIP description is staged beside the ocean products.

    The same files are staged under ``share/meshes/mpas/unified/<id>/``
    by :py:func:`scrip_path`.  They are in both places because developers look
    for them in both: with the mesh files and with the ocean files that were
    built from them.

    Under ``ocn/mpas-o/`` the ``ocean`` in a region name says nothing -- every
    file there is the ocean's -- so it is dropped, leaving
    ``<short>.scrip.<date>.nc`` for the ocean domain and
    ``<short>.no_cavities.scrip.<date>.nc`` for the one without ice-shelf
    cavities.  Land has no copy here, having no business in an ocean
    directory.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    region : str
        The culled-mesh region, one of :py:data:`OCEAN_SCRIP_REGIONS`.

    Returns
    -------
    str
        The path, relative to
        :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.

    Raises
    ------
    ValueError
        If ``region`` is not a region staged beside the ocean products.
    """
    if region not in OCEAN_SCRIP_REGIONS:
        raise ValueError(
            f'No SCRIP file is staged beside the ocean products for the '
            f'region {region!r}.  Expected one of '
            f'{", ".join(OCEAN_SCRIP_REGIONS)}.'
        )
    suffix = region[len('ocean') :].lstrip('_')
    stem = f'{short_name}.{suffix}.scrip' if suffix else f'{short_name}.scrip'
    grid = ocean_grid_name(short_name)
    return f'{ocean_dir(grid)}/{stem}.{creation_date}.nc'


def culled_mesh_path(short_name: str, creation_date: str, region: str) -> str:
    """
    Where one culled mesh is staged.

    Next to the base mesh under ``share/meshes/mpas/unified/<id>/``
    rather than under a component's own directory, for the same reason the
    base mesh is there: a culled mesh describes a domain of the unified mesh,
    not a file one component reads at run time.  Compass files its ocean mesh
    under ``share/meshes/mpas/ocean/`` and E3SM never reads it from
    ``ocn/mpas-o/``, where an earlier version of this workflow put it.

    The ocean mesh carries the vertical coordinate as well, since that is what
    makes it an ocean mesh rather than a horizontal one; the land mesh is
    staged as the cull step wrote it.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    region : str
        The culled-mesh region, one of :py:data:`MESH_REGIONS`.

    Returns
    -------
    str
        The path, relative to
        :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.

    Raises
    ------
    ValueError
        If ``region`` is not a region whose mesh is staged.
    """
    if region not in MESH_REGIONS:
        raise ValueError(
            f'No mesh is staged for the region {region!r}.  Expected one of '
            f'{", ".join(MESH_REGIONS)}.'
        )
    return f'{_mesh_dir(short_name)}/{short_name}.{region}.{creation_date}.nc'


def ocean_moc_masks_path(
    short_name: str, creation_date: str, features_date: str
) -> str:
    """
    Where the MOC basin masks and southern-boundary transects are staged.

    Two dates appear here because two things change independently: the
    ``geometric_features`` aggregation the regions come from, which is
    upstream data shared by every mesh, and the date this mesh's file was
    created.  The aggregation date belongs to the product name, as it does in
    the files already on the inputdata server
    (``oRRS18to6v3_mocBasinsAndTransects20210623.nc``); the creation date
    stays in the trailing field, where every other staged file carries it.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    features_date : str
        The date stamp of the ``geometric_features`` aggregation, as
        ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to
        :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.
    """
    return (
        f'{ocean_dir(ocean_grid_name(short_name))}/'
        f'{short_name}.mocBasinsAndTransects{features_date}.{creation_date}.nc'
    )


def ocean_grid_name(short_name: str) -> str:
    """
    E3SM's name for the ocean and sea-ice grid of a mesh.

    E3SM splits a unified mesh into an ``ocnice`` grid and a land and river
    grid, named for the ID and the matching half of the short name:
    ``u02-oi30`` and ``u02-lr10`` for ``u02-oi30-lr10``.  The ocean and
    sea-ice directories and initial conditions are named for the ``ocnice``
    grid.  A short name with no land part, as an override might give for an
    ocean-only mesh, is the grid name as it stands.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    Returns
    -------
    str
        E3SM's name for the ocean and sea-ice grid.
    """
    if '-lr' not in short_name:
        return short_name
    return short_name.rsplit('-lr', 1)[0]


def _mesh_dir(short_name: str) -> str:
    """
    The shared mesh directory for one unified mesh.

    Every unified mesh gets its own subdirectory, named for the two-digit ID
    that leads its E3SM short name (``u02`` for ``u02-oi30-lr10``), as on the
    inputdata server and in E3SM's own references to these files.  The flat
    directory it replaced held half a dozen files per mesh -- a base mesh,
    three SCRIP descriptions and two culled meshes -- so with more than a
    couple of meshes in it there was no way to see which files belonged
    together.  The short name is already in every filename; what the
    subdirectory adds is that the mesh's files are listed together and can be
    copied or removed as a unit.
    """
    return f'{_UNIFIED_MESH_DIR}/{_mesh_id(short_name)}'


def _mesh_id(short_name: str) -> str:
    """
    The ID that leads an E3SM short name: ``u02`` for ``u02-oi30-lr10``.
    """
    return short_name.split('-', 1)[0]
