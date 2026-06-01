import importlib
from configparser import ConfigParser
from unittest.mock import MagicMock

import pytest
import xarray as xr

from polaris.model_step import ModelStep
from polaris.ocean.model import OceanIOStep, OceanModelStep, io
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
    io.write_initial_state_dataset(ds, str(filename), config, model='omega')

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'temperature' not in ds_out
    assert 'XCell' not in ds_out
    assert 'FCell' not in ds_out


def test_write_initial_state_dataset_omega_drops_vert_coord_vars(tmp_path):
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
    io.write_initial_state_dataset(ds, str(filename), config, model='omega')

    ds_out = xr.open_dataset(filename)
    assert 'Temperature' in ds_out
    assert 'MinLayerCell' not in ds_out
    assert 'MaxLayerCell' not in ds_out
    assert 'BottomGeomDepth' not in ds_out
    assert 'VertCoordMovementWeights' not in ds_out


def test_write_initial_state_dataset_mpas_ocean_keeps_vert_coord_vars(
    tmp_path,
):
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
    io.write_initial_state_dataset(
        ds, str(filename), config, model='mpas-ocean'
    )

    ds_out = xr.open_dataset(filename)
    assert 'temperature' in ds_out
    assert 'minLevelCell' in ds_out
    assert 'maxLevelCell' in ds_out
    assert 'bottomDepth' in ds_out
    assert 'vertCoordMovementWeights' in ds_out


def test_write_vert_coord_dataset_noop_for_mpas_ocean(tmp_path):
    config = MagicMock()

    ds = xr.Dataset(
        data_vars=dict(
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
            restingThickness=(('nCells', 'nVertLevels'), [[50.0], [100.0]]),
            vertCoordMovementWeights=('nVertLevels', [1.0]),
        )
    )

    filename = tmp_path / 'vert_coord.nc'
    io.write_vert_coord_dataset(ds, str(filename), config, model='mpas-ocean')

    assert not filename.exists()


@pytest.mark.parametrize(
    'model,missing_var',
    [
        ('mpas-ocean', 'restingThickness'),
        ('omega', 'RefPseudoThickness'),
    ],
)
def test_write_vert_coord_dataset_raises_on_missing_vars(
    tmp_path, model, missing_var
):
    config = MagicMock()

    # omit the model-specific thickness var and vertCoordMovementWeights
    ds = xr.Dataset(
        data_vars=dict(
            minLevelCell=('nCells', [0, 0]),
            maxLevelCell=('nCells', [0, 0]),
            bottomDepth=('nCells', [100.0, 200.0]),
        )
    )

    filename = tmp_path / 'vert_coord.nc'
    with pytest.raises(ValueError, match=missing_var):
        io.write_vert_coord_dataset(ds, str(filename), config, model=model)


def _make_horiz_mesh_ds(model):
    """Build a minimal dataset with all horiz_mesh_vars as dummy data."""
    horiz_mesh_vars, _ = io._get_variable_lists(model)
    return xr.Dataset(
        data_vars={v: ('nCells', [0.0, 1.0]) for v in horiz_mesh_vars}
    )


def test_write_horiz_mesh_dataset_raises_on_missing_vars(tmp_path):
    config = MagicMock()

    # dataset is missing most horiz_mesh_vars
    ds = xr.Dataset(data_vars=dict(xCell=('nCells', [0.0, 1.0])))

    filename = tmp_path / 'mesh.nc'
    with pytest.raises(ValueError, match='indexToCellID'):
        io.write_horiz_mesh_dataset(
            ds, str(filename), config, model='mpas-ocean'
        )


def test_write_horiz_mesh_dataset_writes_mpas_ocean(tmp_path):
    config = MagicMock()
    ds = _make_horiz_mesh_ds('mpas-ocean')

    filename = tmp_path / 'mesh.nc'
    io.write_horiz_mesh_dataset(ds, str(filename), config, model='mpas-ocean')

    ds_out = xr.open_dataset(filename)
    assert 'xCell' in ds_out
    assert 'fCell' in ds_out


