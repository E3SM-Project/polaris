import xarray as xr

from polaris.config import PolarisConfigParser


def compute_constant_density(
    config: PolarisConfigParser,
    temperature: xr.DataArray | float,
) -> xr.DataArray | float:
    """
    Compute the density of seawater based on the constant equation of state
    with the value specified in the configuration.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    temperature : float or xarray.DataArray
        Temperature of the seawater used to set density type and size.

    Returns
    -------
    density : float or xarray.DataArray
        Computed density of the seawater.
    """
    section = config['ocean']
    rhoref = section.getfloat('eos_constant_rhoref')
    assert rhoref is not None, (
        'eos_constant_rhoref must be specified in the config options for eos '
        'type constant.'
    )
    # Return density of same type and size as temperature
    # (needs to work for both float and xarray DataArray)
    if isinstance(temperature, xr.DataArray):
        density = rhoref * xr.ones_like(temperature)
    else:
        density = rhoref
    return density
