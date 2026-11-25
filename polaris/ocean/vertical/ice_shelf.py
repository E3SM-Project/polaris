"""
The top depth of each ocean column under ice shelves.

Under an ice shelf, z-star would squeeze the whole reference column between
the ice draft and the bed.  Instead, each column under a shelf starts at a
top depth and follows z-star over the reference column below it:

* each ice shelf starts at a percentile of the drafts along its calving
  front, weighted by the length and the weight of each front;

* a cell at a calving front that faces open water starts at its own draft,
  blended with its shelf's top depth by the front's weight, so its layers
  line up with the open ocean;

* where the layers of neighboring columns are still too steep, the cell
  with the deeper draft starts at the shallowest deeper top depth that
  brings the hydrostatic consistency number rx1 down to a maximum.

Reference levels lying entirely above a column's top depth are dropped, and
the level containing it becomes a partial top level.  A partial top level
that keeps less than ``ice_shelf_min_top_fraction`` of its reference
thickness merges into the level below.  A top level that shares its level
with fewer than two neighbors also merges into the level below, since its
flow cannot reach geostrophic balance.  Film cells start at the surface, and
every column keeps at least ``min_vert_levels`` levels.  The ice shelves are
found once, by a flood fill of the floating cells and then of the grounded
(film) cells.
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

# the top depths sampled in each part of a level when searching for the
# shallowest that meets the rx1 maximum, and the number of times the search
# narrows in on it
_RX1_SAMPLES = 8
_RX1_REFINEMENTS = 4


def compute_ice_shelf_top_depth(
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
    Compute the top depth of each column under ice shelves and the ice shelf
    each cell belongs to.

    With ``[vertical_grid] ice_shelf_top_level = surface``, every column
    starts at the surface.  With ``front_draft``, columns under ice shelves
    start at top depths set by the drafts along calving fronts (see the
    module docstring), with the percentile in ``ice_shelf_front_percentile``,
    the maximum rx1 in ``ice_shelf_max_rx1`` and the smallest partial top
    level in ``ice_shelf_min_top_fraction``.

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
        The thickness (m) of each layer of the thin film.  A film column is
        ``min_vert_levels`` of these layers.  A calving front only counts
        where the open water's bed is below the ice draft by more than a film
        column, and its weight ramps up from there.

    logger : logging.Logger, optional
        A logger for a summary of the top depths

    Returns
    -------
    top_depth : xarray.DataArray
        The positive-down depth (m) at which each column starts, 0 at the
        surface

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

    depth = np.zeros(ssh.sizes['nCells'])
    if top_level == 'front_draft':
        depth = _compute_top_depths(
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
            film_column=min_vert_levels * thin_film_layer_thickness,
            logger=logger,
        )

    top_depth = xr.DataArray(depth, dims=('nCells',))
    return top_depth, ice_shelf_group


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


def start_columns_at_top_depth(
    thickness,
    ref_interfaces,
    top_depth,
    max_level_cell,
    column_thickness,
    cells_on_edge,
    min_vert_levels,
    min_top_fraction,
):
    """
    Start each column at its top depth, with a partial top level, and
    stretch the thicknesses that remain to the column's thickness.

    Reference levels lying entirely above the top depth are dropped.  The
    level containing it keeps the part below the top depth, unless that is
    less than ``min_top_fraction`` of its reference thickness, in which case
    it merges into the level below.  Each top depth is capped at the top of
    the level ``min_vert_levels - 1`` levels above the column's last level,
    so the column keeps at least ``min_vert_levels`` levels.  Columns that
    start at the surface are not changed.

    An edge is active at a level when both of its cells have that level.
    The top level of a column that starts below the surface then merges into
    the level below while it has fewer than two active edges, keeping at
    least ``min_vert_levels`` levels.  Merging a level can take an active
    edge from a neighbor's top level, so columns are revisited until none
    changes.  A column with no level that has two active edges, given its
    neighbors' levels before any merge, keeps its levels.  A merge never
    adds an active edge, so the result does not depend on the order of the
    cells.

    Parameters
    ----------
    thickness : xarray.DataArray
        The thickness of each level of each column starting at the top
        level, zero below the column, with dimensions ``nCells`` and
        ``nVertLevels``

    ref_interfaces : numpy.ndarray
        The positive-down depths of the interfaces between reference levels

    top_depth : xarray.DataArray
        The positive-down depth at which each column starts

    max_level_cell : xarray.DataArray
        The zero-based last level of each column

    column_thickness : xarray.DataArray
        The thickness the levels of each column must sum to

    cells_on_edge : xarray.DataArray
        The one-based indices of the two cells on each edge, as in the mesh,
        with 0 where there is no cell

    min_vert_levels : int
        The minimum number of levels in a column

    min_top_fraction : float
        The smallest fraction of its reference thickness that a partial top
        level keeps before it merges into the level below

    Returns
    -------
    min_level_cell : xarray.DataArray
        The zero-based first level of each column

    thickness : xarray.DataArray
        The thickness of each level of each column
    """
    thickness = thickness.transpose('nCells', 'nVertLevels')
    top_depth = _squeeze_time(top_depth).values
    max_level_cell = max_level_cell.values.astype(int)
    min_level_cell, values = _start_at_top_depth(
        thickness=thickness.values,
        interfaces=np.asarray(ref_interfaces),
        top_depth=top_depth,
        max_level_cell=max_level_cell,
        column_thickness=column_thickness.values,
        min_vert_levels=min_vert_levels,
        min_top_fraction=min_top_fraction,
    )
    min_level_cell, values = _merge_weakly_connected_top_levels(
        thickness=values,
        min_level_cell=min_level_cell,
        max_level_cell=max_level_cell,
        cells_on_edge=cells_on_edge.values - 1,
        candidate=top_depth > 0.0,
        min_vert_levels=min_vert_levels,
    )
    min_level_cell = xr.DataArray(min_level_cell, dims=('nCells',))
    return min_level_cell, thickness.copy(data=values)


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
        self.min_vert_levels = section.getint('min_vert_levels')
        self.min_top_fraction = section.getfloat('ice_shelf_min_top_fraction')
        min_level_cell, max_level_cell, _ = compute_min_max_level_cell(
            ref_top,
            ref_bot,
            zero,
            bottom_depth,
            min_vert_levels=self.min_vert_levels,
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
        self.ref_interfaces = np.asarray(interfaces)
        self.ssh = ssh.values
        self.bottom_depth = bottom_depth.values
        self.max_level_cell = max_level_cell.values.astype(int)
        self.resting = resting.transpose('nCells', 'nVertLevels').values
        self.deepest = _deepest_top_depth(
            self.ref_interfaces, self.max_level_cell, self.min_vert_levels
        )

    def interfaces(self, cells, top_depth):
        """
        The thickness and top and bottom heights of each layer of the given
        cells starting at the given top depths, z-star below them
        """
        min_level_cell, resting = _start_at_top_depth(
            thickness=self.resting[cells],
            interfaces=self.ref_interfaces,
            top_depth=top_depth,
            max_level_cell=self.max_level_cell[cells],
            column_thickness=self.bottom_depth[cells],
            min_vert_levels=self.min_vert_levels,
            min_top_fraction=self.min_top_fraction,
        )
        levels = np.arange(resting.shape[1])[np.newaxis, :]
        valid = (levels >= min_level_cell[:, np.newaxis]) & (
            levels <= self.max_level_cell[cells, np.newaxis]
        )
        resting = np.where(valid, resting, 0.0)
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

    def rx1(self, cell_a, cell_b, top_a, top_b):
        """
        The largest rx1 over the shared layers of each pair of cells
        """
        cells = np.concatenate([cell_a, cell_b])
        top_depth = np.concatenate([top_a, top_b])
        thickness, top, bottom, valid = self.interfaces(cells, top_depth)
        a = slice(0, cell_a.size)
        b = slice(cell_a.size, None)
        shared = valid[a] & valid[b]
        num = np.abs(top[a] - top[b] + bottom[a] - bottom[b])
        den = thickness[a] + thickness[b]
        rx1 = np.where(
            shared & (den > 0.0), num / np.where(den > 0.0, den, 1.0), 0.0
        )
        return rx1.max(axis=1)

    def edge_rx1(self, cell, other, top_depths, other_top_depth):
        """
        The rx1 of the edge between ``cell`` and ``other`` with ``cell`` at
        each of the given top depths
        """
        count = top_depths.size
        return self.rx1(
            np.full(count, cell),
            np.full(count, other),
            top_depths,
            np.full(count, other_top_depth),
        )

    def candidate_top_depths(self, start, stop):
        """
        Top depths deeper than ``start`` and down to ``stop``, sampled
        between the reference interfaces and the depths where a partial top
        level merges into the level below
        """
        interfaces = self.ref_interfaces
        merge = interfaces[1:] - self.min_top_fraction * np.diff(interfaces)
        knots = np.unique(np.concatenate([interfaces, merge, [start, stop]]))
        knots = knots[(knots >= start) & (knots <= stop)]
        fractions = np.arange(1, _RX1_SAMPLES + 1) / _RX1_SAMPLES
        depths = knots[:-1, np.newaxis] + np.outer(np.diff(knots), fractions)
        return depths.ravel()


def _start_at_top_depth(
    thickness,
    interfaces,
    top_depth,
    max_level_cell,
    column_thickness,
    min_vert_levels,
    min_top_fraction,
):
    """
    The first level and thicknesses of each column starting at its top
    depth, as numpy arrays (see :py:func:`start_columns_at_top_depth`)
    """
    ncells, nlevels = thickness.shape
    rows = np.arange(ncells)
    deepest = _deepest_top_depth(interfaces, max_level_cell, min_vert_levels)
    top = np.clip(top_depth, 0.0, deepest)

    # the levels lying entirely above the top depth are dropped, and the one
    # containing it is the partial top level
    level = np.searchsorted(interfaces[1:], top, side='right')
    level = np.minimum(level, np.maximum(max_level_cell, 0))
    fraction = (interfaces[level + 1] - top) / np.diff(interfaces)[level]
    partial = thickness[rows, level] - (top - interfaces[level])
    merge = (fraction < min_top_fraction) & (level < max_level_cell)

    levels = np.arange(nlevels)[np.newaxis, :]
    result = np.where(levels < level[:, np.newaxis], 0.0, thickness)
    result[rows, level] = np.where(merge, 0.0, partial)
    below = np.minimum(level + 1, nlevels - 1)
    result[rows[merge], below[merge]] += partial[merge]
    min_level_cell = level + merge.astype(int)

    total = result.sum(axis=1)
    stretch = np.where(
        (top > 0.0) & (total > 0.0),
        column_thickness / np.where(total > 0.0, total, 1.0),
        1.0,
    )
    return min_level_cell, result * stretch[:, np.newaxis]


def _merge_weakly_connected_top_levels(
    thickness,
    min_level_cell,
    max_level_cell,
    cells_on_edge,
    candidate,
    min_vert_levels,
):
    """
    Merge the top level of each candidate column into the level below while
    it has fewer than two active edges, as numpy arrays (see
    :py:func:`start_columns_at_top_depth`)
    """
    ncells, nlevels = thickness.shape
    deepest = np.maximum(max_level_cell - min_vert_levels + 1, 0)
    both = (cells_on_edge[:, 0] >= 0) & (cells_on_edge[:, 1] >= 0)
    cell = np.concatenate([cells_on_edge[both, 0], cells_on_edge[both, 1]])
    other = np.concatenate([cells_on_edge[both, 1], cells_on_edge[both, 0]])
    keep = candidate[cell]
    cell = cell[keep]
    other = other[keep]

    # a column that has no level with two active edges, even before any
    # neighbor merges, keeps its levels
    low = np.maximum(min_level_cell[cell], min_level_cell[other])
    high = np.minimum(deepest[cell], max_level_cell[other])
    reachable = np.zeros(ncells, dtype=bool)
    for level in range(nlevels):
        shared = (low <= level) & (level <= high)
        reachable |= np.bincount(cell[shared], minlength=ncells) >= 2
    movable = candidate & reachable

    first = min_level_cell.copy()
    while True:
        level = first[cell]
        active = (first[other] <= level) & (level <= max_level_cell[other])
        count = np.bincount(cell[active], minlength=ncells)
        merge = movable & (count < 2) & (first < deepest)
        if not merge.any():
            break
        first = first + merge.astype(first.dtype)

    # each merged column's top level gains the thickness of the levels
    # above it
    rows = np.flatnonzero(first > min_level_cell)
    above = np.arange(nlevels)[np.newaxis, :] < first[rows, np.newaxis]
    merged = np.where(above, thickness[rows], 0.0).sum(axis=1)
    values = thickness.copy()
    values[rows] = np.where(above, 0.0, thickness[rows])
    values[rows, first[rows]] += merged
    return first, values


def _deepest_top_depth(interfaces, max_level_cell, min_vert_levels):
    """
    The deepest top depth of each column: the top of the level
    ``min_vert_levels - 1`` levels above its last level
    """
    first = np.clip(max_level_cell - min_vert_levels + 1, 0, None)
    return interfaces[first]


def _compute_top_depths(
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
    film_column,
    logger,
):
    """
    The depth at which each column starts
    """
    ncells = land_ice.size
    both = (cells_on_edge[:, 0] >= 0) & (cells_on_edge[:, 1] >= 0)
    first = np.where(both, cells_on_edge[:, 0], 0)
    second = np.where(both, cells_on_edge[:, 1], 0)
    edges = np.flatnonzero(both & (land_ice[first] | land_ice[second]))
    top_all = np.zeros(ncells)
    if edges.size == 0:
        return top_all

    # only the cells on edges touching land ice can start below the surface
    # or affect those that do, so work on those alone
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
    # more than a film column, each with a weight that ramps up from there
    ice_cell = np.where(land_ice[cell_a], cell_a, cell_b)
    open_cell = np.where(land_ice[cell_a], cell_b, cell_a)
    weight = np.where(
        (land_ice[cell_a] != land_ice[cell_b]) & no_film,
        _front_weights(
            draft=draft[ice_cell],
            ice_bed=column.bottom_depth[ice_cell],
            open_bed=column.bottom_depth[open_cell],
            interfaces=column.ref_interfaces,
            film_column=film_column,
        ),
        0.0,
    )
    front = weight > 0.0
    front_weight = np.zeros(cells.size)
    np.maximum.at(front_weight, ice_cell[front], weight[front])
    percentile_weight = np.zeros(cells.size)
    np.add.at(
        percentile_weight,
        ice_cell[front],
        weight[front] * dv_edge[edges[front]],
    )
    front_cell = front_weight > 0.0

    shelf_top = np.zeros(cells.size)
    front_groups = np.unique(group[front_cell])
    for shelf in front_groups:
        in_shelf = group == shelf
        sel = front_cell & in_shelf
        shelf_top[in_shelf] = weighted_percentile(
            draft[sel], percentile_weight[sel], percentile
        )
    top = front_weight * draft + (1.0 - front_weight) * shelf_top
    top = np.where(floating, np.clip(top, 0.0, column.deepest), 0.0)

    base = top.copy()
    rx1 = column.rx1(cell_a, cell_b, base[cell_a], base[cell_b])
    steep = np.flatnonzero((rx1 > max_rx1) & no_film)
    unmet = 0
    for edge in steep:
        # the cell with the deeper draft starts deeper
        cell, other = cell_a[edge], cell_b[edge]
        if not column.ssh[cell] < column.ssh[other]:
            cell, other = other, cell
        if not floating[cell]:
            continue
        depth = _shallowest_top_depth(column, cell, other, base, max_rx1)
        if depth is None:
            unmet += 1
            depth = column.deepest[cell]
        top[cell] = max(top[cell], depth)

    if logger is not None:
        inner = no_film & land_ice[cell_a] & land_ice[cell_b]
        _log_top_depths(
            logger=logger,
            column=column,
            n_shelves=int(np.unique(group[group > 0]).size),
            n_front_shelves=front_groups.size,
            n_front_cells=int(front_cell.sum()),
            n_land_ice=int(land_ice.sum()),
            top=top,
            base=base,
            unmet=unmet,
            rx1=column.rx1(
                cell_a[inner],
                cell_b[inner],
                top[cell_a[inner]],
                top[cell_b[inner]],
            ),
        )

    top_all[cells] = top
    return top_all


def _front_weights(draft, ice_bed, open_bed, interfaces, film_column):
    """
    The weight of each edge between an ice cell and an open-water cell, the
    product of two ramps from 0 to 1: one as the open cell's bed goes from a
    film column below the draft to a film column plus the reference
    thickness at the draft, and one as the ice cell's column goes from one
    film column to two
    """
    ref_thickness = np.diff(interfaces)
    level = np.searchsorted(interfaces[1:], draft, side='right')
    level = np.clip(level, 0, ref_thickness.size - 1)
    open_ramp = np.clip(
        (open_bed - draft - film_column) / ref_thickness[level], 0.0, 1.0
    )
    ice_column = ice_bed - draft
    if film_column > 0.0:
        column_ramp = np.clip((ice_column - film_column) / film_column, 0, 1)
    else:
        column_ramp = (ice_column > 0.0).astype(float)
    return open_ramp * column_ramp


def _shallowest_top_depth(column, cell, other, base, max_rx1):
    """
    The shallowest top depth of ``cell`` deeper than its base that brings
    its edge with ``other`` to ``max_rx1``, with ``other`` at its base, or
    None if none does
    """
    depths = column.candidate_top_depths(base[cell], column.deepest[cell])
    if depths.size == 0:
        return None
    passing = column.edge_rx1(cell, other, depths, base[other]) <= max_rx1
    if not passing.any():
        return None
    index = int(np.argmax(passing))
    shallow = base[cell] if index == 0 else depths[index - 1]
    deep = depths[index]
    fractions = np.arange(1, _RX1_SAMPLES + 1) / _RX1_SAMPLES
    for _ in range(_RX1_REFINEMENTS):
        # the deepest sample is the one known to pass, exactly
        depths = shallow + fractions * (deep - shallow)
        depths[-1] = deep
        passing = column.edge_rx1(cell, other, depths, base[other]) <= max_rx1
        index = int(np.argmax(passing))
        if index > 0:
            shallow = depths[index - 1]
        deep = depths[index]
    return deep


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


def _log_top_depths(
    logger,
    column,
    n_shelves,
    n_front_shelves,
    n_front_cells,
    n_land_ice,
    top,
    base,
    unmet,
    rx1,
):
    """
    Log a summary of the top depths and the steepness that remains
    """
    logger.info(
        f'Ice-shelf top depths: {n_shelves} ice shelves, {n_front_shelves} '
        f'with calving fronts facing open water, {n_front_cells} front cells'
    )
    below = top > 0.0
    if below.any():
        cells = np.flatnonzero(below)
        min_level_cell, _ = _start_at_top_depth(
            thickness=column.resting[cells],
            interfaces=column.ref_interfaces,
            top_depth=top[cells],
            max_level_cell=column.max_level_cell[cells],
            column_thickness=column.bottom_depth[cells],
            min_vert_levels=column.min_vert_levels,
            min_top_fraction=column.min_top_fraction,
        )
        level = np.searchsorted(
            column.ref_interfaces[1:], top[cells], side='right'
        )
        logger.info(
            f'  {cells.size} of {n_land_ice} cells under land ice start '
            f'below the surface (median {np.median(top[cells]):.0f} m, max '
            f'{top.max():.0f} m); {int((min_level_cell > level).sum())} '
            f'merge their partial top level into the level below; '
            f'{int((top > base).sum())} start deeper to limit rx1, which '
            f'{unmet} edges cannot meet'
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
