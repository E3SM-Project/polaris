from polaris.e3sm.init.inputdata import (
    get_nonempty_option,
    gridmaps_dir,
    landice_dir,
    ocean_dir,
)

#: The config section with E3SM's names for a pair of meshes' grids
GRIDS_SECTION = 'misomip_grids'

#: The config section with the creation date of the staged files
INPUTS_SECTION = 'misomip_inputs'

#: The grids a pair of meshes has an E3SM name for, and their config options
GRID_OPTIONS = {
    'ocean': 'ocean_grid',
    'landice': 'landice_grid',
    'model': 'model_grid',
}


def get_grid_names(config):
    """
    Get E3SM's names for the grids of a pair of MISOMIP meshes

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options

    Returns
    -------
    grids : dict of str to str
        The names of the ``ocean``, ``landice`` and ``model`` grids

    Raises
    ------
    ValueError
        If a name is not set
    """
    grids = dict()
    for grid, option in GRID_OPTIONS.items():
        name = get_nonempty_option(config, GRIDS_SECTION, option)
        if name is None:
            raise ValueError(
                f'The E3SM grid name [{GRIDS_SECTION}] {option} is not set.'
            )
        grids[grid] = name
    return grids


def ocean_initial_condition_path(grid, experiment, creation_date):
    """
    Where an experiment's MPAS-Ocean initial condition is staged

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid

    experiment : str
        The experiment

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'{ocean_dir(grid)}/mpaso.{grid}.{experiment}.{creation_date}.nc'


def ocean_forcing_path(grid, experiment, creation_date):
    """
    Where an experiment's MPAS-Ocean forcing, its interior restoring, is
    staged

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid

    experiment : str
        The experiment

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return (
        f'{ocean_dir(grid)}/mpaso.{grid}.{experiment}_forcing.'
        f'{creation_date}.nc'
    )


def ocean_scrip_path(grid, creation_date):
    """
    Where the ocean grid's SCRIP file is staged

    Parameters
    ----------
    grid : str
        E3SM's name for the ocean grid

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'{ocean_dir(grid)}/{grid}.scrip.{creation_date}.nc'


def landice_initial_condition_path(grid, experiment, creation_date):
    """
    Where an experiment's MALI initial condition is staged

    Parameters
    ----------
    grid : str
        E3SM's name for MALI's grid

    experiment : str
        The experiment

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'{landice_dir(grid)}/{grid}.{experiment}.{creation_date}.nc'


def landice_data_mode_path(grid, experiment, creation_date):
    """
    Where an experiment's MALI data-mode file is staged

    Parameters
    ----------
    grid : str
        E3SM's name for MALI's grid

    experiment : str
        The experiment

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return (
        f'{landice_dir(grid)}/{grid}.{experiment}_datamode.{creation_date}.nc'
    )


def landice_scrip_path(grid, creation_date):
    """
    Where MALI's grid's SCRIP file is staged

    Parameters
    ----------
    grid : str
        E3SM's name for MALI's grid

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'{landice_dir(grid)}/{grid}.scrip.{creation_date}.nc'


def landice_partition_path(grid, creation_date, ncores):
    """
    Where one MALI graph partition is staged

    Parameters
    ----------
    grid : str
        E3SM's name for MALI's grid

    creation_date : str
        The creation date, as ``YYYYMMDD``

    ncores : int
        The number of partitions the graph was divided into

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'{landice_partition_prefix(grid, creation_date)}{ncores}'


def landice_partition_prefix(grid, creation_date):
    """
    The path of MALI's graph partitions up to the core count, as E3SM's
    case variable names them

    Parameters
    ----------
    grid : str
        E3SM's name for MALI's grid

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    prefix : str
        The prefix, relative to the assembled tree
    """
    return f'{landice_dir(grid)}/mpasli.graph.info.{creation_date}.part.'


def map_path(src_grid, dst_grid, method, creation_date):
    """
    Where a map the coupler reads is staged

    Parameters
    ----------
    src_grid : str
        E3SM's name for the source grid

    dst_grid : str
        E3SM's name for the destination grid

    method : str
        E3SM's name for the method, such as ``aave``

    creation_date : str
        The creation date, as ``YYYYMMDD``

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return (
        f'{gridmaps_dir(src_grid)}/map_{src_grid}_to_{dst_grid}_{method}.'
        f'{creation_date}.nc'
    )


def case_config_dir(experiment):
    """
    Where an experiment's E3SM case configuration is staged

    Parameters
    ----------
    experiment : str
        The experiment

    Returns
    -------
    path : str
        The path, relative to the assembled tree
    """
    return f'case_config/{experiment}'
