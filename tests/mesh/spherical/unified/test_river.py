import os
import zipfile

import numpy as np
import pytest
import shapefile
import xarray as xr

from polaris.component import Component
from polaris.mesh.spherical.unified import (
    UNIFIED_MESH_NAMES,
)
from polaris.tasks.mesh.spherical.unified.river import (
    add_river_tasks,
    build_river_network_dataset,
    get_unified_mesh_river_steps,
    simplify_river_network_feature_collection,
)
from polaris.tasks.mesh.spherical.unified.river.clip import (
    clip_outlet_feature_collection,
    condition_base_mesh_river_segments,
)
from polaris.tasks.mesh.spherical.unified.river.simplify import (
    _convert_hydrorivers_shapefile_to_geojson,
    _unpack_hydrorivers_archive,
    read_river_segments_from_feature_collection,
)


def test_simplify_river_network_filters_outlets_and_minor_tributaries():
    feature_collection = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(-1.0, 0.0), (0.0, 0.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
            ),
            _line_feature(
                hyriv_id=11,
                coords=[(-2.0, 0.0), (-1.0, 0.0)],
                next_down=10,
                drainage_area=80.0e6,
                endorheic=0,
            ),
            # ord_stra=2: not a headwater, so the area check is used (not the
            # distance-only headwater path).  35e6 >= 0.3 * 100e6 -> kept.
            _line_feature(
                hyriv_id=12,
                coords=[(-1.5, 1.0), (-1.0, 0.0)],
                next_down=10,
                drainage_area=35.0e6,
                endorheic=0,
                ord_stra=2,
            ),
            # ord_stra=1 (headwater): goes straight to the distance check.
            # Its closest point to retained basin segments is ~22 km < 30 km
            # tolerance, so it is filtered.
            _line_feature(
                hyriv_id=13,
                coords=[(-1.6, 0.2), (-1.2, 0.0)],
                next_down=10,
                drainage_area=10.0e6,
                endorheic=0,
            ),
            _line_feature(
                hyriv_id=20,
                coords=[(0.0, 0.05), (0.05, 0.05)],
                next_down=0,
                drainage_area=90.0e6,
                endorheic=0,
            ),
            _line_feature(
                hyriv_id=30,
                coords=[(50.0, 10.0), (50.1, 10.0)],
                next_down=0,
                drainage_area=25.0e6,
                endorheic=1,
            ),
            _line_feature(
                hyriv_id=31,
                coords=[(50.0, 10.05), (50.1, 10.05)],
                next_down=0,
                drainage_area=20.0e6,
                endorheic=1,
            ),
        ],
    )

    simplified_fc, outlets_fc = simplify_river_network_feature_collection(
        feature_collection=feature_collection,
        drainage_area_threshold=5.0e6,
        outlet_distance_tolerance=30.0e3,
        # ratio relative to the BASIN OUTLET (100e6): 35e6 >= 0.3*100e6=30e6
        tributary_area_ratio=0.3,
    )

    simplified_ids = {
        feature['properties']['hyriv_id']
        for feature in simplified_fc['features']
    }
    outlet_ids = {
        feature['properties']['hyriv_id'] for feature in outlets_fc['features']
    }

    assert simplified_ids == {10, 11, 12, 30, 31}
    assert outlet_ids == {10, 30, 31}


def test_simplify_river_network_handles_deep_main_stem():
    n_segments = 1500
    features = []
    for hyriv_id in range(1, n_segments + 1):
        next_down = hyriv_id - 1 if hyriv_id > 1 else 0
        features.append(
            _line_feature(
                hyriv_id=hyriv_id,
                coords=[
                    (-float(hyriv_id), 0.0),
                    (-float(hyriv_id) + 1.0, 0.0),
                ],
                next_down=next_down,
                drainage_area=(n_segments - hyriv_id + 1) * 1.0e6,
                endorheic=0,
            )
        )

    simplified_fc, outlets_fc = simplify_river_network_feature_collection(
        feature_collection=dict(type='FeatureCollection', features=features),
        drainage_area_threshold=1.0,
        outlet_distance_tolerance=1.0,
        tributary_area_ratio=0.05,
    )

    simplified_ids = {
        feature['properties']['hyriv_id']
        for feature in simplified_fc['features']
    }
    outlet_ids = {
        feature['properties']['hyriv_id'] for feature in outlets_fc['features']
    }

    assert len(simplified_ids) == n_segments
    assert outlet_ids == {1}


