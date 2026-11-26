"""
Overturning across lines of constant x or y on planar MPAS meshes, and
across lines of constant latitude on spherical ones.

A line is represented by the edges whose two cells lie on opposite sides
of it.  Summing the signed transports through those edges gives the exact
discrete transport from the cells on one side of the line to the cells on
the other, on any planar mesh: the zigzag between two rows of cells on a
planar hex mesh, or a staircase within about one cell of the line on any
other mesh.  Only ``cellsOnEdge``, the cell coordinates, ``dvEdge`` and
``dcEdge`` are used, so no mesh structure is assumed.
"""

from typing import Literal, Optional, Tuple

import numpy as np
import xarray as xr
from numpy.typing import ArrayLike

LineCoordType = Literal['x', 'y']


def get_line_edges(
    ds_mesh: xr.Dataset, coord: LineCoordType, value: float
) -> xr.Dataset:
    """
    Find the edges crossing a line of constant x or y on a planar mesh

    An edge crosses the line ``coord = value`` if its two cells lie on
    opposite sides of it.  Edges on a domain boundary are never included.
    Across a periodic seam, cell positions are unwrapped, so the line may
    lie anywhere in the domain.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        A planar MPAS mesh, with ``cellsOnEdge``, ``xCell``, ``yCell``,
        ``dvEdge`` and ``dcEdge`` and the ``x_period`` and ``y_period``
        attributes (zero where the mesh is not periodic)

    coord : {'x', 'y'}
        The coordinate that is constant along the line

    value : float
        The value of ``coord`` on the line (m)

    Returns
    -------
    line : xarray.Dataset
        A dataset with dimension ``nLineEdges`` containing:

        ``edgeIndex``
            zero-based indices of the edges crossing the line

        ``cellsOnLineEdge``
            zero-based indices of the two cells of each edge, with
            dimension ``TWO``

        ``sign``
            +1 where positive normal velocity (from the first cell of the
            edge to the second) is toward increasing ``coord``, -1
            otherwise

        ``dvEdge``
            the length of each edge (m)

        ``weight``
            the length of each edge projected onto the line (m), used
            for along-line means; the weights sum to the length of the
            line

        The ``coord``, ``value`` and ``length`` attributes record the line
        and its length (m).
    """
    if coord not in ('x', 'y'):
        raise ValueError(f'Unexpected line coordinate: {coord}')

    n_cells = ds_mesh.sizes['nCells']
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    cell_pos = ds_mesh[f'{coord}Cell'].values
    period = float(ds_mesh.attrs.get(f'{coord}_period', 0.0))

    valid = np.logical_and(
        np.all(cells_on_edge >= 0, axis=1),
        np.all(cells_on_edge < n_cells, axis=1),
    )
    edge_indices = np.flatnonzero(valid)
    cell1 = cells_on_edge[edge_indices, 0]
    cell2 = cells_on_edge[edge_indices, 1]

    # displacement from the first cell to the second, wrapped to the
    # nearest periodic image
    pos1 = cell_pos[cell1]
    delta = cell_pos[cell2] - pos1
    if period > 0.0:
        delta = delta - period * np.round(delta / period)

    # the offset of the line from the first cell, wrapped into
    # [0, period) so a line on the other side of a periodic seam is found
    offset = value - pos1
    if period > 0.0:
        offset = np.mod(offset, period)

    # an edge from pos1 to pos1 + delta crosses the line if
    # pos1 < value <= pos1 + delta (delta > 0) or
    # pos1 + delta < value <= pos1 (delta < 0)
    increasing = np.logical_and(
        delta > 0.0, np.logical_and(offset > 0.0, offset <= delta)
    )
    if period > 0.0:
        # the line just below pos1, reached by wrapping, lies at
        # offset - period
        below = np.where(offset == 0.0, 0.0, offset - period)
    else:
        below = offset
    decreasing = np.logical_and(
        delta < 0.0, np.logical_and(below > delta, below <= 0.0)
    )
    crossing = np.logical_or(increasing, decreasing)

    edge_indices = edge_indices[crossing]
    delta = delta[crossing]
    cells = np.stack([cell1[crossing], cell2[crossing]], axis=1)

    dv_edge = ds_mesh.dvEdge.values[edge_indices]
    dc_edge = ds_mesh.dcEdge.values[edge_indices]
    sign = np.sign(delta)
    weight = dv_edge * np.abs(delta) / dc_edge

    line = xr.Dataset(
        data_vars=dict(
            edgeIndex=(('nLineEdges',), edge_indices),
            cellsOnLineEdge=(('nLineEdges', 'TWO'), cells),
            sign=(('nLineEdges',), sign),
            dvEdge=(('nLineEdges',), dv_edge),
            weight=(('nLineEdges',), weight),
        ),
        attrs=dict(coord=coord, value=value, length=float(weight.sum())),
    )
    return line


