"""
Tests for the rotation from Cartesian coordinates to the local tangent
plane at a vector-reconstruction point.
"""

import numpy as np
import pytest
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.reconstruct import (
    compute_reconstruction_weights,
    construct_edgesOnVerticesOnVertex,
    construct_rotation_matrix,
    tangential_reconstruction,
)
from polaris.mesh.vector import compute_edge_normal_vec


def planar_mesh(n_cells=4):
    """A minimal planar mesh with the coordinates the rotation needs."""
    x = np.linspace(0.0, 3.0e4, n_cells)
    ds = xr.Dataset(
        {
            'xCell': ('nCells', x),
            'yCell': ('nCells', x[::-1].copy()),
            'zCell': ('nCells', np.zeros(n_cells)),
        }
    )
    # planar MPAS meshes carry a sphere radius of zero
    ds.attrs['on_a_sphere'] = 'NO'
    ds.attrs['sphere_radius'] = 0.0
    return ds


def spherical_mesh():
    """A minimal spherical mesh spanning a range of latitudes."""
    radius = 6.371e6
    lat = np.deg2rad(np.array([-80.0, -25.0, 0.0, 25.0, 80.0]))
    lon = np.deg2rad(np.array([0.0, 45.0, 120.0, 200.0, 330.0]))
    ds = xr.Dataset(
        {
            'xCell': ('nCells', radius * np.cos(lat) * np.cos(lon)),
            'yCell': ('nCells', radius * np.cos(lat) * np.sin(lon)),
            'zCell': ('nCells', radius * np.sin(lat)),
        }
    )
    ds.attrs['on_a_sphere'] = 'YES'
    ds.attrs['sphere_radius'] = radius
    return ds


def test_planar_rotation_matrix_is_identity():
    """
    A planar mesh already lies in the x-y plane, so the rotation to the
    tangent plane must be the identity.  An all-ones matrix would collapse
    the local frame to a single direction and silently produce wrong
    reconstruction weights.
    """
    ds = planar_mesh()
    rotation = construct_rotation_matrix(ds, 'cell')

    assert rotation.dims == ('nCells', 'd1', 'd2')

    expected = np.broadcast_to(np.eye(3), (ds.sizes['nCells'], 3, 3))
    np.testing.assert_array_equal(rotation.values, expected)


def test_planar_rotation_leaves_in_plane_vector_unchanged():
    """The planar rotation must be a no-op on a vector in the mesh plane."""
    ds = planar_mesh()
    rotation = construct_rotation_matrix(ds, 'cell').values

    vector = np.array([1.0, 0.5, 0.0])
    for cell in range(ds.sizes['nCells']):
        np.testing.assert_allclose(rotation[cell] @ vector, vector)


def test_planar_rotation_does_not_divide_by_zero():
    """
    Planar meshes have sphere_radius of zero, so the rotation must not
    normalize the coordinates by it.
    """
    ds = planar_mesh()
    with np.errstate(divide='raise', invalid='raise'):
        rotation = construct_rotation_matrix(ds, 'cell')

    assert np.isfinite(rotation.values).all()


def test_spherical_rotation_matrix_is_orthogonal():
    """
    The spherical rotation is a product of two rotations about the x and y
    axes, so it must be orthogonal at every reconstruction point.
    """
    ds = spherical_mesh()
    rotation = construct_rotation_matrix(ds, 'cell').values

    for cell in range(ds.sizes['nCells']):
        np.testing.assert_allclose(
            rotation[cell] @ rotation[cell].T, np.eye(3), atol=1e-12
        )


def periodic_hex_mesh(nx=12, ny=12, dc=1000.0):
    """A small doubly periodic planar hex mesh with full connectivity."""
    return make_planar_hex_mesh(
        nx=nx, ny=ny, dc=dc, nonperiodic_x=False, nonperiodic_y=False
    )


def point_coords(ds, location):
    """The x and y coordinates of the reconstruction points."""
    suffix = location.capitalize()
    return ds[f'x{suffix}'], ds[f'y{suffix}']


def interior_points(ds, margin, location='cell'):
    """
    Reconstruction points far enough from the domain edge that their
    two-ring stencil does not wrap around the periodic boundary.  A wrapped
    edge is a long way from the point in absolute coordinates, so a field
    defined in those coordinates is discontinuous across the seam.
    """
    x, y = point_coords(ds, location)
    return (
        (x > margin)
        & (x < ds.x_period - margin)
        & (y > margin)
        & (y < ds.y_period - margin)
    )


