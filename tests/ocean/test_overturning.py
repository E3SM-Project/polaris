import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.vector import compute_edge_normal_vec
from polaris.ocean.overturning import (
    bin_line_transport,
    compute_line_edge_interfaces,
    compute_line_transport,
    compute_overturning,
    compute_overturning_from_edge_transport,
    get_latitude_edges,
    get_line_edge_level_range,
    get_line_edges,
    interp_cell_to_line_edges,
)
from tests.ocean.latlon_mesh import EARTH_RADIUS, latlon_mesh

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


@pytest.fixture(scope='module')
def sphere_mesh():
    """A 10-degree latitude-longitude mesh of the sphere"""
    return latlon_mesh(dlat=10.0, dlon=10.0)


def test_a_latitude_line_crosses_the_edges_between_two_rows(sphere_mesh):
    """A line between two rows of cells, or on the northern row's centers,
    crosses the edges between the rows; its length is the parallel's"""
    line = get_latitude_edges(sphere_mesh, [0.0, 5.0, 40.0])
    assert line.sizes['nLines'] == 3
    for index, boundary in enumerate([0.0, 0.0, 40.0]):
        edges = line.lineIndex.values == index
        assert np.count_nonzero(edges) == 36
        lat_cells = np.rad2deg(
            sphere_mesh.latCell.values[line.cellsOnLineEdge.values[edges]]
        )
        assert np.all(lat_cells.min(axis=1) < line.lat.values[index])
        assert np.all(lat_cells.max(axis=1) >= line.lat.values[index])
        expected = 2.0 * np.pi * EARTH_RADIUS * np.cos(np.deg2rad(boundary))
        assert line.length.values[index] == pytest.approx(expected)


def test_latitude_line_signs_point_north(sphere_mesh):
    """An edge whose first cell is north of the line gets a negative sign"""
    ds = sphere_mesh.copy(deep=True)
    cells_on_edge = ds.cellsOnEdge.values.copy()
    cells_on_edge[::2] = cells_on_edge[::2, ::-1]
    ds['cellsOnEdge'] = (ds.cellsOnEdge.dims, cells_on_edge)
    line = get_latitude_edges(ds, [12.0])
    lat = ds.latCell.values[line.cellsOnLineEdge.values]
    northward = np.where(lat[:, 0] < lat[:, 1], 1.0, -1.0)
    np.testing.assert_array_equal(line.sign.values, northward)
    assert np.any(line.sign.values < 0.0)


def test_an_edge_crosses_every_line_between_its_cells(sphere_mesh):
    """Lines closer than the cells are tall all cross the same edges"""
    line = get_latitude_edges(sphere_mesh, [-2.5, 0.0, 2.5, 5.0, 7.5])
    edges = [
        set(line.edgeIndex.values[line.lineIndex.values == index])
        for index in range(5)
    ]
    # the first four lines are between the rows centered at 5S and 5N
    assert all(len(found) == 36 for found in edges)
    assert edges[0] == edges[1] == edges[2] == edges[3]
    assert edges[4].isdisjoint(edges[0])


def test_latitude_lines_stay_in_the_cell_mask(sphere_mesh):
    lon = np.rad2deg(sphere_mesh.lonCell.values)
    mask = lon < 90.0
    line = get_latitude_edges(sphere_mesh, [20.0], cell_mask=mask)
    assert line.sizes['nLineEdges'] == 9
    assert np.all(mask[line.cellsOnLineEdge.values])


@pytest.mark.parametrize(
    'lon_range, count',
    [((170.0, -170.0), 2), ((-170.0, 170.0), 34), ((0.0, 360.0), 36)],
)
def test_a_longitude_range_runs_east_across_any_meridian(
    sphere_mesh, lon_range, count
):
    line = get_latitude_edges(sphere_mesh, [20.0], lon_range=lon_range)
    assert line.sizes['nLineEdges'] == count


def test_latitudes_must_increase(sphere_mesh):
    with pytest.raises(ValueError, match='increasing'):
        get_latitude_edges(sphere_mesh, [10.0, 0.0])


