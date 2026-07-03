from configparser import ConfigParser
from typing import cast

import pytest

from polaris import Step
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean.realistic_global.forward import (
    DatabaseInitialCondition,
    ForwardStage,
    StepInitialCondition,
)


def _forward_config(**overrides):
    """A minimal ``[realistic_global_forward]`` config for stage tests."""
    values = dict(
        time_integrator='split_explicit_ab2',
        run_duration='0030_00:00:00',
        output_interval='0010_00:00:00',
        restart_interval='',
        dt_per_km='30.0',
        btr_dt_per_km='1.5',
        dt='',
        btr_dt='',
        Rayleigh_damping_coeff='',
        start_time='0001-01-01_00:00:00',
    )
    values.update(overrides)
    config = ConfigParser()
    config.add_section('realistic_global_forward')
    for key, value in values.items():
        config.set('realistic_global_forward', key, value)
    return config


class _FakeStep:
    """Records the input files an InitialCondition adds to a forward step."""

    def __init__(self, model='mpas-ocean', eos_type='teos-10', path='WORK'):
        self.path = path
        self.calls = []
        self.config = ConfigParser()
        self.config.add_section('ocean')
        self.config.set('ocean', 'model', model)
        self.config.set('ocean', 'eos_type', eos_type)

    def add_horiz_mesh_input_file(self, **kwargs):
        self.calls.append(('horiz_mesh', kwargs))

    def add_vert_coord_input_file(self, **kwargs):
        self.calls.append(('vert_coord', kwargs))

    def add_init_input_file(self, **kwargs):
        self.calls.append(('init', kwargs))


# --- ForwardStage ---


def test_from_config_defaults_and_restart_default():
    stage = ForwardStage.from_config(_forward_config())
    assert stage.run_duration == '0030_00:00:00'
    assert stage.output_interval == '0010_00:00:00'
    # a blank restart_interval defaults to run_duration
    assert stage.restart_interval == '0030_00:00:00'
    assert stage.dt is None
    assert stage.btr_dt is None
    assert stage.dt_per_km == 30.0
    assert stage.btr_dt_per_km == 1.5
    assert stage.damping is None
    assert stage.do_restart is False


def test_model_replacements_mpas_ocean_from_per_km():
    stage = ForwardStage.from_config(_forward_config())
    rep = stage.model_replacements('mpas-ocean', min_res=30.0)
    assert rep['dt'] == '0000_00:15:00.000'  # 30 s/km * 30 km = 900 s
    assert rep['btr_dt'] == '0000_00:00:45.000'  # 1.5 s/km * 30 km = 45 s
    assert rep['time_integrator'] == 'split_explicit_ab2'
    assert rep['output_freq'] == '864000'  # 10 days
    assert rep['restart_freq'] == '2592000'  # 30 days (restart == run)
    assert rep['do_restart'] == 'false'
    assert rep['start_time'] == '0001-01-01_00:00:00'


def test_model_replacements_explicit_dt_overrides_per_km():
    stage = ForwardStage.from_config(
        _forward_config(dt='00:10:00', btr_dt='00:00:15')
    )
    rep = stage.model_replacements('mpas-ocean', min_res=999.0)
    assert rep['dt'] == '00:10:00'
    assert rep['btr_dt'] == '00:00:15'


def test_model_replacements_omega_maps_rk4():
    stage = ForwardStage.from_config(_forward_config(time_integrator='RK4'))
    rep = stage.model_replacements('omega', min_res=30.0)
    assert rep['time_integrator'] == 'RungeKutta4'


def test_model_replacements_omega_rejects_split_explicit():
    stage = ForwardStage.from_config(_forward_config())  # split_explicit_ab2
    with pytest.raises(ValueError, match='not supported for Omega'):
        stage.model_replacements('omega', min_res=30.0)


def test_model_replacements_requires_a_time_step():
    stage = ForwardStage.from_config(_forward_config(dt_per_km=''))
    with pytest.raises(ValueError, match='dt_per_km'):
        stage.model_replacements('mpas-ocean', min_res=30.0)


def test_bottom_drag_options():
    assert ForwardStage().bottom_drag_options() == {}
    options = ForwardStage(damping=1.0e-4).bottom_drag_options()
    assert options == {
        'config_implicit_bottom_drag_type': 'constant_and_rayleigh',
        'config_Rayleigh_damping_coeff': 1.0e-4,
    }


# --- InitialCondition sources ---


def test_step_initial_condition_wires_inputs_and_graph():
    path = 'ocean/spherical/realistic_global/icos240km/init/initial_state'
    ic = StepInitialCondition(cast(Step, _FakeStep(path=path)))
    assert ic.graph_target == f'{path}/culled_graph.info'

    forward = _FakeStep()
    ic.add_input_files(cast(OceanModelStep, forward))
    by_kind = dict(forward.calls)
    assert set(by_kind) == {'horiz_mesh', 'vert_coord', 'init'}
    assert by_kind['horiz_mesh']['work_dir_target'] == f'{path}/mesh.nc'
    assert by_kind['vert_coord']['work_dir_target'] == f'{path}/vert_coord.nc'
    assert by_kind['init']['work_dir_target'] == f'{path}/init.nc'


def test_database_initial_condition_mpas_ocean():
    ic = DatabaseInitialCondition(mesh_name='QU240km', mesh_id=151209)
    assert ic.graph_target is None

    step = _FakeStep(model='mpas-ocean', eos_type='teos-10')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    # only the initial condition is pulled from the database for MPAS-Ocean
    assert set(by_kind) == {'init'}
    assert by_kind['init']['target'] == 'ocean.QU240km.151209.teos10.nc'
    assert by_kind['init']['database'] == 'realistic_global/mpas-ocean'


def test_database_initial_condition_omega_also_adds_mesh():
    ic = DatabaseInitialCondition(
        mesh_name='QU240km', mesh_id=151209, eos_type='teos10'
    )
    step = _FakeStep(model='omega')
    ic.add_input_files(cast(OceanModelStep, step))
    by_kind = dict(step.calls)
    assert set(by_kind) == {'init', 'horiz_mesh'}
    target = 'ocean.QU240km.151209.teos10.nc'
    assert by_kind['init']['target'] == target
    assert by_kind['horiz_mesh']['target'] == target
    assert by_kind['horiz_mesh']['database'] == 'realistic_global/omega'
