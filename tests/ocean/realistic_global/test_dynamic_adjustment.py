import logging
import os
import textwrap
from unittest import mock

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    STATS_FILENAMES,
    column_names,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    load_schedule_stages,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.task import (
    CONFIG_FILENAME,
    CONFIG_PACKAGE,
    FORWARD_CONFIG_FILENAME,
    FORWARD_CONFIG_PACKAGE,
    RealisticGlobalDynamicAdjustment,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate import (
    SUMMARY_FILENAME,
    Validate,
    _check_ke_flattening,
    _check_temperature_max,
)
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)

LOGGER = logging.getLogger('test_dynamic_adjustment')


def _config(mesh_name='icos240km'):
    """
    A config built the way RealisticGlobalDynamicAdjustment builds it, without
    the cost of constructing the whole task and its init steps.
    """
    config = PolarisConfigParser()
    config.add_from_package(FORWARD_CONFIG_PACKAGE, FORWARD_CONFIG_FILENAME)
    config.add_from_package(CONFIG_PACKAGE, CONFIG_FILENAME)
    add_realistic_global_mesh_config(config=config, mesh_name=mesh_name)
    return config


def _config_for_schedule(tmp_path, text, mesh_name='icos240km'):
    """A task config whose schedule override points at a written YAML file."""
    schedule = tmp_path / 'schedule.yaml'
    schedule.write_text(textwrap.dedent(text))
    override = tmp_path / 'override.cfg'
    override.write_text(f'[{SECTION}]\nschedule = {schedule}\n')
    config = _config(mesh_name)
    config.add_from_file(str(override))
    return config


def _task(mesh_name):
    """A dynamic-adjustment task for one mesh, with its combined config."""
    return RealisticGlobalDynamicAdjustment(
        component=Ocean(), mesh_name=mesh_name
    )


# --- task config ---


def test_task_config_has_the_forward_options():
    # a stage is a forward run, so the forward section has to be there
    config = _task('icos240km').config
    assert config.has_section('realistic_global_forward')
    assert config.has_section('realistic_global_dynamic_adjustment')
    assert config.getfloat('realistic_global_forward', 'mom_del4') == 1.2e11


def _hmix_scaling(mesh_name):
    return _task(mesh_name).config.get(
        'realistic_global_forward', 'hmix_scaling'
    )


def test_task_config_applies_per_mesh_overrides():
    # each per-mesh .cfg overrides hmix_scaling with the value that suits its
    # resolution, and a mesh with no .cfg keeps the forward default
    assert _hmix_scaling('u.oi30.lr10') == 'ref_cell_width'
    assert _hmix_scaling('u.oi6to18.lr6to10') == 'scale_with_mesh'
    assert _hmix_scaling('icos120km') == 'none'


def test_task_config_damping_is_off_by_default():
    # Rayleigh damping is turned on per stage by the schedule, not by config
    config = _task('u.oi30.lr10').config
    assert config.get('realistic_global_forward', 'damping').strip() == ''


# --- built-in schedules: parsing and chaining ---


def test_default_schedule_used_when_no_mesh_file():
    # qu240km has no per-mesh file, so it falls back to default.yaml
    stages = load_schedule_stages('qu240km', _config('qu240km'))
    assert [s.name for s in stages] == ['damped_adjustment_1', 'simulation']


def test_default_schedule_chaining():
    stages = load_schedule_stages('icos240km', _config('icos240km'))
    first, last = stages
    assert first.do_restart is False
    assert first.restart_in is None
    assert first.start_time == '0001-01-01_00:00:00'
    assert first.restart_out == 'restarts/rst.0001-01-02_00.00.00.nc'
    assert last.do_restart is True
    assert last.start_time == '0001-01-02_00:00:00'
    assert last.restart_in == first.restart_out
    assert last.restart_out == 'restarts/rst.0001-01-03_00.00.00.nc'


