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


# The reductions a step can offer without reading any vertical geometry, since
# they pick a layer by index.  Interpolating to an elevation reads ``zMid``
# and ``zInterface``, which the map step does not pass yet.  An elevation
# range is not a slice and is not here at all; see ``elevation_range_weights``.
IMPLEMENTED_KINDS = ('top', 'bottom', 'index')

# The dimension the layer interfaces are along, one longer than ``nVertLevels``
INTERFACE_DIM = 'nVertLevelsP1'


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

    Both options describe a way of reducing the ``nVertLevels`` dimension,
    so
    both are parsed here and the result says which way it is.

    Parameters
    ----------
    spec : str
        One of ``'top'``, ``'bottom'``, ``'k<index>'`` with a zero-based
        index, an elevation in m (positive up, so negative within the
        ocean), or an elevation range written
        ``<top_elevation>:<bottom_elevation>``

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


def range_bound_label(elevation):
    """
    Get the label one end of an elevation range is identified by

    Which end it is follows from the bound itself, since a bound that
    resolves per column is an infinity with the sign of the end it is.

    Parameters
    ----------
    elevation : float
        The elevation of the bound in m, positive up, ``np.inf`` for the sea
        surface or ``-np.inf`` for the seafloor

    Returns
    -------
    label : str
        The label, e.g. ``'top'``, ``'bottom'`` or ``'-700m'``
    """
    if elevation == np.inf:
        return 'top'
    if elevation == -np.inf:
        return 'bottom'
    return elevation_label(elevation)


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

    The whole column, ``top:bottom``, is the one range in which every valid
    layer is whole, so its overlap fraction is one, no ``z_interface`` is read
    and none need be passed.

    Parameters
    ----------
    z_interface : xarray.DataArray or None
        The elevation of layer interfaces, needed for any range but the whole
        column

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
    ValueError
        If a range with a finite bound is asked for without ``z_interface``
    """
    n_levels = layer_mass.sizes['nVertLevels']
    levels = xr.DataArray(np.arange(n_levels), dims='nVertLevels')
    in_column = (levels >= min_level_cell) & (levels <= max_level_cell)

    if z_interface is None:
        if not (z_top == np.inf and z_bot == -np.inf):
            raise ValueError(
                'z_interface is needed to weigh an elevation range with a '
                'bound in the interior of a layer.  The one range that needs '
                'no vertical geometry is the whole column, top:bottom, in '
                'which every valid layer is whole.'
            )
        fraction = 1.0
    else:
        z_upper = _layer_bound(z_interface, slice(0, -1))
        z_lower = _layer_bound(z_interface, slice(1, None))
        thickness = z_upper - z_lower
        overlap = np.minimum(z_upper, z_top) - np.maximum(z_lower, z_bot)
        # a layer the range misses entirely has a negative overlap, and one
        # with no thickness has no fraction to speak of; both weigh nothing
        fraction = xr.where(
            thickness > 0.0, np.maximum(overlap, 0.0) / thickness, 0.0
        )

    # a layer outside the range or outside the column weighs nothing rather
    # than NaN, since a model may write anything below the seafloor and a NaN
    # here would poison the sum the weights are for
    weights = (layer_mass * fraction).where(in_column, 0.0)
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
    min_level_cell=None,
    max_level_cell=None,
):
    """
    Reduce a field with a vertical dimension to a horizontal map

    Slicing at the sea surface, the seafloor, a layer index or an elevation
    are cases of one operation: each picks one layer of each column, or the
    two layers an elevation falls between, for any DataArray.  Only
    the last of them reads the vertical geometry.

    Parameters
    ----------
    da : xarray.DataArray
        The field to reduce, with an ``nVertLevels`` dimension

    reduction : VerticalReduction
        How to reduce it, from :py:func:`parse_vertical_reduction`

    z_mid : xarray.DataArray, optional
        The elevation of layer midpoints, needed only to interpolate to an
        elevation

    z_interface : xarray.DataArray, optional
        The elevation of layer interfaces, as for ``z_mid``

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
    ValueError
        If the reduction is a range, or if what it needs was not passed
    """
    if reduction.kind == 'range':
        raise ValueError(
            'An elevation range is not a slice of a field but a weighted '
            'integral of it, so it goes through elevation_range_weights and '
            'the diagnostic that consumes the weights, rather than through '
            'apply_vertical_reduction.'
        )
    if min_level_cell is None or max_level_cell is None:
        raise ValueError(
            'min_level_cell and max_level_cell are needed to tell the valid '
            'layers of each column from the rest.'
        )

    if reduction.kind == 'elevation':
        return _interpolate_to_elevation(
            da=da,
            elevation=reduction.elevation,
            z_mid=z_mid,
            z_interface=z_interface,
            min_level_cell=min_level_cell,
            max_level_cell=max_level_cell,
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


def _layer_bound(z_interface, levels):
    """One of the two interfaces bounding each layer, along ``nVertLevels``"""
    z_bound = z_interface.isel({INTERFACE_DIM: levels})
    return z_bound.drop_vars(INTERFACE_DIM, errors='ignore').rename(
        {INTERFACE_DIM: 'nVertLevels'}
    )


def _interpolate_to_elevation(
    da, elevation, z_mid, z_interface, min_level_cell, max_level_cell
):
    """
    Interpolate a field linearly in elevation between the two layer midpoints
    an elevation falls between

    The search for the upper of the two layers is a count rather than a loop
    over columns: with the midpoints outside the valid range set to ``NaN``,
    the number of valid midpoints at or above the elevation says how far
    below the topmost valid layer it lies.

    Above the topmost midpoint the topmost value is returned, and below the
    bottommost midpoint the bottommost one, rather than either being masked
    or extrapolated.  Both fall out of clamping the interpolation weight into
    ``[0, 1]``, and the clamping at the top is deliberate: a request for 0 m
    or -5 m lies above every midpoint, and masking it would leave a
    near-surface map empty everywhere.
    """
    if z_mid is None or z_interface is None:
        raise ValueError(
            'z_mid and z_interface are needed to interpolate to an '
            'elevation, which is a position in the vertical geometry rather '
            'than a layer of the grid.'
        )

    n_levels = da.sizes['nVertLevels']
    levels = xr.DataArray(np.arange(n_levels), dims='nVertLevels')
    in_column = (levels >= min_level_cell) & (levels <= max_level_cell)
    # a layer outside the valid range has no position in the column, so it
    # takes no part in the search and cannot supply a value
    z_valid = z_mid.where(in_column)

    # the count is of valid midpoints, so it is measured from the topmost
    # valid layer of the column rather than from layer zero, which is not the
    # same thing under an ice-shelf cavity
    above = (z_valid >= elevation).sum(dim='nVertLevels')
    k_upper = min_level_cell + above - 1
    # the pair is (k_upper, k_upper + 1), so the lowest pair of a column
    # starts one layer above its seafloor.  A column with a single valid
    # layer has no pair at all and is handled below; land has none either and
    # is masked, so both only need an index that can be taken safely.
    lowest_pair = np.maximum(max_level_cell - 1, min_level_cell)
    k_upper = np.minimum(np.maximum(k_upper, min_level_cell), lowest_pair)
    k_upper = np.minimum(np.maximum(k_upper, 0), n_levels - 1)
    k_lower = np.minimum(k_upper + 1, n_levels - 1)

    z_upper = z_valid.isel(nVertLevels=k_upper)
    z_lower = z_valid.isel(nVertLevels=k_lower)
    thickness = z_upper - z_lower
    weight = xr.where(thickness > 0.0, (elevation - z_lower) / thickness, 1.0)
    weight = np.minimum(np.maximum(weight, 0.0), 1.0)

    da_upper = da.isel(nVertLevels=k_upper)
    da_lower = da.isel(nVertLevels=k_lower)
    # a column with one valid layer is that layer everywhere within it; the
    # layer below is outside the column, so it is selected away rather than
    # weighted by zero, which would let a fill value poison the sum
    single_layer = min_level_cell >= max_level_cell
    da_map = xr.where(
        single_layer, da_upper, weight * da_upper + (1.0 - weight) * da_lower
    )

    # land has no layer to take a value from, and an elevation below the
    # seafloor has no water at it
    n_interfaces = z_interface.sizes[INTERFACE_DIM]
    k_floor = np.minimum(np.maximum(max_level_cell + 1, 0), n_interfaces - 1)
    z_floor = z_interface.isel({INTERFACE_DIM: k_floor})
    in_water = (max_level_cell >= min_level_cell) & (elevation >= z_floor)

    da_map = da_map.where(in_water)
    return da_map.drop_vars(['nVertLevels', INTERFACE_DIM], errors='ignore')


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
    top_label = range_bound_label(z_top)
    bot_label = range_bound_label(z_bot)
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