def test_simplify_river_network_rejects_next_down_cycles():
    feature_collection = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(0.0, 0.0), (1.0, 0.0)],
                next_down=11,
                drainage_area=50.0e6,
                endorheic=0,
            ),
            _line_feature(
                hyriv_id=11,
                coords=[(1.0, 0.0), (2.0, 0.0)],
                next_down=10,
                drainage_area=60.0e6,
                endorheic=0,
            ),
        ],
    )

    with pytest.raises(ValueError, match='Cycle detected'):
        simplify_river_network_feature_collection(
            feature_collection=feature_collection,
            drainage_area_threshold=1.0,
            outlet_distance_tolerance=1.0,
            tributary_area_ratio=0.05,
        )


def test_simplify_river_network_preserves_branch_traversal_order():
    feature_collection = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(0.0, 0.0), (1.0, 0.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
                ord_stra=4,
            ),
            # ord_stra=3: passes the area check (80e6 >= 0.4*100e6=40e6).
            _line_feature(
                hyriv_id=11,
                coords=[(-1.0, 0.0), (0.0, 0.0)],
                next_down=10,
                drainage_area=80.0e6,
                endorheic=0,
                ord_stra=3,
            ),
            # ord_stra=3: passes the area check (60e6 >= 0.4*100e6=40e6).
            _line_feature(
                hyriv_id=12,
                coords=[(0.0, 1.0), (0.0, 0.0)],
                next_down=10,
                drainage_area=60.0e6,
                endorheic=0,
                ord_stra=3,
            ),
            _line_feature(
                hyriv_id=21,
                coords=[(-2.0, 0.02), (-1.0, 0.0)],
                next_down=11,
                drainage_area=70.0e6,
                endorheic=0,
                ord_stra=2,
            ),
            _line_feature(
                hyriv_id=22,
                coords=[(0.0, 2.0), (0.0, 1.0)],
                next_down=12,
                drainage_area=55.0e6,
                endorheic=0,
                ord_stra=2,
            ),
            # ord_stra=1 (headwater): skips the area check, uses only the
            # distance check.  Its start point (0.0, 1.0) coincides with
            # the start of segment 12, so distance ~0 < 20 km -> filtered.
            _line_feature(
                hyriv_id=23,
                coords=[(-2.0, 0.03), (0.0, 1.0)],
                next_down=12,
                drainage_area=20.0e6,
                endorheic=0,
            ),
        ],
    )

    simplified_fc, _ = simplify_river_network_feature_collection(
        feature_collection=feature_collection,
        drainage_area_threshold=1.0,
        outlet_distance_tolerance=20.0e3,
        tributary_area_ratio=0.4,
    )

    simplified_ids = {
        feature['properties']['hyriv_id']
        for feature in simplified_fc['features']
    }

    assert simplified_ids == {10, 11, 12, 21, 22}


