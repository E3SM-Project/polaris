"""
General names and paths for files staged in an inputdata-style tree.

The paths here are keyed by E3SM's grid name for a component (``u02-oi30``
for the ocean and sea-ice grid of ``u02-oi30-lr10``), not by how a mesh was
built, so any workflow that stages files for E3SM can use them.  Like the
rest of the staging helpers, this module imports no step and opens no file.
"""

from datetime import datetime

from polaris.config import PolarisConfigParser

#: The directory an assembly step materializes, relative to its work
#: directory.  Every path this module returns is relative to this.
ASSEMBLED_FILES = 'assembled_files'


def get_nonempty_option(
    config: PolarisConfigParser, section: str, option: str
) -> str | None:
    """
    The stripped value of a config option, or ``None`` if it is unset or
    blank.  Blank is how a config file declares an option that has no
    default, such as a name only a person can assign.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options.

    section : str
        The config section.

    option : str
        The config option.

    Returns
    -------
    str or None
        The value, or ``None``.
    """
    if not config.has_option(section, option):
        return None
    value = config.get(section, option).strip()
    return value if value else None


def get_creation_date(config: PolarisConfigParser, section: str) -> str:
    """
    The creation date the staged files are stamped with, as ``YYYYMMDD``.

    The last dotted field of a staged filename before ``.nc`` (or before
    ``.part.<n>`` for a partition) is its creation date.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options.

    section : str
        The config section with the ``creation_date`` option.

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
    creation_date = get_nonempty_option(config, section, 'creation_date')
    if creation_date is None:
        raise ValueError(
            f'No [{section}] creation_date is set.  It is normally filled in '
            f'at setup time.'
        )
    return creation_date


def set_creation_date(config: PolarisConfigParser, section: str) -> str:
    """
    Set the creation date to today if it is not already set, and return it.

    Called at setup so the date lands in the work directory's config file.
    Re-running a step then reuses the date it was set up with, rather than
    silently renaming every staged file to today's.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options, updated in place.

    section : str
        The config section with the ``creation_date`` option.

    Returns
    -------
    str
        The creation date, as ``YYYYMMDD``.
    """
    creation_date = get_nonempty_option(config, section, 'creation_date')
    if creation_date is None:
        creation_date = datetime.now().strftime('%Y%m%d')
        config.set(section, 'creation_date', creation_date)
    return creation_date


def ocean_dir(grid: str) -> str:
    """
    The MPAS-Ocean directory for a grid.

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'inputdata/ocn/mpas-o/{grid}'


def seaice_dir(grid: str) -> str:
    """
    The MPAS-Seaice directory for a grid.

    Parameters
    ----------
    grid : str
        E3SM's name for the sea-ice grid.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'inputdata/ice/mpas-seaice/{grid}'


def ocean_initial_condition_path(grid: str, creation_date: str) -> str:
    """
    Where the MPAS-Ocean initial condition for a grid is staged.

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{ocean_dir(grid)}/mpaso.{grid}.{creation_date}.nc'


def ocean_graph_path(grid: str, creation_date: str) -> str:
    """
    Where the unpartitioned MPAS-Ocean graph is staged, beside its partitions.

    With it, a partition for a core count that was not staged can be made
    later without the work directory.

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{ocean_dir(grid)}/partitions/mpas-o.graph.info.{creation_date}'


def ocean_partition_path(grid: str, creation_date: str, ncores: int) -> str:
    """
    Where one MPAS-Ocean graph partition is staged.

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    ncores : int
        The number of partitions the graph was divided into.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{ocean_graph_path(grid, creation_date)}.part.{ncores}'


def seaice_initial_condition_path(grid: str, creation_date: str) -> str:
    """
    Where the MPAS-Seaice initial condition for a grid is staged.

    Parameters
    ----------
    grid : str
        E3SM's name for the sea-ice grid.

    creation_date : str
        The creation date, as ``YYYYMMDD``.

    Returns
    -------
    str
        The path, relative to :py:data:`ASSEMBLED_FILES`.
    """
    return f'{seaice_dir(grid)}/mpassi.{grid}.{creation_date}.nc'


def seaice_partition_path(grid: str, creation_date: str, ncores: int) -> str:
    """
    Where one MPAS-Seaice graph partition is staged.

    Parameters
    ----------
    grid : str
        E3SM's name for the sea-ice grid.

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
        f'{seaice_dir(grid)}/partitions/'
        f'mpas-seaice.graph.info.{creation_date}.part.{ncores}'
    )
