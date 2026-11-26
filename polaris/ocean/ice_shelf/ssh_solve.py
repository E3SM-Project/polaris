import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from polaris.constants import get_constant


def compute_depth_mean_acceleration(ds_mesh, ds_init, ds_output):
    """
    Compute the depth-mean acceleration on each edge from a short run that
    starts from rest

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh, with ``cellsOnEdge``

    ds_init : xarray.Dataset
        The initial state the run started from, without a ``Time``
        dimension, with one-based ``minLevelCell`` and ``maxLevelCell``

    ds_output : xarray.Dataset
        The run's output, with ``normalVelocity``, ``layerThickness`` and
        ``daysSinceStartOfSim`` at its start (from rest) and at its end

    Returns
    -------
    accel : numpy.ndarray
        The depth-mean acceleration on each edge in m/s^2, positive from the
        first cell on the edge toward the second, and 0 on dry and boundary
        edges

    edge_thickness : numpy.ndarray
        The thickness in m of the water column shared by the two cells on
        each edge at the start of the run
    """
    days = ds_output.daysSinceStartOfSim.values
    dt = float(days[-1] - days[0]) * get_constant('seconds_per_day')
    if dt <= 0.0:
        raise ValueError(
            'The run output must include its start and a later time.'
        )

    cell0, cell1, interior = _edge_cells(ds_mesh)
    min_level = ds_init.minLevelCell.values - 1
    max_level = ds_init.maxLevelCell.values - 1
    n_levels = ds_output.sizes['nVertLevels']
    level = np.arange(n_levels)[np.newaxis, :]
    top = np.maximum(min_level[cell0], min_level[cell1])[:, np.newaxis]
    bottom = np.minimum(max_level[cell0], max_level[cell1])[:, np.newaxis]
    active = interior[:, np.newaxis] & (level >= top) & (level <= bottom)

    h = ds_output.layerThickness.isel(Time=0).values
    h_edge = np.where(active, 0.5 * (h[cell0] + h[cell1]), 0.0)
    velocity = ds_output.normalVelocity
    start = np.where(active, velocity.isel(Time=0).values, 0.0)
    if np.any(start != 0.0):
        raise ValueError('The run did not start from rest.')
    end = np.where(active, velocity.isel(Time=-1).values, 0.0)

    edge_thickness = h_edge.sum(axis=1)
    wet = edge_thickness > 0.0
    mean_velocity = np.zeros(edge_thickness.shape)
    mean_velocity[wet] = (h_edge * end).sum(axis=1)[wet] / edge_thickness[wet]
    accel = mean_velocity / dt
    return accel, edge_thickness


def solve_for_ssh_change(ds_mesh, accel, edge_thickness, unknown):
    """
    Solve for the change in SSH that cancels the depth-mean acceleration
    from a run started from rest

    The change in SSH, nonzero only on ``unknown`` cells, makes
    ``g * grad(delta_ssh)`` best match ``accel`` in the least-squares sense,
    on every wet edge with an unknown cell on either side.  Each edge is
    weighted by ``edge_thickness * dcEdge * dvEdge``, so the solve
    minimizes the kinetic energy the remaining acceleration would produce.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh, with ``cellsOnEdge``, ``dcEdge`` and
        ``dvEdge``

    accel : numpy.ndarray
        The depth-mean acceleration on each edge in m/s^2, from
        :py:func:`compute_depth_mean_acceleration`

    edge_thickness : numpy.ndarray
        The water-column thickness on each edge in m, from
        :py:func:`compute_depth_mean_acceleration`

    unknown : numpy.ndarray
        A boolean mask of the cells where SSH may change

    Returns
    -------
    delta_ssh : numpy.ndarray
        The change in SSH on each cell in m

    rms_before : float
        The weighted root-mean-square acceleration in m/s^2 on the edges
        used in the solve

    rms_after : float
        The weighted root-mean-square acceleration the change in SSH is
        predicted to leave on those edges
    """
    gravity = get_constant('standard_acceleration_of_gravity')
    unknown = np.asarray(unknown, dtype=bool)
    n_cells = unknown.size
    delta_ssh = np.zeros(n_cells)

    cell0, cell1, interior = _edge_cells(ds_mesh)
    wet = interior & (edge_thickness > 0.0)
    edges = np.flatnonzero(wet & (unknown[cell0] | unknown[cell1]))
    n_unknown = int(unknown.sum())
    if edges.size == 0 or n_unknown == 0:
        return delta_ssh, 0.0, 0.0

    dc = ds_mesh.dcEdge.values[edges]
    dv = ds_mesh.dvEdge.values[edges]
    index = -np.ones(n_cells, dtype=int)
    index[unknown] = np.arange(n_unknown)

    # g * (delta_ssh[cell1] - delta_ssh[cell0]) / dcEdge on each edge
    rows = []
    cols = []
    values = []
    for cells, sign in ((cell0[edges], -1.0), (cell1[edges], 1.0)):
        on_edge = np.flatnonzero(index[cells] >= 0)
        rows.append(on_edge)
        cols.append(index[cells[on_edge]])
        values.append(sign * gravity / dc[on_edge])
    gradient = sp.csr_matrix(
        (np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))),
        shape=(edges.size, n_unknown),
    )

    weights = edge_thickness[edges] * dc * dv
    lhs = (gradient.T @ sp.diags(weights) @ gradient).tocsc()
    # a tiny regularization keeps the system solvable for a group of
    # unknown cells that touches no fixed cell
    eps = 1e-10 * lhs.diagonal().mean()
    lhs = lhs + eps * sp.identity(n_unknown, format='csc')
    rhs = gradient.T @ (weights * accel[edges])
    solution = spla.spsolve(lhs, rhs)
    delta_ssh[unknown] = solution

    residual = accel[edges] - gradient @ solution
    total_weight = weights.sum()
    rms_before = np.sqrt(np.sum(weights * accel[edges] ** 2) / total_weight)
    rms_after = np.sqrt(np.sum(weights * residual**2) / total_weight)
    return delta_ssh, float(rms_before), float(rms_after)


def _edge_cells(ds_mesh):
    """
    Get the zero-based cells on each edge and which edges have two cells
    """
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    interior = (cells_on_edge[:, 0] >= 0) & (cells_on_edge[:, 1] >= 0)
    cell0 = np.where(interior, cells_on_edge[:, 0], 0)
    cell1 = np.where(interior, cells_on_edge[:, 1], 0)
    return cell0, cell1, interior
