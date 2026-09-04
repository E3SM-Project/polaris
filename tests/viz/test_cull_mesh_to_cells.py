"""
Unit tests for culling a mesh down to the cells that are being plotted.

Selecting cells with ``isel(nCells=...)`` leaves the connectivity arrays
pointing at cells that are no longer there, and mosaic indexes them out of
bounds when it culls the mesh again for the projection.  These check that the
culled mesh is self-consistent and that mosaic will accept it.
"""

import cartopy.crs as ccrs
import mosaic
import numpy as np
import pytest
import xarray as xr

from polaris.viz.spherical import _CONNECTIVITY_ARRAYS, _cull_mesh_to_cells


def test_the_connectivity_arrays_match_mosaic():
    """Mosaic remaps a fixed set of arrays; ours has to be the same set."""
    from mosaic.descriptor import connectivity_arrays

    assert sorted(_CONNECTIVITY_ARRAYS) == sorted(connectivity_arrays)


def test_culling_keeps_the_cells_asked_for():
    mesh_ds = _quad_mesh_dataset(4, 4)
    cell_indices = np.array([5, 6, 9, 10])

    culled_ds = _cull_mesh_to_cells(mesh_ds, cell_indices)

    assert culled_ds.sizes['nCells'] == cell_indices.size
    np.testing.assert_allclose(
        culled_ds.latCell.values, mesh_ds.latCell.values[cell_indices]
    )
    np.testing.assert_allclose(
        culled_ds.lonCell.values, mesh_ds.lonCell.values[cell_indices]
    )


def test_culling_drops_the_edges_and_vertices_left_behind():
    mesh_ds = _quad_mesh_dataset(4, 4)

    culled_ds = _cull_mesh_to_cells(mesh_ds, np.array([5, 6, 9, 10]))

    assert culled_ds.sizes['nEdges'] < mesh_ds.sizes['nEdges']
    assert culled_ds.sizes['nVertices'] < mesh_ds.sizes['nVertices']


def test_no_connectivity_index_points_outside_the_culled_mesh():
    """The invariant that ``isel(nCells=...)`` on its own breaks."""
    mesh_ds = _quad_mesh_dataset(4, 4)

    culled_ds = _cull_mesh_to_cells(mesh_ds, np.array([5, 6, 9, 10]))

    for array_name in _CONNECTIVITY_ARRAYS:
        dim = 'n' + array_name.split('On')[0].title()
        indices = culled_ds[array_name].values
        assert indices.max() <= culled_ds.sizes[dim], array_name


@pytest.mark.parametrize(
    'projection_name', ['PlateCarree', 'NorthPolarStereo']
)
def test_mosaic_accepts_the_culled_mesh(projection_name):
    """Handing mosaic the uncut mesh subset raises IndexError instead."""
    mesh_ds = _quad_mesh_dataset(4, 4)
    cell_indices = np.array([5, 6, 9, 10])

    culled_ds = _cull_mesh_to_cells(mesh_ds, cell_indices)
    descriptor = mosaic.Descriptor(
        culled_ds,
        projection=getattr(ccrs, projection_name)(),
        transform=ccrs.Geodetic(),
        use_latlon=True,
    )

    assert descriptor.sizes['nCells'] == cell_indices.size
    assert mosaic.utils.get_invalid_patches(descriptor.cell_patches) is None


def _quad_mesh_dataset(nx, ny):
    """
    An ``nx`` by ``ny`` mesh of quadrilateral cells, one degree on a side,
    with the connectivity arrays mosaic needs.  Cells are numbered in row
    order, and a missing neighbor is marked with zero, as MPAS does.
    """
    lon_vertex, lat_vertex = np.meshgrid(
        np.arange(nx + 1, dtype=float), np.arange(ny + 1, dtype=float)
    )

    def vertex(i, j):
        return j * (nx + 1) + i + 1

    def cell(i, j):
        inside = (0 <= i < nx) and (0 <= j < ny)
        return j * nx + i + 1 if inside else 0

    # horizontal edges first, then vertical ones
    def horiz_edge(i, j):
        inside = (0 <= i < nx) and (0 <= j < ny + 1)
        return j * nx + i + 1 if inside else 0

    def vert_edge(i, j):
        inside = (0 <= i < nx + 1) and (0 <= j < ny)
        return nx * (ny + 1) + j * (nx + 1) + i + 1 if inside else 0

    lon_cell, lat_cell = [], []
    vertices_on_cell = []
    for j in range(ny):
        for i in range(nx):
            lon_cell.append(i + 0.5)
            lat_cell.append(j + 0.5)
            vertices_on_cell.append(
                [
                    vertex(i, j),
                    vertex(i + 1, j),
                    vertex(i + 1, j + 1),
                    vertex(i, j + 1),
                ]
            )

    lon_edge, lat_edge = [], []
    cells_on_edge, vertices_on_edge = [], []
    for j in range(ny + 1):
        for i in range(nx):
            lon_edge.append(i + 0.5)
            lat_edge.append(float(j))
            cells_on_edge.append([cell(i, j - 1), cell(i, j)])
            vertices_on_edge.append([vertex(i, j), vertex(i + 1, j)])
    for j in range(ny):
        for i in range(nx + 1):
            lon_edge.append(float(i))
            lat_edge.append(j + 0.5)
            cells_on_edge.append([cell(i - 1, j), cell(i, j)])
            vertices_on_edge.append([vertex(i, j), vertex(i, j + 1)])

    cells_on_vertex, edges_on_vertex = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            cells_on_vertex.append(
                [
                    cell(i - 1, j - 1),
                    cell(i, j - 1),
                    cell(i, j),
                    cell(i - 1, j),
                ]
            )
            edges_on_vertex.append(
                [
                    horiz_edge(i - 1, j),
                    horiz_edge(i, j),
                    vert_edge(i, j - 1),
                    vert_edge(i, j),
                ]
            )

    mesh_ds = xr.Dataset(
        {
            'latCell': ('nCells', np.deg2rad(lat_cell)),
            'lonCell': ('nCells', np.deg2rad(lon_cell)),
            'latEdge': ('nEdges', np.deg2rad(lat_edge)),
            'lonEdge': ('nEdges', np.deg2rad(lon_edge)),
            'latVertex': ('nVertices', np.deg2rad(lat_vertex.ravel())),
            'lonVertex': ('nVertices', np.deg2rad(lon_vertex.ravel())),
            'verticesOnCell': (
                ('nCells', 'maxEdges'),
                np.array(vertices_on_cell),
            ),
            'cellsOnEdge': (('nEdges', 'TWO'), np.array(cells_on_edge)),
            'verticesOnEdge': (('nEdges', 'TWO'), np.array(vertices_on_edge)),
            'cellsOnVertex': (
                ('nVertices', 'vertexDegree'),
                np.array(cells_on_vertex),
            ),
            'edgesOnVertex': (
                ('nVertices', 'vertexDegree'),
                np.array(edges_on_vertex),
            ),
        }
    )
    mesh_ds.attrs['on_a_sphere'] = 'YES'
    mesh_ds.attrs['sphere_radius'] = 6371229.0
    mesh_ds.attrs['is_periodic'] = 'NO'
    return mesh_ds
