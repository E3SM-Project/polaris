"""
Helpers for the pressure needed to convert between tracer conventions.
"""

import logging

import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.ocean.vertical.ztilde import (
    get_iter_count_for_eos,
    pressure_and_spec_vol_from_state_at_geom_height,
)


def pressure_for_tracer_conversion(
    ds: xr.Dataset,
    config: PolarisConfigParser,
    logger: logging.Logger | None = None,
) -> xr.DataArray:
    """
    Get the sea (gauge) pressure at layer midpoints used to convert tracers
    between the TEOS-10 and MPAS-Ocean conventions.

    If ``ds`` already contains a ``pressure`` field (as p-star initial
    conditions do), it is returned unchanged.  Otherwise, the pressure is
    computed from ``layerThickness``, the tracers and the surface pressure
    (``SurfacePressure`` if present and zero if not).

    Since the pressure only enters the conversion through the absolute-
    to-practical salinity correction, it does not need to be particularly
    accurate; see :py:func:`polaris.ocean.eos.convert_tracers()`.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with either ``pressure`` or ``layerThickness``,
        ``temperature`` and ``salinity``.

    config : polaris.config.PolarisConfigParser
        Configuration options with parameters defining the equation of state.

    logger : logging.Logger, optional
        A logger for logging EOS iteration information.

    Returns
    -------
    xarray.DataArray
        The gauge pressure at layer midpoints (Pa).
    """
    if 'pressure' in ds:
        return ds['pressure']

    required = ['layerThickness', 'temperature', 'salinity']
    missing = [name for name in required if name not in ds]
    if missing:
        raise ValueError(
            "A tracer conversion requires either a 'pressure' field or the "
            'fields needed to compute one, but the dataset has neither '
            "'pressure' nor: " + ', '.join(missing)
        )

    layer_thickness = ds['layerThickness']
    if 'SurfacePressure' in ds:
        surf_pressure = ds['SurfacePressure']
    else:
        surf_pressure = xr.zeros_like(layer_thickness.isel(nVertLevels=0))

    _, p_mid, _ = pressure_and_spec_vol_from_state_at_geom_height(
        config=config,
        geom_layer_thickness=layer_thickness,
        temperature=ds['temperature'],
        salinity=ds['salinity'],
        surf_pressure=surf_pressure,
        iter_count=get_iter_count_for_eos(config),
        logger=logger,
    )

    return p_mid
