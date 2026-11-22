"""
The first level of each ocean column under ice shelves.

Under an ice shelf, z-star would squeeze the whole reference column between
the ice draft and the bed.  Instead, each column under a shelf drops the
reference levels at its top and follows z-star over the levels that remain:

* each ice shelf drops the levels lying entirely above a percentile of the
  drafts along its calving front, weighted by the length of front;

* a cell at a calving front that faces open water drops exactly the levels
  lying entirely above its own draft, so its layers line up with the open
  ocean;

* where the layers of neighboring columns are still too steep, the cell
  with the deeper draft drops the fewest further levels that bring the
  hydrostatic consistency number rx1 down to a maximum.

Film cells drop nothing, and every column keeps at least ``min_vert_levels``
levels.  The ice shelves are found once, by a flood fill of the floating
cells and then of the grounded (film) cells.
"""

import numpy as np
import xarray as xr
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from polaris.ocean.vertical.grid_1d import generate_1d_grid
from polaris.ocean.vertical.partial_cells import alter_bottom_depth
from polaris.ocean.vertical.zlevel import (
    compute_min_max_level_cell,
    compute_z_level_layer_thickness,
)

#: the values of ``[vertical_grid] ice_shelf_top_level``
ICE_SHELF_TOP_LEVELS = ('surface', 'front_draft')


def compute_ice_shelf_min_level_cell(
    config,
    ds_mesh,
    ssh,
    bottom_depth,
    land_ice_mask,
    thin_film_mask,
    thin_film_layer_thickness,
    logger=None,
):
    """
    Compute the first level of each column under ice shelves and the ice
    shelf each cell belongs to.

    With ``[vertical_grid] ice_shelf_top_level = surface``, every column
    starts at the top reference level.  With ``front_draft``, columns under
    ice shelves drop reference levels at their top (see the module
    docstring), with the percentile in ``ice_shelf_front_percentile`` and the
    maximum rx1 in ``ice_shelf_max_rx1``.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options, with the ``vertical_grid`` section used to build the
        reference column of each cell

    ds_mesh : xarray.Dataset
        The horizontal mesh, with ``cellsOnEdge`` and ``dvEdge``

    ssh : xarray.DataArray
        The sea-surface height (m), the elevation of the ice draft under land
        ice

    bottom_depth : xarray.DataArray
        The positive-down depth of the seafloor (m), before any partial-cell
        adjustment

    land_ice_mask : xarray.DataArray
        1 in cells under land ice and 0 elsewhere

    thin_film_mask : xarray.DataArray
        1 in cells under land ice that hold a thin film and 0 elsewhere

    thin_film_layer_thickness : float
        The thickness (m) of each layer of the thin film.  A calving front
        only counts where the open water's bed is below the ice draft by more
        than ``min_vert_levels`` of these layers.

    logger : logging.Logger, optional
        A logger for a summary of the drops

    Returns
    -------
    min_level_cell : xarray.DataArray
        The zero-based index of the first level of each column

    ice_shelf_group : xarray.DataArray
        The ice shelf of each cell under land ice, numbered from 1, and 0
        elsewhere
    """
    section = config['vertical_grid']
    top_level = section.get('ice_shelf_top_level')
    if top_level not in ICE_SHELF_TOP_LEVELS:
        raise ValueError(
            f'Unexpected ice_shelf_top_level {top_level!r}, expected one of '
            f'{ICE_SHELF_TOP_LEVELS}'
        )
    min_vert_levels = section.getint('min_vert_levels')

    ssh = _squeeze_time(ssh)
    land_ice = _squeeze_time(land_ice_mask).values == 1
    film = _squeeze_time(thin_film_mask).values == 1
    floating = land_ice & ~film
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1

    group = compute_ice_shelf_groups(
        cells_on_edge=cells_on_edge,
        floating=floating,
        grounded=land_ice & film,
    )
    ice_shelf_group = xr.DataArray(group.astype(np.int32), dims=('nCells',))

    ndrop = np.zeros(ssh.sizes['nCells'], dtype=int)
    if top_level == 'front_draft':
        ndrop = _compute_drops(
            config=config,
            ssh=ssh,
            bottom_depth=_squeeze_time(bottom_depth),
            cells_on_edge=cells_on_edge,
            dv_edge=ds_mesh.dvEdge.values,
            land_ice=land_ice,
            film=film,
            group=group,
            percentile=section.getfloat('ice_shelf_front_percentile'),
            max_rx1=section.getfloat('ice_shelf_max_rx1'),
            front_margin=min_vert_levels * thin_film_layer_thickness,
            min_vert_levels=min_vert_levels,
            logger=logger,
        )

    min_level_cell = xr.DataArray(ndrop, dims=('nCells',))
    return min_level_cell, ice_shelf_group


