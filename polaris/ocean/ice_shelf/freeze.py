def compute_freezing_temperature(config, salinity, pressure):
    """
    Get the freezing temperature in an ice-shelf cavity using the same
    formulation as the ocean model.  Only MPAS-Ocean is currently supported.
    Omega uses TEOS-10 for the freezing temperature, which is not yet
    supported.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with ``ocean`` and ``ice_shelf_freeze`` sections

    salinity : xarray.DataArray
        The salinity field

    pressure : xarray.DataArray
        The pressure field in Pa

    Returns
    -------
    freezing_temp : xarray.DataArray
        The freezing temperature
    """
    model = config.get('ocean', 'model')
    if model == 'mpas-ocean':
        return _compute_mpas_ocean_freezing_temperature(
            config, salinity, pressure
        )
    elif model == 'omega':
        raise NotImplementedError(
            'The freezing temperature in ice-shelf cavities is not yet '
            'supported for Omega, which uses TEOS-10.'
        )
    else:
        raise ValueError(f'Unexpected ocean model: {model}')


def _compute_mpas_ocean_freezing_temperature(config, salinity, pressure):
    """
    Get the freezing temperature in an ice-shelf cavity using the same
    coefficients as MPAS-Ocean
    """
    section = config['ice_shelf_freeze']
    coeff_0 = section.getfloat('mpas_ocean_coeff_0')
    coeff_S = section.getfloat('mpas_ocean_coeff_S')
    coeff_p = section.getfloat('mpas_ocean_coeff_p')
    coeff_pS = section.getfloat('mpas_ocean_coeff_pS')

    freezing_temp = (
        coeff_0
        + coeff_S * salinity
        + coeff_p * pressure
        + coeff_pS * pressure * salinity
    )

    return freezing_temp
