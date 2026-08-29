"""
Reduce a field with a vertical dimension to a horizontal map.

Slicing at the sea surface, the seafloor, a layer index or an elevation, and
integrating over an elevation range, both turn ``nVertLevels`` into nothing,
and both are described by the same parsed reduction.  That is what lets ocean
heat content be a field group of the climatology maps rather than a product of
its own.

They differ in how they get there.  A slice picks one layer, and
``apply_vertical_reduction`` does that for any field.  A range is a weighted
integral, so this module supplies the weights --- ``elevation_range_weights``
--- and the diagnostic that consumes them supplies the rest, because what the
weighted sum of a field means is a property of the diagnostic rather than of
the vertical coordinate.

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
        ``'top'``, ``'bottom'``, ``'index'``, ``'elevation'`` or ``'range'``

    label : str
        The label that identifies the reduction in a file name and a plot
        title, e.g. ``'top'``, ``'k10'``, ``'-100m'`` or ``'top_to_-700m'``

    level : int or None
        The zero-based vertical index, for ``'index'``

    elevation : float or None
        The elevation in m, positive up, for ``'elevation'``

    z_top : float or None
        The upper bound of the range in m, positive up, for ``'range'``.  It
        is ``inf`` where the bound is the free surface of each column.

    z_bot : float or None
        The lower bound of the range in m, positive up, for ``'range'``.  It
        is ``-inf`` where the bound is the seafloor of each column.
    """

    kind: str
    label: str
    level: Optional[int] = None
    elevation: Optional[float] = None
    z_top: Optional[float] = None
    z_bot: Optional[float] = None


# The reductions that pick a layer by index need no vertical geometry at all,
# so they work before there is any.  Interpolating to an elevation reads
# ``zMid`` and ``zInterface`` and is not implemented yet.  An elevation range
# is not a slice and is not here at all; see ``elevation_range_weights``.
IMPLEMENTED_KINDS = ('top', 'bottom', 'index')


def get_valid_level_range(ds):
    """
    Get the zero-based indices of the topmost and bottommost valid layer of
    each column

    Both models write ``minLevelCell`` and ``maxLevelCell`` with the one-based
    indexing of MPAS-Ocean's Fortran, so this is the one place that converts
    them to the zero-based indices the reductions use.

    A data set with no ``minLevelCell`` has no ice-shelf cavities, so the
    topmost valid layer is the topmost layer of the grid.

    Parameters
    ----------
    ds : xarray.Dataset
        The vertical coordinate, with MPAS-Ocean names

    Returns
    -------
    min_level_cell : xarray.DataArray
        The zero-based index of the topmost valid layer of each column

    max_level_cell : xarray.DataArray
        The zero-based index of the bottommost valid layer of each column

    Raises
    ------
    ValueError
        If the data set has no ``maxLevelCell``, without which a column has
        no seafloor
    """
    if 'maxLevelCell' not in ds:
        raise ValueError(
            'The vertical coordinate has no maxLevelCell, so there is no '
            'way to tell the valid layers of a column from the rest.'
        )
    max_level_cell = ds.maxLevelCell - 1
    if 'minLevelCell' in ds:
        min_level_cell = ds.minLevelCell - 1
    else:
        min_level_cell = xr.zeros_like(max_level_cell)
    return min_level_cell, max_level_cell


