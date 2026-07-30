"""
The ``FiniteVolume`` horizontal pressure gradient for the two-column
``horiz_press_grad`` configurations.

This is the Python counterpart of Omega's ``PressureGradFiniteVolume``.  It is
written from the ``PGradHighOrder.md`` design document rather than from the
C++, so that the Omega-vs-Polaris comparison in the analysis steps compares two
independent implementations of the same mathematics.

The scheme evaluates the exact edge-normal acceleration -- the layer mean of
the geopotential difference taken at *fixed pressure* -- as the centered scheme
plus a remainder::

    T^p_{e,k} = -(g / d_e) * (S_{e,k} + R_{e,k})

The tidal-potential and self-attraction-and-loading terms of the design's
``[ho-discrete]`` are identically zero in these configurations and are omitted.

``S_{e,k}`` (:py:func:`centered_shift`) is the first-order conversion of a
height difference taken at fixed layer index into one taken at fixed pressure,
trapezoid-averaged over the layer's two interfaces.  It is exactly what the
centered scheme computes, so ``R_{e,k}`` is the whole difference between the
two schemes.  Only ``S`` is implemented so far.

Every horizontal difference here is the two-column edge operator of
:py:mod:`~polaris.tasks.ocean.horiz_press_grad.edge`.  The identity in
:py:func:`centered_shift` holds against
:py:meth:`polaris.tasks.ocean.horiz_press_grad.init.Init._compute_montgomery_and_hpga`
itself, not against an idealized centered form.
"""

import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import (
    Gravity,
    RhoSw,
    pressure_from_z_tilde,
)
from polaris.tasks.ocean.horiz_press_grad.edge import edge_delta, edge_mean

__all__ = [
    'centered_shift',
    'centered_shift_accumulated',
    'shift_increments',
    'hpga_from_shift',
    'hydrostatic_scale',
]


def centered_shift(ds: xr.Dataset) -> xr.DataArray:
    """
    The first-order fixed-pressure shift ``S_{e,k}`` of the design's
    ``[centered-shift]``,

    .. math::

        S_{e,k} = \\tfrac{1}{2}\\left(\\Delta_e Z_{k}
        + \\Delta_e Z_{k+1}\\right)
        + \\frac{\\bar\\alpha_{e,k}}{2g}\\left(\\Delta_e q_{k}
        + \\Delta_e q_{k+1}\\right),

    where :math:`Z` is the geometric height at layer interfaces, :math:`q` the
    gauge pressure at layer interfaces, and :math:`\\bar\\alpha_{e,k}` the edge
    average of the layer-mean specific volume.

    The centered scheme's entire Montgomery-potential apparatus is this
    conversion and nothing else, so
    ``hpga_from_shift(centered_shift(ds), dx)`` reproduces the ``HPGA`` field
    written by :py:class:`~polaris.tasks.ocean.horiz_press_grad.init.Init` to
    round-off, at any coordinate tilt.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, which must contain ``GeomZInterface``,
        ``ZTildeInterface`` and ``SpecVol``.  Invalid layers are ``NaN`` and
        propagate as ``NaN``.

    Returns
    -------
    shift : xarray.DataArray
        ``S_{e,k}`` at layer midpoints, in m, with the ``nCells`` dimension
        contracted away by the edge operator.

    """
    # PressureInterface is not carried in the dataset; pseudo-height is, and
    # p = -rho0 * g * z_tilde is an exact identity rather than a conversion.
    q = pressure_from_z_tilde(ds.ZTildeInterface)

    delta_z = edge_delta(ds.GeomZInterface)
    delta_q = edge_delta(q)
    alpha_bar = edge_mean(ds.SpecVol)

    geometric = 0.5 * (_layer_top(delta_z) + _layer_bot(delta_z))
    pressure = (
        alpha_bar
        / (2.0 * Gravity)
        * (_layer_top(delta_q) + _layer_bot(delta_q))
    )

    shift = geometric + pressure
    return shift.assign_attrs(
        {
            'long_name': 'first-order fixed-pressure height shift at layer '
            'midpoints',
            'units': 'm',
        }
    )


