import xarray as xr

from polaris.config import PolarisConfigParser

# Constant approximate ocean freezing temperature (degC), matching the
# ConstantEos branch of Omega's Eos::calcCtFreezing()
CONSTANT_CT_FREEZING = -1.9


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


def compute_constant_ct_freezing(
    salinity: xr.DataArray | float,
) -> xr.DataArray | float:
    """
    Compute the freezing temperature of seawater for the constant equation of
    state, which is a constant approximate ocean freezing point.

    Parameters
    ----------
    salinity : float or xarray.DataArray
        Salinity of the seawater used to set the type and size of the result.

    Returns
    -------
    ct_freezing : float or xarray.DataArray
        The freezing temperature (degC) of the seawater.
    """
    # Return a freezing temperature of the same type and size as salinity
    # (needs to work for both float and xarray DataArray)
    if isinstance(salinity, xr.DataArray):
        ct_freezing = CONSTANT_CT_FREEZING * xr.ones_like(salinity)
    else:
        ct_freezing = CONSTANT_CT_FREEZING
    return ct_freezing
