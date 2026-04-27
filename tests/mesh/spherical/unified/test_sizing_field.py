import importlib.resources as imp_res
import os
from types import SimpleNamespace

import numpy as np
import xarray as xr

from polaris.component import Component
from polaris.mesh.spherical.unified import (
    UNIFIED_MESH_NAMES,
    UnifiedCellWidthMeshStep,
    get_unified_mesh_family,
)
from polaris.mesh.spherical.unified.families.default import (
    build_ocean_background_from_mode,
)
from polaris.mesh.spherical.unified.families.so_region import (
    SO_REGION_FILENAME,
    SO_REGION_PACKAGE,
)
from polaris.tasks.mesh.spherical.unified.sizing_field import (
    BuildSizingFieldStep,
    get_lat_lon_sizing_field_steps,
    get_sizing_field_config,
    sizing_field_dataset,
)
from polaris.tasks.mesh.spherical.unified.sizing_field.tasks import (
    add_sizing_field_tasks,
)


def test_sizing_field_mesh_outputs_and_active_control():
    ds_coastline = _make_coastline_dataset(
        ocean_mask=np.array([[1, 1, 0], [1, 0, 0]], dtype=np.int8),
        signed_distance=np.array(
            [[1000.0, 2000.0, -500.0], [3000.0, -4000.0, -1000.0]]
        ),
        lat=np.array([-60.0, 0.0]),
    )
    ds_river = _make_river_dataset(
        river_channel_mask=np.array([[0, 0, 0], [0, 1, 0]], dtype=np.int8),
        river_outlet_mask=np.array([[0, 1, 0], [0, 0, 0]], dtype=np.int8),
        lat=np.array([-60.0, 0.0]),
    )

    ds_uniform = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.25,
        mesh_name='ocn_240km_lnd_240km_riv_240km',
        ocean_background=_constant_ocean_background(
            ds_coastline=ds_coastline, value=240.0
        ),
        land_background_km=240.0,
        river_channel_km=240.0,
        river_outlet_km=240.0,
    )
    assert ds_uniform.attrs['mesh_name'] == 'ocn_240km_lnd_240km_riv_240km'
    assert 'profile_name' not in ds_uniform.attrs
    np.testing.assert_allclose(ds_uniform.cellWidth.values, 240.0)
    assert np.all(ds_uniform.active_control.values == 0)

    ds_split = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.125,
        mesh_name='ocn_30km_lnd_10km_riv_10km',
        ocean_background=_constant_ocean_background(
            ds_coastline=ds_coastline, value=30.0
        ),
        land_background_km=10.0,
        river_channel_km=10.0,
        river_outlet_km=10.0,
    )
    expected_split = np.array([[30.0, 30.0, 10.0], [30.0, 10.0, 10.0]])
    np.testing.assert_allclose(ds_split.cellWidth.values, expected_split)
    assert ds_split.active_control.values[0, 1] == 0
    assert ds_split.active_control.values[1, 1] == 0
    assert ds_split.attrs['river_channel_mask_count'] == 1
    assert ds_split.attrs['river_channel_finer_than_background_count'] == 0
    assert ds_split.attrs['river_channel_equal_to_background_count'] == 1
    assert ds_split.attrs['river_outlet_mask_count'] == 1
    assert ds_split.attrs['river_outlet_finer_than_background_count'] == 0
    assert ds_split.attrs['river_outlet_equal_to_background_count'] == 1

    ds_rrs = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.03125,
        mesh_name='ocn_rrs_6to18km_lnd_12km_riv_6km',
        ocean_background=build_ocean_background_from_mode(
            lat=ds_coastline.lat.values,
            lon=ds_coastline.lon.values,
            mode='rrs_latitude',
            min_km=6.0,
            max_km=18.0,
        ),
        land_background_km=12.0,
        river_channel_km=6.0,
        river_outlet_km=6.0,
    )
    ocean_values = ds_rrs.cellWidth.values[:, 0]
    assert ocean_values[0] < ocean_values[1]
    assert np.isclose(ds_rrs.cellWidth.values[0, 1], ocean_values[0])
    assert np.isclose(ds_rrs.cellWidth.values[1, 1], 6.0)
    assert ds_rrs.active_control.values[0, 1] == 0
    assert ds_rrs.active_control.values[1, 1] == 2


