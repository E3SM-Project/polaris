"""
Reduce a field with a vertical dimension to a horizontal map.

Slicing at the sea surface, the seafloor, a layer index or an elevation, and
integrating over an elevation range, are cases of one operation: every one of
them turns ``nVertLevels`` into nothing.  Keeping them behind a single entry
point is what lets ocean heat content be a field of the climatology maps
rather than a product of its own.

This module is deliberately dependency-light --- it imports nothing from
:py:class:`polaris.Step` --- so that it can be unit tested directly and reused
by any vertically reduced diagnostic.
"""

from typing import NamedTuple, Optional

import numpy as np
import xarray as xr


class VerticalReduction(NamedTuple):
    """
    One way of reducing a field with a vertical dimension to a horizontal map

    Attributes
    ----------
    kind : str
        ``'top'``, ``'bottom'``, ``'index'`` or ``'elevation'``

    label : str
        The label that identifies the reduction in a file name and a plot
        title, e.g. ``'top'``, ``'k10'`` or ``'-100m'``

    level : int or None
        The zero-based vertical index, for ``'index'``

    elevation : float or None
        The elevation in m, positive up, for ``'elevation'``
    """

    kind: str
    label: str
    level: Optional[int] = None
    elevation: Optional[float] = None


# The reductions that pick a layer by index need no vertical geometry at all,
# so they work before there is any.  Interpolating to an elevation and
# integrating over an elevation range both read ``zMid`` and ``zInterface``
# and are not implemented yet.
IMPLEMENTED_KINDS = ('top', 'bottom', 'index')


def parse_vertical_reduction(spec):
    """
    Parse one entry of the ``elevations`` config option

    Parameters
    ----------
    spec : str
        ``'top'``, ``'bottom'``, ``'k<index>'`` with a zero-based index, or an
        elevation in m, positive up, so negative within the ocean

    Returns
    -------
    reduction : VerticalReduction
        The parsed reduction

    Raises
    ------
    ValueError
        If ``spec`` is none of those
    """
    spec = spec.strip()
    lowered = spec.lower()

    if lowered in ('top', 'bottom'):
        return VerticalReduction(kind=lowered, label=lowered)

    if lowered.startswith('k'):
        try:
            index = int(spec[1:])
        except ValueError:
            index = -1
        if index < 0:
            raise ValueError(
                f'"{spec}" is not a vertical index.  A fixed layer is given '
                f'as k<index> with a zero-based index, e.g. k0 for the '
                f'topmost layer of the grid.'
            )
        return VerticalReduction(kind='index', label=f'k{index}', level=index)

    try:
        elevation = float(spec)
    except ValueError:
        raise ValueError(
            f'"{spec}" is not a vertical reduction.  Use "top", "bottom", '
            f'"k<index>" for a fixed layer, or an elevation in m, positive '
            f'up, so negative within the ocean.'
        ) from None
    return VerticalReduction(
        kind='elevation',
        label=elevation_label(elevation),
        elevation=elevation,
    )


def elevation_label(elevation):
    """
    Get the label an elevation is identified by in file names and plot titles

    Parameters
    ----------
    elevation : float
        The elevation in m, positive up

    Returns
    -------
    label : str
        The label, e.g. ``'-100m'``
    """
    return f'{elevation:g}m'


def apply_vertical_reduction(
    da,
    reduction,
    z_mid=None,
    z_interface=None,
    layer_mass=None,
    min_level_cell=None,
    max_level_cell=None,
):
    """
    Reduce a field with a vertical dimension to a horizontal map

    Only the reductions in :py:data:`IMPLEMENTED_KINDS` are available so far;
    interpolating to an elevation and integrating over an elevation range
    raise :py:exc:`NotImplementedError`, since they need vertical geometry
    that nothing writes yet.

    Parameters
    ----------
    da : xarray.DataArray
        The field to reduce, with an ``nVertLevels`` dimension

    reduction : VerticalReduction
        How to reduce it, from :py:func:`parse_vertical_reduction`

    z_mid : xarray.DataArray, optional
        The elevation of layer midpoints, needed only for the reductions that
        are not implemented yet

    z_interface : xarray.DataArray, optional
        The elevation of layer interfaces, as for ``z_mid``

    layer_mass : xarray.DataArray, optional
        The mass per unit area of each layer, as for ``z_mid``

    min_level_cell : xarray.DataArray
        The zero-based index of the topmost valid layer of each column

    max_level_cell : xarray.DataArray
        The zero-based index of the bottommost valid layer of each column

    Returns
    -------
    da_map : xarray.DataArray
        The reduced field, without an ``nVertLevels`` dimension, masked where
        the reduction falls outside the column

    Raises
    ------
    NotImplementedError
        If the reduction needs vertical geometry
    """
    if reduction.kind not in IMPLEMENTED_KINDS:
        raise NotImplementedError(
            f'Reducing a field to {reduction.label} needs the vertical '
            f'geometry, which is not implemented yet.  The reductions that '
            f'work are "top", "bottom" and "k<index>".'
        )
    if min_level_cell is None or max_level_cell is None:
        raise ValueError(
            'min_level_cell and max_level_cell are needed to tell the valid '
            'layers of each column from the rest.'
        )

    n_levels = da.sizes['nVertLevels']
    if reduction.kind == 'top':
        index = min_level_cell
    elif reduction.kind == 'bottom':
        index = max_level_cell
    else:
        index = xr.full_like(min_level_cell, reduction.level)

    # a column is land where maxLevelCell is above minLevelCell, and an index
    # outside the valid range has no value to take, so both are masked rather
    # than extrapolated
    in_column = (index >= min_level_cell) & (index <= max_level_cell)
    # index into the array only where there is something to index, so that a
    # masked column cannot raise
    safe = np.minimum(np.maximum(index, 0), n_levels - 1)

    da_map = da.isel(nVertLevels=safe).where(in_column)
    return da_map.drop_vars('nVertLevels', errors='ignore')
