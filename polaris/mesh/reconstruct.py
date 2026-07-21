"""
NOTE: Intermidiate connecitity arrays are computed using the lightweight
synchronous dask scheduler to avoid the overhead of spinning up a process
pool for small integer topology data.
"""

from typing import Literal

import dask
import numpy as np
import xarray as xr
from dask.diagnostics import ProgressBar
from scipy import linalg

from polaris.mesh.vector import compute_edge_normal_vec

# TODO: when python 3.11 is dropped add type alias
ReconstructionType = Literal['cell', 'vertex']

_RECONSTRUCTION_FIELD_NAMES: dict[ReconstructionType, dict[str, str]] = {
    'cell': {
        'stencil': 'reconstructStencilCell',
        'n_edges': 'nCellReconstructEdges',
        'weights': 'reconstructWeightsCell',
    },
    'vertex': {
        'stencil': 'reconstructStencilVertex',
        'n_edges': 'nVertexReconstructEdges',
        'weights': 'reconstructWeightsVertex',
    },
}


def fix_out_of_bounds_indices(ds: xr.Dataset) -> xr.Dataset:
    """
    Replace indices larger than the dimension size in connectivity arrays with
    zeros.

    Some meshes (e.g. QU240km) don't do masking of ragged indices with zeros,
    instead they use `nInidices+1` as the invalid value.

    NOTE: Assumes connecitity array are 1-indexed

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset containing connectivity arrays

    Returns
    -------
    ds: xr.Dataset
        MPAS mesh dataset with out-of-bounds indices in connectivity arrays
        set to 0 (invalid)
    """

    def _is_connectivity_array(da: xr.DataArray) -> bool:
        # uncapitalize the name
        name = da.name[0].lower() + da.name[1:]
        is_int = da.dtype.kind in ('i', 'u')

        return 'On' in name and is_int and name.startswith(('c', 'e', 'v'))

    for var in ds:
        if _is_connectivity_array(ds[var]):
            # supports both MPASO and Omega naming conventions
            prefix = 'N' if var[0].isupper() else 'n'
            # get the dimension name for the connectivity array
            dim = prefix + var.split('On')[0].title()
            # get the maximum valid size for the array to be indexed too
            max_size = ds.sizes[dim]
            # get mask of where index is out bounds
            mask = ds[var] == max_size + 1
            # where index is out of bounds, set to invalid (i.e. 0)
            ds[var] = xr.where(mask, 0, ds[var])

    return ds


def _stencil_dim(da: xr.DataArray) -> str:
    """Infer the name of the edge-stencil dimension"""

    if 'NINE' in da.dims and 'maxEdges2' in da.dims:
        raise ValueError(
            f'Ambiguous stencil dimension: {da.dims}. '
            "Cannot have both 'NINE' and 'maxEdges2' in the same array."
        )
    elif 'NINE' not in da.dims and 'maxEdges2' not in da.dims:
        raise ValueError(
            f'Could not find stencil dimension in {da.dims}. '
            "Expected either 'NINE' or 'maxEdges2'."
        )
    else:
        return 'NINE' if 'NINE' in da.dims else 'maxEdges2'


def _unique(a, size):
    """Helper function to get the unique values and pad the rest with zeros."""

    out = np.full(size, 0, dtype=a.dtype)

    unique_values = np.unique(a.ravel())
    unique_values = unique_values[unique_values > 0]

    n = len(unique_values)

    if n > size:
        print(unique_values)
        msg = f'Too many unique values: {n} > {size}'
        raise ValueError(msg)

    out[:n] = unique_values

    return out


def construct_edgesOnVerticesOnCell(ds: xr.Dataset) -> xr.DataArray:
    """Build a stencil of the unique edges on the vertices of each cell.

    This stencil is used for cell-centered reconstruction of edge-normal vector
    field, as described by Piexoto and Barros (2014); see Figure 5(a).

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset containing the edgesOnVertex and verticesOnCell
        connectivity arrays

    Returns
    -------
    edgesOnVerticesOnCell: xr.DataArray (nCells, maxEdges2)
        Stencil of the unique edges on the vertices of each cell
    """

    maxEdges2 = ds.sizes['maxEdges2']

    ds['verticesOnCell'] = ds.verticesOnCell.compute(scheduler='sync')

    conn = ds.edgesOnVertex[ds.verticesOnCell - 1]
    conn = conn.where(ds.verticesOnCell != 0, 0)

    return xr.apply_ufunc(
        _unique,
        conn,
        kwargs={'size': maxEdges2},
        input_core_dims=[['maxEdges', 'vertexDegree']],
        output_core_dims=[['maxEdges2']],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[conn.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {'maxEdges2': maxEdges2},
        },
    ).compute(scheduler='sync')