def test_sizing_field_coastline_transition_on_land():
    ds_coastline = _make_coastline_dataset(
        ocean_mask=np.array([[1, 1, 0, 0]], dtype=np.int8),
        signed_distance=np.array([[0.0, 1000.0, -1000.0, -3000.0]]),
        lat=np.array([0.0]),
        lon=np.array([-30.0, -10.0, 10.0, 30.0]),
    )
    ds_river = _make_river_dataset(
        river_channel_mask=np.array([[0, 0, 0, 0]], dtype=np.int8),
        river_outlet_mask=np.array([[0, 0, 0, 0]], dtype=np.int8),
        lat=np.array([0.0]),
        lon=np.array([-30.0, -10.0, 10.0, 30.0]),
    )

    ds_sizing = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.125,
        mesh_name='transition_test',
        ocean_background=_constant_ocean_background(
            ds_coastline=ds_coastline, value=30.0
        ),
        land_background_km=10.0,
        coastline_transition_land_km=2.0,
        enable_river_channel_refinement=False,
        enable_river_outlet_refinement=False,
    )

    np.testing.assert_allclose(
        ds_sizing.coastline_cell_width.values[0],
        np.array([30.0, 30.0, 20.0, 10.0]),
    )
    np.testing.assert_allclose(
        ds_sizing.cellWidth.values[0], np.array([30.0, 30.0, 20.0, 10.0])
    )
    np.testing.assert_array_equal(
        ds_sizing.active_control.values[0],
        np.array([0, 0, 1, 0], dtype=np.int8),
    )


def test_sizing_field_rivers_composed_before_coastline_transition():
    ds_coastline = _make_coastline_dataset(
        ocean_mask=np.array([[1, 1, 1, 0]], dtype=np.int8),
        signed_distance=np.array([[0.0, 1000.0, 3000.0, -1000.0]]),
        lat=np.array([0.0]),
        lon=np.array([-30.0, -10.0, 10.0, 30.0]),
    )
    ds_river = _make_river_dataset(
        river_channel_mask=np.array([[0, 0, 0, 0]], dtype=np.int8),
        river_outlet_mask=np.array([[1, 0, 1, 0]], dtype=np.int8),
        lat=np.array([0.0]),
        lon=np.array([-30.0, -10.0, 10.0, 30.0]),
    )

    ds_sizing = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.125,
        mesh_name='river_transition_test',
        ocean_background=_constant_ocean_background(
            ds_coastline=ds_coastline, value=30.0
        ),
        land_background_km=10.0,
        coastline_transition_land_km=0.0,
        river_channel_km=5.0,
        river_outlet_km=5.0,
    )

    np.testing.assert_allclose(
        ds_sizing.river_outlet_cell_width.values[0],
        np.array([5.0, 10.0, 5.0, 10.0]),
    )
    np.testing.assert_allclose(
        ds_sizing.ocean_background_cell_width.values[0],
        np.array([30.0, 30.0, 30.0, 30.0]),
    )
    np.testing.assert_allclose(
        ds_sizing.land_river_cell_width.values[0],
        np.array([5.0, 10.0, 5.0, 10.0]),
    )
    np.testing.assert_allclose(
        ds_sizing.pre_coastline_cell_width.values[0],
        np.array([30.0, 30.0, 30.0, 10.0]),
    )
    np.testing.assert_allclose(
        ds_sizing.cellWidth.values[0], np.array([30.0, 30.0, 30.0, 10.0])
    )
    np.testing.assert_allclose(
        ds_sizing.coastal_transition_delta.values[0],
        np.array([0.0, 0.0, 0.0, 0.0]),
    )
    np.testing.assert_array_equal(
        ds_sizing.active_control.values[0],
        np.array([0, 0, 0, 0], dtype=np.int8),
    )