def hpga_from_shift(shift: xr.DataArray, dx: float) -> xr.DataArray:
    """
    Convert a fixed-pressure height shift into an edge-normal acceleration,
    ``-(g / d_e) * shift``.

    Parameters
    ----------
    shift : xarray.DataArray
        A fixed-pressure height shift in m, such as
        :py:func:`centered_shift` returns.

    dx : float
        The distance ``d_e`` between the two columns in m.

    Returns
    -------
    hpga : xarray.DataArray
        The edge-normal pressure-gradient acceleration in m s-2.

    """
    if dx == 0.0:
        raise ValueError('dx must be non-zero for finite differences.')

    hpga = -(Gravity / dx) * shift
    return hpga.assign_attrs(
        {
            'long_name': 'along-layer pressure gradient acceleration at layer '
            'midpoints',
            'units': 'm s-2',
        }
    )


def hydrostatic_scale(ds: xr.Dataset) -> float:
    """
    An upper bound on the magnitude of the two hydrostatic terms that cancel
    in :py:func:`centered_shift`.

    At 3500 m those terms are each of order 3500 m and they cancel to
    millimetres or less, so an absolute tolerance says nothing about whether a
    cancellation is at machine precision.  Every round-off assertion against
    this scheme should be written as a multiple of this scale instead
    (``PGradHighOrder.md`` §3.7.5).

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    Returns
    -------
    scale : float
        The bound, in m.  Multiply by ``Gravity / dx`` to scale a tolerance on
        an acceleration.

    """
    q = pressure_from_z_tilde(ds.ZTildeInterface)
    z_magnitude = float(np.abs(ds.GeomZInterface).max())
    pressure_magnitude = float(ds.SpecVol.max() * np.abs(q).max() / Gravity)
    return z_magnitude + pressure_magnitude


def _layer_top(field: xr.DataArray) -> xr.DataArray:
    """
    The value at each layer's top interface, as a layer-indexed field.

    """
    return field.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )


def _layer_bot(field: xr.DataArray) -> xr.DataArray:
    """
    The value at each layer's bottom interface, as a layer-indexed field.

    """
    return field.isel(nVertLevelsP1=slice(1, None)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )


def centered_shift_accumulated(
    ds: xr.Dataset, anchor: str = 'surface'
) -> xr.DataArray:
    """
    ``S_{e,k}`` accumulated down the column through ``[gamma-increments]``.

    Mathematically identical to :py:func:`centered_shift`, but it never forms
    the two large terms that cancel there.  With
    ``Gamma_{e,k} = Delta_e Z_k + (alphabar_{e,k}/g) Delta_e q_k`` and
    ``Gamma^+_{e,k}`` the same at interface ``k+1``, so that
    ``S_{e,k} = (Gamma + Gamma^+)/2``, the design's ``[gamma-increments]``
    gives

        Gamma^+_{e,k} - Gamma_{e,k}
            = -rho0 * htildebar_{e,k} * Delta_e alpha_k
        Gamma_{e,k+1} - Gamma^+_{e,k}
            = (Delta_e q_{k+1}/g) * (alphabar_{e,k+1} - alphabar_{e,k})

    Both increments are a small factor times a bounded one -- the *horizontal*
    contrast in specific volume within a layer, and the *vertical* contrast
    between adjacent layers -- so the walk introduces no cancellation of large
    numbers anywhere.  The starting value is the inverse-barometer residual at
    the sea surface, itself small for a state at rest.

    Per §3.7.5 this is why a single-precision build might pass at all: the
    round-off exposure of the centered scheme lives entirely in the two ~3500 m
    terms of ``[centered-shift]``, and this form never builds them.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    anchor : {'surface', 'bathymetry'}
        Which end of the column to accumulate from.  §3.7.4 leaves this open as
        a round-off question rather than a consistency one; the two agree to
        round-off in double precision, which
        ``tests/ocean/horiz_press_grad/test_finite_volume.py`` measures.

    Returns
    -------
    shift : xarray.DataArray
        ``S_{e,k}`` at layer midpoints, in m.

    """
    if anchor not in ('surface', 'bathymetry'):
        raise ValueError(
            f"anchor must be 'surface' or 'bathymetry'; got {anchor!r}."
        )

    pieces = _shift_pieces(ds)
    within = pieces['within_layer'].values
    between = pieces['between_layers'].values
    gamma_top = pieces['gamma_surface'].values
    gamma_bottom = pieces['gamma_bathymetry'].values
    valid = pieces['valid'].values

    shift = np.full(within.shape, np.nan)
    for index in np.ndindex(within.shape[:-1]):
        levels = np.where(valid[index])[0]
        if len(levels) == 0:
            continue
        column_within = within[index][levels]
        # between_layers[k] is the step from layer k to layer k+1
        column_between = between[index][levels]

        if anchor == 'surface':
            gamma = gamma_top[index]
            for position, level in enumerate(levels):
                gamma_plus = gamma + column_within[position]
                shift[index + (level,)] = 0.5 * (gamma + gamma_plus)
                gamma = gamma_plus + column_between[position]
        else:
            gamma_plus = gamma_bottom[index]
            for position in range(len(levels) - 1, -1, -1):
                level = levels[position]
                gamma = gamma_plus - column_within[position]
                shift[index + (level,)] = 0.5 * (gamma + gamma_plus)
                if position > 0:
                    gamma_plus = gamma - column_between[position - 1]

    return xr.DataArray(
        data=shift,
        dims=pieces['within_layer'].dims,
        attrs={
            'long_name': 'first-order fixed-pressure height shift at layer '
            'midpoints, accumulated',
            'units': 'm',
        },
    )