def compute_ice_shelf_groups(cells_on_edge, floating, grounded):
    """
    Number the ice shelves: connected regions of floating cells first, then
    grounded cells, each joining the shelf that reaches it first.

    Grounded cells join shelves in rings.  A grounded cell next to cells
    already in a shelf joins the one with the lowest number among them.
    Grounded regions that no floating region reaches are shelves of their
    own.

    Parameters
    ----------
    cells_on_edge : numpy.ndarray
        The zero-based indices of the two cells on each edge, negative where
        there is no cell

    floating : numpy.ndarray
        A boolean mask of cells under floating ice

    grounded : numpy.ndarray
        A boolean mask of cells under grounded ice

    Returns
    -------
    group : numpy.ndarray
        The ice shelf of each cell, numbered from 1, and 0 in cells neither
        floating nor grounded
    """
    both = (cells_on_edge[:, 0] >= 0) & (cells_on_edge[:, 1] >= 0)
    cell_a = cells_on_edge[both, 0]
    cell_b = cells_on_edge[both, 1]
    group = np.zeros(floating.size, dtype=np.int64)

    _label_regions(cell_a, cell_b, floating, group, first=1)

    unset = np.iinfo(np.int64).max
    while True:
        candidate = np.full(floating.size, unset)
        for src, dst in ((cell_a, cell_b), (cell_b, cell_a)):
            reach = (group[src] > 0) & grounded[dst] & (group[dst] == 0)
            np.minimum.at(candidate, dst[reach], group[src[reach]])
        new = candidate < unset
        if not new.any():
            break
        group[new] = candidate[new]

    unreached = grounded & (group == 0)
    _label_regions(cell_a, cell_b, unreached, group, first=group.max() + 1)
    return group


def weighted_percentile(values, weights, percentile):
    """
    The smallest value whose cumulative weight reaches the given percentile
    of the total weight (the inverted-CDF percentile).

    Parameters
    ----------
    values : numpy.ndarray
        The values

    weights : numpy.ndarray
        A positive weight for each value

    percentile : float
        The percentile, between 0 and 100

    Returns
    -------
    value : numpy.generic
        One of ``values``
    """
    order = np.argsort(values, kind='stable')
    cumulative = np.cumsum(weights[order])
    index = np.searchsorted(
        cumulative, percentile / 100.0 * cumulative[-1], side='left'
    )
    return values[order][min(index, values.size - 1)]


def cap_min_level_cell(min_level_cell, max_level_cell, min_vert_levels):
    """
    Limit the first level of each column so it keeps at least
    ``min_vert_levels`` levels.

    Parameters
    ----------
    min_level_cell : xarray.DataArray
        The requested zero-based first level of each column

    max_level_cell : xarray.DataArray
        The zero-based last level of each column

    min_vert_levels : int
        The minimum number of levels in a column

    Returns
    -------
    min_level_cell : xarray.DataArray
        The zero-based first level of each column
    """
    top = np.minimum(min_level_cell, max_level_cell - min_vert_levels + 1)
    return np.maximum(top, 0).astype(int)


def stretch_to_column(thickness, column_thickness, min_level_cell):
    """
    Stretch the thicknesses of the remaining levels of each column with
    dropped levels so they sum to the column's thickness.

    Parameters
    ----------
    thickness : xarray.DataArray
        The thickness of each level, zero outside the column

    column_thickness : xarray.DataArray
        The thickness the levels of each column must sum to

    min_level_cell : xarray.DataArray
        The zero-based first level of each column.  Columns starting at the
        top level are not changed.

    Returns
    -------
    thickness : xarray.DataArray
        The stretched thicknesses
    """
    total = thickness.sum(dim='nVertLevels')
    stretch = xr.where(
        (min_level_cell > 0) & (total > 0.0), column_thickness / total, 1.0
    )
    return thickness * stretch