def test_build_river_network_dataset_contract_and_snapped_outlets():
    river_fc = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(-90.0, 0.0), (-45.0, 0.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
                outlet_type='ocean',
                outlet_hyriv_id=10,
            ),
            _line_feature(
                hyriv_id=30,
                coords=[(90.0, 0.0), (45.0, 0.0)],
                next_down=0,
                drainage_area=20.0e6,
                endorheic=1,
                outlet_type='inland_sink',
                outlet_hyriv_id=30,
            ),
        ],
    )
    outlet_fc = dict(
        type='FeatureCollection',
        features=[
            _point_feature(
                hyriv_id=10,
                coords=(-46.0, 1.0),
                drainage_area=100.0e6,
                endorheic=0,
                outlet_type='ocean',
            ),
            _point_feature(
                hyriv_id=30,
                coords=(46.0, 1.0),
                drainage_area=20.0e6,
                endorheic=1,
                outlet_type='inland_sink',
            ),
        ],
    )
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(
                ('lat', 'lon'),
                np.array(
                    [
                        [0, 0, 0, 0, 0],
                        [0, 1, 0, 0, 0],
                        [0, 0, 0, 0, 0],
                    ],
                    dtype=np.int8,
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([10.0, 0.0, -10.0]), dims=('lat',)),
            lon=xr.DataArray(
                np.array([-90.0, -45.0, 0.0, 45.0, 90.0]), dims=('lon',)
            ),
        ),
    )

    ds_river, snapped_outlets = build_river_network_dataset(
        river_feature_collection=river_fc,
        outlet_feature_collection=outlet_fc,
        ds_coastline=ds_coastline,
        resolution=45.0,
        outlet_match_tolerance=200.0e3,
        channel_subsegment_fraction=0.5,
    )

    expected_vars = {
        'river_channel_mask',
        'river_outlet_mask',
        'river_ocean_outlet_mask',
        'river_inland_sink_mask',
    }
    assert expected_vars.issubset(set(ds_river.data_vars))
    assert ds_river.attrs['matched_ocean_outlets'] == 1
    assert ds_river.attrs['unmatched_ocean_outlets'] == 0

    assert ds_river.river_channel_mask.sum() > 0
    assert ds_river.river_ocean_outlet_mask.sel(lat=0.0, lon=-45.0) == 1
    assert ds_river.river_inland_sink_mask.sel(lat=0.0, lon=45.0) == 1

    snapped_by_id = {
        feature['properties']['hyriv_id']: feature
        for feature in snapped_outlets['features']
    }
    assert snapped_by_id[10]['properties']['snapped_lon'] == -45.0
    assert snapped_by_id[10]['properties']['snapped_lat'] == 0.0
    assert snapped_by_id[30]['properties']['snapped_lon'] == 45.0
    assert snapped_by_id[30]['properties']['snapped_lat'] == 0.0
    assert snapped_by_id[10]['properties']['matched_to_ocean']


def test_build_river_network_dataset_applies_physical_channel_buffer():
    river_fc = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(0.0, 59.0), (0.0, 61.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
            ),
        ],
    )
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(
                ('lat', 'lon'),
                np.zeros((3, 5), dtype=np.int8),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([61.0, 60.0, 59.0]), dims=('lat',)),
            lon=xr.DataArray(
                np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), dims=('lon',)
            ),
        ),
    )

    ds_river, _ = build_river_network_dataset(
        river_feature_collection=river_fc,
        outlet_feature_collection=dict(type='FeatureCollection', features=[]),
        ds_coastline=ds_coastline,
        resolution=1.0,
        outlet_match_tolerance=200.0e3,
        channel_subsegment_fraction=0.5,
        channel_buffer_km=80.0,
    )

    assert ds_river.attrs['channel_buffer_m'] == 80.0e3
    assert ds_river.river_channel_mask.sel(lat=60.0, lon=0.0) == 1
    assert ds_river.river_channel_mask.sel(lat=60.0, lon=-1.0) == 1
    assert ds_river.river_channel_mask.sel(lat=60.0, lon=1.0) == 1
    assert ds_river.river_channel_mask.sel(lat=60.0, lon=-2.0) == 0
    assert ds_river.river_channel_mask.sel(lat=60.0, lon=2.0) == 0


def test_build_river_network_dataset_derives_land_mask_from_ocean_mask():
    river_fc = dict(type='FeatureCollection', features=[])
    outlet_fc = dict(
        type='FeatureCollection',
        features=[
            _point_feature(
                hyriv_id=30,
                coords=(46.0, 1.0),
                drainage_area=20.0e6,
                endorheic=1,
                outlet_type='inland_sink',
            ),
        ],
    )
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(
                ('lat', 'lon'),
                np.array(
                    [
                        [1, 1, 1, 1, 1],
                        [1, 1, 1, 0, 1],
                        [1, 1, 1, 1, 1],
                    ],
                    dtype=np.int8,
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([10.0, 0.0, -10.0]), dims=('lat',)),
            lon=xr.DataArray(
                np.array([-90.0, -45.0, 0.0, 45.0, 90.0]), dims=('lon',)
            ),
        ),
    )

    ds_river, snapped_outlets = build_river_network_dataset(
        river_feature_collection=river_fc,
        outlet_feature_collection=outlet_fc,
        ds_coastline=ds_coastline,
        resolution=45.0,
        outlet_match_tolerance=200.0e3,
        channel_subsegment_fraction=0.5,
    )

    assert ds_river.river_inland_sink_mask.sel(lat=0.0, lon=45.0) == 1
    snapped_feature = snapped_outlets['features'][0]
    assert snapped_feature['properties']['snapped_lon'] == 45.0
    assert snapped_feature['properties']['snapped_lat'] == 0.0


