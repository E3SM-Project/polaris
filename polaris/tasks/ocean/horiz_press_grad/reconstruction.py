"""
Mean-preserving vertical reconstruction of temperature and salinity.

This is §3.4 of ``PGradHighOrder.md``.  Within layer ``k`` of column ``i`` the
prognostic layer mean is supplemented by a deviation that integrates to zero
over the layer, ``[vert-recon]``::

    Theta(p) = Theta_{i,k} + slope_{i,k} * (p - p^mid_{i,k})

Phase 1 uses linear deviations, so the reconstruction is exact for profiles
that vary linearly with pressure -- which is what sets the scheme's exact set
in §3.7.3, and is why ``hydrostatic_consistency_linear`` exists.  There is no
limiter: the reconstruction feeds an integral rather than an advective flux,
and a limiter active on smooth data would break the cancellation of §3.7.2
precisely where the profile is well resolved.

Two properties carry the weight, and both are tested.

**Mean-preserving.** ``p^mid`` is the exact arithmetic midpoint of the two
interface pressures, so ``\\int (p - p^mid) dp = 0`` over the layer and the
deviation cannot move the layer mean.  ``[z-increment-exact]`` rests on this:
it is what makes ``VertCoord``'s midpoint rule the exact layer integral of a
Phase 1 reconstruction, and hence what spares ``VertCoord`` any change.

**Exact on a non-uniform grid.** For a profile linear in pressure the layer
means lie exactly on the line *as a function of mid-layer pressure*, because
the mean over a layer of a linear function is its value at the layer's
midpoint.  So a centred difference of the layer means with respect to ``p^mid``
recovers the slope exactly, for any distribution of layer thicknesses.  This is
why the estimator differences against the actual mid-layer pressures and not
against layer index: a formula that assumed uniform thickness would pass a
uniform-thickness test and fail on Omega's grid.
"""

import numpy as np
import xarray as xr

__all__ = ['linear_slope', 'reconstruct', 'layer_deviation']


def linear_slope(
    values: xr.DataArray,
    pressure_mid: xr.DataArray,
) -> xr.DataArray:
    """
    The slope of the mean-preserving linear reconstruction, per layer.

    A centred difference of the layer means with respect to mid-layer
    pressure, one-sided in the shallowest and deepest valid layer of each
    column.  Exact for a profile linear in pressure on an arbitrary grid;
    second-order accurate otherwise.

    The one-sided branches are not an edge case here.  The deepest valid layer
    is a partial cell in both columns and carries the whole signal for the
    ``bathymetry_step`` configuration, so the one-sided branch is exercised
    exactly where the interesting behaviour is.

    Parameters
    ----------
    values : xarray.DataArray
        Layer-mean conservative temperature or absolute salinity, with
        ``nVertLevels`` last.  Invalid layers are ``NaN``.

    pressure_mid : xarray.DataArray
        Mid-layer sea gauge pressure in Pa, on the same points.

    Returns
    -------
    slope : xarray.DataArray
        The slope per Pa, ``NaN`` in invalid layers and zero in a column with
        only one valid layer.
    """
    if values.dims != pressure_mid.dims:
        raise ValueError(
            'values and pressure_mid must have the same dimensions; got '
            f'{values.dims} and {pressure_mid.dims}.'
        )
    if values.dims[-1] != 'nVertLevels':
        raise ValueError(
            f"the last dimension must be 'nVertLevels'; got {values.dims[-1]}."
        )

    value_array = np.asarray(values.values, dtype=float)
    pressure_array = np.asarray(pressure_mid.values, dtype=float)
    slope = np.full(value_array.shape, np.nan)

    for index in np.ndindex(value_array.shape[:-1]):
        column_values = value_array[index]
        column_pressure = pressure_array[index]
        valid = np.logical_and(
            np.isfinite(column_values), np.isfinite(column_pressure)
        )
        levels = np.where(valid)[0]
        if len(levels) == 0:
            continue
        if len(levels) == 1:
            # nothing to difference against; a constant is the only
            # mean-preserving reconstruction available
            slope[index + (levels,)] = 0.0
            continue

        interior_values = column_values[levels]
        interior_pressure = column_pressure[levels]
        column_slope = np.empty(len(levels))
        # centred in the interior, against the actual mid-layer pressures
        column_slope[1:-1] = (interior_values[2:] - interior_values[:-2]) / (
            interior_pressure[2:] - interior_pressure[:-2]
        )
        # one-sided at the two ends of the valid column
        column_slope[0] = (interior_values[1] - interior_values[0]) / (
            interior_pressure[1] - interior_pressure[0]
        )
        column_slope[-1] = (interior_values[-1] - interior_values[-2]) / (
            interior_pressure[-1] - interior_pressure[-2]
        )
        slope[index + (levels,)] = column_slope

    return xr.DataArray(
        data=slope,
        dims=values.dims,
        attrs={
            'long_name': 'slope of the mean-preserving linear reconstruction',
            'units': f'{values.attrs.get("units", "1")} Pa-1',
        },
    )


def layer_deviation(
    slope: xr.DataArray,
    pressure_mid: xr.DataArray,
    pressure: xr.DataArray | float,
) -> xr.DataArray:
    """
    The deviation from the layer mean, ``slope * (p - p^mid)``.

    This is the ``Theta'`` of ``[vert-recon]``.  It integrates to zero over the
    layer because ``pressure_mid`` is the exact arithmetic midpoint of the two
    interface pressures.

    Parameters
    ----------
    slope : xarray.DataArray
        The slope from :py:func:`linear_slope`.

    pressure_mid : xarray.DataArray
        Mid-layer sea gauge pressure in Pa.

    pressure : xarray.DataArray or float
        The pressure at which to evaluate, in Pa.

    Returns
    -------
    deviation : xarray.DataArray
        The deviation from the layer mean.
    """
    return slope * (pressure - pressure_mid)


def reconstruct(
    values: xr.DataArray,
    slope: xr.DataArray,
    pressure_mid: xr.DataArray,
    pressure: xr.DataArray | float,
) -> xr.DataArray:
    """
    Evaluate the reconstruction ``[vert-recon]`` at a pressure.

    Parameters
    ----------
    values : xarray.DataArray
        The prognostic layer means.

    slope : xarray.DataArray
        The slope from :py:func:`linear_slope`.

    pressure_mid : xarray.DataArray
        Mid-layer sea gauge pressure in Pa.

    pressure : xarray.DataArray or float
        The pressure at which to evaluate, in Pa.

    Returns
    -------
    reconstructed : xarray.DataArray
        The reconstructed profile.  Equal to ``values`` at ``pressure_mid``, by
        construction.
    """
    return values + layer_deviation(
        slope=slope, pressure_mid=pressure_mid, pressure=pressure
    )