class _ReferenceColumns:
    """
    The z-star columns of some cells over the reference levels, as
    :py:func:`polaris.ocean.vertical.zstar.init_z_star_vertical_coord` would
    build them
    """

    def __init__(self, config, ssh, bottom_depth):
        section = config['vertical_grid']
        interfaces = generate_1d_grid(config=config)
        ref_top = xr.DataArray(interfaces[:-1], dims=['nVertLevels'])
        ref_bot = xr.DataArray(interfaces[1:], dims=['nVertLevels'])
        zero = xr.zeros_like(bottom_depth)
        min_level_cell, max_level_cell, _ = compute_min_max_level_cell(
            ref_top,
            ref_bot,
            zero,
            bottom_depth,
            min_vert_levels=section.getint('min_vert_levels'),
            min_layer_thickness=section.getfloat('min_layer_thickness'),
        )
        bottom_depth, max_level_cell = alter_bottom_depth(
            config, bottom_depth, ref_bot, max_level_cell
        )
        resting = compute_z_level_layer_thickness(
            ref_top,
            ref_bot,
            zero,
            bottom_depth,
            min_level_cell,
            max_level_cell,
        )
        self.ref_bottom = interfaces[1:]
        self.ssh = ssh.values
        self.bottom_depth = bottom_depth.values
        self.max_level_cell = max_level_cell.values.astype(int)
        self.resting = resting.transpose('nCells', 'nVertLevels').values

    def interfaces(self, cells, ndrop):
        """
        The thickness and top and bottom heights of each layer of the given
        cells with the given drops, z-star over the remaining levels
        """
        levels = np.arange(self.resting.shape[1])[np.newaxis, :]
        valid = (levels >= ndrop[:, np.newaxis]) & (
            levels <= self.max_level_cell[cells, np.newaxis]
        )
        resting = np.where(valid, self.resting[cells], 0.0)
        total = resting.sum(axis=1)
        column = self.ssh[cells] + self.bottom_depth[cells]
        stretch = column / np.where(total > 0.0, total, 1.0)
        thickness = resting * stretch[:, np.newaxis]
        top = (
            self.ssh[cells, np.newaxis]
            - np.cumsum(thickness, axis=1)
            + thickness
        )
        return thickness, top, top - thickness, valid

    def rx1(self, cell_a, cell_b, ndrop_a, ndrop_b):
        """
        The largest rx1 over the shared layers of each pair of cells
        """
        cells = np.concatenate([cell_a, cell_b])
        ndrop = np.concatenate([ndrop_a, ndrop_b])
        thickness, top, bottom, valid = self.interfaces(cells, ndrop)
        a = slice(0, cell_a.size)
        b = slice(cell_a.size, None)
        shared = valid[a] & valid[b]
        num = np.abs(top[a] - top[b] + bottom[a] - bottom[b])
        den = thickness[a] + thickness[b]
        rx1 = np.where(
            shared & (den > 0.0), num / np.where(den > 0.0, den, 1.0), 0.0
        )
        return rx1.max(axis=1)


