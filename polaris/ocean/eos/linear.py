from __future__ import annotations

from typing import TYPE_CHECKING

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.lazy import lazy_module

if TYPE_CHECKING:
    import xarray as xr
else:
    xr = lazy_module('xarray')


# Linear salinity dependence of the freezing temperature (degC/PSU) and the
# absolute-to-practical salinity conversion (g/kg per PSU), matching the
# LinearEos branch of Omega's Eos::calcCtFreezing()
FREEZING_SALINITY_COEFF = -0.054
PSU_TO_GPKG = get_constant('reference_salinity_per_practical_salinity_teos10')


def compute_linear_density(
    config: PolarisConfigParser,
    temperature: xr.DataArray | float,
    salinity: xr.DataArray | float,
) -> xr.DataArray | float:
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


def compute_linear_ct_freezing(
    salinity: xr.DataArray | float,
    model: str = 'omega',
) -> xr.DataArray | float:
    """
    Compute the freezing temperature of seawater for the linear equation of
    state using the model's freezing relation. MPAS-Ocean uses its default
    open-ocean mushy liquidus; Omega uses a linear salinity approximation.

    Parameters
    ----------
    salinity : float or xarray.DataArray
        Salinity of the seawater (g/kg).

    model : {'omega', 'mpas-ocean'}, optional
        Model whose freezing relation to use. The MPAS-Ocean relation assumes
        its default open-ocean coefficients, including az1_liq = -18.48.

    Returns
    -------
    ct_freezing : float or xarray.DataArray
        The freezing temperature (degC) of the seawater.
    """
    if model == 'mpas-ocean':
        ct_freezing = salinity / (-18.48 * (1.0 - salinity / 1000.0))
    elif model == 'omega':
        ct_freezing = FREEZING_SALINITY_COEFF * salinity / PSU_TO_GPKG
    else:
        raise ValueError(f'Unsupported model for linear freezing: {model}')
    return ct_freezing
