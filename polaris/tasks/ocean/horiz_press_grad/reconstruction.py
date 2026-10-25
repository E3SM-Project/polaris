"""
Mean-preserving vertical reconstruction of temperature and salinity.

This is §3.4 of ``PGradHighOrder.md``.  Within layer ``k`` of column ``i`` the
prognostic layer mean is supplemented by a deviation that integrates to zero
over the layer, ``[vert-recon]``::

    Theta(p) = Theta_{i,k} + slope_{i,k} * (p - p^mid_{i,k})

The linear reconstruction is exact for profiles that vary linearly with
pressure -- which is what sets the scheme's exact set in §3.7.3, and is why
``hydrostatic_consistency_linear`` exists.  The parabolic one of
:py:func:`ppm_coefficients` adds a curvature term, ``[ppm-recon]``::

    Theta(p) = Theta_{i,k} + slope_{i,k} * (p - p^mid_{i,k})
               + curvature_{i,k} * ((p - p^mid_{i,k})**2 - dp_{i,k}**2 / 12)

and is exact for profiles that vary quadratically.  Neither has a limiter: the
reconstruction feeds an integral rather than an advective flux, and a limiter
active on smooth data would break the cancellation of §3.7.2 precisely where
the profile is well resolved.

Two properties carry the weight, and both are tested.

**Mean-preserving.** ``p^mid`` is the exact arithmetic midpoint of the two
interface pressures, so ``\\int (p - p^mid) dp = 0`` over the layer, and
likewise ``\\int ((p - p^mid)**2 - dp**2 / 12) dp = 0``, so the deviation
cannot move the layer mean.  ``[z-increment-exact]`` rests on this: it is what
makes ``VertCoord``'s midpoint rule the exact layer integral of a linear
reconstruction, and hence what spares ``VertCoord`` any change.

**Exact on a non-uniform grid.** For a profile linear in pressure the layer
means lie exactly on the line *as a function of mid-layer pressure*, because
the mean over a layer of a linear function is its value at the layer's
midpoint.  So a centred difference of the layer means with respect to ``p^mid``
recovers the slope exactly, for any distribution of layer thicknesses.  This is
why the estimator differences against the actual mid-layer pressures and not
against layer index: a formula that assumed uniform thickness would pass a
uniform-thickness test and fail on Omega's grid.  The parabolic estimator is
exact on any grid for a reason of the same kind; see
:py:func:`ppm_coefficients`.
"""

import math
from typing import TypeVar

import numpy as np
import xarray as xr

__all__ = [
    'linear_slope',
    'ppm_coefficients',
    'reconstruct',
    'layer_deviation',
]

# The evaluation functions are plain arithmetic, so they serve xarray, numpy
# and scalars alike; the finite-volume kernel calls them on numpy arrays.
ArrayLikeT = TypeVar('ArrayLikeT', xr.DataArray, np.ndarray, float)


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