def _compute_drops(
    config,
    ssh,
    bottom_depth,
    cells_on_edge,
    dv_edge,
    land_ice,
    film,
    group,
    percentile,
    max_rx1,
    front_margin,
    min_vert_levels,
    logger,
):
    """
    The number of reference levels each column drops at its top
    """
    ncells = land_ice.size
    both = (cells_on_edge[:, 0] >= 0) & (cells_on_edge[:, 1] >= 0)
    first = np.where(both, cells_on_edge[:, 0], 0)
    second = np.where(both, cells_on_edge[:, 1], 0)
    edges = np.flatnonzero(both & (land_ice[first] | land_ice[second]))
    ndrop_all = np.zeros(ncells, dtype=int)
    if edges.size == 0:
        return ndrop_all

    # only the cells on edges touching land ice can drop levels or affect
    # those that do, so work on those alone
    cells, local = np.unique(
        np.concatenate([first[edges], second[edges]]), return_inverse=True
    )
    cell_a = local[: edges.size]
    cell_b = local[edges.size :]
    column = _ReferenceColumns(
        config,
        ssh.isel(nCells=cells),
        bottom_depth.isel(nCells=cells),
    )
    land_ice = land_ice[cells]
    film = film[cells]
    group = group[cells]
    floating = land_ice & ~film
    draft = -column.ssh
    no_film = ~(film[cell_a] | film[cell_b])

    # fronts: ice next to open water whose bed is below the ice's draft by
    # more than a film column
    ice_cell = np.where(land_ice[cell_a], cell_a, cell_b)
    open_cell = np.where(land_ice[cell_a], cell_b, cell_a)
    front = (
        (land_ice[cell_a] != land_ice[cell_b])
        & no_film
        & (column.bottom_depth[open_cell] > draft[ice_cell] + front_margin)
    )
    front_length = np.zeros(cells.size)
    np.add.at(front_length, ice_cell[front], dv_edge[edges[front]])
    front_cell = front_length > 0.0

    # the number of reference levels entirely above each cell's draft
    above_draft = np.searchsorted(column.ref_bottom, draft, side='right')

    ndrop = np.zeros(cells.size, dtype=int)
    front_groups = np.unique(group[front_cell])
    for shelf in front_groups:
        in_shelf = group == shelf
        sel = front_cell & in_shelf
        ndrop[floating & in_shelf] = weighted_percentile(
            above_draft[sel], front_length[sel], percentile
        )
    ndrop[front_cell] = above_draft[front_cell]
    max_drop = np.maximum(column.max_level_cell + 1 - min_vert_levels, 0)
    ndrop = np.where(floating, np.minimum(ndrop, max_drop), 0)

    base = ndrop.copy()
    rx1 = column.rx1(cell_a, cell_b, base[cell_a], base[cell_b])
    steep = np.flatnonzero((rx1 > max_rx1) & no_film)
    unmet = 0
    for edge in steep:
        # the cell with the deeper draft drops more
        cell, other = cell_a[edge], cell_b[edge]
        if not column.ssh[cell] < column.ssh[other]:
            cell, other = other, cell
        if not floating[cell]:
            continue
        drop = _fewest_drops(column, cell, other, base, max_drop, max_rx1)
        if drop is None:
            unmet += 1
            drop = max_drop[cell]
        ndrop[cell] = max(ndrop[cell], drop)

    if logger is not None:
        inner = no_film & land_ice[cell_a] & land_ice[cell_b]
        _log_drops(
            logger=logger,
            n_shelves=int(np.unique(group[group > 0]).size),
            n_front_shelves=front_groups.size,
            n_front_cells=int(front_cell.sum()),
            n_land_ice=int(land_ice.sum()),
            ndrop=ndrop,
            base=base,
            unmet=unmet,
            rx1=column.rx1(
                cell_a[inner],
                cell_b[inner],
                ndrop[cell_a[inner]],
                ndrop[cell_b[inner]],
            ),
        )

    ndrop_all[cells] = ndrop
    return ndrop_all


def _fewest_drops(column, cell, other, base, max_drop, max_rx1):
    """
    The fewest drops of ``cell`` beyond its base that bring its edge with
    ``other`` to ``max_rx1``, or None if no drop does
    """
    pair_a = np.array([cell])
    pair_b = np.array([other])
    other_drop = np.array([base[other]])
    for drop in range(base[cell] + 1, max_drop[cell] + 1):
        rx1 = column.rx1(pair_a, pair_b, np.array([drop]), other_drop)
        if rx1[0] <= max_rx1:
            return drop
    return None


def _label_regions(cell_a, cell_b, mask, group, first):
    """
    Number the connected regions of ``mask`` from ``first``, in place
    """
    if not mask.any():
        return
    inside = mask[cell_a] & mask[cell_b]
    graph = coo_matrix(
        (np.ones(int(inside.sum())), (cell_a[inside], cell_b[inside])),
        shape=(mask.size, mask.size),
    )
    _, component = connected_components(graph, directed=False)
    _, label = np.unique(component[mask], return_inverse=True)
    group[mask] = label + first


def _log_drops(
    logger,
    n_shelves,
    n_front_shelves,
    n_front_cells,
    n_land_ice,
    ndrop,
    base,
    unmet,
    rx1,
):
    """
    Log a summary of the drops and the steepness that remains
    """
    logger.info(
        f'Ice-shelf top levels: {n_shelves} ice shelves, {n_front_shelves} '
        f'with calving fronts facing open water, {n_front_cells} front cells'
    )
    dropped = ndrop > 0
    if dropped.any():
        logger.info(
            f'  {int(dropped.sum())} of {n_land_ice} cells under land ice '
            f'drop levels (median {np.median(ndrop[dropped]):.0f}, max '
            f'{ndrop.max()}); {int((ndrop > base).sum())} drop more to limit '
            f'rx1, which {unmet} edges cannot meet'
        )
    if rx1.size > 0:
        logger.info(
            f'  rx1 between cells under land ice: max {rx1.max():.0f}, '
            f'99th percentile {np.percentile(rx1, 99):.0f}'
        )


def _squeeze_time(da):
    """
    Drop a ``Time`` dimension of length 1
    """
    if 'Time' in da.dims:
        da = da.isel(Time=0)
    return da