def test_write_horiz_mesh_dataset_writes_omega(tmp_path):
    config = MagicMock()
    ds = _make_horiz_mesh_ds('omega')

    filename = tmp_path / 'mesh.nc'
    io.write_horiz_mesh_dataset(ds, str(filename), config, model='omega')

    ds_out = xr.open_dataset(filename)
    assert 'XCell' in ds_out
    assert 'FCell' in ds_out
    assert 'xCell' not in ds_out


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


def _make_tasks(steps):
    """Return a list of one mock task containing the given steps."""
    task = MagicMock()
    task.steps = {s.name: s for s in steps}
    return [task]


def _make_agnostic_io_step(name='io_step'):
    """OceanIOStep with no self.model (agnostic — reads from config)."""
    component = Ocean()
    step = OceanIOStep(component=component, name=name)
    return step


def _make_fixed_io_step(model, name='fixed_step'):
    """OceanIOStep with self.model set at construction time."""
    component = Ocean()
    step = OceanIOStep(component=component, name=name)
    step.model = model
    return step


class TestOceanConfigure:
    """Tests for Ocean.configure() model-detection enforcement."""

    def _config(self, model='detect'):
        cfg = MagicMock()
        cfg.__getitem__ = lambda self_, key: MagicMock(
            **{'get.return_value': model}
        )
        cfg.get = MagicMock(return_value=model)
        return cfg

    def test_no_ocean_steps_detect_becomes_unknown(self):
        ocean = Ocean()
        plain_step = MagicMock()
        plain_step.name = 'plain'
        # plain_step is not an OceanIOStep or OceanModelStep
        tasks = _make_tasks([plain_step])
        cfg = self._config(model='detect')
        ocean.configure(cfg, tasks)
        assert ocean.model == 'unknown'

    def test_agnostic_io_step_with_explicit_model_succeeds(self):
        ocean = Ocean()
        step = _make_agnostic_io_step()
        tasks = _make_tasks([step])
        # model='omega' skips the detect branch entirely
        cfg = self._config(model='omega')
        cfg.add_from_package = MagicMock()
        ocean.configure(cfg, tasks)
        assert ocean.model == 'omega'
        cfg.add_from_package.assert_called_once_with(
            'polaris.ocean', 'omega.cfg'
        )

    def test_agnostic_io_step_no_model_raises(self, monkeypatch):
        """When --model is not given and only agnostic IO steps exist,
        configure() must raise (via _detect_model) rather than return
        silently with model='unknown'."""
        ocean = Ocean()
        step = _make_agnostic_io_step()
        tasks = _make_tasks([step])
        cfg = self._config(model='detect')
        cfg.add_from_package = MagicMock()

        # Simulate no binary found for either model
        monkeypatch.setattr(
            ocean.__class__, '_detect_omega_build', lambda self_, p: False
        )
        monkeypatch.setattr(
            ocean.__class__,
            '_detect_mpas_ocean_build',
            lambda self_, p: False,
        )
        # _detect_model reads component_path from copies of config;
        # patch copy() to return a simple mock that exposes get()
        cfg_copy = MagicMock()
        cfg_copy.get = MagicMock(return_value='/fake/path')
        cfg.copy = MagicMock(return_value=cfg_copy)
        cfg_copy.add_from_package = MagicMock()

        with pytest.raises(ValueError, match='Could not detect ocean model'):
            ocean.configure(cfg, tasks)

    def test_fixed_io_step_no_model_flag_succeeds(self, monkeypatch):
        """When only model-fixed IO steps exist, configure() must succeed
        without requiring --model, and self.model is set to 'unknown'."""
        ocean = Ocean()
        step = _make_fixed_io_step(model='omega')
        tasks = _make_tasks([step])
        cfg = self._config(model='detect')
        cfg.add_from_package = MagicMock()
        ocean.configure(cfg, tasks)
        assert ocean.model == 'unknown'
        cfg.add_from_package.assert_called_once_with(
            'polaris.ocean', 'omega.cfg'
        )


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
