import json
import os

import numpy as np

from polaris.component import Component
from polaris.mesh.spherical.unified import (
    UnifiedBaseMeshStep,
)
from polaris.mesh.spherical.unified.base_mesh import _read_geojson_line_mesh
from polaris.tasks.mesh.spherical.unified.base_mesh.viz import (
    CONUS_EXTENT,
    _estimate_dc_edge_from_area_cell,
    _get_regional_extent,
)


def test_estimate_dc_edge_from_area_cell_matches_regular_hexagon():
    dc_edge_km = np.array([10.0, 30.0])
    area_km2 = 0.5 * np.sqrt(3.0) * dc_edge_km**2

    estimated_dc_edge_km = _estimate_dc_edge_from_area_cell(area_km2)

    np.testing.assert_allclose(estimated_dc_edge_km, dc_edge_km)


def test_unified_base_mesh_step_writes_river_geometry(tmp_path, monkeypatch):
    step = UnifiedBaseMeshStep(
        component=Component(name='mesh'),
        subdir='spherical/unified/test/base_mesh',
    )
    step.opts.hfun_file = 'hfun.msh'
    step.opts.geom_file = 'geom.msh'
    step.opts.jcfg_file = 'jigsaw.jig'

    feature_collection = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {'hyriv_id': 1},
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[0.0, 0.0], [10.0, 10.0]],
                },
            },
            {
                'type': 'Feature',
                'properties': {'hyriv_id': 2},
                'geometry': {
                    'type': 'MultiLineString',
                    'coordinates': [
                        [[20.0, 5.0], [25.0, 5.0], [30.0, 10.0]],
                    ],
                },
            },
        ],
    }
    river_path = tmp_path / 'clipped_river_network.geojson'
    river_path.write_text(json.dumps(feature_collection), encoding='utf-8')

    saved_meshes = {}

    def fake_savemsh(filename, mesh):
        saved_meshes[filename] = mesh

    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.jigsawpy.savemsh',
        fake_savemsh,
    )
    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.savejig',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.check_call',
        lambda *args, **kwargs: None,
    )

    lon = np.array([-10.0, 0.0, 10.0])
    lat = np.array([-5.0, 5.0])
    cell_width = np.full((lat.size, lon.size), 30.0)

    step.config.set('river_network', 'base_mesh_simplify_tolerance_km', '2.0')
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.make_jigsaw_mesh(lon=lon, lat=lat, cell_width=cell_width)
    finally:
        os.chdir(cwd)

    geom = saved_meshes['geom.msh']
    assert geom.edge2.size == 3
    np.testing.assert_allclose(
        geom.vert2['coord'][0], np.radians(np.array([0.0, 0.0]))
    )
    np.testing.assert_array_equal(
        geom.edge2['index'],
        np.array([[0, 1], [2, 3], [3, 4]], dtype=np.int32),
    )
    np.testing.assert_array_equal(
        geom.edge2['IDtag'], np.array([1, 2, 2], dtype=np.int32)
    )


def test_unified_base_mesh_step_uses_prepared_clipped_river_geometry(
    tmp_path, monkeypatch
):
    step = UnifiedBaseMeshStep(
        component=Component(name='mesh'),
        subdir='spherical/unified/test/base_mesh',
    )
    step.opts.hfun_file = 'hfun.msh'
    step.opts.geom_file = 'geom.msh'
    step.opts.jcfg_file = 'jigsaw.jig'
    feature_collection = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {'hyriv_id': 1},
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[-10.0, 0.0], [-2.5, 0.0]],
                },
            }
        ],
    }
    river_path = tmp_path / 'clipped_river_network.geojson'
    river_path.write_text(json.dumps(feature_collection), encoding='utf-8')

    saved_meshes = {}

    def fake_savemsh(filename, mesh):
        saved_meshes[filename] = mesh

    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.jigsawpy.savemsh',
        fake_savemsh,
    )
    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.savejig',
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        'polaris.mesh.spherical.unified.base_mesh.check_call',
        lambda *args, **kwargs: None,
    )

    lon = np.array([0.0, 180.0, 360.0])
    lat = np.array([-10.0, 10.0])
    cell_width = np.full((lat.size, lon.size), 30.0)

    step.config.set('river_network', 'base_mesh_simplify_tolerance_km', '2.0')
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.make_jigsaw_mesh(lon=lon, lat=lat, cell_width=cell_width)
    finally:
        os.chdir(cwd)

    geom = saved_meshes['geom.msh']
    assert geom.edge2.size == 1
    np.testing.assert_allclose(
        np.degrees(geom.vert2['coord'][:, 0]),
        np.array([-10.0, -2.5]),
    )
    np.testing.assert_allclose(
        np.degrees(geom.vert2['coord'][:, 1]), np.array([0.0, 0.0])
    )


