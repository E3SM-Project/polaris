import logging
import os
import textwrap
from unittest import mock

import matplotlib
import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds
from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.checks import (
    check_cfl_max,
    check_salinity_max,
    check_temperature_max,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    STATS_FILENAMES,
    column_names,
    extreme_and_day,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    excluded_days_in_stage,
    load_schedule_stages,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps import (
    CONFIG_FILENAME,
    CONFIG_PACKAGE,
    FORWARD_CONFIG_FILENAME,
    FORWARD_CONFIG_PACKAGE,
    get_realistic_dynamic_adjustment_steps,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.task import (
    RealisticGlobalDynamicAdjustment,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate import (
    SUMMARY_FILENAME,
    StageCheck,
    Validate,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.viz import (
    FIGURE_FILENAME,
    VizDynamicAdjustmentStep,
    _short_stage_name,
)
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
from polaris.tasks.ocean.realistic_global.forward.initial_condition import (
    InitialCondition,
)
from polaris.tasks.ocean.realistic_global.mesh_configs import (
    add_realistic_global_mesh_config,
)

matplotlib.use('Agg')

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
    # each per-mesh .cfg overrides the mixing options to suit its resolution,
    # and a mesh with no .cfg keeps the forward defaults
    assert _hmix_scaling('u.oi30.lr10') == 'ref_cell_width'
    assert _hmix_scaling('u.oi6to18.lr6to10') == 'ref_cell_width'
    assert _hmix_scaling('icos120km') == 'none'
    # the reference width is what differs, since E3SM's per-grid coefficients
    # are referenced to the finest cells of their own mesh
    assert (
        _task('u.oi6to18.lr6to10').config.getfloat(
            'realistic_global_forward', 'hmix_ref_cell_width'
        )
        == 6.0e3
    )


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
def test_unified_schedules_ramp_the_damping_down(mesh_name):
    """
    The point of the sequence is to relax the damping towards zero, so each
    damped stage must damp no harder than the one before it.  A stage that
    raised the damping again would be undoing its predecessor's work.
    """
    damping = [
        stage.damping
        for stage in load_schedule_stages(mesh_name, _config(mesh_name))
        if stage.damping is not None
    ]
    assert len(damping) >= 2, mesh_name
    for previous, current in zip(damping[:-1], damping[1:], strict=False):
        assert current <= previous, f'{mesh_name}: {damping}'


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


# --- shared steps ---


def test_steps_are_shared_between_consumers():
    """
    A downstream workflow that wants the adjusted restart -- e3sm/init's
    component inputs -- asks for these steps too.  It has to get the same
    instances, or the whole chain would be set up and run a second time.
    """
    component = Ocean()
    task = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name='u.oi240.lr240'
    )
    before = {
        step.subdir: dict(step.dependencies)
        for step in _forward_steps(task) + _check_steps(task)
    }

    steps, _, stages = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240'
    )
    by_subdir = {step.subdir: step for step in task.steps.values()}
    for step in _adjustment_steps(steps).values():
        assert by_subdir[step.subdir] is step, step.subdir
    assert [stage.name for stage in stages] == [
        step.name for step in _forward_steps(task)
    ]
    # the restart chain is wired from the helper rather than from a step
    # constructor, so the second call asks for it again; that has to leave it
    # exactly as it was
    after = {
        step.subdir: dict(step.dependencies)
        for step in _forward_steps(task) + _check_steps(task)
    }
    assert after == before
    assert any(deps for deps in before.values())


def _check_steps(task):
    """The task's per-stage check steps."""
    return [
        step for step in task.steps.values() if isinstance(step, StageCheck)
    ]


def test_every_step_is_registered_on_the_component():
    component = Ocean()
    steps, _, _ = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240', include_viz=True
    )
    adjustment = _adjustment_steps(steps)
    # every stage, its check, validate and viz
    assert len(adjustment) == 2 * 4 + 2
    for step in adjustment.values():
        assert component.steps[step.subdir] is step, step.subdir


def _adjustment_steps(steps):
    """The dynamic-adjustment steps, without the shared init chain."""
    base = 'spherical/realistic_global/u.oi240.lr240/dynamic_adjustment'
    return {
        name: step
        for name, step in steps.items()
        if step.subdir.startswith(f'{base}/')
    }


def test_the_viz_step_is_shared_but_returned_only_when_asked():
    """
    A figure describing a completed adjustment is not what a workflow that
    only wants the relaxed restart is asking about, so it stays out of that
    workflow's steps_to_run -- but it is still the same shared step.
    """
    component = Ocean()
    without, _, _ = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240'
    )
    assert 'viz' not in without
    with_viz, _, _ = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240', include_viz=True
    )
    assert 'viz' in with_viz
    base = 'spherical/realistic_global/u.oi240.lr240/dynamic_adjustment'
    assert with_viz['viz'] is component.steps[f'{base}/viz']


