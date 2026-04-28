import configparser
from types import SimpleNamespace

import numpy as np
import xarray as xr
from scipy import ndimage

from polaris.component import Component
from polaris.mesh.spherical.coastline import (
    CONVENTIONS,
    _rasterize_feature_collection,
    build_coastline_dataset,
    build_coastline_datasets,
)
from polaris.mesh.spherical.critical_transects import CriticalTransects
from polaris.task import Task
from polaris.tasks.mesh.spherical.unified.coastline import (
    get_lat_lon_coastline_steps,
)
from polaris.tasks.mesh.spherical.unified.coastline import (
    prepare as prepare_module,
)
from polaris.tasks.mesh.spherical.unified.coastline.prepare import (
    PrepareCoastlineStep,
)


def test_coastline_contract_and_variants():
    ds_topo = _make_topography_dataset(
        base_elevation=np.array(
            [
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, 20.0, 20.0, -10.0],
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, -20.0, -20.0, -10.0],
            ]
        ),
        ice_mask=np.array(
            [
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 1.0, 0.0],
            ]
        ),
        grounded_mask=np.array(
            [
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
            ]
        ),
    )

    ds_coastlines = build_coastline_datasets(
        ds_topo=ds_topo,
        resolution=1.0,
        mask_threshold=0.5,
        distance_chunk_size=2,
    )
    ds_coastline = ds_coastlines['grounding_line']
    calving = ds_coastlines['calving_front'].ocean_mask.values
    grounding = ds_coastline.ocean_mask.values
    bedrock = ds_coastlines['bedrock_zero'].ocean_mask.values

    expected_vars = {'ocean_mask', 'signed_distance'}
    assert set(ds_coastline.data_vars) == expected_vars
    assert tuple(ds_coastlines.keys()) == (
        'calving_front',
        'grounding_line',
        'bedrock_zero',
    )
    assert ds_coastline.attrs['coastline_convention'] == 'grounding_line'
    assert (
        ds_coastline.attrs['flood_fill_seed_strategy']
        == 'candidate_ocean_on_northernmost_row'
    )

    assert calving[3, 1] == 0
    assert grounding[3, 1] == 1
    assert grounding[3, 2] == 0
    assert bedrock[3, 2] == 1

    assert 'coastline_mask' not in ds_coastline
    assert 'coastline_edge_east' not in ds_coastline
    assert 'coastline_edge_north' not in ds_coastline
    assert 'candidate_ocean_mask' not in ds_coastline
    assert 'land_mask' not in ds_coastline

    signed_distance = ds_coastline.signed_distance.values
    assert np.isfinite(signed_distance).all()
    assert signed_distance[0, 0] > 0.0
    assert signed_distance[1, 1] < 0.0


def test_coastline_excludes_disconnected_inland_water():
    ds_topo = _make_topography_dataset(
        base_elevation=np.array(
            [
                [-10.0, -10.0, -10.0, -10.0],
                [20.0, 20.0, 20.0, 20.0],
                [20.0, -10.0, -10.0, 20.0],
                [20.0, 20.0, 20.0, 20.0],
            ]
        )
    )

    ds_coastline = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        mask_threshold=0.5,
        distance_chunk_size=2,
    )
    ocean_mask = ds_coastline.ocean_mask.values

    assert ocean_mask[2, 1] == 0
    assert ocean_mask[2, 2] == 0


def test_coastline_uses_northernmost_latitude_for_seed_row():
    ds_topo = _make_topography_dataset(
        lat=np.array([-60.0, -20.0, 20.0, 60.0]),
        base_elevation=np.array(
            [
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, -10.0, -10.0, -10.0],
            ]
        ),
        ice_mask=np.array(
            [
                [1.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
            ]
        ),
    )

    ds_coastline = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='calving_front',
        mask_threshold=0.5,
        distance_chunk_size=2,
    )
    ocean_mask = ds_coastline.ocean_mask.values

    assert ocean_mask.sum() == ocean_mask.size - ds_topo.lon.size
    assert np.all(ocean_mask[0, :] == 0)
    assert np.all(ocean_mask[-1, :] == 1)