def interp_cell_to_line_edges(
    line: xr.Dataset, cell_field: xr.DataArray
) -> xr.DataArray:
    """
    Average a cell field to the edges of a line

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges`

    cell_field : xarray.DataArray
        A field with dimension ``nCells``

    Returns
    -------
    edge_field : xarray.DataArray
        The mean of the field in the two cells of each edge, with
        ``nCells`` replaced by ``nLineEdges``
    """
    cells = line.cellsOnLineEdge
    field1 = cell_field.isel(nCells=cells.isel(TWO=0))
    field2 = cell_field.isel(nCells=cells.isel(TWO=1))
    return 0.5 * (field1 + field2)


def compute_line_transport(
    line: xr.Dataset,
    normal_velocity: xr.DataArray,
    layer_thickness: xr.DataArray,
) -> xr.DataArray:
    """
    Compute the transport across a line in each layer of each edge

    The flux thickness on each edge is the mean of the layer thicknesses of
    its two cells, the default in both MPAS-Ocean and Omega.  For Omega,
    pass the pseudo-thickness, which makes the transport a mass transport
    divided by a reference density.

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges`

    normal_velocity : xarray.DataArray
        The normal velocity (m s-1) with dimension ``nEdges``, typically
        also with ``Time`` and ``nVertLevels``

    layer_thickness : xarray.DataArray
        The layer thickness (m) with dimension ``nCells`` and the same
        other dimensions as ``normal_velocity``

    Returns
    -------
    transport : xarray.DataArray
        The transport (m3 s-1) toward increasing ``line.coord`` through
        each edge of the line, with ``nEdges`` replaced by ``nLineEdges``
    """
    velocity = normal_velocity.isel(nEdges=line.edgeIndex)
    thickness = interp_cell_to_line_edges(line, layer_thickness)
    transport = velocity * thickness * (line.sign * line.dvEdge)
    transport = transport.transpose(*velocity.dims)
    transport.attrs = dict(
        long_name=f'transport toward increasing {line.coord}',
        units='m3 s-1',
    )
    return transport


def compute_overturning(
    transport: xr.DataArray, vert_dim: str = 'nVertLevels'
) -> xr.DataArray:
    """
    Compute the overturning stream function at layer interfaces

    The stream function is zero at the surface and, at each interface, is
    the transport toward increasing ``line.coord`` summed along the line
    and over the layers above the interface.  The velocity across the
    line, integrated along it, is then minus the vertical derivative of
    the stream function.

    Parameters
    ----------
    transport : xarray.DataArray
        Transport from :py:func:`compute_line_transport`, with dimensions
        ``nLineEdges`` and ``vert_dim``

    vert_dim : str, optional
        The vertical dimension, indexed from the top

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) with ``nLineEdges``
        removed and ``vert_dim`` replaced by ``nVertLevelsP1``
    """
    layer_transport = transport.sum(dim='nLineEdges')
    cumulative = layer_transport.cumsum(dim=vert_dim)
    surface = xr.zeros_like(layer_transport.isel({vert_dim: [0]}))
    overturning = xr.concat([surface, cumulative], dim=vert_dim)
    overturning = overturning.rename({vert_dim: 'nVertLevelsP1'})
    dims = [dim for dim in transport.dims if dim != 'nLineEdges']
    dims = ['nVertLevelsP1' if dim == vert_dim else dim for dim in dims]
    overturning = overturning.transpose(*dims)
    overturning.attrs = dict(
        long_name='overturning stream function', units='m3 s-1'
    )
    return overturning