def test_sizing_field_coastline_overrides_finer_land_and_river_controls():
    ds_coastline = _make_coastline_dataset(
        ocean_mask=np.array([[1, 0, 0]], dtype=np.int8),
        signed_distance=np.array([[0.0, -1000.0, -3000.0]]),
        lat=np.array([0.0]),
        lon=np.array([-30.0, 0.0, 30.0]),
    )
    ds_river = _make_river_dataset(
        river_channel_mask=np.array([[0, 1, 0]], dtype=np.int8),
        river_outlet_mask=np.array([[0, 0, 0]], dtype=np.int8),
        lat=np.array([0.0]),
        lon=np.array([-30.0, 0.0, 30.0]),
    )

    ds_sizing = sizing_field_dataset(
        ds_coastline=ds_coastline,
        ds_river=ds_river,
        resolution=0.125,
        mesh_name='coastal_override_test',
        ocean_background=_constant_ocean_background(
            ds_coastline=ds_coastline, value=30.0
        ),
        land_background_km=10.0,
        coastline_transition_land_km=2.0,
        river_channel_km=5.0,
        river_outlet_km=5.0,
    )

    np.testing.assert_allclose(
        ds_sizing.land_river_cell_width.values[0], np.array([10.0, 5.0, 10.0])
    )
    np.testing.assert_allclose(
        ds_sizing.coastline_cell_width.values[0], np.array([30.0, 17.5, 10.0])
    )
    np.testing.assert_allclose(
        ds_sizing.cellWidth.values[0], np.array([30.0, 17.5, 10.0])
    )
    np.testing.assert_allclose(
        ds_sizing.coastal_transition_delta.values[0],
        np.array([0.0, 12.5, 0.0]),
    )
    np.testing.assert_array_equal(
        ds_sizing.active_control.values[0], np.array([0, 1, 0], dtype=np.int8)
    )


def test_unified_cell_width_mesh_step_reads_sizing_field(tmp_path):
    step = UnifiedCellWidthMeshStep(
        component=Component(name='mesh'),
        subdir='spherical/unified/base_mesh/test',
    )
    step.work_dir = str(tmp_path)

    ds = xr.Dataset(
        data_vars=dict(
            cellWidth=(('lat', 'lon'), np.array([[1.0, 2.0], [3.0, 4.0]]))
        ),
        coords=dict(
            lat=xr.DataArray(np.array([-45.0, 45.0]), dims=('lat',)),
            lon=xr.DataArray(np.array([-90.0, 90.0]), dims=('lon',)),
        ),
    )
    ds.to_netcdf(tmp_path / 'sizing_field.nc')

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        cell_width, lon, lat = step.build_cell_width_lat_lon()
    finally:
        os.chdir(cwd)

    np.testing.assert_allclose(cell_width, ds.cellWidth.values)
    np.testing.assert_allclose(lon, ds.lon.values)
    np.testing.assert_allclose(lat, ds.lat.values)


def test_generic_ocean_background_modes():
    lat = np.array([-60.0, 0.0])
    lon = np.array([-120.0, 0.0, 120.0])

    constant = build_ocean_background_from_mode(
        lat=lat,
        lon=lon,
        mode='constant',
        min_km=30.0,
        max_km=30.0,
    )
    np.testing.assert_allclose(constant, 30.0)

    rrs = build_ocean_background_from_mode(
        lat=lat,
        lon=lon,
        mode='rrs_latitude',
        min_km=6.0,
        max_km=18.0,
    )
    assert rrs.shape == (2, 3)
    assert rrs[0, 0] < rrs[1, 0]