def test_shared_defaults_merged_and_damping_optional():
    stages = load_schedule_stages('u.oi30.lr10', _config('u.oi30.lr10'))
    # the shared block is applied to every stage
    assert all(s.mpaso_time_integrator == 'split_explicit_ab2' for s in stages)
    assert all(s.output_interval == '10_00:00:00' for s in stages)
    # damping is set on the damped stages and None on the final simulation
    assert stages[0].damping == pytest.approx(1.0e-4)
    assert stages[-1].name == 'simulation'
    assert stages[-1].damping is None


UNIFIED_SCHEDULE_MESHES = (
    'u.oi240.lr240',
    'u.oi30.lr10',
    'u.oi.so12to30.lr10',
    'u.oi6to18.lr6to10',
)


def _stage_count(mesh_name):
    return len(load_schedule_stages(mesh_name, _config(mesh_name)))


def test_per_mesh_schedule_counts():
    assert _stage_count('u.oi240.lr240') == 4
    assert _stage_count('u.oi30.lr10') == 4
    assert _stage_count('u.oi.so12to30.lr10') == 5
    assert _stage_count('u.oi6to18.lr6to10') == 8


@pytest.mark.parametrize('mesh_name', UNIFIED_SCHEDULE_MESHES)
def test_unified_schedules_run_the_ke_check(mesh_name):
    # the settling check is skipped below ke_check_num_stages stages, so every
    # unified mesh needs at least that many for validation to mean anything
    config = _config(mesh_name)
    ke_num = config.getint(SECTION, 'ke_check_num_stages')
    assert _stage_count(mesh_name) >= ke_num


@pytest.mark.parametrize('mesh_name', UNIFIED_SCHEDULE_MESHES)
def test_unified_schedules_end_undamped(mesh_name):
    # the chain ramps damping out and hands off an undamped restart
    stages = load_schedule_stages(mesh_name, _config(mesh_name))
    assert stages[-1].name == 'simulation'
    assert stages[-1].damping is None


@pytest.mark.parametrize('mesh_name', UNIFIED_SCHEDULE_MESHES)
def test_statistics_are_written_within_every_stage(mesh_name):
    """
    A stats interval longer than a stage means the only sample is the one
    written at startup, so the summary would report the state the stage began
    from rather than what it did.
    """
    for stage in load_schedule_stages(mesh_name, _config(mesh_name)):
        stats = duration_to_seconds(stage.stats_interval)
        duration = duration_to_seconds(stage.run_duration)
        assert stats <= duration, f'{mesh_name} {stage.name}'


def test_restart_chain_is_consistent():
    for mesh in UNIFIED_SCHEDULE_MESHES:
        stages = load_schedule_stages(mesh, _config(mesh))
        assert stages[0].do_restart is False
        for previous, current in zip(stages[:-1], stages[1:], strict=False):
            assert current.do_restart is True
            assert current.restart_in == previous.restart_out
            # each stage starts where the previous stage's restart was written
            assert previous.restart_out is not None
            filename_time = current.start_time.replace(':', '.')
            assert filename_time in previous.restart_out


# --- the restart chain, as the task and the step see it ---


def _forward_steps(task):
    """The task's forward steps, in schedule order."""
    return [
        step
        for step in task.steps.values()
        if isinstance(step, Forward) and step.stage is not None
    ]


def test_task_forward_steps_share_one_restarts_directory():
    # the restart paths are relative to the task work directory, so stage n's
    # restart_in has to resolve to the same place as stage n-1's restart_out
    task = _task('u.oi240.lr240')
    steps = _forward_steps(task)
    assert len(steps) == 4

    def resolve(step, path):
        return os.path.normpath(os.path.join(step.subdir, '..', path))

    previous = None
    for step in steps:
        stage = step.stage
        if previous is None:
            assert stage.restart_in is None
        else:
            assert resolve(step, stage.restart_in) == resolve(
                previous, previous.stage.restart_out
            )
        previous = step

    # and they all land in the one shared directory beside the stages
    restarts = f'{task.subdir.rsplit("/", 1)[0]}/restarts'
    for step in steps:
        assert resolve(step, step.stage.restart_out).startswith(restarts)


