import numpy as np
import xarray as xr

from polaris.config import PolarisConfigParser

from .constant import compute_constant_ct_freezing, compute_constant_density
from .linear import compute_linear_ct_freezing, compute_linear_density
from .teos10 import TRACER_ATTRS as TRACER_ATTRS
from .teos10 import TRACER_CONVENTIONS as TRACER_CONVENTIONS
from .teos10 import compute_ct_freezing as compute_teos10_ct_freezing
from .teos10 import compute_specvol as compute_teos10_specvol
from .teos10 import convert_tracer_pair as convert_tracer_pair
from .teos10 import convert_tracers as convert_tracers
from .teos10 import (
    ct_from_potential_density as ct_from_potential_density,
)


def compute_density(
    config: PolarisConfigParser,
    temperature: xr.DataArray | float,
    salinity: xr.DataArray | float,
    pressure: xr.DataArray | float | None = None,
    tracer_convention: str = 'teos-10',
    lon: xr.DataArray | np.ndarray | float | None = None,
    lat: xr.DataArray | np.ndarray | float | None = None,
) -> xr.DataArray | float:
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

    tracer_convention : {'teos-10', 'mpas-ocean'}, optional
        The convention of ``temperature`` and ``salinity``.  TEOS-10 requires
        conservative temperature and absolute salinity, so tracers straight
        out of MPAS-Ocean must say so and are converted first, which needs
        ``lon`` and ``lat``.  The two conventions are indistinguishable for
        any other equation of state.

    lon : float, numpy.ndarray or xarray.DataArray, optional
        Longitude(s) in degrees, needed only to convert from the MPAS-Ocean
        convention.

    lat : float, numpy.ndarray or xarray.DataArray, optional
        Latitude(s) in degrees, as for ``lon``.

    Returns
    -------
    density : float or xarray.DataArray
        Computed density (in-situ or reference) of the seawater.
    """
    eos_type = config.get('ocean', 'eos_type')
    eos_type = eos_type.strip()
    if eos_type == 'constant':
        density = compute_constant_density(config, temperature)
    elif eos_type == 'linear':
        density = compute_linear_density(config, temperature, salinity)
    elif eos_type == 'teos-10':
        if pressure is None:
            raise ValueError(
                'Pressure must be provided when using the TEOS-10 equation of '
                'state.'
            )
        temperature, salinity = _tracers_in_teos10_convention(
            temperature=temperature,
            salinity=salinity,
            tracer_convention=tracer_convention,
            pressure=pressure,
            lon=lon,
            lat=lat,
        )
        density = 1.0 / compute_teos10_specvol(
            sa=salinity, ct=temperature, p=pressure
        )
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    if isinstance(density, xr.DataArray):
        density.attrs['units'] = 'kg m-3'
        density.attrs['long_name'] = 'density'
    return density


def compute_ct_freezing(
    config: PolarisConfigParser,
    salinity: xr.DataArray | float,
    pressure: xr.DataArray | float | None = None,
    saturation_fraction: float = 0.0,
    tracer_convention: str = 'teos-10',
    lon: xr.DataArray | np.ndarray | float | None = None,
    lat: xr.DataArray | np.ndarray | float | None = None,
) -> xr.DataArray | float:
    """
    Compute the freezing temperature of seawater based on the equation of
    state specified in the configuration, following Omega's
    ``Eos::calcCtFreezing()``.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration object containing ocean parameters.

    salinity : float or xarray.DataArray
        Salinity (practical or absolute) of the seawater.

    pressure : float or xarray.DataArray, optional
        Sea (gauge) pressure in Pa, required for the TEOS-10 equation of
        state.

    saturation_fraction : float, optional
        The fraction of dissolved air in seawater (0 to 1), used only by the
        TEOS-10 equation of state.

    tracer_convention : {'teos-10', 'mpas-ocean'}, optional
        The convention of ``salinity``.  TEOS-10 requires absolute salinity,
        so salinity straight out of MPAS-Ocean must say so and is converted
        first, which needs ``lon`` and ``lat``.  The two conventions are
        indistinguishable for any other equation of state.

    lon : float, numpy.ndarray or xarray.DataArray, optional
        Longitude(s) in degrees, needed only to convert from the MPAS-Ocean
        convention.

    lat : float, numpy.ndarray or xarray.DataArray, optional
        Latitude(s) in degrees, as for ``lon``.

    Returns
    -------
    ct_freezing : float or xarray.DataArray
        The freezing temperature (degC) of the seawater, conservative
        temperature for the TEOS-10 equation of state.
    """
    eos_type = config.get('ocean', 'eos_type')
    eos_type = eos_type.strip()
    if eos_type == 'constant':
        ct_freezing = compute_constant_ct_freezing(salinity)
    elif eos_type == 'linear':
        ct_freezing = compute_linear_ct_freezing(salinity)
    elif eos_type == 'teos-10':
        if pressure is None:
            raise ValueError(
                'Pressure must be provided when using the TEOS-10 equation of '
                'state.'
            )
        _, salinity = _tracers_in_teos10_convention(
            temperature=0.0,
            salinity=salinity,
            tracer_convention=tracer_convention,
            pressure=pressure,
            lon=lon,
            lat=lat,
        )
        ct_freezing = compute_teos10_ct_freezing(
            sa=salinity,
            p=pressure,
            saturation_fraction=saturation_fraction,
        )
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    if isinstance(ct_freezing, xr.DataArray):
        ct_freezing.attrs['units'] = 'degC'
        ct_freezing.attrs['long_name'] = 'freezing temperature'
    return ct_freezing


def compute_specvol(
    config: PolarisConfigParser,
    temperature: xr.DataArray | float,
    salinity: xr.DataArray | float,
    pressure: xr.DataArray | float | None = None,
) -> xr.DataArray | float:
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
    eos_type = eos_type.strip()
    if eos_type == 'constant':
        specvol = 1.0 / compute_constant_density(config, temperature)
    elif eos_type == 'linear':
        specvol = 1.0 / compute_linear_density(config, temperature, salinity)
    elif eos_type == 'teos-10':
        if pressure is None:
            raise ValueError(
                'Pressure must be provided when using the TEOS-10 equation of '
                'state.'
            )
        specvol = compute_teos10_specvol(
            sa=salinity, ct=temperature, p=pressure
        )
    else:
        raise ValueError(f'Unsupported equation of state type: {eos_type}')
    if isinstance(specvol, xr.DataArray):
        specvol.attrs['units'] = 'm3 kg-1'
        specvol.attrs['long_name'] = 'specific volume'
    return specvol


def _tracers_in_teos10_convention(
    temperature: xr.DataArray | float,
    salinity: xr.DataArray | float,
    tracer_convention: str,
    pressure: xr.DataArray | float,
    lon: xr.DataArray | np.ndarray | float | None,
    lat: xr.DataArray | np.ndarray | float | None,
) -> tuple[xr.DataArray | float, xr.DataArray | float]:
    """
    Return conservative temperature and absolute salinity, converting from the
    MPAS-Ocean convention if that is what the caller has.
    """
    if tracer_convention not in TRACER_CONVENTIONS:
        raise ValueError(
            f'Unknown tracer convention {tracer_convention!r}; expected one '
            'of ' + ', '.join(repr(name) for name in TRACER_CONVENTIONS)
        )

    if tracer_convention == 'teos-10':
        return temperature, salinity

    if lon is None or lat is None:
        raise ValueError(
            'lon and lat are required to convert tracers from the MPAS-Ocean '
            'convention to the conservative temperature and absolute '
            'salinity that TEOS-10 requires.'
        )

    scalar = not any(
        isinstance(value, xr.DataArray)
        for value in (temperature, salinity, pressure, lon, lat)
    )
    cons_temp, abs_salin = convert_tracer_pair(
        temperature=temperature,
        salinity=salinity,
        target='teos-10',
        pressure=pressure,
        lon=lon,
        lat=lat,
    )
    if scalar:
        return float(cons_temp), float(abs_salin)

    return cons_temp, abs_salin
