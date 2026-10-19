import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.vector import compute_edge_normal_vec
from polaris.ocean.overturning import (
    bin_line_transport,
    compute_line_transport,
    compute_overturning,
    get_line_edges,
    interp_cell_to_line_edges,
)

DC = 1000.0


@pytest.fixture(scope='module')
def periodic_mesh():
    """A small doubly periodic planar hex mesh"""
    return make_planar_hex_mesh(
        nx=8, ny=6, dc=DC, nonperiodic_x=False, nonperiodic_y=False
    )


@pytest.fixture(scope='module')
def channel_mesh(periodic_mesh):
    """
    The periodic mesh with its x seam cut: the edges across the seam
    become boundary edges and the mesh is no longer periodic in x
    """
    ds = periodic_mesh.copy(deep=True)
    x_period = ds.attrs['x_period']
    cells_on_edge = ds.cellsOnEdge.values.copy()
    x_cell = ds.xCell.values
    x1 = x_cell[cells_on_edge[:, 0] - 1]
    x2 = x_cell[cells_on_edge[:, 1] - 1]
    seam = np.abs(x2 - x1) > 0.5 * x_period
    cells_on_edge[seam, 1] = 0
    ds['cellsOnEdge'] = (ds.cellsOnEdge.dims, cells_on_edge)
    ds.attrs['x_period'] = 0.0
    return ds


def _uniform_normal_velocity(ds_mesh, u, v, nlevels):
    """The normal component of a uniform (u, v) flow on every edge"""
    normal = compute_edge_normal_vec(ds_mesh)
    normal_velocity = u * normal.isel(R3=0) + v * normal.isel(R3=1)
    return normal_velocity.expand_dims(nVertLevels=nlevels, axis=1)


def _uniform_thickness(ds_mesh, thickness):
    """Layer thicknesses that are the same in every cell"""
    thickness = xr.DataArray(np.asarray(thickness), dims=('nVertLevels',))
    return xr.ones_like(ds_mesh.xCell) * thickness


def _line_values(ds_mesh, coord):
    """
    Line positions between cell centers, on cell centers, and across the
    periodic seam (below the first and above the last cell center)
    """
    positions = np.unique(ds_mesh[f'{coord}Cell'].values)
    between = 0.5 * (positions[:-1] + positions[1:])
    period = ds_mesh.attrs[f'{coord}_period']
    seam = [0.0, positions[0] - 1.0, positions[-1] + 1.0, period - 1.0]
    return list(between) + list(positions) + seam


@pytest.mark.parametrize('coord', ['x', 'y'])
def test_weights_sum_to_the_period(periodic_mesh, coord):
    # a line of constant x runs along y, and vice versa
    along = 'y' if coord == 'x' else 'x'
    period = periodic_mesh.attrs[f'{along}_period']
    for value in _line_values(periodic_mesh, coord):
        line = get_line_edges(periodic_mesh, coord, value)
        assert line.sizes['nLineEdges'] > 0
        np.testing.assert_allclose(line.weight.sum(), period, rtol=1e-12)
        assert line.attrs['length'] == pytest.approx(period, rel=1e-12)


def test_y_lines_on_a_hex_mesh_are_row_zigzags(periodic_mesh):
    """On a hex mesh, a line between rows crosses two edges per cell"""
    y_cell = np.unique(periodic_mesh.yCell.values)
    value = 0.5 * (y_cell[1] + y_cell[2])
    line = get_line_edges(periodic_mesh, 'y', value)
    nx = int(round(periodic_mesh.attrs['x_period'] / DC))
    assert line.sizes['nLineEdges'] == 2 * nx
    np.testing.assert_allclose(line.weight, 0.5 * DC, rtol=1e-12)


@pytest.mark.parametrize('coord', ['x', 'y'])
def test_uniform_flow_gives_velocity_times_length(periodic_mesh, coord):
    u, v = 0.3, -0.2
    thickness = [10.0, 20.0, 40.0]
    normal_velocity = _uniform_normal_velocity(
        periodic_mesh, u, v, len(thickness)
    )
    layer_thickness = _uniform_thickness(periodic_mesh, thickness)
    speed = u if coord == 'x' else v
    for value in _line_values(periodic_mesh, coord):
        line = get_line_edges(periodic_mesh, coord, value)
        transport = compute_line_transport(
            line, normal_velocity, layer_thickness
        )
        layer_transport = transport.sum(dim='nLineEdges').values
        expected = speed * np.array(thickness) * line.attrs['length']
        np.testing.assert_allclose(layer_transport, expected, rtol=1e-12)