def test_the_last_stage_names_the_restart_a_consumer_wants():
    """
    The stages come back with the steps because which stage hands off the
    adjusted state, and what that restart is called, depend on the schedule.
    """
    component = Ocean()
    steps, _, stages = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240'
    )
    assert stages[-1].name == 'simulation'
    assert stages[-1].restart_out == 'restarts/rst.0001-02-10_00.00.00.nc'
    last = steps['simulation']
    assert isinstance(last, Forward)
    assert last.stage is stages[-1]


def test_the_shared_config_is_reused_rather_than_rebuilt():
    component = Ocean()
    task = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name='u.oi240.lr240'
    )
    _, config, _ = get_realistic_dynamic_adjustment_steps(
        component=component, mesh_name='u.oi240.lr240'
    )
    assert config is task.config


def test_configure_rebuilds_only_when_the_schedule_changed(tmp_path):
    """
    A user's setup-time schedule override has to take effect, and the shared
    steps are keyed by work directory -- so a stage whose name survived the
    override would otherwise come back carrying its old run duration.
    """
    component = Ocean()
    task = RealisticGlobalDynamicAdjustment(
        component=component, mesh_name='u.oi240.lr240'
    )
    before = dict(task.steps)

    # no override: nothing is rebuilt
    task.configure()
    assert task.steps == before

    schedule = tmp_path / 'schedule.yaml'
    schedule.write_text(
        textwrap.dedent(
            """
            dynamic_adjustment:
              stages:
                damped_adjustment_1:
                  run_duration: 5_00:00:00
                simulation:
                  run_duration: 5_00:00:00
            """
        )
    )
    override = tmp_path / 'override.cfg'
    override.write_text(f'[{SECTION}]\nschedule = {schedule}\n')
    task.config.add_from_file(str(override))

    task.configure()
    assert [stage.name for stage in task.stages] == [
        'damped_adjustment_1',
        'simulation',
    ]
    # the surviving name now carries the override's duration rather than the
    # built-in schedule's
    assert task.steps['damped_adjustment_1'].stage.run_duration == '5_00:00:00'
    assert (
        task.steps['damped_adjustment_1'] is not before['damped_adjustment_1']
    )
    # the dropped stages are gone from the component, not just from the task
    base = 'spherical/realistic_global/u.oi240.lr240/dynamic_adjustment'
    assert f'{base}/damped_adjustment_3' not in component.steps
    # the init steps upstream are untouched: they do not depend on the
    # schedule and are shared with other tasks
    assert task.steps['initial_state'] is before['initial_state']


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
    # u.oi6to18.lr6to10.cfg references the mixing to its finest cells
    for stage in load_schedule_stages(
        'u.oi6to18.lr6to10', _config('u.oi6to18.lr6to10')
    ):
        assert stage.hmix_scaling == 'ref_cell_width'
        assert stage.hmix_ref_cell_width == 6.0e3
        assert stage.mom_del4_div_factor == 10.0
    for stage in load_schedule_stages('u.oi30.lr10', _config('u.oi30.lr10')):
        assert stage.hmix_scaling == 'ref_cell_width'
        assert stage.hmix_ref_cell_width == 30.0e3


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


# --- a stage must write the records the chain needs ---


def test_restart_interval_that_misses_the_stage_end_raises(tmp_path):
    """
    MPAS-Ocean's restart alarm runs from a fixed reference time, so a stage
    ending 1.5 restart intervals in never writes the restart the chain
    declares, and the failure only shows up after the model has run.
    """
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 03_00:00:00
              restart_interval: 02_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='restart the next stage reads'):
        load_schedule_stages('icos240km', config)