def test_forward_setup_declares_both_ends_of_the_restart_chain():
    stage = ForwardStage(
        name='damped_adjustment_2',
        restart_in='restarts/rst.0001-01-11_00.00.00.nc',
        restart_out='restarts/rst.0001-01-21_00.00.00.nc',
        do_restart=True,
    )
    step = _recording_forward_setup(stage)
    assert step.recorded_inputs == ['../restarts/rst.0001-01-11_00.00.00.nc']
    assert '../restarts/rst.0001-01-21_00.00.00.nc' in step.recorded_outputs


def test_forward_setup_declares_no_restart_for_a_lone_stage():
    # the simple `short` forward run is not part of a chain
    step = _recording_forward_setup(ForwardStage(name='short'))
    assert step.recorded_inputs == []
    assert step.recorded_outputs == []


def test_forward_setup_declares_no_restart_files_for_omega():
    # Omega's restart filename convention is unverified, so the chain is not
    # declared there rather than guessed at
    stage = ForwardStage(
        name='damped_adjustment_2',
        restart_in='restarts/rst.0001-01-11_00.00.00.nc',
        restart_out='restarts/rst.0001-01-21_00.00.00.nc',
        do_restart=True,
    )
    step = _recording_forward_setup(stage, model='omega')
    assert step.recorded_inputs == []
    assert step.recorded_outputs == []


class _RecordingForward(Forward):
    """
    Exercises ``Forward.setup``'s restart declarations without the cost (and
    the work directory) of setting up a real model step.  ``Forward.__init__``
    is deliberately not called; only the attributes ``setup`` touches are set.
    """

    def __init__(self, stage, model='mpas-ocean'):
        self.stage = stage
        self.init_condition = _NullInitialCondition()
        self.recorded_inputs = []
        self.recorded_outputs = []
        config = PolarisConfigParser()
        config.add_section('ocean')
        config.set('ocean', 'model', model)
        self.config = config

    def add_input_file(
        self,
        filename=None,
        target=None,
        database=None,
        database_component=None,
        url=None,
        work_dir_target=None,
        package=None,
        copy=False,
    ):
        self.recorded_inputs.append(filename)

    def add_output_file(
        self,
        filename,
        validate_vars=None,
        check_properties=None,
        validate_class=None,
    ):
        self.recorded_outputs.append(filename)


class _NullInitialCondition(InitialCondition):
    """An initial condition that stages nothing."""

    min_res = 240.0
    approx_cell_count = 10417

    def add_input_files(self, step):
        pass


def _recording_forward_setup(stage, model='mpas-ocean'):
    """Run ``Forward.setup`` on a recording step, with the base stubbed."""
    step = _RecordingForward(stage, model=model)
    with mock.patch.object(OceanModelStep, 'setup', lambda self: None):
        step.setup()
    return step


def test_model_replacements_carry_the_restart_state():
    """
    The schedule's chain has to reach the model: each stage after the first
    restarts, from the timestamp its predecessor's restart is named for.
    """
    stages = load_schedule_stages('u.oi240.lr240', _config('u.oi240.lr240'))
    first = stages[0].model_replacements('mpas-ocean', min_res=240.0)
    assert first['do_restart'] == 'false'
    assert first['start_time'] == '0001-01-01_00:00:00'

    second = stages[1].model_replacements('mpas-ocean', min_res=240.0)
    assert second['do_restart'] == 'true'
    assert second['start_time'] == '0001-01-11_00:00:00'
    assert stages[0].restart_out == 'restarts/rst.0001-01-11_00.00.00.nc'


# --- stages inherit the forward config ---