def shift_increments(ds: xr.Dataset) -> xr.Dataset:
    """
    The two increments of ``[gamma-increments]``, for the D7 measurement.

    Deliverable D7 of the plan asks how much precision the accumulation saves,
    and the quantitative form of "no large-number cancellation occurs" is the
    ratio of the largest increment to the largest of ``Delta_e Z`` -- the
    quantity ``[centered-shift]`` differences directly.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    Returns
    -------
    increments : xarray.Dataset
        ``within_layer`` (``Gamma^+_k - Gamma_k``), ``between_layers``
        (``Gamma_{k+1} - Gamma^+_k``), and ``delta_z_interface``
        (``Delta_e Z`` at interfaces) to scale them against.  All in m.

    """
    pieces = _shift_pieces(ds)
    return xr.Dataset(
        {
            'within_layer': pieces['within_layer'],
            'between_layers': pieces['between_layers'],
            'delta_z_interface': pieces['delta_z_interface'],
        }
    )


def _shift_pieces(ds: xr.Dataset) -> dict:
    """The increments and anchors of ``[gamma-increments]``, and the mask of
    layers valid in both columns.
    """
    q = pressure_from_z_tilde(ds.ZTildeInterface)
    delta_q = edge_delta(q)
    delta_z = edge_delta(ds.GeomZInterface)
    alpha_bar = edge_mean(ds.SpecVol)
    delta_alpha = edge_delta(ds.SpecVol)
    thickness_bar = edge_mean(ds.PseudoThickness)

    within = -RhoSw * thickness_bar * delta_alpha

    # the step from layer k to layer k+1, stored at k; the deepest layer has no
    # neighbour below and its entry is never read
    alpha_below = alpha_bar.shift(nVertLevels=-1)
    between = _layer_bot(delta_q) / Gravity * (alpha_below - alpha_bar)
    between = between.fillna(0.0)

    valid = np.isfinite(within)

    gamma_surface = _first_valid(
        _layer_top(delta_z) + alpha_bar / Gravity * _layer_top(delta_q), valid
    )
    gamma_bathymetry = _last_valid(
        _layer_bot(delta_z) + alpha_bar / Gravity * _layer_bot(delta_q), valid
    )

    return {
        'within_layer': within.assign_attrs({'units': 'm'}),
        'between_layers': between.assign_attrs({'units': 'm'}),
        'delta_z_interface': delta_z.assign_attrs({'units': 'm'}),
        'gamma_surface': gamma_surface,
        'gamma_bathymetry': gamma_bathymetry,
        'valid': valid,
    }


def _first_valid(field: xr.DataArray, valid: xr.DataArray) -> xr.DataArray:
    """The value in the shallowest layer valid in both columns."""
    return _at_valid_end(field, valid, first=True)


def _last_valid(field: xr.DataArray, valid: xr.DataArray) -> xr.DataArray:
    """The value in the deepest layer valid in both columns."""
    return _at_valid_end(field, valid, first=False)


def _at_valid_end(
    field: xr.DataArray, valid: xr.DataArray, first: bool
) -> xr.DataArray:
    values = field.values
    mask = valid.values
    result = np.full(values.shape[:-1], np.nan)
    for index in np.ndindex(values.shape[:-1]):
        levels = np.where(mask[index])[0]
        if len(levels) == 0:
            continue
        result[index] = values[index][levels[0 if first else -1]]
    return xr.DataArray(data=result, dims=field.dims[:-1])