def test_restart_interval_is_measured_from_the_reference_not_the_stage(
    tmp_path,
):
    """
    A second stage of 2 days whose restart interval divides its own duration
    still fails when the chain has put its stop time off the alarm.
    """
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            first:
              run_duration: 01_00:00:00
              restart_interval: 01_00:00:00
            second:
              run_duration: 02_00:00:00
              restart_interval: 02_00:00:00
        """,
    )
    # 'second' ends 3 days in, which is not a whole number of 2-day intervals
    # from the reference even though 2 days divides its own duration
    with pytest.raises(ValueError, match="'second'"):
        load_schedule_stages('icos240km', config)


def test_restart_interval_on_the_alarm_is_accepted(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            first:
              run_duration: 02_00:00:00
              restart_interval: 02_00:00:00
            second:
              run_duration: 02_00:00:00
              restart_interval: 02_00:00:00
        """,
    )
    stages = load_schedule_stages('icos240km', config)
    assert [stage.restart_out for stage in stages] == [
        'restarts/rst.0001-01-03_00.00.00.nc',
        'restarts/rst.0001-01-05_00.00.00.nc',
    ]


def test_stats_interval_longer_than_the_stage_raises(tmp_path):
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 01_00:00:00
              stats_interval: 10_00:00:00
        """,
    )
    with pytest.raises(ValueError, match='stats_interval'):
        load_schedule_stages('icos240km', config)


def test_output_interval_longer_than_the_stage_is_allowed(tmp_path):
    # a long 3-D output interval is how the ported Compass schedules say "do
    # not write 3-D fields during the damped stages"
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          stages:
            only_stage:
              run_duration: 01_00:00:00
              output_interval: 10_00:00:00
        """,
    )
    stage = load_schedule_stages('icos240km', config)[0]
    assert stage.output_interval == '10_00:00:00'


# --- validation helpers ---


def test_check_temperature_max_passes():
    check_temperature_max(30.0, 1.0, 33.0, 'simulation', LOGGER)


def test_check_temperature_max_raises():
    with pytest.raises(ValueError, match='above the allowed'):
        check_temperature_max(40.0, 1.0, 33.0, 'simulation', LOGGER)


def test_check_reports_when_the_extreme_happened():
    # an extreme at day zero is the initial condition, not something the stage
    # did -- which is the whole point of reporting the time
    with pytest.raises(ValueError, match='before any time step'):
        check_temperature_max(40.0, 0.0, 33.0, 'damped_adjustment_1', LOGGER)
    with pytest.raises(ValueError, match='3 days into the stage'):
        check_temperature_max(40.0, 3.0, 33.0, 'damped_adjustment_1', LOGGER)


def test_check_temperature_max_skipped_when_not_reported():
    # a model that reports no temperature has nothing to check
    check_temperature_max(None, 1.0, 33.0, 'simulation', LOGGER)


def test_cfl_max_passes():
    check_cfl_max(0.053, 1.0, 0.2, 'damped_adjustment_2', LOGGER)


def test_cfl_max_raises():
    with pytest.raises(ValueError, match='CFL number reached'):
        check_cfl_max(0.35, 1.0, 0.2, 'damped_adjustment_2', LOGGER)


def test_cfl_max_skipped_when_not_reported():
    # Omega's GlobalStats reports no CFL number
    check_cfl_max(None, 1.0, 0.2, 'simulation', LOGGER)


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
        subdir='spherical/realistic_global/u.oi240.lr240/dynamic_adjustment/validate',
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
def test_validate_summarizes_for_either_model(tmp_path, monkeypatch, model):
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
def test_stage_check_catches_a_blow_up_for_either_model(
    tmp_path, monkeypatch, model
):
    step = _stage_check(tmp_path, model, 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['temperatureMax'] = [28.0, 99.0, 30.0]
    _write_stage_stats(tmp_path, 'damped_1', model, **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='above the allowed'):
        step.run()


def test_stage_check_ignores_the_initial_condition(tmp_path, monkeypatch):
    """
    The u.oi30.lr10 case: the WOA23 source data puts a 33.5 degC cell in the
    initial condition, which the model mixes away.  A stage is judged on what
    it did, so that sample is not checked.
    """
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['temperatureMax'] = [33.458, 31.710, 31.359]
    series['salinityMax'] = [43.974, 42.008, 41.425]
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    step.run()


def test_stage_check_still_catches_an_extreme_after_the_first_sample(
    tmp_path, monkeypatch
):
    # excluding the initial sample must not blind the check to the rest
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['temperatureMax'] = [29.0, 99.0, 30.0]
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='temperature reached 99'):
        step.run()


