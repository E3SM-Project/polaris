"""
Overturning across lines of constant x or y on planar MPAS meshes.

A line is represented by the edges whose two cells lie on opposite sides
of it.  Summing the signed transports through those edges gives the exact
discrete transport from the cells on one side of the line to the cells on
the other, on any planar mesh: the zigzag between two rows of cells on a
planar hex mesh, or a staircase within about one cell of the line on any
other mesh.  Only ``cellsOnEdge``, the cell coordinates, ``dvEdge`` and
``dcEdge`` are used, so no mesh structure is assumed.
"""

from typing import Literal

import numpy as np
import xarray as xr

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


def compute_line_interfaces(
    line: xr.Dataset,
    ssh: xr.DataArray,
    layer_thickness: xr.DataArray,
    vert_dim: str = 'nVertLevels',
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Compute the elevations of the top and bottom of each layer on the edges
    of a line

    The layers stack down from the sea-surface height, which is the ice
    draft under an ice shelf.  Each edge takes the mean of its two cells, as
    the thickness in :py:func:`compute_line_transport` does.  Layers outside
    a cell's valid range, NaN in E3SM's monthly means, count as zero
    thickness, so their interfaces collapse onto the nearest valid one and
    every edge has every interface.

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges`

    ssh : xarray.DataArray
        The sea-surface height (m) with dimension ``nCells``

    layer_thickness : xarray.DataArray
        The layer thickness (m) with dimensions ``nCells`` and ``vert_dim``

    vert_dim : str, optional
        The vertical dimension, indexed from the top

    Returns
    -------
    z_top, z_bottom : xarray.DataArray
        The elevation (m) of the top and bottom of each layer, with
        ``nCells`` replaced by ``nLineEdges``
    """
    layer_thickness = layer_thickness.fillna(0.0)
    z_bottom = ssh - layer_thickness.cumsum(dim=vert_dim)
    z_top = z_bottom + layer_thickness
    return (
        interp_cell_to_line_edges(line, z_top),
        interp_cell_to_line_edges(line, z_bottom),
    )


def compute_overturning_in_z(
    transport: xr.DataArray,
    z_top: xr.DataArray,
    z_bottom: xr.DataArray,
    dz: float,
    vert_dim: str = 'nVertLevels',
    top: float | None = None,
    bottom: float | None = None,
) -> xr.DataArray:
    """
    Compute the overturning stream function at fixed elevations

    Each layer's transport is spread over bins of height ``dz`` by the
    fraction of the layer each bin overlaps, summed along the line, and
    accumulated from the top.  By default the bins span the layers, so all
    of the transport is counted; a ``top`` and ``bottom`` that span them too
    put several lines on the same elevations.

    Parameters
    ----------
    transport : xarray.DataArray
        Transport from :py:func:`compute_line_transport`, with dimensions
        ``nLineEdges`` and ``vert_dim``

    z_top, z_bottom : xarray.DataArray
        The elevations (m) of the top and bottom of each layer, from
        :py:func:`compute_line_interfaces`

    dz : float
        The height (m) of the bins

    vert_dim : str, optional
        The vertical dimension, indexed from the top

    top, bottom : float, optional
        The elevations (m) of the top of the first bin and the bottom of the
        last, multiples of ``dz`` that must span the layers.  By default,
        the nearest multiples of ``dz`` beyond the layers.

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) on the dimension
        ``nZInterfaces``, with the coordinate ``zInterface`` (m), descending
        from the top
    """
    other_dims = [
        dim for dim in transport.dims if dim not in (vert_dim, 'nLineEdges')
    ]
    dims = other_dims + ['nLineEdges', vert_dim]
    transport_values = transport.transpose(*dims).values
    top_values = z_top.broadcast_like(transport).transpose(*dims).values
    bottom_values = z_bottom.broadcast_like(transport).transpose(*dims).values

    if top is None:
        top = dz * np.ceil(np.nanmax(top_values) / dz)
    if bottom is None:
        bottom = dz * np.floor(np.nanmin(bottom_values) / dz)
    if np.nanmax(top_values) > top or np.nanmin(bottom_values) < bottom:
        raise ValueError(
            f'The bins from {top} to {bottom} m do not span the layers.'
        )
    count = int(round((top - bottom) / dz))
    edges = top - dz * np.arange(count + 1)

    # the overlap of each layer with each bin, on a last dimension of bins
    upper = np.minimum(top_values[..., np.newaxis], edges[:-1])
    lower = np.maximum(bottom_values[..., np.newaxis], edges[1:])
    thickness = (top_values - bottom_values)[..., np.newaxis]
    with np.errstate(invalid='ignore', divide='ignore'):
        fraction = np.where(
            thickness > 0.0, np.clip(upper - lower, 0.0, None) / thickness, 0.0
        )
    binned = np.nansum(
        transport_values[..., np.newaxis] * fraction, axis=(-3, -2)
    )
    cumulative = np.cumsum(binned, axis=-1)
    surface = np.zeros(cumulative.shape[:-1] + (1,))
    values = np.concatenate([surface, cumulative], axis=-1)

    overturning = xr.DataArray(
        values,
        dims=other_dims + ['nZInterfaces'],
        coords={'zInterface': ('nZInterfaces', edges)},
    )
    for dim in other_dims:
        if dim in transport.coords:
            overturning.coords[dim] = transport.coords[dim]
    overturning.attrs = dict(
        long_name='overturning stream function', units='m3 s-1'
    )
    return overturning


def compute_overturning_from_volume_budget(
    low_side: xr.DataArray,
    area_cell: xr.DataArray,
    thickness_start: xr.DataArray,
    thickness_end: xr.DataArray,
    duration: float,
    vert_transport_top: xr.DataArray,
    thickness_source: xr.DataArray,
    vert_dim: str = 'nVertLevels',
    interface_dim: str = 'nVertLevelsP1',
) -> xr.DataArray:
    """
    Compute the overturning stream function across a line on each layer
    interface from the volume budget of the region on the line's low side

    Over a period, the water each layer of the region gains, less what
    sources add to it, is what crosses the line in that layer and what
    flows through the layer's interfaces.  So the transport across the line
    above interface ``k``, toward the line's high side, is

    .. math::

        \\psi_k = \\sum_{j<k} \\left(S_j - \\frac{\\Delta V_j}{\\Delta t}
        \\right) + F_k - F_0,

    where :math:`\\Delta V_j` is layer ``j``'s change in volume in the
    region, :math:`S_j` the volume its sources add each second and
    :math:`F_k` the upward volume flux through interface ``k``.  With the
    mean vertical transport over the period and the thicknesses at its
    start and end, the result is the period's mean transport, which the
    product of mean velocity and mean thickness is not where columns wet
    and dry.  The region must hold no cells whose thickness is set
    directly, as tidal forcing does.

    Parameters
    ----------
    low_side : xarray.DataArray
        Whether each cell is on the low side of the line, below its
        coordinate, as the cells of :py:func:`get_line_edges` are split

    area_cell : xarray.DataArray
        The area of each cell (m2)

    thickness_start, thickness_end : xarray.DataArray
        The layer thickness (m) at the period's start and end, with
        dimensions ``nCells`` and ``vert_dim``

    duration : float
        The length of the period (s)

    vert_transport_top : xarray.DataArray
        The mean upward volume flux per unit area (m s-1) through each
        layer's top interface, such as MPAS-Ocean's
        ``vertAleTransportTop``, with dimensions ``nCells`` and
        ``interface_dim``

    thickness_source : xarray.DataArray
        The mean thickness (m s-1) that sources add to each layer, such as
        melt in the top layer and frazil, with dimensions ``nCells`` and
        ``vert_dim``

    vert_dim : str, optional
        The dimension of layers, indexed from the top

    interface_dim : str, optional
        The dimension of interfaces, one more than layers

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) on ``interface_dim``,
        zero at the top
    """
    weights = area_cell.where(low_side, 0.0)
    gain = (thickness_end - thickness_start) / duration
    net = ((thickness_source - gain) * weights).sum(dim='nCells')
    flux = (vert_transport_top * weights).sum(dim='nCells')
    layers = net.transpose(..., vert_dim).values
    above = np.concatenate(
        [np.zeros(layers.shape[:-1] + (1,)), np.cumsum(layers, axis=-1)],
        axis=-1,
    )
    flux_values = flux.transpose(..., interface_dim).values
    values = above + flux_values - flux_values[..., :1]
    other_dims = [dim for dim in net.dims if dim != vert_dim]
    overturning = xr.DataArray(values, dims=other_dims + [interface_dim])
    overturning.attrs = dict(
        long_name='overturning stream function on layer interfaces',
        units='m3 s-1',
    )
    return overturning


def compute_overturning_from_layer_flux(
    line: xr.Dataset,
    layer_thickness_flux: xr.DataArray,
    vert_dim: str = 'nVertLevels',
    interface_dim: str = 'nVertLevelsP1',
) -> xr.DataArray:
    """
    Compute the overturning stream function across a line on each layer
    interface from the thickness flux each layer carries across each edge

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges`

    layer_thickness_flux : xarray.DataArray
        The thickness flux per unit edge length (m2 s-1) of each layer
        across each edge, from the edge's first cell to its second, such as
        a mean of MPAS-Ocean's ``normalLayerThicknessFlux``, with
        dimensions ``nEdges`` and ``vert_dim``

    vert_dim : str, optional
        The dimension of layers, indexed from the top

    interface_dim : str, optional
        The dimension of interfaces, one more than layers

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) on ``interface_dim``,
        zero at the top
    """
    transport = (
        layer_thickness_flux.isel(nEdges=line.edgeIndex)
        * line.sign
        * line.dvEdge
    ).sum(dim='nLineEdges')
    layers = transport.transpose(..., vert_dim).values
    values = np.concatenate(
        [np.zeros(layers.shape[:-1] + (1,)), np.cumsum(layers, axis=-1)],
        axis=-1,
    )
    other_dims = [dim for dim in transport.dims if dim != vert_dim]
    overturning = xr.DataArray(values, dims=other_dims + [interface_dim])
    overturning.attrs = dict(
        long_name='overturning stream function on layer interfaces',
        units='m3 s-1',
    )
    return overturning


def compute_line_interface_elevations(
    line: xr.Dataset,
    ssh: xr.DataArray,
    layer_thickness: xr.DataArray,
    vert_dim: str = 'nVertLevels',
    interface_dim: str = 'nVertLevelsP1',
) -> xr.DataArray:
    """
    Compute the mean elevation of each layer interface along a line

    Each edge counts by its length along the line times its column's
    thickness, so edges that hold only a thin film, as under grounded ice,
    count little.  Where the interfaces tilt across the line, as under an
    ice shelf whose draft varies along it, the mean is an approximation of
    where each interface lies.

    Parameters
    ----------
    line : xarray.Dataset
        A line from :py:func:`get_line_edges`

    ssh : xarray.DataArray
        The sea-surface height (m) with dimension ``nCells``

    layer_thickness : xarray.DataArray
        The layer thickness (m) with dimensions ``nCells`` and ``vert_dim``

    vert_dim : str, optional
        The dimension of layers, indexed from the top

    interface_dim : str, optional
        The dimension of interfaces, one more than layers

    Returns
    -------
    elevation : xarray.DataArray
        The mean elevation (m) of each interface on ``interface_dim``
    """
    z_top, z_bottom = compute_line_interfaces(
        line, ssh, layer_thickness, vert_dim=vert_dim
    )
    interfaces = xr.concat(
        [z_top, z_bottom.isel({vert_dim: slice(-1, None)})], dim=vert_dim
    ).rename({vert_dim: interface_dim})
    column = (z_top - z_bottom).sum(dim=vert_dim)
    weights = line.weight * column
    elevation = (interfaces * weights).sum(dim='nLineEdges') / weights.sum(
        dim='nLineEdges'
    )
    elevation.attrs = dict(
        long_name='mean elevation of each layer interface along the line',
        units='m',
    )
    return elevation


def interp_overturning_to_z(
    overturning: xr.DataArray,
    elevation: xr.DataArray,
    z: np.ndarray,
    interface_dim: str = 'nVertLevelsP1',
) -> xr.DataArray:
    """
    Interpolate an overturning stream function on layer interfaces to fixed
    elevations, linearly between the interfaces' elevations

    Parameters
    ----------
    overturning : xarray.DataArray
        The stream function on ``interface_dim``, as from
        :py:func:`compute_overturning_from_volume_budget`

    elevation : xarray.DataArray
        The interfaces' elevations (m) on ``interface_dim``, descending,
        as from :py:func:`compute_line_interface_elevations`

    z : numpy.ndarray
        The elevations (m) to interpolate to

    interface_dim : str, optional
        The dimension of interfaces

    Returns
    -------
    overturning_z : xarray.DataArray
        The stream function on ``nZInterfaces``, with the coordinate
        ``zInterface`` (m) and the coordinates of its other dimensions, and
        NaN above the top interface and below the bottom one
    """
    psi = overturning.transpose(..., interface_dim).values
    heights = elevation.transpose(..., interface_dim).values
    other_dims = [dim for dim in overturning.dims if dim != interface_dim]
    psi_2d = psi.reshape(-1, psi.shape[-1])
    heights_2d = np.broadcast_to(heights, psi.shape).reshape(psi_2d.shape)
    values = np.full((psi_2d.shape[0], len(z)), np.nan)
    for index in range(psi_2d.shape[0]):
        valid = np.isfinite(heights_2d[index])
        if not np.any(valid):
            continue
        order = np.argsort(heights_2d[index][valid])
        values[index] = np.interp(
            z,
            heights_2d[index][valid][order],
            psi_2d[index][valid][order],
            left=np.nan,
            right=np.nan,
        )
    coords = {
        name: coord
        for name, coord in overturning.coords.items()
        if set(coord.dims) <= set(other_dims)
    }
    coords['zInterface'] = ('nZInterfaces', np.asarray(z))
    overturning_z = xr.DataArray(
        values.reshape(psi.shape[:-1] + (len(z),)),
        dims=other_dims + ['nZInterfaces'],
        coords=coords,
    )
    overturning_z.attrs = dict(overturning.attrs)
    return overturning_z