def test_stages_inherit_the_forward_physics_options():
    # these are the options the model needs and no schedule sets; before the
    # stages were built from config they all took their dataclass defaults,
    # which left horizontal mixing off
    for stage in load_schedule_stages('icos240km', _config('icos240km')):
        assert stage.mom_del2 == pytest.approx(1.0e3)
        assert stage.mom_del4 == pytest.approx(1.2e11)
        assert stage.use_GM is True
        assert stage.use_Redi is True


def test_stages_inherit_the_per_mesh_overrides():
    # u.oi6to18.lr6to10.cfg sets hmix_scaling for a variable-resolution mesh
    for stage in load_schedule_stages(
        'u.oi6to18.lr6to10', _config('u.oi6to18.lr6to10')
    ):
        assert stage.hmix_scaling == 'scale_with_mesh'
    for stage in load_schedule_stages('u.oi30.lr10', _config('u.oi30.lr10')):
        assert stage.hmix_scaling == 'ref_cell_width'


def test_stages_inherit_the_time_integrators():
    # neither is set in any shipped schedule any more
    for stage in load_schedule_stages('u.oi30.lr10', _config('u.oi30.lr10')):
        assert stage.mpaso_time_integrator == 'split_explicit_ab2'
        assert stage.omega_time_integrator == 'RK4'


def test_damping_is_off_in_config_and_turned_on_per_stage():
    # the config default is no Rayleigh damping; the schedule ramps it in and
    # back out, and the final simulation stage inherits the config default
    config = _config('u.oi30.lr10')
    assert ForwardStage.from_config(config).damping is None
    stages = load_schedule_stages('u.oi30.lr10', config)
    damping = [stage.damping for stage in stages]
    assert damping == [
        pytest.approx(1.0e-4),
        pytest.approx(1.0e-5),
        pytest.approx(1.0e-6),
        None,
    ]


def test_schedule_overrides_a_config_option(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 1_00:00:00
              mom_del2: 5.0e3
              use_GM: false
        """,
    )
    stage = load_schedule_stages('icos240km', config)[0]
    assert stage.mom_del2 == pytest.approx(5.0e3)
    assert stage.use_GM is False
    # and an option it does not mention still comes from config
    assert stage.mom_del4 == pytest.approx(1.2e11)


def test_blank_schedule_value_clears_an_optional_field(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 1_00:00:00
              mom_del4:
        """,
    )
    assert load_schedule_stages('icos240km', config)[0].mom_del4 is None


def test_restart_interval_defaults_to_the_stage_duration(tmp_path):
    # each stage has to write the restart the next one reads, so the config's
    # restart_interval is not what a stage of a different length wants
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 3_00:00:00
        """,
    )
    assert (
        load_schedule_stages('icos240km', config)[0].restart_interval
        == '3_00:00:00'
    )


def test_unknown_schedule_option_raises(tmp_path):
    # the old key name, split upstream into mpaso_/omega_time_integrator
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 1_00:00:00
              time_integrator: split_explicit_ab2
        """,
    )
    with pytest.raises(ValueError, match='time_integrator'):
        load_schedule_stages('icos240km', config)


def test_unknown_shared_option_raises(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          shared:
            nonsense: 1
          stages:
            only_stage:
              run_duration: 1_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='nonsense'):
        load_schedule_stages('icos240km', config)


def test_chain_owned_option_cannot_be_set_by_a_stage(tmp_path):
    # do_restart and the restart filenames follow from the chain, so a stage
    # that tried to set one would be silently ignored
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 1_00:00:00
              do_restart: true
        """,
    )
    with pytest.raises(ValueError, match='do_restart'):
        load_schedule_stages('icos240km', config)


def test_start_time_is_accepted_only_in_the_shared_block(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          shared:
            start_time: 0002-01-01_00:00:00
          stages:
            only_stage:
              run_duration: 1_00:00:00
        """,
    )
    assert (
        load_schedule_stages('icos240km', config)[0].start_time
        == '0002-01-01_00:00:00'
    )

    per_stage = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 1_00:00:00
              start_time: 0002-01-01_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='start_time'):
        load_schedule_stages('icos240km', per_stage)


