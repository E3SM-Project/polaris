import os

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.omega_initial_condition import (
    STATE_VARS,
    OmegaInitialConditionStep,
)
from polaris.tasks.e3sm.init.component_inputs.steps import (
    component_inputs_subdir,
    get_component_inputs_config,
    get_component_inputs_steps,
)
from polaris.tasks.e3sm.init.component_inputs.task import ComponentInputsTask
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'u-oi240-lr240'
BASE = f'e3sm/init/{component_inputs_subdir(MESH_NAME)}'


def test_omega_stages_only_what_omega_reads():
    """
    Omega partitions its mesh at run time and does not read region masks
    yet, and the culled ocean mesh is made from MPAS-Ocean's initial state.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='all', model='omega'
    )
    for key in ['ocean_graph_partition', 'ocean_moc_masks', 'ocean_mesh']:
        assert key not in steps, key
    assert isinstance(
        steps['ocean_initial_condition'], OmegaInitialConditionStep
    )
    assert 'seaice_initial_condition' in steps
    # and nothing of MPAS-Ocean's is set up
    stale = [s.path for s in steps.values() if '/mpas-ocean/' in s.path]
    assert not stale, stale


def test_the_omega_initial_condition_reads_omegas_adjustment():
    """
    The mesh and vertical coordinate from Omega's initial state, and the state
    from the restart Omega wrote at the end of its final stage, which it
    waits for along with that stage's check.
    """
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='ocean', model='omega'
    )
    step = steps['ocean_initial_condition']
    targets = {
        entry['filename']: entry['work_dir_target']
        for entry in step.input_data
    }
    init_path = steps['initial_state'].path
    assert '/init/omega/' in init_path
    assert targets['mesh.nc'] == f'{init_path}/mesh.nc'
    assert targets['vert_coord.nc'] == f'{init_path}/vert_coord.nc'
    assert '/dynamic_adjustment/omega/restarts/' in targets['restart.nc']
    assert os.path.basename(targets['restart.nc']).startswith('ocn.restart.')
    dependencies = step.dependencies.values()
    assert any(dep is steps['simulation'] for dep in dependencies)
    assert any(dep is steps['simulation_check'] for dep in dependencies)


def test_each_models_steps_have_a_directory_and_config_of_their_own():
    _reset_shared_components()
    mpaso, mpaso_config = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='all', model='mpas-ocean'
    )
    omega, omega_config = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='all', model='omega'
    )
    assert mpaso_config.filepath == f'{BASE}/mpas-ocean/component_inputs.cfg'
    assert omega_config.filepath == f'{BASE}/omega/component_inputs.cfg'

    for model, steps, config in [
        ('mpas-ocean', mpaso, mpaso_config),
        ('omega', omega, omega_config),
    ]:
        for key in ['ocean_initial_condition', 'assemble_all']:
            assert steps[key].path.startswith(f'{BASE}/{model}/'), key
            assert steps[key].config is config, key

    # the model-neutral steps are the same instances for both models
    neutral = get_component_inputs_config(MESH_NAME)
    for key in ['staged_base_mesh', 'scrip', 'seaice_initial_condition']:
        assert omega[key] is mpaso[key], key
        assert omega[key].config is neutral, key


def test_the_mesh_date_comes_from_the_work_directorys_record(
    tmp_path, monkeypatch
):
    """
    A second model set up in a work directory has to stamp the mesh's
    products with the date already used for them, which is recorded in the
    model-neutral config file every setup writes, and gets an ocean date of
    its own.
    """
    _reset_shared_components()
    monkeypatch.setattr(ocean, 'model', 'omega')
    task = ComponentInputsTask(
        component=e3sm_init, mesh_name=MESH_NAME, target='all', model='omega'
    )
    neutral = get_component_inputs_config(MESH_NAME)
    recorded = tmp_path / neutral.filepath
    recorded.parent.mkdir(parents=True)
    recorded.write_text('[component_inputs]\ncreation_date = 20240101\n')
    task.config.set('paths', 'base_work_dir', str(tmp_path))

    task.configure()

    assert task.config.get('component_inputs', 'creation_date') == '20240101'
    assert neutral.get('component_inputs', 'creation_date') == '20240101'
    ocean_date = task.config.get('component_inputs', 'ocean_creation_date')
    assert ocean_date not in ['', '20240101']


def test_a_task_set_up_for_another_model_is_refused(monkeypatch):
    _reset_shared_components()
    monkeypatch.setattr(ocean, 'model', 'mpas-ocean')
    task = ComponentInputsTask(
        component=e3sm_init, mesh_name=MESH_NAME, target='ocean', model='omega'
    )
    with pytest.raises(ValueError, match='omega.*mpas-ocean'):
        task.configure()


def test_the_initial_condition_merges_the_mesh_and_the_adjusted_state(
    tmp_path,
):
    step = _initial_condition_step(tmp_path)
    _write_inputs(tmp_path)

    _run(step, tmp_path)

    with xr.open_dataset(tmp_path / 'ocean_initial_condition.nc') as ds:
        assert 'AreaCell' in ds
        assert 'MaxLayerCell' in ds
        for var in STATE_VARS:
            assert var in ds, var
        # the state is the restart's, not anything from the initial state
        np.testing.assert_array_equal(
            ds.Temperature.values, np.full((1, 3, 2), 7.0)
        )
        # the restart's own fields that are not part of the state are left
        assert 'NormalBarotropicVelocity' not in ds
        # the restart's time says where the adjustment ended
        assert 'time' not in ds.variables
        assert 'SimulationTime' not in ds.attrs
        assert ds.sizes['time'] == 1


def test_a_restart_missing_part_of_the_state_is_reported(tmp_path):
    step = _initial_condition_step(tmp_path)
    _write_inputs(tmp_path, drop='SurfacePressure')
    with pytest.raises(ValueError, match='SurfacePressure'):
        _run(step, tmp_path)


def _initial_condition_step(tmp_path):
    _reset_shared_components()
    steps, _ = get_component_inputs_steps(
        mesh_name=MESH_NAME, target='ocean', model='omega'
    )
    step = steps['ocean_initial_condition']
    step.work_dir = str(tmp_path)
    return step


def _write_inputs(tmp_path, drop=None):
    """Small stand-ins for Omega's mesh, vertical coordinate and restart."""
    ds_mesh = xr.Dataset({'AreaCell': ('NCells', np.ones(3))})
    ds_mesh.to_netcdf(tmp_path / 'mesh.nc')
    ds_vert = xr.Dataset({'MaxLayerCell': ('NCells', np.full(3, 2))})
    ds_vert.to_netcdf(tmp_path / 'vert_coord.nc')

    cell_layers = ('time', 'NCells', 'NVertLayers')
    edge_layers = ('time', 'NEdges', 'NVertLayers')
    ds_restart = xr.Dataset(
        {
            'NormalVelocity': (edge_layers, np.zeros((1, 4, 2))),
            'PseudoThickness': (cell_layers, np.ones((1, 3, 2))),
            'SurfacePressure': (('time', 'NCells'), np.zeros((1, 3))),
            'Temperature': (cell_layers, np.full((1, 3, 2), 7.0)),
            'Salinity': (cell_layers, np.full((1, 3, 2), 35.0)),
            'NormalBarotropicVelocity': (('time', 'NEdges'), np.zeros((1, 4))),
        },
        coords={'time': ('time', [40.0])},
        attrs={'SimulationTime': '0001-02-10_00:00:00'},
    )
    if drop is not None:
        ds_restart = ds_restart.drop_vars(drop)
    ds_restart.to_netcdf(tmp_path / 'restart.nc')


def _run(step, tmp_path):
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        step.run()
    finally:
        os.chdir(cwd)


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