def bin_line_transport(
    transport: xr.DataArray,
    edge_thickness: xr.DataArray,
    edge_tracer: xr.DataArray,
    bins: np.ndarray,
    vert_dim: str = 'nVertLevels',
) -> xr.Dataset:
    """
    Sort the transport and thickness on each edge of a line into tracer
    classes, for overturning in tracer (e.g. density) coordinates

    Parameters
    ----------
    transport : xarray.DataArray
        Transport from :py:func:`compute_line_transport`, with dimensions
        ``nLineEdges`` and ``vert_dim``

    edge_thickness : xarray.DataArray
        The layer thickness on each edge of the line, e.g. from
        :py:func:`interp_cell_to_line_edges`, with the same dimensions as
        ``transport``

    edge_tracer : xarray.DataArray
        The tracer on each edge of the line, with the same dimensions as
        ``transport``

    bins : numpy.ndarray
        Monotonically increasing bin boundaries; values outside them fall
        into no bin

    vert_dim : str, optional
        The vertical dimension

    Returns
    -------
    ds_binned : xarray.Dataset
        A dataset with ``vert_dim`` replaced by ``nBins``, containing
        ``transport`` (m3 s-1) and ``thickness`` (m) summed over the
        layers in each class, and the coordinates ``binLower`` and
        ``binUpper``
    """
    bins = np.asarray(bins, dtype=float)
    if bins.ndim != 1 or bins.size < 2 or np.any(np.diff(bins) <= 0.0):
        raise ValueError('bins must be a monotonically increasing 1D array')

    binned_transport = []
    binned_thickness = []
    for lower, upper in zip(bins[:-1], bins[1:], strict=True):
        in_bin = np.logical_and(edge_tracer >= lower, edge_tracer < upper)
        binned_transport.append(transport.where(in_bin, 0.0).sum(dim=vert_dim))
        binned_thickness.append(
            edge_thickness.where(in_bin, 0.0).sum(dim=vert_dim)
        )

    ds_binned = xr.Dataset()
    ds_binned['transport'] = xr.concat(binned_transport, dim='nBins')
    ds_binned['thickness'] = xr.concat(binned_thickness, dim='nBins')
    ds_binned['transport'].attrs = dict(
        long_name='transport in each tracer class', units='m3 s-1'
    )
    ds_binned['thickness'].attrs = dict(
        long_name='thickness in each tracer class', units='m'
    )
    ds_binned.coords['binLower'] = ('nBins', bins[:-1])
    ds_binned.coords['binUpper'] = ('nBins', bins[1:])
    return ds_binned


