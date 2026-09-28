def estimate_cell_count(config, resolution):
    """
    Estimate the number of ocean cells in an ISOMIP+ mesh, used to determine
    the resources for model runs

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with an ``isomip_plus`` section

    resolution : float
        The horizontal resolution (km) of the mesh

    Returns
    -------
    cell_count : int
        The approximate number of cells in the mesh
    """
    approx_ocean_area = config.getfloat('isomip_plus', 'approx_ocean_area')
    return int(approx_ocean_area / resolution**2)
