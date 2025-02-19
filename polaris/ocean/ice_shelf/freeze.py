def compute_freezing_temperature(config, salinity, pressure):
    """
    Get the freezing temperature in an ice-shelf cavity using the same equation
    of state as in the ocean model

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options

    salinity : xarray.DataArray
        The salinity field

    pressure
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

    freezing_temp = (coeff_0 +
                     coeff_S * salinity +
                     coeff_p * pressure +
                     coeff_pS * pressure * salinity)

    return freezing_temp
