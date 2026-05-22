import importlib
from configparser import ConfigParser
from unittest.mock import MagicMock

import pytest
import xarray as xr

from polaris.model_step import ModelStep
from polaris.ocean.model import OceanIOStep, OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.yaml import PolarisYaml


def _make_config(
    horiz_mesh_filename='mesh.nc',
    vert_coord_filename='vert_coord.nc',
    init_filename='init.nc',
):
    config = ConfigParser()
    config.add_section('ocean_model_files')
    config.set('ocean_model_files', 'horiz_mesh_filename', horiz_mesh_filename)
    config.set('ocean_model_files', 'vert_coord_filename', vert_coord_filename)
    config.set('ocean_model_files', 'init_filename', init_filename)
    return config


def test_write_initial_state_dataset_omega_drops_horiz_mesh_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            xCell=('nCells', [0.0, 1.0]),
            fCell=('nCells', [1.0, 2.0]),
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'temperature' not in ds_out
    assert 'XCell' not in ds_out
    assert 'FCell' not in ds_out


def test_write_initial_state_dataset_omega_drops_vert_coord_vars(tmp_path):
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'MinLayerCell' not in ds_out
    assert 'MaxLayerCell' not in ds_out
    assert 'BottomGeomDepth' not in ds_out
    assert 'VertCoordMovementWeights' not in ds_out


def test_write_initial_state_dataset_mpas_ocean_keeps_vert_coord_vars(
    tmp_path,
):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            temperature=(('nCells', 'nVertLevels'), [[3.0], [4.0]]),
            salinity=(('nCells', 'nVertLevels'), [[35.0], [35.0]]),
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'initial_state.nc'
    component.write_initial_state_dataset(ds, str(filename), config)

    ds_out = xr.open_dataset(filename)
    assert 'temperature' in ds_out
    assert 'minLevelCell' in ds_out
    assert 'maxLevelCell' in ds_out
    assert 'bottomDepth' in ds_out
    assert 'vertCoordMovementWeights' in ds_out


def test_write_vert_coord_dataset_noop_for_mpas_ocean(tmp_path):
    component = Ocean()
    component.model = 'mpas-ocean'
    component._read_var_map()

    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            bottomDepth=('nCells', [100.0, 200.0]),
        )
    )

    filename = tmp_path / 'vert_coord.nc'
    component.write_vert_coord_dataset(ds, str(filename), config)

    assert not filename.exists()


def test_process_inputs_and_outputs_resolves_model_input_filenames(
    monkeypatch,
):
    component = Ocean()
    component.model = 'omega'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(
        horiz_mesh_filename='custom_mesh.nc',
        vert_coord_filename='custom_vc.nc',
        init_filename='custom_init.nc',
    )

    step.add_horiz_mesh_input_file(work_dir_target='mesh_target.nc')
    step.add_vert_coord_input_file(work_dir_target='vc_target.nc')
    step.add_init_input_file(work_dir_target='init_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    input_data = {
        entry['work_dir_target']: entry['filename']
        for entry in step.input_data
        if entry.get('work_dir_target') is not None
    }
    assert input_data['mesh_target.nc'] == 'custom_mesh.nc'
    assert input_data['vc_target.nc'] == 'custom_vc.nc'
    assert input_data['init_target.nc'] == 'custom_init.nc'


def test_vert_coord_placeholder_skipped_for_mpas_ocean(monkeypatch):
    component = Ocean()
    component.model = 'mpas-ocean'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config()
    step.add_vert_coord_input_file(work_dir_target='vc_target.nc')

    monkeypatch.setattr(
        ModelStep, 'process_inputs_and_outputs', lambda _: None
    )

    step.process_inputs_and_outputs()

    filenames = [entry['filename'] for entry in step.input_data]
    assert 'vert_coord.nc' not in filenames
    assert '<<<vert_coord>>>' not in filenames


def test_dynamic_model_config_uses_model_input_filename_replacements():
    component = Ocean()
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )

    step.config = _make_config(
        horiz_mesh_filename='custom_mesh.nc',
        vert_coord_filename='custom_vc.nc',
        init_filename='custom_init.nc',
    )

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
    assert yaml.streams['InitialVertCoord']['Filename'] == 'custom_vc.nc'
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