# --- config override and per-km time steps ---


def test_schedule_config_override(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          shared:
            output_interval: 1_00:00:00
          stages:
            only_stage:
              run_duration: 1_00:00:00
              dt: 01:00:00
              btr_dt: 00:03:00
        """,
    )
    stages = load_schedule_stages('icos240km', config)
    assert [s.name for s in stages] == ['only_stage']
    assert stages[0].dt == '01:00:00'
    assert stages[0].btr_dt == '00:03:00'


def test_per_km_time_steps(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          shared:
            output_interval: 1_00:00:00
          stages:
            only_stage:
              run_duration: 1_00:00:00
              dt_per_km: 30.0
              btr_dt_per_km: 1.5
        """,
    )
    stage = load_schedule_stages('icos240km', config)[0]
    assert stage.dt is None
    assert stage.btr_dt is None
    assert stage.dt_per_km == 30.0
    assert stage.btr_dt_per_km == 1.5


# --- malformed schedules ---


def test_missing_dynamic_adjustment_key(tmp_path):
    config = _config_for_schedule(tmp_path, 'stages: {}\n')
    with pytest.raises(ValueError, match='dynamic_adjustment'):
        load_schedule_stages('icos240km', config)


def test_missing_stages(tmp_path):
    config = _config_for_schedule(
        tmp_path, 'dynamic_adjustment:\n  shared: {}\n'
    )
    with pytest.raises(ValueError, match='stages'):
        load_schedule_stages('icos240km', config)


def test_stage_not_a_mapping(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            bad_stage: 1_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='mapping'):
        load_schedule_stages('icos240km', config)


def test_missing_required_option(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              output_interval: 1_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='run_duration'):
        load_schedule_stages('icos240km', config)


# --- validation helpers ---


def test_check_temperature_max_passes():
    _check_temperature_max(30.0, 33.0, 'simulation', LOGGER)


def test_check_temperature_max_raises():
    with pytest.raises(ValueError, match='exceeds'):
        _check_temperature_max(40.0, 33.0, 'simulation', LOGGER)


def test_check_temperature_max_skipped_when_not_reported():
    # a model that reports no temperature has nothing to check
    _check_temperature_max(None, 33.0, 'simulation', LOGGER)


def test_ke_flattening_skipped_when_not_reported():
    _check_ke_flattening(['a', 'b', 'c'], [1.0, None, 3.0], 3, 0.01, LOGGER)


def test_ke_flattening_passes():
    names = ['a', 'b', 'c', 'd']
    max_ke = [10.0, 5.0, 4.0, 4.0]
    _check_ke_flattening(names, max_ke, 3, 0.01, LOGGER)


def test_ke_flattening_within_tolerance_passes():
    _check_ke_flattening(['a', 'b', 'c'], [5.0, 4.0, 4.02], 3, 0.01, LOGGER)


def test_ke_flattening_raises_on_increase():
    names = ['a', 'b', 'c', 'd']
    max_ke = [10.0, 4.0, 4.0, 5.0]
    with pytest.raises(ValueError, match='not settling'):
        _check_ke_flattening(names, max_ke, 3, 0.01, LOGGER)


def test_ke_flattening_skipped_when_too_few_stages():
    # fewer than ke_num stages: the check is skipped even if KE increases
    _check_ke_flattening(['a', 'b'], [1.0, 100.0], 3, 0.01, LOGGER)


# --- the validate step, for both models ---


