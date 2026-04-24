import importlib
from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.constants import get_constant
from polaris.model_step import ModelStep
from polaris.ocean.coriolis import (
    add_beta_plane_coriolis,
    add_constant_coriolis,
    add_rotated_sphere_coriolis,
)
from polaris.ocean.model import OceanIOStep, OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.yaml import PolarisYaml


def test_write_initial_state_dataset_omega_drops_horiz_mesh_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    ds = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0]),
            fCell=('nCells', [1.0, 2.0]),
            temperature=(('Time', 'nCells'), [[3.0, 4.0]]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename))

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'temperature' not in ds_out
    assert 'XCell' not in ds_out
    assert 'FCell' not in ds_out


def test_write_model_dataset_omega_keeps_horiz_mesh_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    ds = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0]),
            fCell=('nCells', [1.0, 2.0]),
        )
    )

    filename = tmp_path / 'mesh.nc'
    component.write_model_dataset(ds, str(filename))

    ds_out = xr.open_dataset(filename)
    assert 'XCell' in ds_out
    assert 'FCell' in ds_out
    assert 'xCell' not in ds_out
    assert 'fCell' not in ds_out


def test_add_constant_coriolis_populates_all_mesh_locations():
    ds_mesh = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0]),
            xEdge=('nEdges', [0.0, 1.0, 2.0]),
            xVertex=('nVertices', [0.0, 1.0]),
        )
    )

    add_constant_coriolis(ds_mesh, coriolis_parameter=1.0e-4)

    assert np.all(ds_mesh.fCell.values == 1.0e-4)
    assert np.all(ds_mesh.fEdge.values == 1.0e-4)
    assert np.all(ds_mesh.fVertex.values == 1.0e-4)
    assert ds_mesh.fCell.attrs['standard_name'] == 'coriolis_parameter'


def test_add_beta_plane_coriolis_uses_each_mesh_coordinate():
    ds_mesh = xr.Dataset(
        data_vars=dict(
            yCell=('nCells', [0.0, 2.0]),
            yEdge=('nEdges', [-1.0, 3.0]),
            yVertex=('nVertices', [4.0]),
            xCell=('nCells', [0.0, 0.0]),
            xEdge=('nEdges', [0.0, 0.0]),
            xVertex=('nVertices', [0.0]),
        )
    )

    add_beta_plane_coriolis(ds_mesh, f0=1.0, beta=2.0)

    np.testing.assert_allclose(ds_mesh.fCell.values, [1.0, 5.0])
    np.testing.assert_allclose(ds_mesh.fEdge.values, [-1.0, 7.0])
    np.testing.assert_allclose(ds_mesh.fVertex.values, [9.0])


def test_add_rotated_sphere_coriolis_matches_alpha_zero_formula():
    omega = get_constant('angular_velocity')
    lat = np.array([-np.pi / 6.0, np.pi / 6.0])
    ds_mesh = xr.Dataset(
        data_vars=dict(
            lonCell=('nCells', [0.0, 1.0]),
            latCell=('nCells', lat),
            lonEdge=('nEdges', [0.0, 1.0]),
            latEdge=('nEdges', lat),
            lonVertex=('nVertices', [0.0, 1.0]),
            latVertex=('nVertices', lat),
            xCell=('nCells', [0.0, 1.0]),
            xEdge=('nEdges', [0.0, 1.0]),
            xVertex=('nVertices', [0.0, 1.0]),
        )
    )

    add_rotated_sphere_coriolis(ds_mesh, alpha=0.0, omega=omega)

    expected = 2.0 * omega * np.sin(lat)
    np.testing.assert_allclose(ds_mesh.fCell.values, expected)
    np.testing.assert_allclose(ds_mesh.fEdge.values, expected)
    np.testing.assert_allclose(ds_mesh.fVertex.values, expected)


def test_process_inputs_and_outputs_resolves_model_input_filenames(
    monkeypatch,
):
    component = Ocean()
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    config = ConfigParser()
    config.add_section('ocean_model_files')
    config.set('ocean_model_files', 'horiz_mesh_filename', 'custom_mesh.nc')
    config.set('ocean_model_files', 'init_filename', 'custom_init.nc')
    step.config = config  # type: ignore[assignment]

    step.add_horiz_mesh_input_file(target='mesh_target.nc')
    step.add_init_input_file(target='init_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    input_data = {
        entry['target']: entry['filename']
        for entry in step.input_data
        if entry['target'] is not None
    }
    assert input_data['mesh_target.nc'] == 'custom_mesh.nc'
    assert input_data['init_target.nc'] == 'custom_init.nc'


def test_dynamic_model_config_uses_model_input_filename_replacements():
    component = Ocean()
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    config = ConfigParser()
    config.add_section('ocean_model_files')
    config.set('ocean_model_files', 'horiz_mesh_filename', 'custom_mesh.nc')
    config.set('ocean_model_files', 'init_filename', 'custom_init.nc')
    step.config = config  # type: ignore[assignment]

    step.dynamic_model_config(at_setup=True)

    entry = step.model_config_data[0]
    yaml = PolarisYaml.read(
        filename=entry['yaml'],
        package=entry['package'],
        replacements=entry['replacements'],
        model='Omega',
        streams_section='IOStreams',
    )
    assert yaml.streams['HorzMeshIn']['Filename'] == 'custom_mesh.nc'
    assert yaml.streams['InitialVertCoord']['Filename'] == 'custom_init.nc'
    assert yaml.streams['InitialState']['Filename'] == 'custom_init.nc'


@pytest.mark.parametrize(
    'module_name',
    [
        'polaris.tasks.ocean.baroclinic_channel.init',
        'polaris.tasks.ocean.barotropic_channel.init',
        'polaris.tasks.ocean.geostrophic.init',
        'polaris.tasks.ocean.ice_shelf_2d.init',
        'polaris.tasks.ocean.inertial_gravity_wave.init',
        'polaris.tasks.ocean.internal_wave.init',
        'polaris.tasks.ocean.single_column.init',
    ],
)
def test_init_steps_with_ocean_model_io_descend_from_ocean_io_step(
    module_name,
):
    module = importlib.import_module(module_name)
    assert issubclass(module.Init, OceanIOStep)
