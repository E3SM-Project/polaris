from .linear import compute_linear_density


def compute_density(config, temperature, salinity, pressure=None):
    """
    Compute the density of seawater based on the equation of state specified
    in the configuration.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    temperature : float or xarray.DataArray
        Temperature (conservative, potential or in-situ) of the seawater.

    salinity : float or xarray.DataArray
        Salinity (practical or absolute) of the seawater.

    pressure : float or xarray.DataArray, optional
        Pressure (in-situ or reference) of the seawater.

    Returns
    -------
    density : float or xarray.DataArray
        Computed density (in-situ or reference) of the seawater.
    """
    eos_type = config.get('ocean', 'eos_type')
    if eos_type == 'linear':
        density = compute_linear_density(config, temperature, salinity)
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    return density


def compute_specvol(config, temperature, salinity, pressure=None):
    """
    Compute the specific volume of seawater based on the equation of state
    specified in the configuration.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    temperature : float or xarray.DataArray
        Temperature (conservative, potential or in-situ) of the seawater.

    salinity : float or xarray.DataArray
        Salinity (practical or absolute) of the seawater.

    pressure : float or xarray.DataArray, optional
        Pressure (in-situ or reference) of the seawater.

    Returns
    -------
    specvol : float or xarray.DataArray
        Computed specific volume (in-situ or reference) of the seawater.
    """
    eos_type = config.get('ocean', 'eos_type')
    if eos_type == 'linear':
        specvol = 1.0 / compute_linear_density(config, temperature, salinity)
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    return specvol
