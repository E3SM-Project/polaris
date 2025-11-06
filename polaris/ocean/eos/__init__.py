import xarray as xr

from polaris.config import PolarisConfigParser

from .linear import compute_linear_density
from .teos10 import compute_specvol as compute_teos10_specvol


def compute_density(
    config: PolarisConfigParser,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    pressure: xr.DataArray | None = None,
) -> xr.DataArray:
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
    elif eos_type == 'teos-10':
        if pressure is None:
            raise ValueError(
                'Pressure must be provided when using the TEOS-10 equation of '
                'state.'
            )
        density = 1.0 / compute_teos10_specvol(salinity, temperature, pressure)
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    return density


def compute_specvol(
    config: PolarisConfigParser,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    pressure: xr.DataArray | None = None,
) -> xr.DataArray:
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
    elif eos_type == 'teos-10':
        if pressure is None:
            raise ValueError(
                'Pressure must be provided when using the TEOS-10 equation of '
                'state.'
            )
        specvol = compute_teos10_specvol(temperature, salinity, pressure)
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    return specvol
