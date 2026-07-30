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

Every horizontal difference here is the two-column edge operator.  The mesh has
exactly two cells and one internal edge, and the edge normal points from cell 0
to cell 1, so ``Delta_e f = f_1 - f_0`` and ``[grad_n f]_e = Delta_e f / d_e``.
That is the convention
:py:meth:`polaris.tasks.ocean.horiz_press_grad.init.Init._compute_montgomery_and_hpga`
uses, and the identity in :py:func:`centered_shift` holds against that function
and not against an idealized centered form.
"""

import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import Gravity, pressure_from_z_tilde

__all__ = [
    'centered_shift',
    'hpga_from_shift',
    'hydrostatic_scale',
    'edge_delta',
    'edge_mean',
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


def edge_delta(field: xr.DataArray) -> xr.DataArray:
    """
    The two-column edge difference ``Delta_e f = f_1 - f_0``, the numerator of
    the TRiSK gradient operator for the single internal edge.

    Parameters
    ----------
    field : xarray.DataArray
        A field with an ``nCells`` dimension of size 2.

    Returns
    -------
    delta : xarray.DataArray
        The difference, with ``nCells`` contracted away.
    """
    _check_two_columns(field)
    return field.isel(nCells=1) - field.isel(nCells=0)


def edge_mean(field: xr.DataArray) -> xr.DataArray:
    """
    The two-column edge average ``0.5 * (f_0 + f_1)``.

    Parameters
    ----------
    field : xarray.DataArray
        A field with an ``nCells`` dimension of size 2.

    Returns
    -------
    mean : xarray.DataArray
        The average, with ``nCells`` contracted away.
    """
    _check_two_columns(field)
    return 0.5 * (field.isel(nCells=0) + field.isel(nCells=1))


def _check_two_columns(field: xr.DataArray) -> None:
    """
    Verify that ``field`` spans exactly the two columns the edge operator is
    defined for.
    """
    ncells = field.sizes.get('nCells', 0)
    if ncells != 2:
        raise ValueError(
            'The two-column edge operator requires exactly 2 cells, but the '
            f'field has {ncells}.'
        )


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