def test_read_geojson_line_mesh_deduplicates_shared_endpoints(tmp_path):
    # Two LineString features that share the endpoint [10.0, 5.0]. Without
    # deduplication this creates two coincident vert2 entries, which causes
    # JIGSAW to produce degenerate mesh cells.
    feature_collection = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[0.0, 0.0], [10.0, 5.0]],
                },
            },
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[10.0, 5.0], [20.0, 0.0]],
                },
            },
        ],
    }
    geojson_path = tmp_path / 'rivers.geojson'
    geojson_path.write_text(json.dumps(feature_collection), encoding='utf-8')

    vert2, edge2 = _read_geojson_line_mesh(
        str(geojson_path), snap_tolerance_km=1.0, earth_radius_km=6371.0
    )

    # Three unique vertices, not four.
    assert vert2 is not None
    assert vert2.size == 3

    # No duplicate rows in vert2.
    coords_deg = np.degrees(vert2['coord'])
    unique_rows = np.unique(coords_deg, axis=0)
    assert unique_rows.shape[0] == 3

    # Two edges total; the shared vertex appears in both.
    assert edge2 is not None
    assert edge2.size == 2

    shared_idx = int(
        np.argmin(
            np.abs(coords_deg[:, 0] - 10.0) + np.abs(coords_deg[:, 1] - 5.0)
        )
    )
    assert shared_idx in edge2['index'][0]
    assert shared_idx in edge2['index'][1]

    # IDtags distinguish the two features.
    np.testing.assert_array_equal(
        edge2['IDtag'], np.array([1, 2], dtype=np.int32)
    )


def test_read_geojson_line_mesh_drops_degenerate_edges_after_dedup(tmp_path):
    # A two-point LineString whose both points duplicate an interior vertex of
    # a longer feature. After deduplication the short feature collapses to a
    # single vertex and its constraint edge must be dropped.
    feature_collection = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[0.0, 0.0], [5.0, 5.0], [10.0, 0.0]],
                },
            },
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    # Both points are duplicates of the same vertex above —
                    # this edge becomes degenerate after deduplication.
                    'coordinates': [[5.0, 5.0], [5.0, 5.0]],
                },
            },
        ],
    }
    geojson_path = tmp_path / 'rivers.geojson'
    geojson_path.write_text(json.dumps(feature_collection), encoding='utf-8')

    vert2, edge2 = _read_geojson_line_mesh(
        str(geojson_path), snap_tolerance_km=1.0, earth_radius_km=6371.0
    )

    # Three unique vertices.
    assert vert2 is not None
    assert vert2.size == 3

    # Only the two non-degenerate edges from Feature 1 survive.
    assert edge2 is not None
    assert edge2.size == 2
    np.testing.assert_array_equal(
        edge2['IDtag'], np.array([1, 1], dtype=np.int32)
    )

    # No edge maps a vertex to itself.
    assert not np.any(edge2['index'][:, 0] == edge2['index'][:, 1])


def test_get_regional_extent_uses_conus_example_for_global_bounds():
    extent = _get_regional_extent(
        bounds=(-170.0, 170.0, -60.0, 70.0), padding=3.0
    )

    assert extent == CONUS_EXTENT
