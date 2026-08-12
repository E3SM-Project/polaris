import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def active_edge_masks(ds_mesh, cell_mask):
    """
    Find, for each local edge of each cell, whether the neighboring cell
    across that edge and across the next and previous edges around the same
    cell belong to the domain.

    An edge is "active" when the cell on the other side of it is part of the
    domain, so an active edge is one across which the two models can move
    water or ice.  Two edges that are adjacent in a cell's edge ordering meet
    at a vertex, so ``active & active_next`` marks the vertices of the cell
    whose surrounding cells all belong to the domain.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    cell_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True for cells in the domain

    Returns
    -------
    active : numpy.ndarray
        A boolean array of shape ``(nCells, maxEdges)`` that is True where
        the neighbor across the local edge is in the domain

    active_next : numpy.ndarray
        The same for the next edge around each cell

    active_prev : numpy.ndarray
        The same for the previous edge around each cell
    """
    cells_on_cell = ds_mesh.cellsOnCell.values - 1
    n_edges_on_cell = np.asarray(ds_mesh.nEdgesOnCell.values)
    mask = np.asarray(cell_mask).astype(bool)

    n_cells, max_edges = cells_on_cell.shape
    local = np.arange(max_edges)[np.newaxis, :]
    count = n_edges_on_cell[:, np.newaxis]
    # local edge indices beyond nEdgesOnCell are padding
    real = local < count

    rows = np.arange(n_cells)[:, np.newaxis]
    next_on_cell = cells_on_cell[rows, (local + 1) % count]
    prev_on_cell = cells_on_cell[rows, (local - 1) % count]

    active = real & _in_domain(cells_on_cell, mask)
    active_next = real & _in_domain(next_on_cell, mask)
    active_prev = real & _in_domain(prev_on_cell, mask)

    return active, active_next, active_prev


def count_active_edges(ds_mesh, cell_mask):
    """
    Count the active edges of each cell.

    A cell of the ocean domain needs at least two of them, so that a C-grid
    has a way to move water in and a way to move it out.  The two edges need
    not be adjacent.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    cell_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True for cells in the domain

    Returns
    -------
    count : numpy.ndarray
        The number of active edges of each cell, as an integer array of
        shape ``(nCells,)``.  Cells outside the domain are counted too;
        callers that care should mask the result.
    """
    active, _, _ = active_edge_masks(ds_mesh, cell_mask)
    return active.sum(axis=1)


def has_active_vertex(ds_mesh, cell_mask):
    """
    Find the cells with at least one active vertex, meaning a vertex all of
    whose surrounding cells are in the domain.

    A cell of the sea-ice domain needs one of these, or a B-grid has no
    velocity point by which ice can leave it.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    cell_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True for cells in the domain

    Returns
    -------
    has_vertex : numpy.ndarray
        A boolean array of shape ``(nCells,)``.  Cells outside the domain
        are evaluated too; callers that care should mask the result.
    """
    active, active_next, _ = active_edge_masks(ds_mesh, cell_mask)
    return np.logical_and(active, active_next).any(axis=1)


def transport_link_mask(ds_mesh, cell_mask):
    """
    Find the active edges across which a B-grid can move sea ice.

    The velocity used to move ice across an edge is built from the
    velocities at the edge's two vertices, so an edge whose vertices are
    both inactive carries no flux and does not connect the cells it
    separates, even though they share an edge.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    cell_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True for cells in the domain

    Returns
    -------
    link_mask : numpy.ndarray
        A boolean array of shape ``(nCells, maxEdges)`` that is True for
        active edges with at least one active vertex
    """
    active, active_next, active_prev = active_edge_masks(ds_mesh, cell_mask)
    return np.logical_and(active, np.logical_or(active_next, active_prev))


def connected_to_seeds(ds_mesh, cell_mask, seed_mask, link_mask=None):
    """
    Find the cells of the domain that are connected to at least one seed
    cell.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``cellsOnCell`` and ``nEdgesOnCell``

    cell_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True for cells in the domain

    seed_mask : numpy.ndarray or xarray.DataArray
        A boolean mask on cells that is True at the seed cells.  Seeds
        outside the domain are ignored.

    link_mask : numpy.ndarray, optional
        A boolean array of shape ``(nCells, maxEdges)`` selecting the local
        edges that connect cells.  The default connects every active edge,
        which is the ocean's C-grid connectivity; pass the result of
        :py:func:`transport_link_mask` for the sea ice's B-grid
        connectivity.

    Returns
    -------
    connected : numpy.ndarray
        A boolean array of shape ``(nCells,)`` that is True for cells in the
        domain that are reachable from a seed
    """
    cells_on_cell = ds_mesh.cellsOnCell.values - 1
    mask = np.asarray(cell_mask).astype(bool)
    seeds = np.asarray(seed_mask).astype(bool)
    n_cells = cells_on_cell.shape[0]

    if link_mask is None:
        link_mask, _, _ = active_edge_masks(ds_mesh, cell_mask)
    # a link is only usable if the cell it belongs to is in the domain
    link_mask = np.logical_and(link_mask, mask[:, np.newaxis])

    source = np.repeat(np.arange(n_cells), link_mask.sum(axis=1))
    target = cells_on_cell[link_mask]
    graph = coo_matrix(
        (np.ones(source.size, dtype=bool), (source, target)),
        shape=(n_cells, n_cells),
    )
    _, label = connected_components(graph, directed=False)

    seeds = np.logical_and(seeds, mask)
    if not seeds.any():
        return np.zeros(n_cells, dtype=bool)

    return np.logical_and(mask, np.isin(label, np.unique(label[seeds])))


def seed_mask_from_points(ds_mesh, lon_seed, lat_seed):
    """
    Find the cells nearest to a set of seed points.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        An MPAS mesh with ``lonCell`` and ``latCell`` in radians

    lon_seed : array_like
        The longitudes of the seed points in degrees

    lat_seed : array_like
        The latitudes of the seed points in degrees

    Returns
    -------
    seed_mask : numpy.ndarray
        A boolean array of shape ``(nCells,)`` that is True at the cell
        nearest to each seed point
    """
    lon_cell = np.degrees(ds_mesh.lonCell.values)
    lat_cell = np.degrees(ds_mesh.latCell.values)

    tree = cKDTree(_lon_lat_to_xyz(lon_cell, lat_cell))
    _, index = tree.query(
        _lon_lat_to_xyz(np.asarray(lon_seed), np.asarray(lat_seed))
    )

    seed_mask = np.zeros(lon_cell.size, dtype=bool)
    seed_mask[np.atleast_1d(index)] = True
    return seed_mask


def _in_domain(neighbors, mask):
    """
    Find where a neighbor index array points at a cell in the domain.
    """
    return np.logical_and(neighbors >= 0, mask[np.maximum(neighbors, 0)])


def _lon_lat_to_xyz(lon, lat):
    """
    Convert longitude and latitude in degrees to points on the unit sphere.
    """
    lon = np.radians(lon)
    lat = np.radians(lat)
    return np.column_stack(
        (np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat))
    )
