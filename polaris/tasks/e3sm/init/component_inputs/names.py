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

_MESH_DIR = 'inputdata/share/meshes/mpas/unified'


def get_mesh_short_name(config: PolarisConfigParser) -> str:
    """
    The E3SM short name of the mesh the files are staged for.

    A Polaris mesh name says how a mesh was built (``u.oi30.lr10``); an E3SM
    short name identifies a released mesh (``u02.oi30.lr10``), and the
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

    Under ``share/meshes/mpas/unified/`` rather than Compass'
    ``share/meshes/mpas/ocean/``: for a unified mesh the base mesh belongs to
    the ocean, sea-ice, land and river components equally, and filing it under
    the ocean would misdescribe it.

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
    return f'{_MESH_DIR}/{short_name}.base.{creation_date}.nc'


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
    return f'{_MESH_DIR}/{short_name}.{region}.scrip.{creation_date}.nc'


def ocean_mesh_path(short_name: str, creation_date: str) -> str:
    """
    Where the MPAS-Ocean mesh file is staged.

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
    return f'{_ocean_dir(short_name)}/{short_name}.{creation_date}.nc'


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


def seaice_mesh_path(short_name: str, creation_date: str) -> str:
    """
    Where the MPAS-Seaice mesh file is staged.

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
    return f'{_seaice_dir(short_name)}/{short_name}.{creation_date}.nc'


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