def _write_stage_output(
    directory, stage_name, temperature, kinetic_energy, model
):
    """
    Write one stage's ``output.nc`` with the variable and dimension names the
    given model would have used.
    """
    if model == 'omega':
        names = dict(
            temperature='Temperature',
            kinetic_energy='KineticEnergyCell',
            dims=('time', 'NCells'),
        )
    else:
        names = dict(
            temperature='temperature',
            kinetic_energy='kineticEnergyCell',
            dims=('Time', 'nCells'),
        )
    dims = names['dims']
    ds = xr.Dataset(
        {
            names['temperature']: (dims, np.array(temperature)),
            names['kinetic_energy']: (dims, np.array(kinetic_energy)),
        }
    )
    work_dir = directory / 'validate'
    work_dir.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(work_dir / f'output_{stage_name}.nc')


def _validate_step(tmp_path, model, stages, temperature, kinetic_energy):
    """A Validate step with its stage outputs written, ready to run."""
    component = Ocean()
    component.model = model
    if model == 'omega':
        # normally done by Ocean.configure(); the maps are what let the
        # checks read an Omega output.nc with MPAS-Ocean names
        component._read_var_map()
    step = Validate(
        component=component,
        stages=[
            ForwardStage(name=name, run_duration='10_00:00:00')
            for name in stages
        ],
        indir='spherical/realistic_global/u.oi240.lr240/dynamic_adjustment',
    )
    config = _config('u.oi240.lr240')
    override = tmp_path / 'model.cfg'
    override.write_text(f'[ocean]\nmodel = {model}\n')
    config.add_from_file(str(override))
    step.config = config
    step.logger = LOGGER

    for index, stage_name in enumerate(stages):
        _write_stage_output(
            tmp_path,
            stage_name,
            temperature[index],
            kinetic_energy[index],
            model,
        )
    return step


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_validate_passes_a_settling_sequence(tmp_path, monkeypatch, model):
    stages = ['damped_1', 'damped_2', 'damped_3', 'simulation']
    step = _validate_step(
        tmp_path,
        model,
        stages,
        temperature=[[[10.0, 20.0]]] * 4,
        kinetic_energy=[
            [[1.0, 10.0]],
            [[1.0, 5.0]],
            [[1.0, 4.0]],
            [[1.0, 4.0]],
        ],
    )
    monkeypatch.chdir(tmp_path / 'validate')
    step.run()


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_validate_catches_a_blow_up_for_either_model(
    tmp_path, monkeypatch, model
):
    stages = ['damped_1', 'simulation']
    step = _validate_step(
        tmp_path,
        model,
        stages,
        temperature=[[[10.0, 20.0]], [[10.0, 99.0]]],
        kinetic_energy=[[[1.0, 2.0]], [[1.0, 2.0]]],
    )
    monkeypatch.chdir(tmp_path / 'validate')
    with pytest.raises(ValueError, match='exceeds'):
        step.run()


@pytest.mark.parametrize('model', ['mpas-ocean', 'omega'])
def test_validate_catches_growing_kinetic_energy(tmp_path, monkeypatch, model):
    stages = ['damped_1', 'damped_2', 'damped_3', 'simulation']
    step = _validate_step(
        tmp_path,
        model,
        stages,
        temperature=[[[10.0, 20.0]]] * 4,
        kinetic_energy=[
            [[1.0, 10.0]],
            [[1.0, 4.0]],
            [[1.0, 4.0]],
            [[1.0, 9.0]],
        ],
    )
    monkeypatch.chdir(tmp_path / 'validate')
    with pytest.raises(ValueError, match='not settling'):
        step.run()


# --- per-stage diagnostics ---