def ppm_coefficients(
    values: xr.DataArray,
    pressure_interface: xr.DataArray,
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    The slope and curvature of the parabolic reconstruction, per layer.

    This is the piecewise parabolic method of Colella and Woodward (1984)
    without its limiter, as design §3.4 specifies it.  Each layer's parabola
    keeps the layer mean and takes the values ``a_top`` and ``a_bot`` at the
    layer's two interfaces, ``[ppm-coeffs]``::

        slope = (a_bot - a_top) / dp
        curvature = 3 * (a_top + a_bot - 2 * Theta) / dp**2

    The value at an interface is the derivative there of the polynomial ``P``
    that interpolates the cumulative integral of ``Theta`` at five consecutive
    interfaces centred on it, the window shifted inward near the ends of the
    column so that it stays among the valid layers.  A column of fewer than
    four valid layers uses the polynomial through all of its interfaces.

    **Exact on a non-uniform grid.** The layer means are exact layer averages,
    so the cumulative integral is known exactly at every interface, whatever
    the thicknesses.  For a profile cubic in pressure the cumulative integral
    is a quartic, which ``P`` reproduces, so the interface values are exact;
    for a quadratic, the only parabola through two exact interface values
    with the exact mean is the profile itself.

    **No cumulative integral is summed.**  Its first divided differences
    between neighbouring interfaces are the layer means themselves, so the
    divided-difference table of ``P`` starts from the means, taken as
    departures from the mean of the layer being reconstructed.

    **At the ends of a column the coefficients come from ``P`` itself.**
    Where both of a layer's interfaces take their values from the same window
    -- the two outermost valid layers at each end, and every layer of a column
    of four or fewer -- ``[ppm-coeffs-end]``::

        slope = P''(p^mid) + dp**2 * P''''(p^mid) / 24
        curvature = P'''(p^mid) / 2

    which is ``[ppm-coeffs]`` rearranged.  The two agree in exact arithmetic,
    but in a thin layer ``[ppm-coeffs]`` forms the curvature from a small
    difference of nearly equal quantities and divides it by the square of the
    thickness.  That does no harm within the layer and a great deal beyond
    it, and the outermost layers are the ones extrapolated past the column.

    Parameters
    ----------
    values : xarray.DataArray
        Layer-mean conservative temperature or absolute salinity, with
        ``nVertLevels`` last.  Invalid layers are ``NaN``, and the valid ones
        must be contiguous.

    pressure_interface : xarray.DataArray
        Interface sea gauge pressure in Pa, with ``nVertLevelsP1`` last and
        the other dimensions as for ``values``.

    Returns
    -------
    slope : xarray.DataArray
        The slope per Pa, ``NaN`` in invalid layers.

    curvature : xarray.DataArray
        The curvature per Pa squared, ``NaN`` in invalid layers.
    """
    if values.dims[-1] != 'nVertLevels':
        raise ValueError(
            f"the last dimension of values must be 'nVertLevels'; got "
            f'{values.dims[-1]}.'
        )
    if pressure_interface.dims[-1] != 'nVertLevelsP1':
        raise ValueError(
            'the last dimension of pressure_interface must be '
            f"'nVertLevelsP1'; got {pressure_interface.dims[-1]}."
        )
    if values.dims[:-1] != pressure_interface.dims[:-1]:
        raise ValueError(
            'values and pressure_interface must have the same leading '
            f'dimensions; got {values.dims} and {pressure_interface.dims}.'
        )

    value_array = np.asarray(values.values, dtype=float)
    interface_array = np.asarray(pressure_interface.values, dtype=float)
    if interface_array.shape[-1] != value_array.shape[-1] + 1:
        raise ValueError(
            'pressure_interface must have one more level than values; got '
            f'{interface_array.shape[-1]} and {value_array.shape[-1]}.'
        )
    slope = np.full(value_array.shape, np.nan)
    curvature = np.full(value_array.shape, np.nan)

    for index in np.ndindex(value_array.shape[:-1]):
        levels = np.where(np.isfinite(value_array[index]))[0]
        if len(levels) == 0:
            continue
        if np.any(np.diff(levels) != 1):
            raise ValueError(
                f'the valid layers of column {index} are not contiguous.'
            )
        interfaces = interface_array[index][levels[0] : levels[-1] + 2]
        if not np.all(np.isfinite(interfaces)):
            raise ValueError(
                f'column {index} has a valid layer without finite interface '
                'pressures.'
            )
        column_slope, column_curvature = _ppm_column(
            value_array[index][levels], interfaces
        )
        slope[index + (levels,)] = column_slope
        curvature[index + (levels,)] = column_curvature

    units = values.attrs.get('units', '1')
    return (
        xr.DataArray(
            data=slope,
            dims=values.dims,
            attrs={
                'long_name': 'slope of the mean-preserving parabolic '
                'reconstruction',
                'units': f'{units} Pa-1',
            },
        ),
        xr.DataArray(
            data=curvature,
            dims=values.dims,
            attrs={
                'long_name': 'curvature of the mean-preserving parabolic '
                'reconstruction',
                'units': f'{units} Pa-2',
            },
        ),
    )


def layer_deviation(
    slope: ArrayLikeT,
    pressure_mid: ArrayLikeT,
    pressure: ArrayLikeT,
    curvature: ArrayLikeT | None = None,
    thickness: ArrayLikeT | None = None,
) -> ArrayLikeT:
    """
    The deviation from the layer mean, ``slope * (p - p^mid)``, plus
    ``curvature * ((p - p^mid)**2 - dp**2 / 12)`` for the parabolic
    reconstruction.

    This is the ``Theta'`` of ``[vert-recon]`` and ``[ppm-recon]``.  It
    integrates to zero over the layer because ``pressure_mid`` is the exact
    arithmetic midpoint of the two interface pressures.  The arguments are
    all xarray, all numpy or all scalars, and the result is of the same kind.

    Parameters
    ----------
    slope : xarray.DataArray
        The slope from :py:func:`linear_slope` or :py:func:`ppm_coefficients`.

    pressure_mid : xarray.DataArray
        Mid-layer sea gauge pressure in Pa.

    pressure : xarray.DataArray or float
        The pressure at which to evaluate, in Pa.

    curvature : xarray.DataArray, optional
        The curvature from :py:func:`ppm_coefficients`.  Without it the
        deviation is linear.

    thickness : xarray.DataArray, optional
        The layer's thickness in pressure, in Pa, which the curvature term
        needs.

    Returns
    -------
    deviation : xarray.DataArray
        The deviation from the layer mean.
    """
    deviation = slope * (pressure - pressure_mid)
    if curvature is None:
        return deviation
    if thickness is None:
        raise ValueError('the curvature term needs the layer thickness.')
    offset = pressure - pressure_mid
    return deviation + curvature * (offset**2 - thickness**2 / 12.0)


def reconstruct(
    values: ArrayLikeT,
    slope: ArrayLikeT,
    pressure_mid: ArrayLikeT,
    pressure: ArrayLikeT,
    curvature: ArrayLikeT | None = None,
    thickness: ArrayLikeT | None = None,
) -> ArrayLikeT:
    """
    Evaluate the reconstruction ``[vert-recon]`` at a pressure.

    The arguments are all xarray, all numpy or all scalars, as for
    :py:func:`layer_deviation`.

    Parameters
    ----------
    values : xarray.DataArray
        The prognostic layer means.

    slope : xarray.DataArray
        The slope from :py:func:`linear_slope` or :py:func:`ppm_coefficients`.

    pressure_mid : xarray.DataArray
        Mid-layer sea gauge pressure in Pa.

    pressure : xarray.DataArray or float
        The pressure at which to evaluate, in Pa.

    curvature : xarray.DataArray, optional
        The curvature from :py:func:`ppm_coefficients`.  Without it the
        reconstruction is linear.

    thickness : xarray.DataArray, optional
        The layer's thickness in pressure, in Pa, which the curvature term
        needs.

    Returns
    -------
    reconstructed : xarray.DataArray
        The reconstructed profile.  Equal to ``values`` at ``pressure_mid`` for
        the linear reconstruction, and its mean over the layer is ``values``
        for both.
    """
    return values + layer_deviation(
        slope=slope,
        pressure_mid=pressure_mid,
        pressure=pressure,
        curvature=curvature,
        thickness=thickness,
    )


def _ppm_column(
    means: np.ndarray, interfaces: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    ``[ppm-coeffs]`` and ``[ppm-coeffs-end]`` for one column's valid layers.
    """
    count = len(means)
    slope = np.empty(count)
    curvature = np.empty(count)
    for layer in range(count):
        thickness = interfaces[layer + 1] - interfaces[layer]
        window_top = _ppm_window(layer, count)
        window_bot = _ppm_window(layer + 1, count)
        if window_top == window_bot:
            # both interfaces from one polynomial: its own derivatives at the
            # midpoint, which form no small difference in a thin layer
            mid = 0.5 * (interfaces[layer] + interfaces[layer + 1])
            derivatives = _ppm_derivatives(
                means, interfaces, window_top, mid, means[layer]
            )
            slope[layer] = (
                derivatives[1] + thickness**2 * derivatives[3] / 24.0
            )
            curvature[layer] = 0.5 * derivatives[2]
        else:
            # interface values as departures from this layer's own mean
            top = _ppm_derivatives(
                means, interfaces, window_top, interfaces[layer], means[layer]
            )[0]
            bot = _ppm_derivatives(
                means,
                interfaces,
                window_bot,
                interfaces[layer + 1],
                means[layer],
            )[0]
            slope[layer] = (bot - top) / thickness
            curvature[layer] = 3.0 * (top + bot) / thickness**2
    return slope, curvature


def _ppm_window(interface: int, count: int) -> tuple[int, int]:
    """
    The first and last interface of the window for an interface of a column
    with ``count`` valid layers: five consecutive interfaces centred on it,
    shifted inward near the ends, or all of them in a column of fewer than
    four layers.
    """
    if count < 4:
        return 0, count
    first = min(max(interface - 2, 0), count - 4)
    return first, first + 4


def _ppm_derivatives(
    means: np.ndarray,
    interfaces: np.ndarray,
    window: tuple[int, int],
    pressure: float,
    reference: float,
) -> np.ndarray:
    """
    The first four derivatives at ``pressure`` of the polynomial through the
    cumulative integral of ``means - reference`` at the window's interfaces.

    The first divided differences of the cumulative integral are the layer
    means, so the Newton form is built from them directly.  Subtracting
    ``reference`` shifts the first derivative by that constant and leaves the
    others unchanged.
    """
    first, last = window
    nodes = interfaces[first : last + 1] - pressure
    table = means[first:last] - reference
    newton = [table[0]]
    for order in range(2, last - first + 1):
        table = (table[1:] - table[:-1]) / (nodes[order:] - nodes[:-order])
        newton.append(table[0])

    # P = I_0 + sum_r newton[r - 1] * prod_{i < r} (p - p_i); the q-th
    # derivative at the point is q! times the coefficient of s**q in each
    # product, written in s = p - pressure
    derivatives = np.zeros(4)
    for degree, coefficient in enumerate(newton, start=1):
        basis = np.polynomial.polynomial.polyfromroots(nodes[:degree])
        for order in range(1, min(degree, 4) + 1):
            derivatives[order - 1] += (
                coefficient * math.factorial(order) * basis[order]
            )
    return derivatives
