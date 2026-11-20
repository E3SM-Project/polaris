"""
General names and paths for files staged in an inputdata-style tree.

The paths here are keyed by E3SM's grid name for a component (``u02-oi30``
for the ocean and sea-ice grid of ``u02-oi30-lr10``), not by how a mesh was
built, so any workflow that stages files for E3SM can use them.  Like the
rest of the staging helpers, this module imports no step and opens no file.
"""

import os
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


def get_creation_date(
    config: PolarisConfigParser, section: str, option: str = 'creation_date'
) -> str:
    """
    The creation date the staged files are stamped with, as ``YYYYMMDD``.

    The last dotted field of a staged filename before ``.nc`` (or before
    ``.part.<n>`` for a partition) is its creation date.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options.

    section : str
        The config section with the date.

    option : str, optional
        The config option with the date.

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
    creation_date = get_nonempty_option(config, section, option)
    if creation_date is None:
        raise ValueError(
            f'No [{section}] {option} is set.  It is normally filled in at '
            f'setup time.'
        )
    return creation_date


def set_creation_date(
    config: PolarisConfigParser,
    section: str,
    option: str = 'creation_date',
    recorded_in: str | None = None,
) -> str:
    """
    Set a creation date if it is not already set, and return it.

    Called at setup so the date lands in the work directory's config file.
    Re-running a step then reuses the date it was set up with, rather than
    silently renaming every staged file to today's.

    A date that is not set is taken from the work directory's copy of the
    config file, if a previous setup recorded one there, and is otherwise
    today's.  Setting the work directory up again therefore keeps the names
    already staged; to stamp a new date, set it in a user config file.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options, updated in place.  Its ``[paths] base_work_dir``
        locates the work directory.

    section : str
        The config section with the date.

    option : str, optional
        The config option with the date.

    recorded_in : str, optional
        The config file, relative to the base work directory, in which a
        previous setup recorded the date.  The default is ``config``'s own
        file.

    Returns
    -------
    str
        The creation date, as ``YYYYMMDD``.
    """
    creation_date = get_nonempty_option(config, section, option)
    if creation_date is None:
        if recorded_in is None:
            recorded_in = config.filepath
        creation_date = get_recorded_option(
            config, recorded_in, section, option
        )
    if creation_date is None:
        creation_date = datetime.now().strftime('%Y%m%d')
    config.set(section, option, creation_date)
    return creation_date


def get_recorded_option(
    config: PolarisConfigParser,
    filepath: str | None,
    section: str,
    option: str,
) -> str | None:
    """
    The value a previous setup recorded in the work directory's copy of a
    config file, if there is one.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with ``[paths] base_work_dir``.

    filepath : str or None
        The config file, relative to the base work directory.

    section : str
        The config section.

    option : str
        The config option.

    Returns
    -------
    str or None
        The recorded value, or ``None`` if there is no such file or it records
        no value.
    """
    if filepath is None or not config.has_option('paths', 'base_work_dir'):
        return None
    path = os.path.join(config.get('paths', 'base_work_dir'), filepath)
    if not os.path.isfile(path):
        return None
    recorded = PolarisConfigParser()
    recorded.add_from_file(path)
    return get_nonempty_option(recorded, section, option)


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
