"""
Tests for the rotation from Cartesian coordinates to the local tangent
plane at a vector-reconstruction point.
"""

import numpy as np
import xarray as xr

from polaris.mesh.reconstruct import construct_rotation_matrix


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