def get_latitude_edges(
    ds_mesh: xr.Dataset,
    latitudes: ArrayLike,
    cell_mask: Optional[ArrayLike] = None,
    lon_range: Optional[Tuple[float, float]] = None,
) -> xr.Dataset:
    """
    Find the edges crossing lines of constant latitude on a spherical mesh

    An edge crosses the line at latitude ``lat`` if one of its cells is
    south of it, ``latCell < lat``, and the other is not, ``latCell >=
    lat``.  Both cells must be in ``cell_mask`` and in ``lon_range``.  The
    signed transport through those edges is the transport from the cells
    south of the line to those north of it, within the mask.  An edge may
    cross several lines and is then listed once for each.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        A spherical MPAS mesh, with ``cellsOnEdge``, ``latCell``,
        ``lonCell``, ``dvEdge`` and ``dcEdge``

    latitudes : array-like
        The latitudes of the lines (degrees north), in increasing order

    cell_mask : array-like, optional
        Which cells are in the region the lines cross, with dimension
        ``nCells``.  The default is every cell.

    lon_range : tuple of float, optional
        The longitudes (degrees east) the lines run from and to.  A range
        runs east from its first value to its second, with longitudes
        compared modulo 360, so it may cross 0 or 180 degrees.  The default
        is all longitudes.

    Returns
    -------
    line : xarray.Dataset
        A dataset with dimensions ``nLineEdges`` and ``nLines`` containing
        the same variables as :py:func:`get_line_edges`, with ``sign``
        positive where positive normal velocity is northward, and:

        ``lineIndex``
            the zero-based index of the line each edge crosses

        ``lat``
            the latitude of each line (degrees north), a coordinate on
            ``nLines``

        ``length``
            the length of each line (m) within the mask, the sum of the
            weights of its edges

        The ``coord`` attribute is ``lat``, as :py:func:`get_line_edges`
        gives the coordinate its line is constant in.
    """
    lats = np.atleast_1d(np.asarray(latitudes, dtype=float))
    if lats.ndim != 1 or np.any(np.diff(lats) <= 0.0):
        raise ValueError('latitudes must be a 1D array in increasing order')

    n_cells = ds_mesh.sizes['nCells']
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    lat_cell = np.rad2deg(ds_mesh.latCell.values)
    lon_cell = np.rad2deg(ds_mesh.lonCell.values)

    in_region = np.ones(n_cells, dtype=bool)
    if cell_mask is not None:
        in_region = np.asarray(cell_mask).astype(bool)
    if lon_range is not None:
        in_region = np.logical_and(
            in_region, _in_lon_range(lon_cell, lon_range)
        )

    valid = np.logical_and(
        np.all(cells_on_edge >= 0, axis=1),
        np.all(cells_on_edge < n_cells, axis=1),
    )
    edge_indices = np.flatnonzero(valid)
    cell1 = cells_on_edge[edge_indices, 0]
    cell2 = cells_on_edge[edge_indices, 1]
    both_in = np.logical_and(in_region[cell1], in_region[cell2])
    edge_indices = edge_indices[both_in]
    cell1 = cell1[both_in]
    cell2 = cell2[both_in]

    lat1 = lat_cell[cell1]
    lat2 = lat_cell[cell2]
    south = np.minimum(lat1, lat2)
    north = np.maximum(lat1, lat2)
    # the lines an edge crosses are those with south < lat <= north
    first = np.searchsorted(lats, south, side='right')
    last = np.searchsorted(lats, north, side='right')
    count = last - first
    line_index = np.repeat(first, count) + _ranges_from_zero(count)
    edge_rows = np.repeat(np.arange(len(edge_indices)), count)

    edge_indices = edge_indices[edge_rows]
    cell1 = cell1[edge_rows]
    cell2 = cell2[edge_rows]
    lat1 = lat1[edge_rows]
    lat2 = lat2[edge_rows]

    dv_edge = ds_mesh.dvEdge.values[edge_indices]
    sign = np.where(lat1 < lat2, 1.0, -1.0)
    # the edge's length projected onto the line, from the fraction of the
    # great-circle arc between its cells that is northward
    arc = _great_circle_angle(
        np.deg2rad(lat1),
        np.deg2rad(lon_cell[cell1]),
        np.deg2rad(lat2),
        np.deg2rad(lon_cell[cell2]),
    )
    with np.errstate(invalid='ignore', divide='ignore'):
        north_fraction = np.where(
            arc > 0.0, np.abs(np.deg2rad(lat2 - lat1)) / arc, 0.0
        )
    weight = dv_edge * np.minimum(north_fraction, 1.0)
    length = np.bincount(line_index, weights=weight, minlength=len(lats))

    line = xr.Dataset(
        data_vars=dict(
            edgeIndex=(('nLineEdges',), edge_indices),
            cellsOnLineEdge=(
                ('nLineEdges', 'TWO'),
                np.stack([cell1, cell2], axis=1),
            ),
            lineIndex=(('nLineEdges',), line_index),
            sign=(('nLineEdges',), sign),
            dvEdge=(('nLineEdges',), dv_edge),
            weight=(('nLineEdges',), weight),
            length=(('nLines',), length),
        ),
        coords=dict(lat=(('nLines',), lats)),
        # the coordinate the transport across the line increases toward
        attrs=dict(coord='lat'),
    )
    line.lat.attrs = dict(units='degrees_north')
    return line


