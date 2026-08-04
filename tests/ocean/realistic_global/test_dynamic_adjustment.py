import logging
import textwrap
from configparser import ConfigParser

import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    load_schedule_stages,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate import (
    _check_ke_flattening,
    _check_temperature_max,
    _final_max_ke,
)

LOGGER = logging.getLogger('test_dynamic_adjustment')


def _config_for_schedule(tmp_path, text):
    """A config whose schedule override points at a written YAML file."""
    schedule = tmp_path / 'schedule.yaml'
    schedule.write_text(textwrap.dedent(text))
    config = ConfigParser()
    config.add_section(SECTION)
    config.set(SECTION, 'schedule', str(schedule))
    return config


# --- built-in schedules: parsing and chaining ---


def test_default_schedule_used_when_no_mesh_file():
    # qu240km has no per-mesh file, so it falls back to default.yaml
    stages = load_schedule_stages('qu240km')
    assert [s.name for s in stages] == ['damped_adjustment_1', 'simulation']


def test_default_schedule_chaining():
    stages = load_schedule_stages('icos240km')
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
    stages = load_schedule_stages('u.oi30.lr10')
    # the shared block is applied to every stage
    assert all(s.mpaso_time_integrator == 'split_explicit_ab2' for s in stages)
    assert all(s.output_interval == '10_00:00:00' for s in stages)
    # damping is set on the damped stages and None on the final simulation
    assert stages[0].damping == pytest.approx(1.0e-4)
    assert stages[-1].name == 'simulation'
    assert stages[-1].damping is None


def test_per_mesh_schedule_counts():
    assert len(load_schedule_stages('u.oi30.lr10')) == 4
    assert len(load_schedule_stages('u.oi.so12to30.lr10')) == 5
    assert len(load_schedule_stages('u.oi6to18.lr6to10')) == 8


def test_restart_chain_is_consistent():
    for mesh in ('u.oi30.lr10', 'u.oi.so12to30.lr10', 'u.oi6to18.lr6to10'):
        stages = load_schedule_stages(mesh)
        assert stages[0].do_restart is False
        for previous, current in zip(stages[:-1], stages[1:], strict=False):
            assert current.do_restart is True
            assert current.restart_in == previous.restart_out
            # each stage starts where the previous stage's restart was written
            assert previous.restart_out is not None
            filename_time = current.start_time.replace(':', '.')
            assert filename_time in previous.restart_out


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