def test_stage_check_catches_an_excessive_salinity(tmp_path, monkeypatch):
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['salinityMax'] = [40.0, 99.0, 41.0]
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='salinity reached 99'):
        step.run()


def test_check_salinity_max():
    check_salinity_max(42.0, 1.0, 45.0, 'damped_adjustment_1', LOGGER)
    with pytest.raises(ValueError, match='above the allowed'):
        check_salinity_max(50.0, 1.0, 45.0, 'damped_adjustment_1', LOGGER)
    # Omega reports salinity, but a model that did not would skip
    check_salinity_max(None, None, 45.0, 'damped_adjustment_1', LOGGER)


def test_extremes_exclude_the_initial_sample():
    ds = xr.Dataset(
        {
            'temperatureMax': (('Time',), np.array([99.0, 30.0, 29.0])),
            'daysSinceStartOfSim': (('Time',), np.array([0.0, 5.0, 10.0])),
        }
    )
    value, when = extreme_and_day(ds, 'temperatureMax', 'max')
    assert value == pytest.approx(30.0)
    assert when == pytest.approx(5.0)


def test_extremes_skip_the_startup_window():
    """
    The u.oi6to18.lr6to10 case: the statistics are hourly and the WOA23 warm
    cell off Sumatra is still at 35.77 degC an hour in, so skipping only the
    initial sample leaves the artifact as the maximum the stage is judged on.
    """
    ds = xr.Dataset(
        {
            'temperatureMax': (
                ('Time',),
                np.array([35.784, 35.770, 34.539, 34.530, 34.408]),
            ),
            'daysSinceStartOfSim': (('Time',), np.arange(5.0) / 24.0),
        }
    )
    value, _ = extreme_and_day(ds, 'temperatureMax', 'max')
    assert value == pytest.approx(35.770)

    value, when = extreme_and_day(ds, 'temperatureMax', 'max', 2.0 / 24.0)
    assert value == pytest.approx(34.530)
    assert when == pytest.approx(3.0 / 24.0)


def test_the_startup_window_excludes_a_sample_that_lands_on_it():
    # the model writes 2 hours as 0.0833..., so matching the window against it
    # cannot rely on exact equality
    ds = xr.Dataset(
        {
            'temperatureMax': (('Time',), np.array([40.0, 39.0, 38.0, 30.0])),
            'daysSinceStartOfSim': (('Time',), np.arange(4.0) / 24.0),
        }
    )
    value, _ = extreme_and_day(ds, 'temperatureMax', 'max', 7200.0 / 86400.0)
    assert value == pytest.approx(30.0)


def test_a_stage_wholly_inside_the_startup_window_has_nothing_to_judge():
    ds = xr.Dataset(
        {
            'temperatureMax': (('Time',), np.array([40.0, 39.0, 38.0])),
            'daysSinceStartOfSim': (('Time',), np.arange(3.0) / 24.0),
        }
    )
    assert extreme_and_day(ds, 'temperatureMax', 'max', 5.0 / 24.0) == (
        None,
        None,
    )


def test_extremes_are_unavailable_from_a_single_sample():
    # a stage that wrote only its startup record has nothing to judge
    ds = xr.Dataset(
        {
            'temperatureMax': (('Time',), np.array([99.0])),
            'daysSinceStartOfSim': (('Time',), np.array([0.0])),
        }
    )
    assert extreme_and_day(ds, 'temperatureMax', 'max') == (None, None)


