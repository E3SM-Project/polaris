"""
Tests for the rotation from Cartesian coordinates to the local tangent
plane at a vector-reconstruction point.
"""

import numpy as np
import xarray as xr
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.reconstruct import (
    compute_reconstruction_weights,
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


def interior_cells(ds, margin):
    """
    Cells far enough from the domain edge that their two-ring stencil does
    not wrap around the periodic boundary.  A wrapped edge is a long way
    from the cell in absolute coordinates, so a field defined in those
    coordinates is discontinuous across the seam.
    """
    x, y = ds.xCell, ds.yCell
    return (
        (x > margin)
        & (x < ds.x_period - margin)
        & (y > margin)
        & (y < ds.y_period - margin)
    )


def reconstruct_planar_field(ds, u_of_edge, v_of_edge):
    """
    Reconstruct a planar vector field at cell centers from its edge-normal
    component, using weights built from the mesh itself.
    """
    weights_ds = compute_reconstruction_weights(ds, 'cell')
    normal = compute_edge_normal_vec(ds)
    normal_velocity = normal.isel(R3=0) * u_of_edge(
        ds.xEdge, ds.yEdge
    ) + normal.isel(R3=1) * v_of_edge(ds.xEdge, ds.yEdge)
    return tangential_reconstruction(
        ds,
        normal_velocity,
        stencil=weights_ds.reconstructStencilCell,
        weights=weights_ds.reconstructWeightsCell,
    )


def test_planar_reconstruction_of_uniform_field_is_exact():
    """
    A spatially uniform field must come back exactly, with no out-of-plane
    component.  An all-ones rotation matrix collapsed the local frame to a
    single direction and gave errors of order the field itself.
    """
    ds = periodic_hex_mesh()

    u_x, u_y, u_z = reconstruct_planar_field(
        ds, lambda x, y: 1.0 + 0.0 * x, lambda x, y: 0.5 + 0.0 * x
    )

    np.testing.assert_allclose(u_x.values, 1.0, atol=1e-12)
    np.testing.assert_allclose(u_y.values, 0.5, atol=1e-12)
    np.testing.assert_array_equal(u_z.values, 0.0)


def test_planar_reconstruction_of_linear_field_is_exact():
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

    u_x, u_y, _ = reconstruct_planar_field(ds, u_of, v_of)

    inside = interior_cells(ds, margin=3.0 * ds.dc)
    assert int(inside.sum()) > 0

    scale = max(abs(u_of(ds.x_period, ds.y_period)), 1.0)
    np.testing.assert_allclose(
        u_x.where(inside, u_of(ds.xCell, ds.yCell)).values,
        u_of(ds.xCell, ds.yCell).values,
        atol=1e-10 * scale,
    )
    np.testing.assert_allclose(
        u_y.where(inside, v_of(ds.xCell, ds.yCell)).values,
        v_of(ds.xCell, ds.yCell).values,
        atol=1e-10 * scale,
    )