def _write_stage_stats(directory, stage_name, model, **series):
    """
    Write one stage's global-statistics file with the variable names the given
    model would have used.
    """
    if model == 'omega':
        names = {
            'kineticEnergyCellMax': None,  # Omega reports no kinetic energy
            'kineticEnergyCellAvg': None,
            'kineticEnergyCellSum': None,
            'volumeCellGlobal': None,
            'CFLNumberGlobal': None,
            'temperatureMax': 'Temperature_SpatialMax_TimeMean1Day',
            'temperatureMin': 'Temperature_SpatialMin_TimeMean1Day',
            'temperatureAvg': 'Temperature_SpatialMean_TimeMean1Day',
            'salinityMax': 'Salinity_SpatialMax_TimeMean1Day',
            'salinityMin': 'Salinity_SpatialMin_TimeMean1Day',
            'salinityAvg': 'Salinity_SpatialMean_TimeMean1Day',
            'layerThicknessMin': 'PseudoThickness_SpatialMin_TimeMean1Day',
            'normalVelocityMax': 'NormalVelocity_SpatialMax_TimeMean1Day',
        }
        time_dim = 'time'
    else:
        names = {key: key for key in series}
        time_dim = 'Time'

    data = {}
    for key, values in series.items():
        native = names.get(key, key)
        if native is None:
            continue
        data[native] = ((time_dim,), np.array(values, dtype=float))
    stats_dir = directory / stage_name
    stats_dir.mkdir(parents=True, exist_ok=True)
    filename = STATS_FILENAMES[model]
    xr.Dataset(data).to_netcdf(stats_dir / filename)


def _stats_series(ke_end, temperature_mean):
    """A plausible falling-kinetic-energy stage."""
    return dict(
        kineticEnergyCellMax=[ke_end * 1.4, ke_end * 1.2, ke_end],
        kineticEnergyCellAvg=[ke_end * 0.02, ke_end * 0.015, ke_end * 0.01],
        kineticEnergyCellSum=[
            ke_end * 2.0e18,
            ke_end * 1.6e18,
            ke_end * 1.3e18,
        ],
        volumeCellGlobal=[1.3e18] * 3,
        CFLNumberGlobal=[0.4, 0.35, 0.3],
        temperatureMax=[28.0, 29.0, 30.0],
        temperatureMin=[-1.9, -1.9, -1.9],
        temperatureAvg=[
            temperature_mean,
            temperature_mean - 0.005,
            temperature_mean - 0.01,
        ],
        salinityMax=[40.0, 40.0, 40.0],
        salinityMin=[3.0, 3.0, 3.0],
        salinityAvg=[34.7, 34.7, 34.7],
        layerThicknessMin=[1.5, 1.5, 1.5],
        normalVelocityMax=[2.0, 1.6, 1.2],
    )


def _run_with_stats(tmp_path, monkeypatch, model, stages, ke_end):
    """Run a Validate step that has both stats files and output.nc."""
    step = _validate_step(
        tmp_path,
        model,
        stages,
        temperature=[[[10.0, 20.0]]] * len(stages),
        kinetic_energy=[[[1.0, value]] for value in ke_end],
    )
    for index, stage_name in enumerate(stages):
        _write_stage_stats(
            tmp_path,
            stage_name,
            model,
            **_stats_series(ke_end[index], 3.5 - 0.01 * index),
        )
    monkeypatch.chdir(tmp_path / 'validate')
    step.run()
    return step


def test_diagnostics_summary_is_written(tmp_path, monkeypatch):
    stages = ['damped_1', 'damped_2', 'damped_3', 'simulation']
    _run_with_stats(
        tmp_path, monkeypatch, 'mpas-ocean', stages, [10.0, 5.0, 4.2, 4.1]
    )
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    assert len(lines) == len(stages) + 1

    header = lines[0].split(',')
    assert header[0] == 'stage'
    assert header[1] == 'kinetic_energy_max [m^2/s^2]'
    rows = {line.split(',')[0]: line.split(',')[1:] for line in lines[1:]}
    assert list(rows) == stages
    # the end-of-stage kinetic energy, from global statistics rather than the
    # end-of-stage field in output.nc
    assert float(rows['damped_2'][0]) == pytest.approx(5.0)