def construct_edgesOnVerticesOnVertex(ds: xr.Dataset) -> xr.DataArray:
    """Build a stencil of the unique edges on the vertices of each vertex.

    This stencil is used for vertex-centered reconstruction of edge-normal
    vector field, as described by Piexoto and Barros (2014); see Figure
    5(b).

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset containing the edgesOnVertex and verticesOnEdge
        connectivity arrays

    Returns
    -------
    edgesOnVerticesOnVertex: xr.DataArray (nVertices, NINE)
        Stencil of the unique edges on the vertices of each vertex
    """

    vertex_degree = ds.sizes['vertexDegree']
    max_neighbors = 2 * vertex_degree
    nine = 3 * vertex_degree

    ds['edgesOnVertex'] = ds.edgesOnVertex.compute(scheduler='sync')

    # one-ring of neighboring vertices (including the vertex itself),
    conn = ds.verticesOnEdge[ds.edgesOnVertex - 1]
    conn = conn.where(ds.edgesOnVertex != 0, 0)

    neighbor_vertices = xr.apply_ufunc(
        _unique,
        conn,
        kwargs={'size': max_neighbors},
        input_core_dims=[['vertexDegree', 'TWO']],
        output_core_dims=[['maxVertexNeighbors']],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[conn.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {'maxVertexNeighbors': max_neighbors},
        },
    )

    # union of edgesOnVertex over the two-ring edge stencil for target vertex
    conn = conn.where(neighbor_vertices != 0, 0)

    return xr.apply_ufunc(
        _unique,
        conn,
        kwargs={'size': nine},
        input_core_dims=[['maxVertexNeighbors', 'vertexDegree']],
        output_core_dims=[['NINE']],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[conn.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {'NINE': nine},
        },
    ).compute(scheduler='sync')


def construct_rotation_matrix(
    ds: xr.Dataset, location: ReconstructionType = 'cell'
) -> xr.DataArray:
    """
    Construct a rotation matrix from Cartesian coordinates to local orthogonal
    projection to a tangent plane at the recoconstruction point.

    The projection is done in two steps: first a rotation about the x-axis and
    then a rotation about the y-axis.

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh containing the reconstruction-point coordinates
        (e.g. xCell/yCell/zCell or xVertex/yVertex/zVertex) and the
        sphere radius (sphere_radius) for the mesh.
    location: str ["cell", "vertex"]
        Point location where the reconstruction occurs

    Returns
    -------
    rotation_matrix: xr.DataArray (nCells or nVertices, 3, 3)
        Rotation matrix for each reconstruction point to go from
        Cartesian coordinates to local orthogonal projection, where the
        reconstruction point is (0, 0, sphere_radius) in the local
        coordinate system.
    """

    # e.g. "cell" -> "xCell", "vertex" -> "xVertex"
    prefix = location.capitalize()
    x_hat = ds[f'x{prefix}'] / ds.sphere_radius
    y_hat = ds[f'y{prefix}'] / ds.sphere_radius
    z_hat = ds[f'z{prefix}'] / ds.sphere_radius

    # infer the reconstruction-point dimension ("nCells" or "nVertices")
    # directly from the coordinate arrays, rather than hard-coding it
    point_dim = x_hat.dims[0]
    n_points = x_hat.sizes[point_dim]

    c_y = np.sqrt(y_hat**2 + z_hat**2)
    s_y = x_hat

    c_x = xr.where(c_y != 0, z_hat / c_y, 1.0)
    s_x = xr.where(c_y != 0.0, y_hat / c_y, 0.0)

    U_x = np.zeros((n_points, 3, 3))
    U_y = np.zeros((n_points, 3, 3))

    U_x[:, 0, 0] = 1.0
    U_x[:, 1, 1] = c_x
    U_x[:, 1, 2] = s_x * -1.0
    U_x[:, 2, 1] = s_x
    U_x[:, 2, 2] = c_x

    U_y[:, 0, 0] = c_y
    U_y[:, 0, 2] = s_y * -1.0
    U_y[:, 1, 1] = 1.0
    U_y[:, 2, 0] = s_y
    U_y[:, 2, 2] = c_y

    # preserve existing chunking along point_dim. If None; use a single chunk
    point_chunks = ds.chunksizes.get(point_dim, -1)

    return xr.DataArray(
        np.matmul(U_y, U_x), dims=(point_dim, 'd1', 'd2')
    ).chunk({point_dim: point_chunks, 'd1': -1, 'd2': -1})


