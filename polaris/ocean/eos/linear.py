import xarray as xr

from polaris.config import PolarisConfigParser


def compute_linear_density(
    config: PolarisConfigParser,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
) -> xr.DataArray:
    """
    Compute the density of seawater based on the the linear equation of state
    with coefficients specified in the configuration. The distinction between
    conservative, potential, and in-situ temperature or between absolute and
    practical salinity is not relevant for the linear EOS.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    temperature : float or xarray.DataArray
        Temperature of the seawater.

    salinity : float or xarray.DataArray
        Salinity of the seawater.

    Returns
    -------
    density : float or xarray.DataArray
        Computed density of the seawater.
    """
    section = config['ocean']
    alpha = section.getfloat('eos_linear_alpha')
    beta = section.getfloat('eos_linear_beta')
    rhoref = section.getfloat('eos_linear_rhoref')
    Tref = section.getfloat('eos_linear_Tref')
    Sref = section.getfloat('eos_linear_Sref')
    assert (
        alpha is not None
        and beta is not None
        and rhoref is not None
        and Tref is not None
        and Sref is not None
    ), 'All linear EOS parameters must be specified in the config options.'
    density = rhoref + -alpha * (temperature - Tref) + beta * (salinity - Sref)
    return density