def get_line_edge_level_range(
    line: xr.Dataset,
    min_level_cell: xr.DataArray,
    max_level_cell: xr.DataArray,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """
    Get the layers each edge of a line carries flow in: the layers valid in
    both of its cells

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges` or
        :py:func:`get_latitude_edges`

    min_level_cell, max_level_cell : xarray.DataArray
        The zero-based indices of the topmost and bottommost valid layer of
        each cell

    Returns
    -------
    min_level_edge, max_level_edge : xarray.DataArray
        The zero-based indices of the topmost and bottommost valid layer of
        each edge, on ``nLineEdges``.  Where the two cells share no valid
        layer, ``max_level_edge`` is less than ``min_level_edge``.
    """
    min_levels = _cells_of_line_edges(line, min_level_cell)
    max_levels = _cells_of_line_edges(line, max_level_cell)
    min_level_edge = min_levels.max(dim='TWO')
    max_level_edge = max_levels.min(dim='TWO')
    return min_level_edge, max_level_edge


def compute_line_edge_interfaces(
    line: xr.Dataset,
    z_interface: xr.DataArray,
    min_level_edge: xr.DataArray,
    max_level_edge: xr.DataArray,
    vert_dim: str = 'nVertLevels',
    interface_dim: str = 'nVertLevelsP1',
) -> Tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the elevations of the top and bottom of each layer on the edges
    of a line from the elevations of the cells' layer interfaces

    Each edge takes the mean of its two cells' interfaces.  Layers outside
    the edge's valid range have zero thickness: their interfaces collapse
    onto the nearest valid one, so every edge has every interface and
    values the model wrote outside a cell's valid layers are never read.

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges` or
        :py:func:`get_latitude_edges`

    z_interface : xarray.DataArray
        The elevation (m) of each layer interface, with dimensions
        ``nCells`` and ``interface_dim``, indexed from the top

    min_level_edge, max_level_edge : xarray.DataArray
        The valid layers of each edge, from
        :py:func:`get_line_edge_level_range`

    vert_dim : str, optional
        The dimension of layers in the result

    interface_dim : str, optional
        The dimension of interfaces in ``z_interface``

    Returns
    -------
    z_top, z_bottom : xarray.DataArray
        The elevation (m) of the top and bottom of each layer, with
        dimensions ``nLineEdges`` and ``vert_dim``
    """
    other_dims = [
        dim for dim in z_interface.dims if dim not in ('nCells', interface_dim)
    ]
    if other_dims:
        raise ValueError(
            f'z_interface has dimensions {z_interface.dims}; only nCells '
            f'and {interface_dim} are supported'
        )
    values = z_interface.transpose('nCells', interface_dim).values
    n_interfaces = values.shape[1]
    cells = line.cellsOnLineEdge.values
    min_level = min_level_edge.values
    max_level = max_level_edge.values

    # each edge reads only the interfaces of its valid layers, the top of
    # the first to the bottom of the last; the others collapse onto them
    index = np.arange(n_interfaces)[np.newaxis, :]
    index = np.minimum(
        np.maximum(index, min_level[:, np.newaxis]),
        max_level[:, np.newaxis] + 1,
    )
    index = np.clip(index, 0, n_interfaces - 1)
    z1 = np.take_along_axis(values[cells[:, 0], :], index, axis=1)
    z2 = np.take_along_axis(values[cells[:, 1], :], index, axis=1)
    z_edge = 0.5 * (z1 + z2)

    dims = ('nLineEdges', vert_dim)
    z_top = xr.DataArray(z_edge[:, :-1], dims=dims)
    z_bottom = xr.DataArray(z_edge[:, 1:], dims=dims)
    return z_top, z_bottom


def compute_overturning_from_edge_transport(
    transport: xr.DataArray,
    z_top: xr.DataArray,
    z_bottom: xr.DataArray,
    z: ArrayLike,
    edge_dim: str = 'nLineEdges',
    vert_dim: str = 'nVertLevels',
    line_index: Optional[xr.DataArray] = None,
    n_lines: Optional[int] = None,
    chunk_size: int = 10000,
) -> xr.DataArray:
    r"""
    Compute the overturning stream function at fixed elevations from the
    transport each layer carries across the edges of one or more lines

    For each edge, the transport is integrated up from the seafloor to each
    elevation: the layers below it in full and the part of the layer it
    falls in, by the fraction of that layer's height below it, with the
    edge's own interface heights.  Summed over the edges with their signs,
    the stream function is minus that transport,

    .. math::

        \psi(z) = -\sum_e \sum_k T_{e,k}\, f_{e,k}(z),\quad
        f_{e,k}(z) = \min\left(1, \max\left(0,
        \frac{z - z^{bot}_{e,k}}{z^{top}_{e,k} - z^{bot}_{e,k}}\right)
        \right),

    so that the transport per unit height is :math:`-\partial \psi /
    \partial z`, as the MISOMIP protocol defines its overturning stream
    function (Asay-Davis et al. 2016) and as Omega and MPAS-Analysis define
    the meridional overturning.  This is Method B of Sidorenko et al.
    (2020).  The sum is the vertical flux through the level :math:`z`
    summed over the cells on one side of the line: each interior face's
    integral to :math:`z` is shared by its two cells with opposite signs,
    so it cancels however much the layers tilt.

    The sum is never formed as an array of edges, layers and elevations.
    Each layer adds its whole transport to the elevations above its top and
    a linear ramp to the few elevations inside it, which are accumulated as
    differences along the sorted elevations and summed once per line.  The
    cost is then the number of layers plus the number of elevations, not
    their product.

    Parameters
    ----------
    transport : xarray.DataArray
        The transport (m3 s-1) of each layer across each edge, with
        dimensions ``edge_dim`` and ``vert_dim``, positive toward the side
        of the line the stream function is minus the transport to, as from
        :py:func:`compute_line_transport`

    z_top, z_bottom : xarray.DataArray
        The elevations (m) of the top and bottom of each layer on each edge,
        as from :py:func:`compute_line_edge_interfaces`.  Layers with no
        height carry no transport.

    z : array-like
        The elevations (m)

    edge_dim : str, optional
        The dimension of edges

    vert_dim : str, optional
        The dimension of layers

    line_index : xarray.DataArray, optional
        The zero-based index of the line each edge belongs to, on
        ``edge_dim``, as from :py:func:`get_latitude_edges`.  The default
        is that every edge belongs to one line.

    n_lines : int, optional
        The number of lines; the default is one more than the largest
        ``line_index``

    chunk_size : int, optional
        The number of edges summed at a time, which bounds the memory used

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) on ``nZInterfaces``, with
        the coordinate ``zInterface`` (m), and the transport's other
        dimensions, preceded by ``nLines`` if ``line_index`` was given:
        zero below every layer and minus the transport below each elevation
    """
    z = np.atleast_1d(np.asarray(z, dtype=float))
    if z.ndim != 1:
        raise ValueError('z must be a 1D array')
    order = np.argsort(z, kind='stable')
    z_sorted = z[order]

    other_dims = [
        dim for dim in transport.dims if dim not in (edge_dim, vert_dim)
    ]
    dims = other_dims + [edge_dim, vert_dim]
    transport_values = np.nan_to_num(transport.transpose(*dims).values)
    top_values = z_top.broadcast_like(transport).transpose(*dims).values
    bottom_values = z_bottom.broadcast_like(transport).transpose(*dims).values

    n_edges = transport.sizes[edge_dim]
    if line_index is None:
        lines = np.zeros(n_edges, dtype=int)
        line_count = 1
    else:
        lines = np.asarray(line_index.values, dtype=int)
        line_count = int(lines.max()) + 1 if len(lines) > 0 else 0
        if n_lines is not None:
            line_count = n_lines

    other_shape = transport_values.shape[:-2]
    values = np.zeros(other_shape + (line_count, len(z)))
    for other in np.ndindex(*other_shape):
        values[other] = _sum_edge_overturning(
            transport_values[other],
            top_values[other],
            bottom_values[other],
            lines,
            line_count,
            z_sorted,
            chunk_size,
        )[:, np.argsort(order, kind='stable')]

    out_dims = other_dims + ['nLines', 'nZInterfaces']
    if line_index is None:
        values = values[..., 0, :]
        out_dims = other_dims + ['nZInterfaces']
    overturning = xr.DataArray(
        values,
        dims=out_dims,
        coords={'zInterface': ('nZInterfaces', z)},
    )
    for dim in other_dims:
        if dim in transport.coords:
            overturning.coords[dim] = transport.coords[dim]
    overturning.attrs = dict(
        long_name='overturning stream function', units='m3 s-1'
    )
    return overturning


def _sum_edge_overturning(
    transport, z_top, z_bottom, lines, n_lines, z_sorted, chunk_size
):
    """
    Sum minus the transport below each sorted elevation over the edges of
    each line, for one time
    """
    n_z = len(z_sorted)
    size = n_lines * (n_z + 1)
    full = np.zeros(size)
    slope = np.zeros(size)
    offset = np.zeros(size)
    n_edges = transport.shape[0]
    for start in range(0, n_edges, chunk_size):
        end = min(start + chunk_size, n_edges)
        top = z_top[start:end]
        bottom = z_bottom[start:end]
        height = top - bottom
        with np.errstate(invalid='ignore'):
            valid = height > 0.0
        edge, _ = np.nonzero(valid)
        layer_transport = transport[start:end][valid]
        top = top[valid]
        bottom = bottom[valid]
        height = height[valid]
        base = lines[start:end][edge] * (n_z + 1)

        # the first elevation above the bottom of each layer, and the first
        # at or above its top
        low = base + np.searchsorted(z_sorted, bottom, side='right')
        high = base + np.searchsorted(z_sorted, top, side='left')
        rate = layer_transport / height
        full += np.bincount(high, weights=layer_transport, minlength=size)
        slope += np.bincount(low, weights=rate, minlength=size)
        slope -= np.bincount(high, weights=rate, minlength=size)
        offset -= np.bincount(low, weights=rate * bottom, minlength=size)
        offset += np.bincount(high, weights=rate * bottom, minlength=size)

    shape = (n_lines, n_z + 1)
    full = np.cumsum(full.reshape(shape), axis=1)[:, :n_z]
    slope = np.cumsum(slope.reshape(shape), axis=1)[:, :n_z]
    offset = np.cumsum(offset.reshape(shape), axis=1)[:, :n_z]
    return -(full + slope * z_sorted[np.newaxis, :] + offset)


def _in_lon_range(lon, lon_range):
    """Whether each longitude (degrees) is in a range running east"""
    lon_min, lon_max = (float(value) for value in lon_range)
    width = lon_max - lon_min
    if width >= 360.0:
        return np.ones(np.shape(lon), dtype=bool)
    width = np.mod(width, 360.0)
    return np.mod(np.asarray(lon) - lon_min, 360.0) <= width


def _ranges_from_zero(count):
    """Concatenate ``arange(n)`` for each ``n`` in ``count``"""
    total = int(np.sum(count))
    if total == 0:
        return np.zeros(0, dtype=int)
    starts = np.cumsum(count) - count
    return np.arange(total) - np.repeat(starts, count)


def _great_circle_angle(lat1, lon1, lat2, lon2):
    """The angle (radians) between points on a sphere"""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(0.5 * dlat) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(0.5 * dlon) ** 2
    )
    return 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _cells_of_line_edges(line, cell_field):
    """A cell field in both cells of each edge of a line, on ``TWO``"""
    return cell_field.isel(nCells=line.cellsOnLineEdge)
