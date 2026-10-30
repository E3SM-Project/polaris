from polaris.e3sm.init.inputdata import get_nonempty_option

#: The config section with E3SM's names for a pair of meshes' grids
GRIDS_SECTION = 'misomip_grids'

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