def test_prescribed_overturning_is_recovered(periodic_mesh):
    """
    A meridional flow v(y, z) that varies between rows, with the stream
    function Psi(y, z) prescribed at each row boundary, is recovered there
    to round-off
    """
    ds = periodic_mesh
    thickness = np.array([5.0, 10.0, 15.0, 20.0])
    z_inter = np.concatenate([[0.0], -np.cumsum(thickness)])
    x_period = ds.attrs['x_period']
    y_period = ds.attrs['y_period']

    def psi(y, z):
        return np.sin(2.0 * np.pi * y / y_period) * z * (z + z_inter[-1])

    normal = compute_edge_normal_vec(ds)
    y_edge = ds.yEdge.values
    # v = -dPsi/dz, from the change in Psi across each layer
    v_layer = (
        -(
            psi(y_edge[:, np.newaxis], z_inter[np.newaxis, :-1])
            - psi(y_edge[:, np.newaxis], z_inter[np.newaxis, 1:])
        )
        / thickness[np.newaxis, :]
    )
    normal_velocity = xr.DataArray(
        v_layer * normal.isel(R3=1).values[:, np.newaxis],
        dims=('nEdges', 'nVertLevels'),
    )
    layer_thickness = _uniform_thickness(ds, thickness)

    y_cell = np.unique(ds.yCell.values)
    for value in 0.5 * (y_cell[:-1] + y_cell[1:]):
        line = get_line_edges(ds, 'y', value)
        transport = compute_line_transport(
            line, normal_velocity, layer_thickness
        )
        overturning = compute_overturning(transport) / x_period
        np.testing.assert_allclose(
            overturning.values, psi(value, z_inter), atol=1e-12
        )


def test_overturning_is_zero_at_the_surface_and_keeps_other_dims(
    periodic_mesh,
):
    thickness = [10.0, 20.0]
    normal_velocity = _uniform_normal_velocity(
        periodic_mesh, 0.0, 0.1, len(thickness)
    )
    normal_velocity = normal_velocity.expand_dims(Time=3)
    layer_thickness = _uniform_thickness(periodic_mesh, thickness)
    layer_thickness = layer_thickness.expand_dims(Time=3)
    line = get_line_edges(periodic_mesh, 'y', 1000.0)
    transport = compute_line_transport(line, normal_velocity, layer_thickness)
    assert transport.dims == ('Time', 'nLineEdges', 'nVertLevels')
    overturning = compute_overturning(transport)
    assert overturning.dims == ('Time', 'nVertLevelsP1')
    np.testing.assert_allclose(overturning.isel(nVertLevelsP1=0), 0.0)
    length = line.attrs['length']
    np.testing.assert_allclose(
        overturning.isel(Time=0).values,
        [0.0, 0.1 * 10.0 * length, 0.1 * 30.0 * length],
        rtol=1e-12,
    )


def test_boundary_edges_are_excluded(channel_mesh):
    """
    Lines of constant x in the channel never use the cut seam, and a line
    beyond the last cell center crosses no edges.  Next to the jagged
    boundary, rows without a cell on both sides of a line contribute no
    edges, so only interior lines span the full width of the channel.
    """
    x_cell = np.unique(channel_mesh.xCell.values)
    y_period = channel_mesh.attrs['y_period']
    for value in 0.5 * (x_cell[1:-2] + x_cell[2:-1]):
        line = get_line_edges(channel_mesh, 'x', value)
        np.testing.assert_allclose(line.weight.sum(), y_period, rtol=1e-12)
    for value in [x_cell[0] - 1.0, x_cell[-1] + 1.0]:
        line = get_line_edges(channel_mesh, 'x', value)
        assert line.sizes['nLineEdges'] == 0


def test_binning_by_layer_reproduces_layer_transports(periodic_mesh):
    thickness = [10.0, 20.0, 40.0]
    normal_velocity = _uniform_normal_velocity(
        periodic_mesh, 0.0, 0.1, len(thickness)
    )
    layer_thickness = _uniform_thickness(periodic_mesh, thickness)
    line = get_line_edges(periodic_mesh, 'y', 1000.0)
    transport = compute_line_transport(line, normal_velocity, layer_thickness)
    edge_thickness = interp_cell_to_line_edges(line, layer_thickness)
    tracer = xr.ones_like(transport) * xr.DataArray(
        [0.5, 1.5, 2.5], dims=('nVertLevels',)
    )

    ds_binned = bin_line_transport(
        transport, edge_thickness, tracer, np.array([0.0, 1.0, 2.0])
    )

    # the deepest layer falls outside the bins
    np.testing.assert_allclose(
        ds_binned.transport.sum(dim='nLineEdges'),
        transport.sum(dim='nLineEdges').isel(nVertLevels=[0, 1]),
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        ds_binned.thickness.isel(nLineEdges=0), [10.0, 20.0], rtol=1e-12
    )
    np.testing.assert_allclose(ds_binned.binLower, [0.0, 1.0])


def test_bins_must_increase(periodic_mesh):
    line = get_line_edges(periodic_mesh, 'y', 1000.0)
    data = xr.zeros_like(line.weight).expand_dims(nVertLevels=1, axis=1)
    with pytest.raises(ValueError, match='monotonically increasing'):
        bin_line_transport(data, data, data, np.array([1.0, 0.0]))


def test_unknown_coordinate_is_an_error(periodic_mesh):
    with pytest.raises(ValueError, match='Unexpected line coordinate'):
        get_line_edges(periodic_mesh, 'z', 0.0)  # type: ignore[arg-type]