def test_startup_window_covers_only_the_stages_it_reaches():
    stages = load_schedule_stages(
        'u.oi6to18.lr6to10', _config('u.oi6to18.lr6to10')
    )
    sequence_start = stages[0].start_time
    excluded = [
        excluded_days_in_stage(stage, sequence_start, '00_02:00:00')
        for stage in stages
    ]
    assert excluded[0] == pytest.approx(2.0 / 24.0)
    # every later stage begins well after the window has closed, so none of
    # them stops watching its own opening hours
    assert excluded[1:] == [0.0] * (len(stages) - 1)


def test_startup_window_carries_over_into_a_short_first_stage(tmp_path):
    # a first stage shorter than the window: the second stage carries what is
    # left of it rather than the window quietly stopping at the stage boundary
    config = _config_for_schedule(
        tmp_path,
        """
        dynamic_adjustment:
          shared:
            stats_interval: 00_00:30:00
          stages:
            damped_1:
              run_duration: 00_01:00:00
            simulation:
              run_duration: 00_23:00:00
              restart_interval: 01_00:00:00
        """,
    )
    stages = load_schedule_stages('icos240km', config)
    sequence_start = stages[0].start_time
    assert excluded_days_in_stage(
        stages[0], sequence_start, '00_02:00:00'
    ) == pytest.approx(2.0 / 24.0)
    assert excluded_days_in_stage(
        stages[1], sequence_start, '00_02:00:00'
    ) == pytest.approx(1.0 / 24.0)


def test_no_startup_window_leaves_only_the_first_sample_excluded():
    stage = ForwardStage(name='damped_1', run_duration='00_06:00:00')
    excluded = excluded_days_in_stage(stage, stage.start_time, '00_00:00:00')
    assert excluded == 0.0


def test_stage_check_ignores_the_startup_window(tmp_path, monkeypatch):
    """
    The u.oi6to18.lr6to10 first stage: the WOA23 artifacts start at 35.8 degC
    and 44.1 PSU and erode too slowly to clear the thresholds within an hour,
    so the stage is judged from the end of the startup window instead.
    """
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    _write_stage_stats(
        tmp_path, 'damped_1', 'mpas-ocean', **_hourly_stats_series()
    )
    monkeypatch.chdir(tmp_path / 'checks')
    step.run()


def test_stage_check_still_catches_a_blow_up_after_the_startup_window(
    tmp_path, monkeypatch
):
    # the window must not blind the check to the rest of the stage
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _hourly_stats_series()
    series['temperatureMax'][4] = 99.0
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='temperature reached 99'):
        step.run()


def test_stage_check_watches_the_cfl_inside_the_startup_window(
    tmp_path, monkeypatch
):
    # the window is for the tracer artifacts; a time step too long for the
    # flow shows up in the opening hours and has to stay caught there
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _hourly_stats_series()
    series['CFLNumberGlobal'][1] = 0.42
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='CFL number'):
        step.run()


def _hourly_stats_series():
    """
    The first six hours of the real u.oi6to18.lr6to10 ``damped_adjustment_1``,
    whose statistics are hourly because its stages are as short as six hours.
    """
    return dict(
        daysSinceStartOfSim=list(np.arange(7.0) / 24.0),
        kineticEnergyCellMax=[0.0, 0.169, 0.185, 0.367, 1.132, 0.957, 0.519],
        kineticEnergyCellAvg=[
            1.0e-6,
            2.0e-4,
            6.0e-4,
            1.1e-3,
            1.6e-3,
            1.9e-3,
            2.0e-3,
        ],
        kineticEnergyCellSum=[1.0e12] * 7,
        volumeCellGlobal=[1.3e18] * 7,
        CFLNumberGlobal=[0.0, 0.0018, 0.002, 0.0037, 0.0061, 0.0056, 0.0045],
        temperatureMax=[
            35.784,
            35.770,
            34.539,
            34.530,
            34.408,
            34.320,
            34.292,
        ],
        temperatureMin=[-2.12] * 7,
        temperatureAvg=[3.5] * 7,
        salinityMax=[
            44.128,
            43.028,
            42.626,
            42.599,
            42.597,
            42.596,
            42.594,
        ],
        salinityMin=[5.0] * 7,
        salinityAvg=[34.7] * 7,
        layerThicknessMin=[0.3] * 7,
        normalVelocityMax=[0.0, 0.55, 0.55, 1.13, 1.86, 1.72, 1.39],
    )