def project_edge_normal_to_tangent_plane(
    normal_vector: xr.DataArray,
    rotation_matrix: xr.DataArray,
    stencil: xr.DataArray,
) -> xr.DataArray:
    """ "

    Parameters
    ----------
    normal_vector : xr.DataArray (nEdges, 3)
        Normal vector in Cartesian coordinates for each edge in the mesh
    rotation_matrix: np.ndarray (nCells or nVertices, 3, 3)
        Rotation matrix from Cartesian to local orthogonal projection to a
        tangent plane at the reconstruction point
    stencil: xr.DataArray (nCells or nVertices, maxEdges2 or NINE)
        Indices of the unique edges on the vertices of each reconstruction
        point. Produces a larger footprint stencil than just edges on cell
        (or edges on vertex)
    """

    stencil_dim = _stencil_dim(stencil)
    stencil_size = stencil.sizes[stencil_dim]

    # get the edge normal vector for the edges in the stencil
    edge_normal_vector = normal_vector.isel(nEdges=stencil - 1)

    return xr.apply_ufunc(
        lambda U, n: np.einsum('lg,eg->el', U, n),
        rotation_matrix,
        edge_normal_vector,
        input_core_dims=[['d1', 'd2'], [stencil_dim, 'R3']],
        output_core_dims=[[stencil_dim, 'R3']],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[edge_normal_vector.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {stencil_dim: stencil_size, 'R3': 3},
        },
    )


def compute_lstsq_weights(
    local_edge_coords: xr.DataArray,
    stencil: xr.DataArray,
    sphere_radius: float,
) -> xr.DataArray:
    """
    Compute the least squares weights as described by Renka (1984) pg. 422.

    Parameters
    ----------
    local_edge_coords: xr.DataArray (nCells or nVertices, maxEdges2/NINE, R3)
        Edge coordinate vectors projected onto the local tangent plane at the
        the reconstruction point
    stencil: xr.DataArray (nCells or nVertices, maxEdges2 or NINE)
        A two level stencil of edges neighboring the reconstruction point
    sphere_radius: float
        Radius of the sphere for the mesh

    Returns
    -------
    weights: xr.DataArray (nCells or nVertices, maxEdges2 or NINE)
        Least squares weights for each edge in the stencil
    """
    stencil_dim = _stencil_dim(stencil)
    valid = stencil != 0

    # normalize the rotated z coord onto the unit sphere to match Renka (1984)
    # z_hat = 1 at reconstruction point and decreases with increasing angular
    # distance from the reconstruction point.
    z_hat = local_edge_coords.isel(R3=2) / sphere_radius

    if bool((z_hat.where(valid) < 0).any()):
        raise ValueError(
            'A stencil edge has been rotated into the lower hemisphere of the'
            'local tangent plane. This is not expexted for realistic MPAS mesh'
            'resolution; check for degenerate or high distorted cells'
        )

    D = xr.where(valid, 1.0 - z_hat, np.nan)

    # Unlike Renka (1984) we use a static stencil, so R_k is set to the
    # maximum distance of the stencil edges from the reconstruction
    # point, plus a small epsilon to avoid divide by zero errors
    R = D.max(dim=stencil_dim, skipna=True) * (1 + 1.0e-3)

    w = 1.0 / D - 1.0 / R

    return xr.where(valid, w, 0.0)