def parse_vertical_reduction(spec):
    """
    Parse one entry of the ``elevations`` or the ``elevation_ranges`` config
    option

    Both options describe a way of turning ``nVertLevels`` into nothing, so
    both are parsed here and the result says which way it is.

    Parameters
    ----------
    spec : str
        ``'top'``, ``'bottom'``, ``'k<index>'`` with a zero-based index, an
        elevation in m, positive up, so negative within the ocean, or an
        elevation range written ``<top>:<bottom>``

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

    if ':' in spec:
        return _parse_elevation_range(spec)

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


def is_whole_column(reduction):
    """
    Whether an elevation range covers every valid layer of every column

    The whole column is the one range whose weights need no geometry at all.
    Every valid layer lies entirely within it, so the overlap fraction is one
    and the geometric coordinate drops out of the answer, which is why it is
    the range that works before there is any vertical geometry to read.

    Parameters
    ----------
    reduction : VerticalReduction
        The reduction to ask about

    Returns
    -------
    whole_column : bool
        Whether it is the whole column
    """
    return (
        reduction.kind == 'range'
        and reduction.z_top == np.inf
        and reduction.z_bot == -np.inf
    )


def elevation_range_weights(
    z_interface,
    layer_mass,
    min_level_cell,
    max_level_cell,
    z_top,
    z_bot,
):
    r"""
    Get the mass per unit area of the part of each layer within an elevation
    range

    The range is given in geometric elevation while the integral it weights is
    in mass, so the geometric overlap thickness

    .. math::
        w_k = \max\left(0, \min(z^{int}_k, z_{top}) -
              \max(z^{int}_{k+1}, z_{bot})\right)

    is computed from ``z_interface`` and used only as the fraction
    :math:`w_k / h_k` of the layer, which is then applied to ``layer_mass``.
    A layer lying entirely within the range therefore contributes its whole
    mass, and the geometric coordinate enters only through the partial layers
    at the boundaries.

    Only the whole column, ``top:bottom``, is implemented so far.  It is the
    range in which every valid layer is whole, so no ``z_interface`` is read
    and none need be passed.  A range with a boundary in the interior of a
    layer needs the vertical geometry and is not implemented yet.

    Parameters
    ----------
    z_interface : xarray.DataArray or None
        The elevation of layer interfaces, needed only for a range with a
        finite boundary

    layer_mass : xarray.DataArray
        The mass per unit area of each layer, from
        :py:func:`polaris.ocean.model.get_layer_mass`.  Passing differences of
        ``z_interface`` instead recovers the purely geometric weights.

    min_level_cell : xarray.DataArray
        The zero-based index of the topmost valid layer of each column

    max_level_cell : xarray.DataArray
        The zero-based index of the bottommost valid layer of each column

    z_top : float
        The upper bound of the range in m, positive up, or ``inf`` for the
        free surface of each column

    z_bot : float
        The lower bound of the range in m, positive up, or ``-inf`` for the
        seafloor of each column

    Returns
    -------
    weights : xarray.DataArray
        The mass per unit area of the overlap of each layer with the range,
        zero outside the valid layers of a column

    Raises
    ------
    NotImplementedError
        If either bound is a finite elevation
    """
    if not (z_top == np.inf and z_bot == -np.inf):
        raise NotImplementedError(
            'Weighting an elevation range with a boundary in the interior of '
            'a layer needs the vertical geometry, which is not implemented '
            'yet.  The range that works is the whole column, top:bottom.'
        )

    n_levels = layer_mass.sizes['nVertLevels']
    levels = xr.DataArray(np.arange(n_levels), dims='nVertLevels')
    in_column = (levels >= min_level_cell) & (levels <= max_level_cell)
    weights = layer_mass.where(in_column, 0.0)
    weights.attrs = dict(
        units='kg m-2',
        long_name='mass per unit area within the elevation range',
    )
    return weights


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
    if reduction.kind == 'range':
        raise ValueError(
            'An elevation range is not a slice of a field but a weighted '
            'integral of it, so it goes through elevation_range_weights and '
            'the diagnostic that consumes the weights, rather than through '
            'apply_vertical_reduction.'
        )
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


def _parse_elevation_range(spec):
    """Parse an elevation range written ``<top>:<bottom>``"""
    parts = spec.split(':')
    if len(parts) != 2:
        raise ValueError(
            f'"{spec}" is not an elevation range.  A range is given as '
            f'<top>:<bottom> in m, positive up, e.g. top:-700.0.'
        )
    z_top = _parse_range_bound(spec, parts[0], 'top')
    z_bot = _parse_range_bound(spec, parts[1], 'bottom')
    if z_top <= z_bot:
        raise ValueError(
            f'The elevation range "{spec}" does not descend.  A range is '
            f'given as <top>:<bottom> in m, positive up, so the first '
            f'elevation is the higher one.'
        )
    top_label = _range_bound_label(z_top, 'top')
    bot_label = _range_bound_label(z_bot, 'bottom')
    return VerticalReduction(
        kind='range',
        label=f'{top_label}_to_{bot_label}',
        z_top=z_top,
        z_bot=z_bot,
    )


def _parse_range_bound(spec, text, keyword):
    """Parse one end of an elevation range, which may be a keyword"""
    text = text.strip()
    if text.lower() == keyword:
        return np.inf if keyword == 'top' else -np.inf
    try:
        return float(text)
    except ValueError:
        raise ValueError(
            f'"{text}" is not the {keyword} of the elevation range "{spec}".'
            f'  It is either "{keyword}" or an elevation in m, positive up, '
            f'so negative within the ocean.'
        ) from None


def _range_bound_label(elevation, keyword):
    """The label one end of an elevation range is identified by"""
    if np.isinf(elevation):
        return keyword
    return elevation_label(elevation)