def test_diagnostics_prefer_global_statistics(tmp_path, monkeypatch):
    # output.nc says the max temperature is 20; the statistics say it reached
    # 30 partway through the stage, and the statistics are what is recorded
    stages = ['damped_1', 'simulation']
    _run_with_stats(tmp_path, monkeypatch, 'mpas-ocean', stages, [5.0, 4.0])
    columns = column_names()
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    values = dict(zip(columns, lines[1].split(',')[1:], strict=False))
    assert float(values['temperature_max_in_stage']) == pytest.approx(30.0)
    assert float(values['kinetic_energy_max_in_stage']) == pytest.approx(7.0)


def test_diagnostics_record_the_tracer_drift(tmp_path, monkeypatch):
    # temperatureAvg falls by 0.01 degC over a 10-day stage
    stages = ['damped_1', 'simulation']
    _run_with_stats(tmp_path, monkeypatch, 'mpas-ocean', stages, [5.0, 4.0])
    columns = column_names()
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    values = dict(zip(columns, lines[1].split(',')[1:], strict=False))
    assert float(values['temperature_drift_per_day']) == pytest.approx(-0.001)


def test_diagnostics_leave_unreported_metrics_blank(tmp_path, monkeypatch):
    # Omega reports no kinetic energy, CFL number or volume-weighted sums; the
    # volume-weighted means are left blank rather than replaced with unweighted
    # ones computed from output.nc
    stages = ['damped_1', 'simulation']
    _run_with_stats(tmp_path, monkeypatch, 'omega', stages, [5.0, 4.0])
    columns = column_names()
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    values = dict(zip(columns, lines[1].split(',')[1:], strict=False))
    assert values['kinetic_energy_mean'] == ''
    assert values['kinetic_energy_total'] == ''
    assert values['cfl_max_in_stage'] == ''
    # but the max is computed from output.nc, since a max is a max either way
    assert float(values['kinetic_energy_max']) == pytest.approx(5.0)
    # and what Omega does report still comes from the statistics
    assert float(values['temperature_max_in_stage']) == pytest.approx(30.0)


def test_diagnostics_fall_back_when_there_are_no_statistics(
    tmp_path, monkeypatch
):
    # no stats file at all: the step still runs, on output.nc alone
    stages = ['damped_1', 'simulation']
    step = _validate_step(
        tmp_path,
        'mpas-ocean',
        stages,
        temperature=[[[10.0, 20.0]]] * 2,
        kinetic_energy=[[[1.0, 5.0]], [[1.0, 4.0]]],
    )
    monkeypatch.chdir(tmp_path / 'validate')
    step.run()
    columns = column_names()
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    values = dict(zip(columns, lines[1].split(',')[1:], strict=False))
    assert float(values['kinetic_energy_max']) == pytest.approx(5.0)
    assert float(values['temperature_max_in_stage']) == pytest.approx(20.0)
    assert values['kinetic_energy_total'] == ''
    assert values['temperature_drift_per_day'] == ''


def test_blow_up_is_caught_mid_stage_from_the_statistics(
    tmp_path, monkeypatch
):
    # output.nc ends at a calm 20 degC, but the run passed through 99 degC
    # partway through the stage; the end-of-stage field alone would miss it
    stages = ['damped_1', 'simulation']
    step = _validate_step(
        tmp_path,
        'mpas-ocean',
        stages,
        temperature=[[[10.0, 20.0]]] * 2,
        kinetic_energy=[[[1.0, 5.0]], [[1.0, 4.0]]],
    )
    for index, stage_name in enumerate(stages):
        series = _stats_series([5.0, 4.0][index], 3.5)
        if stage_name == 'damped_1':
            series['temperatureMax'] = [28.0, 99.0, 30.0]
        _write_stage_stats(tmp_path, stage_name, 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'validate')
    with pytest.raises(ValueError, match='exceeds'):
        step.run()