def rotate_local_to_cartesian(
    rotation_matrix: xr.DataArray,
    weights: xr.DataArray,
) -> xr.DataArray:
    """
    Rotate the reconstruction weights from the local tangent-plane frame
    back to Cartesian coordinates, by applying the inverse (i.e. transpose)
    of the rotation matrix.

    Parameters
    ----------
    rotation_matrix: xr.DataArray (nCells or nVertices, d1, d2)
        Rotation matrix from Cartesian to local orthogonal projection to a
        tangent plane at the reconstruction point, as produced by
        ``construct_rotation_matrix``
    weights: xr.DataArray (nCells or nVertices, R3, maxEdges2 or NINE)
        Reconstruction weights in the local tangent-plane frame

    Returns
    -------
    weights: xr.DataArray (nCells or nVertices, R3, maxEdges2 or NINE)
        Reconstruction weights rotated into Cartesian coordinates
    """
    stencil_dim = _stencil_dim(weights)

    return xr.apply_ufunc(
        lambda U, w: np.einsum('lg,le->ge', U, w),
        rotation_matrix,
        weights,
        input_core_dims=[['d1', 'd2'], ['R3', stencil_dim]],
        output_core_dims=[['R3', stencil_dim]],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[weights.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {'R3': 3, stencil_dim: weights.sizes[stencil_dim]},
        },
    )


def solve_psuedo_inverse(M: xr.DataArray) -> xr.DataArray:
    """
    Solve the batched pseudo-inverse of a matrix M using scipy.linalg.pinv

    Will parallelize over the reconstruction-point dimension if M is a
    dask array and chunked along said dimension.

    Parameters
    ----------
    M : xr.DataArray (nCells or nVertices, maxEdges2 or NINE, SIX)
        Matrix to be inverted

    Returns
    -------
    M_inv : xr.DataArray (nCells or nVertices, SIX, maxEdges2 or NINE)
        Pseudo-inverse of M
    """
    stencil_dim = _stencil_dim(M)

    return xr.apply_ufunc(
        linalg.pinv,
        M,
        input_core_dims=[[stencil_dim, 'SIX']],
        output_core_dims=[['SIX', stencil_dim]],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[M.dtype],
        dask_gufunc_kwargs={
            'output_sizes': {'SIX': 6, stencil_dim: M.sizes[stencil_dim]},
        },
    )