def _fraction_form(transport, z_top, z_bottom, lines, n_lines, z):
    """The streamfunction summed directly over edges, layers and z"""
    height = (z_top - z_bottom)[..., np.newaxis]
    with np.errstate(invalid='ignore', divide='ignore'):
        fraction = np.where(
            height > 0.0,
            np.clip((z - z_bottom[..., np.newaxis]) / height, 0.0, 1.0),
            0.0,
        )
    result = np.zeros(transport.shape[:-2] + (n_lines, len(z)))
    for line in range(n_lines):
        edges = lines == line
        result[..., line, :] = -np.sum(
            transport[..., edges, :, np.newaxis] * fraction[..., edges, :, :],
            axis=(-3, -2),
        )
    return result


def test_running_sum_matches_the_fraction_form():
    """The streamfunction summed with differences along the elevations is
    the sum over edges, layers and elevations, for layers of any thickness
    including none, unsorted elevations and an extra dimension"""
    rng = np.random.default_rng(42)
    n_time, n_edges, n_levels, n_lines = 2, 60, 8, 4
    thickness = rng.uniform(0.0, 80.0, (n_time, n_edges, n_levels))
    thickness[rng.uniform(size=thickness.shape) < 0.2] = 0.0
    ssh = rng.uniform(-2.0, 1.0, (n_time, n_edges, 1))
    z_bottom = ssh - np.cumsum(thickness, axis=-1)
    z_top = z_bottom + thickness
    transport = rng.normal(size=thickness.shape) * 1.0e5
    lines = rng.integers(0, n_lines - 1, n_edges)
    z = rng.permutation(np.linspace(-700.0, 5.0, 31))

    dims = ('Time', 'nLineEdges', 'nVertLevels')
    psi = compute_overturning_from_edge_transport(
        xr.DataArray(transport, dims=dims),
        xr.DataArray(z_top, dims=dims),
        xr.DataArray(z_bottom, dims=dims),
        z,
        line_index=xr.DataArray(lines, dims=('nLineEdges',)),
        n_lines=n_lines,
        chunk_size=7,
    )
    assert psi.dims == ('Time', 'nLines', 'nZInterfaces')
    np.testing.assert_allclose(psi.zInterface.values, z)
    expected = _fraction_form(transport, z_top, z_bottom, lines, n_lines, z)
    np.testing.assert_allclose(
        psi.values, expected, rtol=0.0, atol=1.0e-9 * np.abs(expected).max()
    )
    # a line with no edges has no transport
    np.testing.assert_array_equal(psi.values[:, -1, :], 0.0)


def _two_layer_state(ds_mesh, upper, lower, thickness=100.0):
    """Northward flow in the upper layer and the lower one, layers of equal
    thickness from the sea surface, and the vertical coordinate of every
    cell"""
    lat1, lat2 = (
        ds_mesh.latCell.values[ds_mesh.cellsOnEdge.values[:, i] - 1]
        for i in range(2)
    )
    northward = np.where(lat2 > lat1, 1.0, np.where(lat2 < lat1, -1.0, 0.0))
    velocity = xr.DataArray(
        northward[:, np.newaxis] * np.array([upper, lower]),
        dims=('nEdges', 'nVertLevels'),
    )
    n_cells = ds_mesh.sizes['nCells']
    layer_thickness = xr.DataArray(
        np.full((n_cells, 2), thickness), dims=('nCells', 'nVertLevels')
    )
    z_interface = xr.DataArray(
        np.tile([0.0, -thickness, -2.0 * thickness], (n_cells, 1)),
        dims=('nCells', 'nVertLevelsP1'),
    )
    levels = xr.DataArray(np.zeros(n_cells, dtype=int), dims=('nCells',))
    return velocity, layer_thickness, z_interface, levels, levels + 1