def test_stage_check_catches_an_excessive_cfl(tmp_path, monkeypatch):
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['CFLNumberGlobal'] = [0.05, 0.42, 0.06]
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='CFL number'):
        step.run()


def test_stage_check_passes_a_healthy_stage(tmp_path, monkeypatch):
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    _write_stage_stats(
        tmp_path, 'damped_1', 'mpas-ocean', **_stats_series(5.0, 3.5)
    )
    monkeypatch.chdir(tmp_path / 'checks')
    step.run()


def test_stage_check_skips_a_stage_without_statistics(tmp_path, monkeypatch):
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    monkeypatch.chdir(tmp_path / 'checks')
    step.run()


def _stage_check(tmp_path, model, stage_name):
    """A StageCheck step in a work directory beside the stage directories."""
    component = Ocean()
    component.model = model
    if model == 'omega':
        component._read_var_map()
    step = StageCheck(
        component=component,
        stage=ForwardStage(name=stage_name, run_duration='10_00:00:00'),
        subdir=f'spherical/realistic_global/u.oi240.lr240/dynamic_adjustment/{stage_name}_check',
    )
    config = _config('u.oi240.lr240')
    override = tmp_path / 'check_model.cfg'
    override.write_text(f'[ocean]\nmodel = {model}\n')
    config.add_from_file(str(override))
    step.config = config
    step.logger = LOGGER
    (tmp_path / 'checks').mkdir(parents=True, exist_ok=True)
    return step


def test_validate_does_not_judge_the_kinetic_energy(tmp_path, monkeypatch):
    """
    A sequence whose mean kinetic energy accelerates -- 2x, 2x, then 4x --
    which the removed settling check would have rejected.  Whether an
    adjustment has settled is now read from the summary and the viz figure,
    so validate collects and reports it rather than ruling on it.
    """
    stages = ['damped_1', 'damped_2', 'damped_3', 'simulation']
    step = _run_with_stats(
        tmp_path, monkeypatch, 'mpas-ocean', stages, [1.0, 2.0, 4.0, 16.0]
    )
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    assert len(lines) == len(stages) + 1
    assert step is not None


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
        daysSinceStartOfSim=[0.0, 5.0, 10.0],
        kineticEnergyCellMax=[ke_end * 1.4, ke_end * 1.2, ke_end],
        kineticEnergyCellAvg=[ke_end * 0.02, ke_end * 0.015, ke_end * 0.01],
        kineticEnergyCellSum=[
            ke_end * 2.0e18,
            ke_end * 1.6e18,
            ke_end * 1.3e18,
        ],
        volumeCellGlobal=[1.3e18] * 3,
        CFLNumberGlobal=[0.04, 0.035, 0.03],
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


def test_the_summary_applies_the_startup_window_to_tracers_only(
    tmp_path, monkeypatch
):
    # the summary a user reads and the checks that passed cannot disagree, so
    # the same window has to reach the CSV -- and reach only the columns the
    # checks apply it to
    step = _validate_step(
        tmp_path,
        'mpas-ocean',
        ['damped_1'],
        temperature=[[[10.0, 20.0]]],
        kinetic_energy=[[[1.0, 5.0]]],
    )
    series = _hourly_stats_series()
    series['normalVelocityMax'][1] = 9.0
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'validate')
    step.run()

    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    row = dict(zip(column_names(), lines[1].split(',')[1:], strict=True))
    # the artifact's first two hours are excluded, so the stage is judged from
    # hour 3
    assert float(row['temperature_max_in_stage']) == pytest.approx(34.530)
    assert float(row['salinity_max_in_stage']) == pytest.approx(42.599)
    # the velocity extreme still sees the opening hours
    assert float(row['normal_velocity_max_in_stage']) == pytest.approx(9.0)


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
    # the first sample (7.0) is the state the stage was handed, not its own
    assert float(values['kinetic_energy_max_in_stage']) == pytest.approx(6.0)


