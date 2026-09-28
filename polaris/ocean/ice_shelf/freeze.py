def compute_freezing_temperature(config, salinity, pressure):
    """
    Get the freezing temperature in an ice-shelf cavity using the same
    coefficients as MPAS-Ocean

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with an ``ice_shelf_freeze`` section

    salinity : xarray.DataArray
        The salinity field

    pressure : xarray.DataArray
        The pressure field

    Returns
    -------
    freezing_temp : xarray.DataArray
        The freezing temperature
    """
    section = config['ice_shelf_freeze']
    coeff_0 = section.getfloat('coeff_0')
    coeff_S = section.getfloat('coeff_S')
    coeff_p = section.getfloat('coeff_p')
    coeff_pS = section.getfloat('coeff_pS')

    freezing_temp = (
        coeff_0
        + coeff_S * salinity
        + coeff_p * pressure
        + coeff_pS * pressure * salinity
    )

    return freezing_temp