def _latitude_overturning(ds_mesh, state, lat, z, mask=None):
    """The streamfunction across lines of latitude for a state"""
    velocity, thickness, z_interface, min_level, max_level = state
    line = get_latitude_edges(ds_mesh, lat, cell_mask=mask)
    min_edge, max_edge = get_line_edge_level_range(line, min_level, max_level)
    transport = compute_line_transport(line, velocity, thickness)
    z_top, z_bottom = compute_line_edge_interfaces(
        line, z_interface, min_edge, max_edge
    )
    return compute_overturning_from_edge_transport(
        transport,
        z_top,
        z_bottom,
        z,
        line_index=line.lineIndex,
        n_lines=len(lat),
    )


def test_northward_flow_above_southward_flow_is_positive(sphere_mesh):
    """A positive overturning is northward flow above its maximum, as the
    AMOC is"""
    u = 0.1
    state = _two_layer_state(sphere_mesh, upper=u, lower=-u)
    psi = _latitude_overturning(
        sphere_mesh, state, [0.0], [-200.0, -100.0, 0.0]
    )
    length = 2.0 * np.pi * EARTH_RADIUS
    np.testing.assert_allclose(
        psi.values[0], [0.0, u * 100.0 * length, 0.0], atol=1.0e-3
    )


def test_basins_that_tile_sum_to_the_whole(sphere_mesh):
    """Where two basins hold every edge across a latitude, their
    streamfunctions sum to that of the whole sphere"""
    rng = np.random.default_rng(7)
    state = list(_two_layer_state(sphere_mesh, upper=0.0, lower=0.0))
    state[0] = state[0].copy(data=rng.normal(size=state[0].shape) * 0.1)
    lat = np.arange(-80.0, 81.0, 5.0)
    z = np.linspace(-200.0, 0.0, 9)
    lon = np.rad2deg(sphere_mesh.lonCell.values)
    lat_cell = np.rad2deg(sphere_mesh.latCell.values)
    # a basin boundary along a meridian, so no edge across a latitude joins
    # the two basins
    west = lon < 180.0
    whole = _latitude_overturning(sphere_mesh, state, lat, z)
    parts = sum(
        _latitude_overturning(sphere_mesh, state, lat, z, mask=mask)
        for mask in (west, ~west)
    )
    np.testing.assert_allclose(
        parts.values, whole.values, atol=1.0e-6 * np.abs(whole).max()
    )
    # a basin of the northern cells has no edges across southern lines
    north = _latitude_overturning(
        sphere_mesh, state, lat, z, mask=lat_cell > 0.0
    )
    np.testing.assert_array_equal(north.values[lat <= 0.0], 0.0)


def test_edge_interfaces_collapse_outside_the_valid_layers(sphere_mesh):
    """An edge carries flow only in the layers both of its cells have, and
    reads nothing the model wrote below either sea floor"""
    line = get_latitude_edges(sphere_mesh, [0.0])
    n_cells = sphere_mesh.sizes['nCells']
    cells = line.cellsOnLineEdge.values
    z_interface = np.tile([0.0, -10.0, -30.0, -60.0], (n_cells, 1))
    # the deeper cell of the first edge has a bogus value below its floor
    z_interface[cells[0, 1], 3] = np.nan
    max_level = np.full(n_cells, 2)
    max_level[cells[0, 1]] = 1
    min_level = np.zeros(n_cells, dtype=int)
    min_edge, max_edge = get_line_edge_level_range(
        line,
        xr.DataArray(min_level, dims=('nCells',)),
        xr.DataArray(max_level, dims=('nCells',)),
    )
    assert max_edge.values[0] == 1
    z_top, z_bottom = compute_line_edge_interfaces(
        line,
        xr.DataArray(z_interface, dims=('nCells', 'nVertLevelsP1')),
        min_edge,
        max_edge,
    )
    np.testing.assert_array_equal(z_top.values[0], [0.0, -10.0, -30.0])
    np.testing.assert_array_equal(z_bottom.values[0], [-10.0, -30.0, -30.0])
    np.testing.assert_array_equal(z_bottom.values[1], [-10.0, -30.0, -60.0])
