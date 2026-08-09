import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.mesh.spherical.quality import check_cell_polygon_quality


def test_cell_polygon_quality_accepts_regular_hexagon():
    ds_mesh = _cell_polygon_mesh_dataset(
        np.array(
            [
                [1.0, 0.0, 0.0],
                [0.5, np.sqrt(3.0) / 2.0, 0.0],
                [-0.5, np.sqrt(3.0) / 2.0, 0.0],
                [-1.0, 0.0, 0.0],
                [-0.5, -np.sqrt(3.0) / 2.0, 0.0],
                [0.5, -np.sqrt(3.0) / 2.0, 0.0],
            ]
        )
    )

    diagnostics = check_cell_polygon_quality(
        ds_mesh=ds_mesh,
        minimum_edge_length_ratio=1.0e-4,
        minimum_corner_sine=1.0e-3,
        max_bad_cells_to_report=10,
    )

    np.testing.assert_allclose(diagnostics['minimum_edge_length_ratio'], 1.0)
    np.testing.assert_allclose(
        diagnostics['minimum_corner_sine'], np.sqrt(3.0) / 2.0
    )


def test_cell_polygon_quality_rejects_short_edge():
    nearly_duplicate_vertex = np.array([1.0, 1.0e-8, 0.0])
    ds_mesh = _cell_polygon_mesh_dataset(
        np.array(
            [
                [1.0, 0.0, 0.0],
                nearly_duplicate_vertex,
                [-0.5, np.sqrt(3.0) / 2.0, 0.0],
                [-1.0, 0.0, 0.0],
                [-0.5, -np.sqrt(3.0) / 2.0, 0.0],
                [0.5, -np.sqrt(3.0) / 2.0, 0.0],
            ]
        )
    )

    with pytest.raises(ValueError, match='nCell=1'):
        check_cell_polygon_quality(
            ds_mesh=ds_mesh,
            minimum_edge_length_ratio=1.0e-4,
            minimum_corner_sine=1.0e-3,
            max_bad_cells_to_report=10,
        )


def test_cell_polygon_quality_rejects_collinear_corner():
    ds_mesh = _cell_polygon_mesh_dataset(
        np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [2.0, 1.0, 0.0],
                [1.0, 2.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        )
    )

    with pytest.raises(ValueError, match='min_corner_sine=0.000e\\+00'):
        check_cell_polygon_quality(
            ds_mesh=ds_mesh,
            minimum_edge_length_ratio=1.0e-4,
            minimum_corner_sine=1.0e-3,
            max_bad_cells_to_report=10,
        )


def test_shipped_edge_length_ratio_clears_the_river_constraint_floor():
    """
    Unified meshes pin mesh vertices on river-network line constraints,
    which drives land cell polygons down to 2.2e-4 to 5.1e-4 on
    u.oi6to18.lr6to10 and u.oi30.lr10.  The guard has to sit well below
    that floor, since it drifts lower as meshes get finer, while staying
    far above genuine degeneracy.
    """
    config = PolarisConfigParser()
    config.add_from_package('polaris.mesh.spherical', 'spherical.cfg')
    threshold = config.getfloat(
        'spherical_mesh_quality', 'minimum_edge_length_ratio'
    )

    assert threshold == 1.0e-5
    assert threshold < 0.1 * 2.2e-4, (
        'the guard must keep an order of magnitude below the observed '
        'land-cell floor, or river constraints alone will fail a build'
    )
    assert threshold > 1.0e-9, (
        'the guard must stay far above numerical degeneracy to remain '
        'meaningful'
    )


def _cell_polygon_mesh_dataset(vertex_coords):
    """
    Build a one-cell MPAS-like mesh dataset for polygon-quality tests.
    """
    n_vertices = vertex_coords.shape[0]
    return xr.Dataset(
        data_vars={
            'nEdgesOnCell': (('nCells',), np.array([n_vertices])),
            'verticesOnCell': (
                ('nCells', 'maxEdges'),
                np.arange(1, n_vertices + 1, dtype=np.int32)[None, :],
            ),
            'xVertex': (('nVertices',), vertex_coords[:, 0]),
            'yVertex': (('nVertices',), vertex_coords[:, 1]),
            'zVertex': (('nVertices',), vertex_coords[:, 2]),
        }
    )
