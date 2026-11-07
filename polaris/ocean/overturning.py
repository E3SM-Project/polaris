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


def compute_overturning_from_edge_transport(
    transport: xr.DataArray,
    z_top: xr.DataArray,
    z_bottom: xr.DataArray,
    z: np.ndarray,
    edge_dim: str = 'nLineEdges',
    vert_dim: str = 'nVertLevels',
) -> xr.DataArray:
    r"""
    Compute the overturning stream function at fixed elevations from the
    transport each layer carries across the edges that bound a region

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
    function (Asay-Davis et al. 2016).  Where the net transport is zero,
    :math:`\psi` is the transport out of the region above :math:`z`, as an
    Atlantic overturning is usually shown.  The sum is the vertical flux
    through the level :math:`z` summed over the region's cells: each
    interior face's integral to :math:`z` is shared by its two cells with
    opposite signs, so only the boundary's remain.  That holds on any mesh,
    whatever the tilt of the layers.  The approximations are the flux
    spread evenly through each edge's layer and, for a mean over a period,
    the mean interface heights of the layer each elevation falls in.

    The edges are any set that bounds a region, with signs toward its
    outside.  For a line of constant x or y on a planar mesh,
    :py:func:`get_line_edges` gives them, with the low side as the region.
    For a latitude within a basin on the sphere, the edges whose two cells
    are both in the basin and on either side of the latitude give the
    transport across it directly; a transect along the basin's southern
    boundary is needed only to sum vertical fluxes over the region instead.

    Parameters
    ----------
    transport : xarray.DataArray
        The transport (m3 s-1) of each layer across each edge, out of the
        region, with dimensions ``edge_dim`` and ``vert_dim``, as from
        :py:func:`compute_line_transport` or a layer thickness flux times
        each edge's length and sign

    z_top, z_bottom : xarray.DataArray
        The elevations (m) of the top and bottom of each layer on each edge,
        as from :py:func:`compute_line_interfaces`

    z : numpy.ndarray
        The elevations (m)

    edge_dim : str, optional
        The dimension of edges

    vert_dim : str, optional
        The dimension of layers

    Returns
    -------
    overturning : xarray.DataArray
        The overturning stream function (m3 s-1) on ``nZInterfaces``, with
        the coordinate ``zInterface`` (m), and the transport's other
        dimensions: zero at the seafloor and minus the transport out of the
        region below each elevation
    """
    z = np.asarray(z, dtype=float)
    other_dims = [
        dim for dim in transport.dims if dim not in (edge_dim, vert_dim)
    ]
    dims = other_dims + [edge_dim, vert_dim]
    transport_values = np.nan_to_num(transport.transpose(*dims).values)
    top_values = z_top.broadcast_like(transport).transpose(*dims).values
    bottom_values = z_bottom.broadcast_like(transport).transpose(*dims).values
    height = (top_values - bottom_values)[..., np.newaxis]
    with np.errstate(invalid='ignore', divide='ignore'):
        fraction = np.where(
            height > 0.0,
            np.clip((z - bottom_values[..., np.newaxis]) / height, 0.0, 1.0),
            0.0,
        )
    values = -np.sum(
        transport_values[..., np.newaxis] * fraction, axis=(-3, -2)
    )
    overturning = xr.DataArray(
        values,
        dims=other_dims + ['nZInterfaces'],
        coords={'zInterface': ('nZInterfaces', z)},
    )
    for dim in other_dims:
        if dim in transport.coords:
            overturning.coords[dim] = transport.coords[dim]
    overturning.attrs = dict(
        long_name='overturning stream function', units='m3 s-1'
    )
    return overturning
