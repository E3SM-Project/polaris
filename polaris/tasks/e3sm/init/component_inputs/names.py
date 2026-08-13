"""
The E3SM-facing names and paths of the staged component input files.

Every staged path is a function here, so the layout of the assembled tree is
described in one place rather than scattered across the steps that write into
it.  This module is deliberately dependency-light -- it imports no step and
opens no file -- so the naming rules can be unit tested without a work
directory.
"""

from datetime import datetime

from polaris.config import PolarisConfigParser

#: The directory an assembly step materializes, relative to its work
#: directory.  Every path this module returns is relative to this.
ASSEMBLED_FILES = 'assembled_files'

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
    short_name = _get_nonempty(config, 'component_inputs', 'mesh_short_name')
    if short_name is not None:
        return short_name

    short_name = _get_nonempty(config, 'unified_mesh', 'e3sm_short_name')
    if short_name is not None:
        return short_name

    raise ValueError(
        'This mesh has no E3SM short name, so the component input files '
        'cannot be named.  Set [component_inputs] mesh_short_name, or '
        'register the mesh by setting [unified_mesh] e3sm_short_name in its '
        'config file.'
    )


def get_creation_date(config: PolarisConfigParser) -> str:
    """
    The creation date the staged files are stamped with, as ``YYYYMMDD``.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the component-input steps.

    Returns
    -------
    str
        The creation date.

    Raises
    ------
    ValueError
        If the date has not been set.  :py:func:`set_creation_date` sets it at
        setup time, so this means it was cleared afterwards.
    """
    creation_date = _get_nonempty(config, 'component_inputs', 'creation_date')
    if creation_date is None:
        raise ValueError(
            'No [component_inputs] creation_date is set.  It is normally '
            'filled in at setup time.'
        )
    return creation_date


def set_creation_date(config: PolarisConfigParser) -> str:
    """
    Set the creation date to today if it is not already set, and return it.

    Called at setup so the date lands in the work directory's config file.
    Re-running a step then reuses the date it was set up with, rather than
    silently renaming every staged file to today's.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options for the component-input steps, updated in place.

    Returns
    -------
    str
        The creation date, as ``YYYYMMDD``.
    """
    creation_date = _get_nonempty(config, 'component_inputs', 'creation_date')
    if creation_date is None:
        creation_date = datetime.now().strftime('%Y%m%d')
        config.set('component_inputs', 'creation_date', creation_date)
    return creation_date


def base_mesh_path(short_name: str, creation_date: str) -> str:
    """
    Where the base mesh, carrying the base-to-culled index maps, is staged.

    Under ``share/meshes/mpas/unified/<short_name>/`` rather than Compass'
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
        The path, relative to :py:data:`ASSEMBLED_FILES`.
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
        The path, relative to :py:data:`ASSEMBLED_FILES`.

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

    The same files are staged under ``share/meshes/mpas/unified/<short_name>/``
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
        The path, relative to :py:data:`ASSEMBLED_FILES`.

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
    return f'{_ocean_dir(short_name)}/{stem}.{creation_date}.nc'


def culled_mesh_path(short_name: str, creation_date: str, region: str) -> str:
    """
    Where one culled mesh is staged.

    Next to the base mesh under ``share/meshes/mpas/unified/<short_name>/``
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
        The path, relative to :py:data:`ASSEMBLED_FILES`.

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


def ocean_initial_condition_path(short_name: str, creation_date: str) -> str:
    """
    Where the MPAS-Ocean initial condition is staged.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{_ocean_dir(short_name)}/mpaso.{short_name}.{creation_date}.nc'


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
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return (
        f'{_ocean_dir(short_name)}/{short_name}.mocBasinsAndTransects'
        f'{features_date}.{creation_date}.nc'
    )


def ocean_partition_path(
    short_name: str, creation_date: str, ncores: int
) -> str:
    """
    Where one MPAS-Ocean graph partition is staged.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    ncores : int
        The number of partitions the graph was divided into.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return (
        f'{_ocean_dir(short_name)}/partitions/'
        f'mpas-o.graph.info.{creation_date}.part.{ncores}'
    )


def seaice_initial_condition_path(short_name: str, creation_date: str) -> str:
    """
    Where the MPAS-Seaice initial condition is staged.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{_seaice_dir(short_name)}/mpassi.{short_name}.{creation_date}.nc'


def seaice_partition_path(
    short_name: str, creation_date: str, ncores: int
) -> str:
    """
    Where one MPAS-Seaice graph partition is staged.

    Parameters
    ----------
    short_name : str
        The E3SM short name of the mesh.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    ncores : int
        The number of partitions the graph was divided into.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return (
        f'{_seaice_dir(short_name)}/partitions/'
        f'mpas-seaice.graph.info.{creation_date}.part.{ncores}'
    )


def _mesh_dir(short_name: str) -> str:
    """
    The shared mesh directory for one unified mesh.

    Every unified mesh gets its own subdirectory, named for its E3SM short
    name.  The flat directory it replaced held half a dozen files per mesh --
    a base mesh, three SCRIP descriptions and two culled meshes -- so with
    more than a couple of meshes in it there was no way to see which files
    belonged together.  The short name is already in every filename, so the
    subdirectory adds no information; what it adds is that the mesh's files
    are listed together and can be copied or removed as a unit.
    """
    return f'{_UNIFIED_MESH_DIR}/{short_name}'


def _ocean_dir(short_name: str) -> str:
    return f'inputdata/ocn/mpas-o/{short_name}'


def _seaice_dir(short_name: str) -> str:
    return f'inputdata/ice/mpas-seaice/{short_name}'


def _get_nonempty(
    config: PolarisConfigParser, section: str, option: str
) -> str | None:
    """
    The stripped value of a config option, or ``None`` if it is unset or
    blank.  Blank is how a config file declares an option that has no default.
    """
    if not config.has_option(section, option):
        return None
    value = config.get(section, option).strip()
    return value if value else None