def test_coastline_none_transects_matches_legacy_behavior():
    ds_topo = _make_topography_dataset(
        base_elevation=np.array(
            [
                [-10.0, -10.0, -10.0, -10.0],
                [20.0, 20.0, 20.0, 20.0],
                [-10.0, -10.0, -10.0, -10.0],
                [-10.0, -10.0, -10.0, -10.0],
            ]
        )
    )

    legacy = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
    )
    explicit_none = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
        critical_transects=None,
    )

    np.testing.assert_array_equal(
        legacy.ocean_mask.values, explicit_none.ocean_mask.values
    )
    np.testing.assert_allclose(
        legacy.signed_distance.values,
        explicit_none.signed_distance.values,
    )


def test_critical_land_blockage_closes_a_narrow_ocean_connection():
    base_elevation = -10.0 * np.ones((5, 5))
    base_elevation[1, :] = 20.0
    base_elevation[1, 2] = -10.0
    ds_topo = _make_topography_dataset(base_elevation=base_elevation)

    baseline = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
    )
    critical_transects = CriticalTransects(
        land_blockages=_feature_collection([(0.0, 40.0), (0.0, 20.0)]),
        passages=None,
    )
    blocked = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
        critical_transects=critical_transects,
    )

    assert baseline.ocean_mask.values[-1, 2] == 1
    assert blocked.ocean_mask.values[-1, 2] == 0


def test_critical_passage_connects_otherwise_disconnected_ocean():
    base_elevation = -10.0 * np.ones((5, 5))
    base_elevation[1, :] = 20.0
    ds_topo = _make_topography_dataset(base_elevation=base_elevation)

    baseline = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
    )
    critical_transects = CriticalTransects(
        land_blockages=None,
        passages=_feature_collection([(0.0, 40.0), (0.0, 20.0)]),
    )
    connected = build_coastline_dataset(
        ds_topo=ds_topo,
        resolution=1.0,
        convention='bedrock_zero',
        distance_chunk_size=2,
        critical_transects=critical_transects,
    )

    assert baseline.ocean_mask.values[-1, 2] == 0
    assert connected.ocean_mask.values[-1, 2] == 1


def test_diagonal_transect_rasterization_is_four_connected():
    lon = np.array([-135.0, -45.0, 45.0, 135.0])
    lat = np.array([60.0, 20.0, -20.0, -60.0])
    mask = _rasterize_feature_collection(
        feature_collection=_feature_collection(
            [(-120.0, 60.0), (20.0, -60.0)]
        ),
        lon=lon,
        lat=lat,
    )

    labels, count = ndimage.label(
        mask,
        structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8),
    )
    assert labels.any()
    assert count == 1
    assert mask.sum() > 2


def test_antimeridian_transect_rasterization_uses_periodic_longitude():
    lon = np.array([-135.0, -45.0, 45.0, 135.0])
    lat = np.array([60.0, 20.0, -20.0, -60.0])
    mask = _rasterize_feature_collection(
        feature_collection=_feature_collection(
            [(170.0, 20.0), (-170.0, 20.0)]
        ),
        lon=lon,
        lat=lat,
    )

    assert mask[1, 0]
    assert mask[1, -1]


def test_coastline_step_configures_critical_transects(monkeypatch):
    component = Component('mesh')
    combine_step = SimpleNamespace(
        combined_filename='combined_topography.nc',
        subdir='combine',
        path='combine',
    )
    dummy_dataset = xr.Dataset()

    calls = []
    sentinel = object()

    def fake_build(**kwargs):
        calls.append(kwargs['critical_transects'])
        return {convention: dummy_dataset.copy() for convention in CONVENTIONS}

    monkeypatch.setattr(prepare_module, 'build_coastline_datasets', fake_build)
    monkeypatch.setattr(
        prepare_module,
        '_write_netcdf_with_fill_values',
        lambda ds, filename: None,
    )
    monkeypatch.setattr(
        prepare_module.xr,
        'open_dataset',
        lambda filename: xr.Dataset(),
    )

    enabled_calls = {'count': 0}

    def fake_loader():
        enabled_calls['count'] += 1
        return sentinel

    monkeypatch.setattr(
        prepare_module,
        'load_default_critical_transects',
        fake_loader,
    )

    disabled_step = PrepareCoastlineStep(
        component=component,
        combine_step=combine_step,
        subdir='prepare_disabled',
    )
    disabled_step.config = _make_prepare_config(False)
    disabled_step.run()

    enabled_step = PrepareCoastlineStep(
        component=component,
        combine_step=combine_step,
        subdir='prepare_enabled',
    )
    enabled_step.config = _make_prepare_config(True)
    enabled_step.run()

    assert calls == [None, sentinel]
    assert enabled_calls['count'] == 1