def test_condition_base_mesh_river_segments_clips_then_simplifies():
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(('lat', 'lon'), np.zeros((2, 3), dtype=np.int8)),
            signed_distance=(
                ('lat', 'lon'),
                np.array(
                    [
                        [-2.0e5, -2.0e5, 1.0e5],
                        [-2.0e5, -2.0e5, 1.0e5],
                    ]
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([-5.0, 5.0]), dims=('lat',)),
            lon=xr.DataArray(np.array([0.0, 10.0, 20.0]), dims=('lon',)),
        ),
    )
    river_fc = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(0.0, 0.0), (8.0, 0.0), (16.0, 0.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
                outlet_type='ocean',
                outlet_hyriv_id=10,
            )
        ],
    )

    segments = condition_base_mesh_river_segments(
        segments=read_river_segments_from_feature_collection(river_fc),
        ds_coastline=ds_coastline,
        clip_distance_m=50.0e3,
        simplify_tolerance_deg=0.5,
        min_segment_length_m=100.0,
    )

    assert len(segments) == 1
    coords = np.asarray(segments[0].geometry.coords)
    assert coords.shape[0] == 2
    assert coords[0, 0] == 0.0
    assert 8.0 < coords[-1, 0] < 16.0
    assert segments[0].outlet_type is None
    assert segments[0].outlet_hyriv_id is None


def test_condition_base_mesh_river_segments_drops_short_fragments():
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(('lat', 'lon'), np.zeros((2, 3), dtype=np.int8)),
            signed_distance=(
                ('lat', 'lon'),
                np.array(
                    [
                        [1.0e5, -1.0e4, 1.0e5],
                        [1.0e5, -1.0e4, 1.0e5],
                    ]
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([-5.0, 5.0]), dims=('lat',)),
            lon=xr.DataArray(np.array([0.0, 1.0, 2.0]), dims=('lon',)),
        ),
    )
    river_fc = dict(
        type='FeatureCollection',
        features=[
            _line_feature(
                hyriv_id=10,
                coords=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)],
                next_down=0,
                drainage_area=100.0e6,
                endorheic=0,
            )
        ],
    )

    segments = condition_base_mesh_river_segments(
        segments=read_river_segments_from_feature_collection(river_fc),
        ds_coastline=ds_coastline,
        clip_distance_m=20.0e3,
        simplify_tolerance_deg=0.0,
        min_segment_length_m=200.0e3,
    )

    assert segments == []


def test_clip_outlet_feature_collection_removes_ocean_outlets():
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(('lat', 'lon'), np.zeros((2, 2), dtype=np.int8)),
            signed_distance=(
                ('lat', 'lon'),
                np.array(
                    [
                        [-2.0e5, 1.0e5],
                        [-2.0e5, 1.0e5],
                    ]
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([-5.0, 5.0]), dims=('lat',)),
            lon=xr.DataArray(np.array([0.0, 10.0]), dims=('lon',)),
        ),
    )
    outlet_fc = dict(
        type='FeatureCollection',
        features=[
            _point_feature(
                hyriv_id=10,
                coords=(9.0, 0.0),
                drainage_area=100.0e6,
                endorheic=0,
                outlet_type='ocean',
            ),
            _point_feature(
                hyriv_id=20,
                coords=(1.0, 0.0),
                drainage_area=50.0e6,
                endorheic=1,
                outlet_type='inland_sink',
            ),
        ],
    )

    clipped = clip_outlet_feature_collection(
        outlet_feature_collection=outlet_fc,
        ds_coastline=ds_coastline,
        clip_distance_m=50.0e3,
    )

    clipped_ids = {
        feature['properties']['hyriv_id'] for feature in clipped['features']
    }
    assert clipped_ids == {20}


