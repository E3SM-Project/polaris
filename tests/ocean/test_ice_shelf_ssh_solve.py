"""
Unit tests for solving for the SSH under ice shelves that cancels the
depth-mean acceleration of a short run from rest
"""

import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.constants import get_constant
from polaris.ocean.ice_shelf.ssh_solve import (
    compute_depth_mean_acceleration,
    solve_for_ssh_change,
)

N_LEVELS = 4
DT = 10.0


def test_solve_flattens_a_bump_in_ssh():
    """
    The acceleration from a bump in SSH on the unknown cells must give back
    minus the bump, which leaves the SSH flat
    """
    ds_mesh = _make_mesh()
    unknown = _unknown_cells(ds_mesh)
    rng = np.random.default_rng(seed=1)
    bump = np.where(unknown, rng.uniform(-2.0, 2.0, unknown.size), 0.0)

    # pressure-gradient acceleration, positive from cellsOnEdge[0] to
    # cellsOnEdge[1]
    accel = -_gradient(ds_mesh, bump)
    edge_thickness = np.full(accel.shape, 100.0)

    delta_ssh, rms_before, rms_after = solve_for_ssh_change(
        ds_mesh, accel, edge_thickness, unknown
    )

    np.testing.assert_allclose(delta_ssh, -bump, atol=1e-8)
    assert rms_before > 0.0
    assert rms_after < 1e-8 * rms_before


def test_solve_leaves_fixed_cells_alone():
    """
    Acceleration on edges between fixed cells must not change the SSH, and
    the SSH of fixed cells must not change
    """
    ds_mesh = _make_mesh()
    unknown = _unknown_cells(ds_mesh)
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    fixed_edges = ~unknown[cells_on_edge[:, 0]] & ~unknown[cells_on_edge[:, 1]]
    accel = np.where(fixed_edges, 1e-3, 0.0)
    edge_thickness = np.full(accel.shape, 100.0)

    delta_ssh, rms_before, rms_after = solve_for_ssh_change(
        ds_mesh, accel, edge_thickness, unknown
    )

    np.testing.assert_array_equal(delta_ssh, 0.0)
    assert rms_before == 0.0
    assert rms_after == 0.0


def test_depth_mean_acceleration_weights_layers():
    """
    The depth-mean acceleration must weight each layer's velocity by its
    thickness and use only the layers both cells on an edge have
    """
    ds_mesh = _make_mesh()
    n_cells = ds_mesh.sizes['nCells']
    n_edges = ds_mesh.sizes['nEdges']

    # the top layer of every cell is 10 m thick and the others 30 m; layer
    # velocities after one step are 1, 2, 3 and 4 times 1e-4 m/s
    layer_thickness = np.full((n_cells, N_LEVELS), 30.0)
    layer_thickness[:, 0] = 10.0
    velocity = 1e-4 * np.arange(1.0, N_LEVELS + 1.0)
    end = np.broadcast_to(velocity, (n_edges, N_LEVELS))
    ds_init = _make_init(n_cells)
    ds_output = _make_output(layer_thickness, end)

    accel, edge_thickness = compute_depth_mean_acceleration(
        ds_mesh, ds_init, ds_output
    )

    expected = np.sum(layer_thickness[0] * velocity) / 100.0 / DT
    np.testing.assert_allclose(accel, expected)
    np.testing.assert_allclose(edge_thickness, 100.0)

    # a cell whose column starts a level lower leaves the top layer out on
    # its edges
    ds_init['minLevelCell'][0] = 2
    accel, edge_thickness = compute_depth_mean_acceleration(
        ds_mesh, ds_init, ds_output
    )
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    on_cell = np.any(cells_on_edge == 0, axis=1)
    expected = np.sum(layer_thickness[0, 1:] * velocity[1:]) / 90.0 / DT
    np.testing.assert_allclose(accel[on_cell], expected)
    np.testing.assert_allclose(edge_thickness[on_cell], 90.0)


def test_depth_mean_acceleration_needs_a_start_from_rest():
    """
    A run that does not start from rest does not measure the acceleration
    from the initial state alone, so it must be refused
    """
    ds_mesh = _make_mesh()
    n_cells = ds_mesh.sizes['nCells']
    n_edges = ds_mesh.sizes['nEdges']
    layer_thickness = np.full((n_cells, N_LEVELS), 25.0)
    end = np.full((n_edges, N_LEVELS), 1e-4)
    ds_output = _make_output(layer_thickness, end)
    ds_output['normalVelocity'][0, 0, 0] = 1e-3

    with pytest.raises(ValueError, match='from rest'):
        compute_depth_mean_acceleration(
            ds_mesh, _make_init(n_cells), ds_output
        )


def _make_mesh():
    return make_planar_hex_mesh(
        nx=8, ny=8, dc=1000.0, nonperiodic_x=False, nonperiodic_y=False
    )


def _unknown_cells(ds_mesh):
    """A block of cells in the middle of the mesh"""
    x = ds_mesh.xCell.values
    y = ds_mesh.yCell.values
    return (x > 2000.0) & (x < 6000.0) & (y > 1500.0) & (y < 5000.0)


def _gradient(ds_mesh, field):
    gravity = get_constant('standard_acceleration_of_gravity')
    cells_on_edge = ds_mesh.cellsOnEdge.values - 1
    return (
        gravity
        * (field[cells_on_edge[:, 1]] - field[cells_on_edge[:, 0]])
        / ds_mesh.dcEdge.values
    )


def _make_init(n_cells):
    ds_init = xr.Dataset()
    ds_init['minLevelCell'] = ('nCells', np.ones(n_cells, dtype=int))
    ds_init['maxLevelCell'] = ('nCells', np.full(n_cells, N_LEVELS))
    return ds_init


def _make_output(layer_thickness, end):
    start = np.zeros(end.shape)
    ds_output = xr.Dataset()
    ds_output['normalVelocity'] = (
        ('Time', 'nEdges', 'nVertLevels'),
        np.stack([start, end]),
    )
    ds_output['layerThickness'] = (
        ('Time', 'nCells', 'nVertLevels'),
        np.stack([layer_thickness, layer_thickness]),
    )
    ds_output['daysSinceStartOfSim'] = (
        'Time',
        np.array([0.0, DT / get_constant('seconds_per_day')]),
    )
    return ds_output