def test_get_lat_lon_coastline_steps_reuses_shared_config_for_viz():
    component = Component('mesh')
    combine_step = SimpleNamespace(
        combined_filename='combined_topography.nc',
        subdir='combine',
        path='combine',
    )

    steps_without_viz, config_without_viz = get_lat_lon_coastline_steps(
        component=component,
        combine_topo_step=combine_step,
        resolution=0.25,
        include_viz=False,
    )
    steps_with_viz, config_with_viz = get_lat_lon_coastline_steps(
        component=component,
        combine_topo_step=combine_step,
        resolution=0.25,
        include_viz=True,
    )

    assert len(steps_without_viz) == 1
    assert len(steps_with_viz) == 2
    assert steps_without_viz[0] is steps_with_viz[0]
    assert config_without_viz is config_with_viz


def test_task_can_include_shared_coastline_viz_without_default_run():
    component = Component('mesh')
    combine_step = SimpleNamespace(
        combined_filename='combined_topography.nc',
        subdir='combine',
        path='combine',
    )
    coastline_steps, _ = get_lat_lon_coastline_steps(
        component=component,
        combine_topo_step=combine_step,
        resolution=0.25,
        include_viz=True,
    )

    task = Task(component=component, name='coastline_consumer')
    task.add_step(coastline_steps[0], symlink='coastline')
    task.add_step(
        coastline_steps[1],
        symlink='viz_coastline',
        run_by_default=False,
    )

    assert coastline_steps[0].name in task.steps
    assert coastline_steps[1].name in task.steps
    assert coastline_steps[0].name in task.steps_to_run
    assert coastline_steps[1].name not in task.steps_to_run


def _make_topography_dataset(
    base_elevation,
    lon=None,
    lat=None,
    ice_mask=None,
    grounded_mask=None,
):
    if lon is None:
        n_lon = base_elevation.shape[1]
        if n_lon == 5:
            lon = np.array([-144.0, -72.0, 0.0, 72.0, 144.0])
        else:
            lon = np.array([-135.0, -45.0, 45.0, 135.0])
    if lat is None:
        n_lat = base_elevation.shape[0]
        if n_lat == 5:
            lat = np.array([60.0, 30.0, 0.0, -30.0, -60.0])
        else:
            lat = np.array([60.0, 20.0, -20.0, -60.0])

    if ice_mask is None:
        ice_mask = np.zeros_like(base_elevation)
    if grounded_mask is None:
        grounded_mask = np.zeros_like(base_elevation)

    return xr.Dataset(
        data_vars=dict(
            base_elevation=(('lat', 'lon'), base_elevation),
            ice_mask=(('lat', 'lon'), ice_mask),
            grounded_mask=(('lat', 'lon'), grounded_mask),
        ),
        coords=dict(
            lat=xr.DataArray(np.asarray(lat), dims=('lat',)),
            lon=xr.DataArray(np.asarray(lon), dims=('lon',)),
        ),
    )


def _feature_collection(*lines):
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {},
                'geometry': {
                    'type': 'LineString',
                    'coordinates': list(line),
                },
            }
            for line in lines
        ],
    }


def _make_prepare_config(include_critical_transects):
    config = configparser.ConfigParser()
    config.add_section('coastline')
    config.set('coastline', 'resolution_latlon', '1.0')
    config.set(
        'coastline',
        'include_critical_transects',
        str(include_critical_transects),
    )
    config.set('coastline', 'mask_threshold', '0.5')
    config.set('coastline', 'sea_level_elevation', '0.0')
    config.set('coastline', 'distance_chunk_size', '2')
    return config