def test_build_river_network_dataset_marks_distant_ocean_outlet_unmatched():
    river_fc = dict(type='FeatureCollection', features=[])
    outlet_fc = dict(
        type='FeatureCollection',
        features=[
            _point_feature(
                hyriv_id=10,
                coords=(-46.0, 1.0),
                drainage_area=100.0e6,
                endorheic=0,
                outlet_type='ocean',
            ),
        ],
    )
    ds_coastline = xr.Dataset(
        data_vars=dict(
            ocean_mask=(
                ('lat', 'lon'),
                np.array(
                    [
                        [0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 1],
                        [0, 0, 0, 0, 0],
                    ],
                    dtype=np.int8,
                ),
            ),
        ),
        coords=dict(
            lat=xr.DataArray(np.array([10.0, 0.0, -10.0]), dims=('lat',)),
            lon=xr.DataArray(
                np.array([-90.0, -45.0, 0.0, 45.0, 90.0]), dims=('lon',)
            ),
        ),
    )

    ds_river, snapped_outlets = build_river_network_dataset(
        river_feature_collection=river_fc,
        outlet_feature_collection=outlet_fc,
        ds_coastline=ds_coastline,
        resolution=45.0,
        outlet_match_tolerance=200.0e3,
        channel_subsegment_fraction=0.5,
    )

    assert ds_river.attrs['matched_ocean_outlets'] == 0
    assert ds_river.attrs['unmatched_ocean_outlets'] == 1

    snapped_feature = snapped_outlets['features'][0]
    assert not snapped_feature['properties']['matched_to_ocean']
    assert snapped_feature['properties']['snapped_lon'] == -45.0
    assert snapped_feature['properties']['snapped_lat'] == 0.0


def test_unpack_hydrorivers_archive(tmp_path):
    archive_filename = tmp_path / 'HydroRIVERS_v10_shp.zip'
    shp_directory = tmp_path / 'HydroRIVERS_v10_shp'

    with zipfile.ZipFile(archive_filename, 'w') as archive:
        archive.writestr('HydroRIVERS_v10_shp/HydroRIVERS_v10.shp', 'x')

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        _unpack_hydrorivers_archive(
            archive_filename=str(archive_filename),
            data_directory='HydroRIVERS_v10_shp',
        )
    finally:
        os.chdir(cwd)

    assert shp_directory.is_dir()
    assert (shp_directory / 'HydroRIVERS_v10.shp').exists()


def test_convert_hydrorivers_shapefile_to_geojson(tmp_path):
    base = tmp_path / 'HydroRIVERS_v10'
    writer = shapefile.Writer(str(base))
    writer.field('HYRIV_ID', 'N', 10, 0)
    writer.field('MAIN_RIV', 'N', 10, 0)
    writer.field('ORD_STRA', 'N', 10, 0)
    writer.field('UPLAND_SKM', 'F', 18, 3)
    writer.field('NEXT_DOWN', 'N', 10, 0)
    writer.field('ENDORHEIC', 'N', 10, 0)
    writer.line([[[-1.0, 0.0], [0.0, 0.0]]])
    writer.record(1, 1, 1, 100.0, 0, 0)
    writer.close()

    output_filename = tmp_path / 'source_river_network.geojson'
    _convert_hydrorivers_shapefile_to_geojson(
        shp_filename=f'{base}.shp',
        output_filename=str(output_filename),
    )

    feature_collection = output_filename.read_text(encoding='utf-8')
    assert 'HYRIV_ID' in feature_collection
    assert 'LineString' in feature_collection


def test_mesh_river_step_factories_use_mesh_subdirs():
    mesh_name = 'u.oi30.lr10'
    unified_steps, _ = get_unified_mesh_river_steps(
        mesh_name=mesh_name,
        include_viz=False,
    )
    simplify_step = unified_steps['river_simplify']
    rasterize_step = unified_steps['river_rasterize']
    clip_step = unified_steps['river_clip']

    assert (
        simplify_step.subdir == f'spherical/unified/{mesh_name}/river/simplify'
    )
    assert (
        rasterize_step.subdir
        == f'spherical/unified/{mesh_name}/river/rasterize'
    )

    assert clip_step.subdir == f'spherical/unified/{mesh_name}/river/clip'