def build_reconstruction_weights(
    ds: xr.Dataset,
    location: ReconstructionType = 'cell',
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Build the reconstruction weights for each reconstruction point in the
    mesh.

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset
    location: str ["cell", "vertex"]
        Point location where the reconstruction occurs

    Returns
    -------
    stencil: xr.DataArray (nCells or nVertices, maxEdges2 or NINE)
        Edge stencil for each reconstruction point

    weights: xr.DataArray (nCells or nVertices, R3, maxEdges2 or NINE)
        Reconstruction weights for each reconstruction point
    """
    if location == 'cell':
        stencil = construct_edgesOnVerticesOnCell(ds)
    elif location == 'vertex':
        stencil = construct_edgesOnVerticesOnVertex(ds)
    else:
        raise ValueError(
            f"Invalid location: {location}. Must be 'cell' or 'vertex'."
        )

    rotation_matrix = construct_rotation_matrix(ds, location)

    # compute the normal vector for each edge in Cartesian coordinates
    cartesian_normal_vector = compute_edge_normal_vec(ds)
    # build the edge coord vec (nEdges, R3), w/ single chunk along the R3 dim
    cartesian_edge_coords = xr.concat(
        [ds.xEdge, ds.yEdge, ds.zEdge], dim='R3'
    ).T.chunk({'R3': -1})

    # project the normal vector onto the tangent plane at the cell center
    local_normal_vector = project_edge_normal_to_tangent_plane(
        cartesian_normal_vector, rotation_matrix, stencil
    )
    # project the edge coordinate vectors onto the local tangent plane
    local_edge_coords = project_edge_normal_to_tangent_plane(
        cartesian_edge_coords, rotation_matrix, stencil
    )

    # weight the LSTSQ matrix following Renka (1984) pg. 422
    w = compute_lstsq_weights(local_edge_coords, stencil, ds.sphere_radius)

    # Build Eqn. 20 from Piexoto and Barros (2014)
    matrix = xr.concat(
        [local_normal_vector.isel(R3=[0, 1])] * 3, dim='R3'
    ).rename({'R3': 'SIX'})

    # We just want to parallelize over the reconstruction point dimension
    # so we set a single chunk along all other dimensions
    stencil_dim = _stencil_dim(stencil)
    matrix = matrix.chunk({'SIX': -1, stencil_dim: -1})

    matrix.loc[{'SIX': [2, 3]}] *= local_edge_coords.isel(R3=0)
    matrix.loc[{'SIX': [4, 5]}] *= local_edge_coords.isel(R3=1)

    # replace the out of bounds values with zeros
    matrix = matrix.where(stencil != 0, 0.0)

    # apply the weights to the matrix
    matrix *= np.sqrt(w)
    # solve pseudo-inverse of the matrix to get the reconstruction weights
    weights = solve_psuedo_inverse(matrix)
    weights *= np.sqrt(w)

    # Becuase we only support reconstruction at the reconstruction points
    # (i.e. cell or vertex centers) we only need to keep the first two rows
    # of the weights matrix. But that will produce a vector reconstructed on
    # the tangent plane. So, we keep an extra column of the weights matrix,
    # and assume the z component to be zero, in order to be able to apply the
    # inverse of 3x3 rotation matrix resiluting in a catesian vector
    weights = weights.isel(SIX=[0, 1, 2]).rename({'SIX': 'R3'})
    weights.loc[{'R3': 2}] = 0.0

    weights = rotate_local_to_cartesian(rotation_matrix, weights)

    return stencil, weights


def tangential_reconstruction(
    ds: xr.Dataset,
    edge_normal_field: xr.DataArray,
    stencil: xr.DataArray | None = None,
    weights: xr.DataArray | None = None,
    location: ReconstructionType | None = None,
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Reconstruct a tangential vector field from an edge-normal vector field.

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset

    edge_normal_field: xr.DataArray (nEdges, ...)
        Scalar field defined normal to each edge (e.g. ``normalVelocity``).
        May include additional dimensions besides ``nEdges`` (e.g.
        ``nVertLevels``, ``Time``); these are carried through unchanged.

    stencil: xr.DataArray (nCells or nVertices, maxEdges2 or NINE), optional
        Precomputed edge stencil for each reconstruction point. If not
        provided (along with ``weights``), it is built from ``ds`` using
        ``location``.

    weights: xr.DataArray (nCells or nVertices, R3, maxEdges2/NINE), optional
        Precomputed reconstruction weights for each reconstruction point.
        If not provided (along with ``stencil``), it is built from ``ds``
        using ``location``.

    location: str ["cell", "vertex"], optional
        Point location where the reconstruction occurs. Required if
        ``stencil`` and ``weights`` are not both provided.

    Returns
    -------
    u_x: xr.DataArray (nCells or nVertices, ...)
        Reconstructed x-component of the tangential vector field
    u_y: xr.DataArray (nCells or nVertices, ...)
        Reconstructed y-component of the tangential vector field
    u_z: xr.DataArray (nCells or nVertices, ...)
        Reconstructed z-component of the tangential vector field
    """
    if stencil is None or weights is None:
        if location is None:
            raise ValueError(
                'If stencil and weights are not provided, location must be '
                'provided to build the reconstruction weights.'
            )
        stencil, weights = build_reconstruction_weights(ds, location)

    stencil_dim = _stencil_dim(stencil)
    valid = stencil != 0

    # gather the field values onto the stencil edges; padded entries
    # (stencil == 0) are redirected to edge 0 to avoid wrapping around to
    # the last edge via a "-1" index, then masked out immediately below
    field_on_stencil = edge_normal_field.isel(
        nEdges=stencil.where(valid, 1) - 1
    )
    field_on_stencil = field_on_stencil.where(valid, 0.0)

    # weights and field_on_stencil share the stencil and reconstruction
    # point dimensions by name, so `xr.dot` contracts over the stencil dim
    # and broadcasts over R3 and any extra dims (e.g. nVertLevels, Time)
    # regardless of whether the reconstruction point is a cell or vertex
    reconstructed = xr.dot(weights, field_on_stencil, dims=stencil_dim)

    return (
        reconstructed.isel(R3=0),
        reconstructed.isel(R3=1),
        reconstructed.isel(R3=2),
    )


def cartesian_to_local_geographic(
    ds: xr.Dataset, u_x: xr.DataArray, u_y: xr.DataArray, u_z: xr.DataArray
) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Convert a vector field from Cartesian coordinates to local geographic
    coordinates (zonal, meridional, radial) at the reconstruction point.

    Parameters
    ----------
    ds: xr.Dataset
        mesh dataset containing geographic coordinates of reconstruction
        points
    u_x: xr.DataArray (nCells or nVertices)
        x-component of the vector field in Cartesian coordinates
    u_y: xr.DataArray (nCells or nVertices)
        y-component of the vector field in Cartesian coordinates
    u_z: xr.DataArray (nCells or nVertices)
        z-component of the vector field in Cartesian coordinates

    Returns
    -------
    u_zonal: xr.DataArray (nCells or nVertices)
        Zonal component of the vec field in local geographic coordinates
    u_merid: xr.DataArray (nCells or nVertices)
        Meridional component of the vec field in local geographic coordinates
    u_radial: xr.DataArray (nCells or nVertices)
        Radial component of the vec field in local geographic coordinates
    """
    # infer whether these are cell- or vertex-centered values from the
    # dimensions of u_x, rather than requiring a separate location arg
    if 'nCells' in u_x.dims:
        lon, lat = ds.lonCell, ds.latCell
    elif 'nVertices' in u_x.dims:
        lon, lat = ds.lonVertex, ds.latVertex
    else:
        raise ValueError(
            'Could not infer the reconstruction point location from '
            f"the dimensions of u_x: {u_x.dims}. Expected 'nCells' or "
            "'nVertices'."
        )

    clon = np.cos(lon)
    slon = np.sin(lon)
    clat = np.cos(lat)
    slat = np.sin(lat)

    u_zonal = -u_x * slon + u_y * clon
    # horizontal is the component of the vector in the equatorial plane,
    # i.e. before it is split into meridional and radial parts
    horizontal = u_x * clon + u_y * slon
    u_merid = -horizontal * slat + u_z * clat
    u_radial = horizontal * clat + u_z * slat

    return u_zonal, u_merid, u_radial


def compute_reconstruction_weights(
    ds: xr.Dataset, location: ReconstructionType = 'cell'
) -> xr.Dataset:
    """
    Compute the weights and stencil indices needed for recoconstruction
    a edge normal vector field at cell or vertex centers

    Parameters
    ----------
    ds: xr.Dataset
        MPAS mesh dataset
    location: str ["cell", "vertex"]
        Point location where the reconstruction occurs

    Returns
    -------
    ds: xr.Dataset
        A minimal dataset containing the reconstruction stencil, edge-count,
        and coefficent fields for the requeste reconstruction point location.
    """

    names = _RECONSTRUCTION_FIELD_NAMES[location]

    if names['weights'] in ds:
        print(
            f"Warning: overwriting existing '{names['weights']}' field "
            'in the mesh dataset.'
        )

    # For stencil creation to work all indices in the connectivity arrays must
    # [0, dim_size], where 0 is the invalid index sentinel
    ds = fix_out_of_bounds_indices(ds)

    stencil, weights = build_reconstruction_weights(ds, location)

    stencil_dim = _stencil_dim(stencil)
    n_edges = (stencil != 0).sum(dim=stencil_dim).astype(stencil.dtype)

    stencil = _add_reconstruct_attrs(
        stencil, 'edge stencil used to reconstruct a vector'
    )
    n_edges = _add_reconstruct_attrs(
        n_edges, 'number of edges in the reconstruction stencil'
    )
    weights = _add_reconstruct_attrs(
        weights,
        'weights used to reconstruct a Cartesian vector from '
        'edge-normal values on the reconstruction stencil',
        units='unitless',
    )

    with ProgressBar():
        stencil, n_edges, weights = dask.compute(stencil, n_edges, weights)

    return xr.Dataset(
        {
            names['stencil']: stencil,
            names['n_edges']: n_edges,
            names['weights']: weights,
        }
    )


def add_reconstruction_weights_to_dataset(
    ds_mesh: xr.Dataset,
    location: ReconstructionType = 'cell',
) -> xr.Dataset:
    """
    Add vector-reconstruction stencil and weight fields to a mesh dataset.

    Parameters
    ----------
    ds_mesh: xr.Dataset
        The mesh dataset to update

    location: str ["cell", "vertex"]
        Point location where the reconstruction occurs

    Returns
    -------
    xr.Dataset
        The updated dataset with reconstruction stencil, edge-count, and
        coefficient fields whose names depend on ``location`` (see
        ``_RECONSTRUCTION_FIELD_NAMES``)
    """

    weights_ds = compute_reconstruction_weights(ds_mesh, location)

    return ds_mesh.merge(weights_ds)


def _add_reconstruct_attrs(
    data_array: xr.DataArray, long_name: str, units: str | None = None
) -> xr.DataArray:
    attrs = {'long_name': long_name}
    if units is not None:
        attrs['units'] = units
    data_array.attrs.update(attrs)
    return data_array
