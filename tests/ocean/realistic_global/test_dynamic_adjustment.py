import logging
import textwrap

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean import Ocean
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
    _check_ke_flattening,
    _check_temperature_max,
    _final_max_ke,
)
from polaris.tasks.ocean.realistic_global.forward import ForwardStage
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
    assert (
        config.get(
            'realistic_global_forward', 'Rayleigh_damping_coeff'
        ).strip()
        == ''
    )


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


def test_per_mesh_schedule_counts():
    assert (
        len(load_schedule_stages('u.oi30.lr10', _config('u.oi30.lr10'))) == 4
    )
    assert (
        len(
            load_schedule_stages(
                'u.oi.so12to30.lr10', _config('u.oi.so12to30.lr10')
            )
        )
        == 5
    )
    assert (
        len(
            load_schedule_stages(
                'u.oi6to18.lr6to10', _config('u.oi6to18.lr6to10')
            )
        )
        == 8
    )


def test_restart_chain_is_consistent():
    for mesh in ('u.oi30.lr10', 'u.oi.so12to30.lr10', 'u.oi6to18.lr6to10'):
        stages = load_schedule_stages(mesh, _config(mesh))
        assert stages[0].do_restart is False
        for previous, current in zip(stages[:-1], stages[1:], strict=False):
            assert current.do_restart is True
            assert current.restart_in == previous.restart_out
            # each stage starts where the previous stage's restart was written
            assert previous.restart_out is not None
            filename_time = current.start_time.replace(':', '.')
            assert filename_time in previous.restart_out


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


def _dataset(temperature, kinetic_energy):
    """A minimal (Time, nCells) dataset for the validation helpers."""
    return xr.Dataset(
        {
            'temperature': (('Time', 'nCells'), np.array(temperature)),
            'kineticEnergyCell': (
                ('Time', 'nCells'),
                np.array(kinetic_energy),
            ),
        }
    )


def test_check_temperature_max_passes():
    ds = _dataset([[10.0, 20.0], [15.0, 30.0]], [[1.0, 2.0], [1.0, 2.0]])
    # the final-time max (30) is below the threshold, so no exception
    _check_temperature_max(ds, 33.0, 'simulation', LOGGER)


def test_check_temperature_max_raises():
    ds = _dataset([[10.0, 20.0], [15.0, 40.0]], [[1.0, 2.0], [1.0, 2.0]])
    with pytest.raises(ValueError, match='exceeds'):
        _check_temperature_max(ds, 33.0, 'simulation', LOGGER)


def test_final_max_ke_uses_last_time():
    ds = _dataset([[10.0, 10.0], [10.0, 10.0]], [[1.0, 2.0], [3.0, 7.0]])
    assert _final_max_ke(ds) == pytest.approx(7.0)


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