def test_mesh_river_step_factories_reuse_shared_configs():
    mesh_name = 'u.oi30.lr10'

    unified_steps_first, unified_config_first = get_unified_mesh_river_steps(
        mesh_name=mesh_name,
        include_viz=False,
    )
    unified_steps_second, unified_config_second = get_unified_mesh_river_steps(
        mesh_name=mesh_name,
        include_viz=True,
    )

    # source and lat-lon steps are shared across both calls
    assert (
        unified_steps_first['river_simplify']
        is unified_steps_second['river_simplify']
    )
    assert (
        unified_steps_first['river_rasterize']
        is unified_steps_second['river_rasterize']
    )
    assert (
        unified_steps_first['river_clip'] is unified_steps_second['river_clip']
    )
    assert unified_config_first is unified_config_second
    # without viz: {combine_topo, coastline_compute, coastline_final,
    #               river_simplify, river_rasterize, river_clip}
    # with viz: those plus river_viz
    print(unified_steps_first.keys())
    print(unified_steps_second.keys())
    assert len(unified_steps_first) == 6
    assert len(unified_steps_second) == 7


def test_add_river_tasks_registers_mesh_tasks():
    component = Component(name='mesh')
    add_river_tasks(component=component)

    assert len(component.tasks) == len(UNIFIED_MESH_NAMES)

    for mesh_name in UNIFIED_MESH_NAMES:
        subdir = f'spherical/unified/{mesh_name}/river/task'
        assert subdir in component.tasks
        task = component.tasks[subdir]
        assert task.name == f'river_network_{mesh_name}_task'


def test_drainage_area_threshold_auto_derived_from_config():
    # High-resolution mesh: 10 km land,
    # multiplier 100 → 10² × 100 × 1e6 = 1e10 m²
    steps_10km, config_10km = get_unified_mesh_river_steps(
        mesh_name='u.oi30.lr10', include_viz=False
    )
    land_background_km = config_10km.getfloat(
        'sizing_field', 'land_background_km'
    )
    multiplier = config_10km.getfloat(
        'river_network', 'drainage_area_multiplier'
    )
    assert land_background_km == pytest.approx(10.0)
    assert multiplier == pytest.approx(100.0)
    assert land_background_km**2 * multiplier * 1e6 == pytest.approx(1.0e10)

    # Coarse mesh: 240 km land, multiplier 10 → 240² × 10 × 1e6 = 5.76e11 m²
    steps_240km, config_240km = get_unified_mesh_river_steps(
        mesh_name='u.oi240.lr240', include_viz=False
    )
    land_background_km = config_240km.getfloat(
        'sizing_field', 'land_background_km'
    )
    multiplier = config_240km.getfloat(
        'river_network', 'drainage_area_multiplier'
    )
    assert land_background_km == pytest.approx(240.0)
    assert multiplier == pytest.approx(10.0)
    assert land_background_km**2 * multiplier * 1e6 == pytest.approx(5.76e11)


def test_outlet_distance_tolerance_auto_derived_from_config():
    # 10 km river channel → 10 000 m tolerance
    _, config_10km = get_unified_mesh_river_steps(
        mesh_name='u.oi30.lr10', include_viz=False
    )
    river_channel_km = config_10km.getfloat('sizing_field', 'river_channel_km')
    assert river_channel_km == pytest.approx(10.0)
    assert river_channel_km * 1000.0 == pytest.approx(10_000.0)

    # 240 km river channel → 240 000 m tolerance
    _, config_240km = get_unified_mesh_river_steps(
        mesh_name='u.oi240.lr240', include_viz=False
    )
    river_channel_km = config_240km.getfloat(
        'sizing_field', 'river_channel_km'
    )
    assert river_channel_km == pytest.approx(240.0)
    assert river_channel_km * 1000.0 == pytest.approx(240_000.0)


def _line_feature(
    hyriv_id,
    coords,
    next_down,
    drainage_area,
    endorheic,
    outlet_type=None,
    outlet_hyriv_id=None,
    ord_stra=1,
):
    return dict(
        type='Feature',
        properties=dict(
            hyriv_id=hyriv_id,
            main_riv=hyriv_id,
            ord_stra=ord_stra,
            drainage_area=drainage_area,
            next_down=next_down,
            endorheic=endorheic,
            outlet_type=outlet_type,
            outlet_hyriv_id=outlet_hyriv_id,
        ),
        geometry=dict(type='LineString', coordinates=coords),
    )


def _point_feature(
    hyriv_id,
    coords,
    drainage_area,
    endorheic,
    outlet_type,
):
    return dict(
        type='Feature',
        properties=dict(
            hyriv_id=hyriv_id,
            main_riv=hyriv_id,
            drainage_area=drainage_area,
            endorheic=endorheic,
            outlet_type=outlet_type,
        ),
        geometry=dict(type='Point', coordinates=coords),
    )
