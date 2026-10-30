import os
from types import SimpleNamespace

import numpy as np
import xarray as xr

from polaris.component import Component
from polaris.tasks.e3sm.init.misomip import get_misomip_experiment_steps
from polaris.tasks.e3sm.init.misomip.land_ice_fields import (
    apply_map,
    compute_land_ice_fields,
    compute_mali_export,
    import_geometry,
    read_map,
)
from polaris.tasks.e3sm.init.misomip.land_ice_on_ocean import (
    LandIceOnOceanStep,
)
from polaris.tasks.e3sm.init.misomip.landice_data import (
    write_data_mode_file,
)
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.misomip import MisomipInit


def _map(tmp_path):
    """A map from 3 MALI cells to 2 ocean cells"""
    ds = xr.Dataset()
    ds['S'] = ('n_s', np.array([0.5, 0.5, 1.0]))
    ds['row'] = ('n_s', np.array([1, 1, 2], dtype=np.int32))
    ds['col'] = ('n_s', np.array([1, 2, 3], dtype=np.int32))
    ds['area_a'] = ('n_a', np.ones(3))
    ds['area_b'] = ('n_b', np.ones(2))
    filename = str(tmp_path / 'map.nc')
    ds.to_netcdf(filename)
    return filename


def test_compute_land_ice_fields(tmp_path):
    matrix = read_map(_map(tmp_path))
    bed = np.array([-900.0, -900.0, -500.0])
    thickness = np.array([[500.0, 1100.0, 0.0], [0.0, 0.0, 400.0]])
    fields = compute_land_ice_fields(matrix, thickness, bed)
    export = compute_mali_export(thickness, bed)
    expected = import_geometry(
        {name: apply_map(matrix, field) for name, field in export.items()}
    )
    for name, field in expected.items():
        np.testing.assert_allclose(fields[name], field)
        assert fields[name].shape == (2, 2)


def _step(path):
    return SimpleNamespace(path=path)


def test_misomip_init(tmp_path):
    init = MisomipInit(
        component=Ocean(),
        subdir='planar/misomip/test/iceocean1ra/init',
        ocean_mesh_step=_step('e3sm/init/test/ocean_mesh'),
        topo_step=_step('ocean/planar/misomip/test/topo/remap'),
        land_ice_fields_step=_step('e3sm/init/test/land_ice_on_ocean'),
        experiment='iceocean1ra',
    )
    assert init.name == 'ocean_init'
    assert init.subdir == 'planar/misomip/test/iceocean1ra/init'
    assert init.gravity == 9.80616
    assert init.profiles == {'init': 'cold', 'restoring': 'cold'}
    targets = {
        entry['filename']: entry['work_dir_target']
        for entry in init.input_data
    }
    assert targets['culled_mesh.nc'] == (
        'e3sm/init/test/ocean_mesh/ocean_mesh.nc'
    )
    assert targets['land_ice_fields.nc'] == (
        'e3sm/init/test/land_ice_on_ocean/land_ice_fields.nc'
    )

    ds_bed = xr.Dataset()
    ds_bed['bedrockTopography'] = ('nCells', np.array([-700.0, -600.0]))
    ds_bed.bedrockTopography.attrs['cell_measures'] = 'area: area'
    ds_bed.to_netcdf(tmp_path / 'topography.nc')
    ds_fields = xr.Dataset()
    ds_fields['landIcePressure'] = (('Time', 'nCells'), np.ones((3, 2)))
    ds_fields.to_netcdf(tmp_path / 'land_ice_fields.nc')
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        ds_topo = init.read_topography()
    finally:
        os.chdir(cwd)
    assert ds_topo.sizes['Time'] == 3
    np.testing.assert_array_equal(
        ds_topo.bedrockTopography.values, [-700.0, -600.0]
    )
    assert 'cell_measures' not in ds_topo.bedrockTopography.attrs


def test_experiment_steps():
    mesh_name = 'misomip-o4km-li1km'
    steps, _ = get_misomip_experiment_steps(mesh_name, 'ocean3')
    assert steps['land_ice_on_ocean'].data_mode
    assert 'ocean/init' in steps
    assert 'ocean/ssh_adjustment/ssh_adjust_0' in steps
    init = steps['ocean/init']
    assert init.config.getfloat('isomip_plus', 'min_land_ice_fraction') == 0.0
    assert init.config.get('vertical_grid', 'coord_type') == 'z-star'

    steps, _ = get_misomip_experiment_steps(mesh_name, 'ocean0')
    assert not steps['land_ice_on_ocean'].data_mode

    # IceOcean1ra has only its restoring, made on IceOcean1r's geometry
    steps, _ = get_misomip_experiment_steps(mesh_name, 'iceocean1ra')
    assert steps['iceocean1r/land_ice_on_ocean'].path == (
        f'e3sm/init/{mesh_name}/misomip/iceocean1r/land_ice_on_ocean'
    )
    assert 'ocean/init' in steps
    assert not any(name.startswith('ocean/ssh') for name in steps)


def test_land_ice_on_ocean_from_data_mode(tmp_path):
    step = LandIceOnOceanStep(
        component=Component(name='e3sm/init'),
        subdir='test/land_ice_on_ocean',
        landice_init_step=_step('landice_init'),
        map_step=_step('map'),
        landice_data_step=_step('landice_data'),
    )
    bed = np.array([-900.0, -900.0, -500.0])
    ds_init = xr.Dataset()
    ds_init['bedTopography'] = (('Time', 'nCells'), bed[np.newaxis, :])
    ds_init['thickness'] = (('Time', 'nCells'), np.zeros((1, 3)))
    ds_init.to_netcdf(tmp_path / 'landice_init.nc')
    os.rename(_map(tmp_path), tmp_path / 'map.nc')
    xtimes = ['0001-01-01_00:00:00', '0001-02-01_00:00:00']
    records = np.array([[500.0, 1100.0, 0.0], [0.0, 0.0, 400.0]])
    write_data_mode_file(
        filename=str(tmp_path / 'landice_datamode.nc'),
        xtimes=xtimes,
        get_thickness=lambda index: records[index],
    )
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.run()
    finally:
        os.chdir(cwd)

    ds = xr.open_dataset(tmp_path / 'land_ice_fields.nc')
    assert [value.decode().strip() for value in ds.xtime.values] == xtimes
    expected = compute_land_ice_fields(
        read_map(str(tmp_path / 'map.nc')), records, bed
    )
    for name, field in expected.items():
        np.testing.assert_allclose(ds[name].values, field)