def test_diagnostics_record_the_mean_tracer_change(tmp_path, monkeypatch):
    # temperatureAvg falls by 0.01 degC over a 10-day stage
    stages = ['damped_1', 'simulation']
    _run_with_stats(tmp_path, monkeypatch, 'mpas-ocean', stages, [5.0, 4.0])
    columns = column_names()
    lines = (tmp_path / 'validate' / SUMMARY_FILENAME).read_text().splitlines()
    values = dict(zip(columns, lines[1].split(',')[1:], strict=False))
    assert float(values['mean_temperature_change_per_day']) == pytest.approx(
        -0.001
    )


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
    assert values['mean_temperature_change_per_day'] == ''


def test_blow_up_is_caught_mid_stage_from_the_statistics(
    tmp_path, monkeypatch
):
    # the statistics pass through 99 degC partway through the stage; an
    # end-of-stage field alone would miss it
    step = _stage_check(tmp_path, 'mpas-ocean', 'damped_1')
    series = _stats_series(5.0, 3.5)
    series['temperatureMax'] = [28.0, 99.0, 30.0]
    _write_stage_stats(tmp_path, 'damped_1', 'mpas-ocean', **series)
    monkeypatch.chdir(tmp_path / 'checks')
    with pytest.raises(ValueError, match='5 days into the stage'):
        step.run()


# --- the viz step ---


def test_short_stage_name_fits_above_a_stage():
    # the full name is far wider than a stage is on the axis
    assert _short_stage_name('damped_adjustment_1') == 'damped 1'
    assert _short_stage_name('damped_adjustment_12') == 'damped 12'
    assert _short_stage_name('simulation') == 'simulation'


def test_viz_plots_the_stage_series(tmp_path, monkeypatch):
    stages = ['damped_1', 'damped_2', 'simulation']
    step = _viz_step(tmp_path, 'mpas-ocean', stages)
    for index, stage_name in enumerate(stages):
        _write_stage_stats(
            tmp_path,
            stage_name,
            'mpas-ocean',
            **_stats_series([5.0, 4.0, 3.9][index], 3.5 - 0.01 * index),
        )
    monkeypatch.chdir(tmp_path / 'viz')
    step.run()
    figure = tmp_path / 'viz' / FIGURE_FILENAME
    assert figure.exists() and figure.stat().st_size > 0


def test_viz_skips_stages_without_statistics(tmp_path, monkeypatch):
    # a run that died partway still gets a figure of what it managed
    stages = ['damped_1', 'damped_2', 'simulation']
    step = _viz_step(tmp_path, 'mpas-ocean', stages)
    _write_stage_stats(
        tmp_path, 'damped_1', 'mpas-ocean', **_stats_series(5.0, 3.5)
    )
    monkeypatch.chdir(tmp_path / 'viz')
    step.run()
    assert (tmp_path / 'viz' / FIGURE_FILENAME).exists()


def test_viz_writes_nothing_without_any_statistics(tmp_path, monkeypatch):
    step = _viz_step(tmp_path, 'mpas-ocean', ['damped_1', 'simulation'])
    monkeypatch.chdir(tmp_path / 'viz')
    step.run()
    assert not (tmp_path / 'viz' / FIGURE_FILENAME).exists()


def _viz_step(tmp_path, model, stage_names):
    """A viz step in a work directory beside the stage directories."""
    component = Ocean()
    component.model = model
    if model == 'omega':
        component._read_var_map()
    step = VizDynamicAdjustmentStep(
        component=component,
        stages=[
            ForwardStage(
                name=name,
                run_duration='10_00:00:00',
                start_time=f'0001-01-{1 + 10 * index:02d}_00:00:00',
                damping=None if name == 'simulation' else 1.0e-4,
            )
            for index, name in enumerate(stage_names)
        ],
        subdir='spherical/realistic_global/u.oi240.lr240/dynamic_adjustment/viz',
    )
    config = _config('u.oi240.lr240')
    override = tmp_path / 'viz_model.cfg'
    override.write_text(f'[ocean]\nmodel = {model}\n')
    config.add_from_file(str(override))
    step.config = config
    step.logger = LOGGER
    # the step runs in a work directory beside the stage directories
    (tmp_path / 'viz').mkdir(parents=True, exist_ok=True)
    return step