def test_constant_ocean_background_requires_equal_min_max():
    lat = np.array([-60.0, 0.0])
    lon = np.array([-120.0, 0.0, 120.0])

    try:
        build_ocean_background_from_mode(
            lat=lat,
            lon=lon,
            mode='constant',
            min_km=6.0,
            max_km=18.0,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError('Expected constant mode to raise ValueError.')

    assert 'ocean_background_min_km' in message
    assert 'ocean_background_max_km' in message


def test_generic_ocean_background_rejects_ec_latitude():
    lat = np.array([-60.0, 0.0])
    lon = np.array([-120.0, 0.0, 120.0])

    try:
        build_ocean_background_from_mode(
            lat=lat,
            lon=lon,
            mode='ec_latitude',
            min_km=6.0,
            max_km=18.0,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError('Expected ec_latitude to raise ValueError.')

    assert 'ec_latitude' in message
    assert 'Mesh-specific ocean backgrounds' in message


def test_add_sizing_field_tasks_registers_named_meshes():
    component = Component(name='mesh')
    add_sizing_field_tasks(component=component)

    assert 'ocn_so_12to30km_lnd_10km_riv_10km' in UNIFIED_MESH_NAMES
    assert len(component.tasks) == len(UNIFIED_MESH_NAMES)

    for mesh_name in UNIFIED_MESH_NAMES:
        subdir = f'spherical/unified/{mesh_name}/sizing_field/task'
        assert subdir in component.tasks
        task = component.tasks[subdir]
        assert task.name == f'sizing_field_{mesh_name}_task'


def test_sizing_field_step_factory_uses_mesh_subdir():
    component = Component(name='mesh')
    mesh_name = 'ocn_30km_lnd_10km_riv_10km'
    coastline_step = SimpleNamespace(
        subdir='spherical/unified/coastline/lat_lon/0.12500_degree/prepare',
        path='coastline',
        output_filenames={'calving_front': 'coastline.nc'},
    )
    river_step = SimpleNamespace(
        subdir='spherical/unified/ocn_30km_lnd_10km_riv_10km/river/lat_lon/prepare',
        path='river',
        masks_filename='river_network.nc',
    )

    steps, config = get_lat_lon_sizing_field_steps(
        component=component,
        coastline_step=coastline_step,
        river_step=river_step,
        mesh_name=mesh_name,
        include_viz=True,
    )

    assert (
        steps[0].subdir == f'spherical/unified/{mesh_name}/sizing_field/build'
    )
    assert steps[1].subdir == f'{steps[0].subdir}/viz'
    assert config.get('unified_mesh', 'mesh_name') == mesh_name
    assert config.has_option('unified_mesh', 'coastline_convention')


def test_sizing_field_step_factory_uses_mesh_family():
    component = Component(name='mesh')
    mesh_name = 'ocn_so_12to30km_lnd_10km_riv_10km'
    coastline_step = SimpleNamespace(
        subdir='spherical/unified/coastline/lat_lon/0.06250_degree/prepare',
        path='coastline',
        output_filenames={'calving_front': 'coastline.nc'},
    )
    river_step = SimpleNamespace(
        subdir='spherical/unified/ocn_so_12to30km_lnd_10km_riv_10km/'
        'river/lat_lon/prepare',
        path='river',
        masks_filename='river_network.nc',
    )

    steps, config = get_lat_lon_sizing_field_steps(
        component=component,
        coastline_step=coastline_step,
        river_step=river_step,
        mesh_name=mesh_name,
        include_viz=False,
    )

    assert type(steps[0]) is BuildSizingFieldStep
    assert config.get('unified_mesh', 'mesh_family') == 'so_region'
    assert get_unified_mesh_family(config).name == 'so_region'


def test_sizing_field_step_factory_reuses_shared_config_for_viz():
    component = Component(name='mesh')
    mesh_name = 'ocn_30km_lnd_10km_riv_10km'
    coastline_step = SimpleNamespace(
        subdir='spherical/unified/coastline/lat_lon/0.12500_degree/prepare',
        path='coastline',
        output_filenames={'calving_front': 'coastline.nc'},
    )
    river_step = SimpleNamespace(
        subdir='spherical/unified/ocn_30km_lnd_10km_riv_10km/river/lat_lon/prepare',
        path='river',
        masks_filename='river_network.nc',
    )

    build_steps, _ = get_lat_lon_sizing_field_steps(
        component=component,
        coastline_step=coastline_step,
        river_step=river_step,
        mesh_name=mesh_name,
        include_viz=False,
    )
    steps, config = get_lat_lon_sizing_field_steps(
        component=component,
        coastline_step=coastline_step,
        river_step=river_step,
        mesh_name=mesh_name,
        include_viz=True,
    )

    assert steps[0] is build_steps[0]
    assert len(steps) == 2
    assert config is component.configs[config.filepath]


def test_so_mesh_family_links_shared_region_and_builds_field(
    tmp_path,
):
    component = Component(name='mesh')
    coastline_step = SimpleNamespace(
        subdir='spherical/unified/coastline/lat_lon/0.06250_degree/prepare',
        path='coastline',
        output_filenames={'calving_front': 'coastline.nc'},
    )
    river_step = SimpleNamespace(
        subdir='spherical/unified/ocn_so_12to30km_lnd_10km_riv_10km/'
        'river/lat_lon/prepare',
        path='river',
        masks_filename='river_network.nc',
    )
    config = get_sizing_field_config(
        mesh_name='ocn_so_12to30km_lnd_10km_riv_10km',
        filepath='mesh/spherical/unified/'
        'ocn_so_12to30km_lnd_10km_riv_10km/sizing_field/sizing_field.cfg',
    )
    step = BuildSizingFieldStep(
        component=component,
        coastline_step=coastline_step,
        river_step=river_step,
        subdir='spherical/unified/ocn_so_12to30km_lnd_10km_riv_10km/'
        'sizing_field/build',
    )
    step.set_shared_config(config, link='sizing_field.cfg')
    step.setup()

    assert get_unified_mesh_family(config).name == 'so_region'
    assert any(
        input_file['filename'] == SO_REGION_FILENAME
        and input_file['package'] == SO_REGION_PACKAGE
        for input_file in step.input_data
    )

    ds_coastline = _make_coastline_dataset(
        ocean_mask=np.ones((3, 4), dtype=np.int8),
        signed_distance=np.zeros((3, 4), dtype=float),
        lat=np.array([-80.0, -60.0, -20.0]),
        lon=np.array([-180.0, -60.0, 60.0, 180.0]),
    )

    region_resource = imp_res.files(SO_REGION_PACKAGE).joinpath(
        SO_REGION_FILENAME
    )
    with imp_res.as_file(region_resource) as region_path:
        os.symlink(region_path, tmp_path / SO_REGION_FILENAME)
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ocean_background = step._get_ocean_background(
                ds_coastline=ds_coastline,
                section=config['sizing_field'],
            )
        finally:
            os.chdir(cwd)

    assert ocean_background.shape == (3, 4)
    assert np.min(ocean_background) < np.max(ocean_background)
    assert np.mean(ocean_background[0, :]) < np.mean(ocean_background[-1, :])


def _make_coastline_dataset(ocean_mask, signed_distance, lat=None, lon=None):
    if lat is None:
        lat = np.array([-30.0, 30.0])
    if lon is None:
        lon = np.array([-120.0, 0.0, 120.0])

    return xr.Dataset(
        data_vars=dict(
            ocean_mask=(('lat', 'lon'), ocean_mask),
            signed_distance=(('lat', 'lon'), signed_distance),
        ),
        coords=dict(
            lat=xr.DataArray(np.asarray(lat), dims=('lat',)),
            lon=xr.DataArray(np.asarray(lon), dims=('lon',)),
        ),
    )


def _make_river_dataset(
    river_channel_mask, river_outlet_mask, lat=None, lon=None
):
    if lat is None:
        lat = np.array([-30.0, 30.0])
    if lon is None:
        lon = np.array([-120.0, 0.0, 120.0])

    zeros = np.zeros_like(river_channel_mask)
    return xr.Dataset(
        data_vars=dict(
            river_channel_mask=(('lat', 'lon'), river_channel_mask),
            river_outlet_mask=(('lat', 'lon'), river_outlet_mask),
            river_ocean_outlet_mask=(('lat', 'lon'), zeros),
            river_inland_sink_mask=(('lat', 'lon'), zeros),
        ),
        coords=dict(
            lat=xr.DataArray(np.asarray(lat), dims=('lat',)),
            lon=xr.DataArray(np.asarray(lon), dims=('lon',)),
        ),
    )


def _constant_ocean_background(ds_coastline, value):
    lat_size = ds_coastline.sizes['lat']
    lon_size = ds_coastline.sizes['lon']
    return np.full((lat_size, lon_size), value, dtype=float)