def reconstruct_planar_field(ds, u_of_edge, v_of_edge, location='cell'):
    """
    Reconstruct a planar vector field at cell or vertex centers from its
    edge-normal component, using weights built from the mesh itself.
    """
    suffix = location.capitalize()
    weights_ds = compute_reconstruction_weights(ds, location)
    normal = compute_edge_normal_vec(ds)
    normal_velocity = normal.isel(R3=0) * u_of_edge(
        ds.xEdge, ds.yEdge
    ) + normal.isel(R3=1) * v_of_edge(ds.xEdge, ds.yEdge)
    return tangential_reconstruction(
        ds,
        normal_velocity,
        stencil=weights_ds[f'reconstructStencil{suffix}'],
        weights=weights_ds[f'reconstructWeights{suffix}'],
    )


@pytest.mark.parametrize('location', ['cell', 'vertex'])
def test_planar_reconstruction_of_uniform_field_is_exact(location):
    """
    A spatially uniform field must come back exactly, with no out-of-plane
    component.  An all-ones rotation matrix collapsed the local frame to a
    single direction and gave errors of order the field itself.
    """
    ds = periodic_hex_mesh()

    u_x, u_y, u_z = reconstruct_planar_field(
        ds,
        lambda x, y: 1.0 + 0.0 * x,
        lambda x, y: 0.5 + 0.0 * x,
        location=location,
    )

    np.testing.assert_allclose(u_x.values, 1.0, atol=1e-12)
    np.testing.assert_allclose(u_y.values, 0.5, atol=1e-12)
    np.testing.assert_array_equal(u_z.values, 0.0)


@pytest.mark.parametrize('location', ['cell', 'vertex'])
def test_planar_reconstruction_of_linear_field_is_exact(location):
    """
    The least-squares basis includes the linear terms, so a linear field
    must also come back exactly.  It does so only if the local edge
    coordinates are relative to the reconstruction point; in absolute
    coordinates the fit is anchored at the mesh origin and returns the
    field extrapolated there instead.
    """
    ds = periodic_hex_mesh()

    def u_of(x, y):
        return 0.2 + 1.3e-3 * x - 0.7e-3 * y

    def v_of(x, y):
        return -1.1 + 0.4e-3 * x + 2.0e-3 * y

    u_x, u_y, _ = reconstruct_planar_field(ds, u_of, v_of, location=location)

    inside = interior_points(ds, margin=3.0 * ds.dc, location=location)
    assert int(inside.sum()) > 0

    x, y = point_coords(ds, location)
    scale = max(abs(u_of(ds.x_period, ds.y_period)), 1.0)
    np.testing.assert_allclose(
        u_x.where(inside, u_of(x, y)).values,
        u_of(x, y).values,
        atol=1e-10 * scale,
    )
    np.testing.assert_allclose(
        u_y.where(inside, v_of(x, y)).values,
        v_of(x, y).values,
        atol=1e-10 * scale,
    )


def test_vertex_stencil_holds_edges_not_vertices():
    """
    The vertex stencil is the union of edgesOnVertex over the one-ring of
    neighboring vertices.  Gathering that union from the wrong connectivity
    array filled the stencil with vertex indices and leaked the TWO
    dimension of verticesOnEdge into the result.
    """
    ds = periodic_hex_mesh()

    stencil = construct_edgesOnVerticesOnVertex(ds)

    assert stencil.dims == ('nVertices', 'NINE')
    assert int(stencil.max()) <= ds.sizes['nEdges']

    # every hex vertex has three edges of its own plus six more from its
    # three neighbors, so the two-ring stencil is full
    np.testing.assert_array_equal(
        (stencil != 0).sum(dim='NINE').values, ds.sizes['vertexDegree'] * 3
    )

    # a vertex's own edges are always part of its stencil
    for vertex in range(ds.sizes['nVertices']):
        own = set(ds.edgesOnVertex.isel(nVertices=vertex).values.tolist())
        assert own <= set(stencil.isel(nVertices=vertex).values.tolist())


@pytest.mark.parametrize('location', ['cell', 'vertex'])
def test_reconstruction_weights_have_expected_dims(location):
    """
    Trimming the mesh to the variables needed for reconstruction must keep
    the dimensions of every connectivity array reachable.  Dropping the cell
    coordinates from the vertex list left nCells undefined, so bounds
    checking cellsOnEdge raised a KeyError.
    """
    ds = periodic_hex_mesh()
    suffix = location.capitalize()
    point_dim = 'nCells' if location == 'cell' else 'nVertices'
    stencil_dim = 'maxEdges2' if location == 'cell' else 'NINE'

    weights_ds = compute_reconstruction_weights(ds, location)

    assert weights_ds[f'reconstructStencil{suffix}'].dims == (
        point_dim,
        stencil_dim,
    )
    assert weights_ds[f'nEdgesReconstructOn{suffix}'].dims == (point_dim,)
    assert weights_ds[f'reconstructWeights{suffix}'].dims == (
        point_dim,
        'R3',
        stencil_dim,
    )
