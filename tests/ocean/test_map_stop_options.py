from configparser import ConfigParser

import pytest

from polaris.ocean.model import OceanModelStep
from polaris.tasks.ocean import Ocean


def _make_config():
    config = ConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', 'omega')
    return config


def _make_step():
    """An Omega forward step with the MPAS-Ocean-to-Omega option map loaded"""
    component = Ocean()
    component.model = 'omega'
    step = OceanModelStep(
        component=component,
        name='forward',
        ntasks=1,
        min_tasks=1,
    )
    step.config = _make_config()
    step._read_config_map()
    return step


def _map(**time_management):
    """Map an ``ocean`` ``time_management`` section to Omega options"""
    step = _make_step()
    configs = step.map_yaml_configs(
        configs={'time_management': time_management},
        config_model='ocean',
    )
    return configs['TimeIntegration']


def test_run_duration_becomes_a_duration_criterion():
    options = _map(
        config_start_time='0001-01-01_00:00:00',
        config_stop_time='none',
        config_run_duration='0000_00:20:00',
    )

    assert options['StopType'] == 'AfterDuration'
    assert options['StopCriterion'] == '0000_00:20:00'
    assert options['StartTime'] == '0001-01-01_00:00:00'


def test_stop_time_becomes_a_time_criterion():
    options = _map(
        config_stop_time='0001-01-02_00:00:00',
        config_run_duration='none',
    )

    assert options['StopType'] == 'AtTime'
    assert options['StopCriterion'] == '0001-01-02_00:00:00'


def test_setting_both_criteria_is_an_error():
    """
    Omega holds one stop criterion, so asking for both says nothing it can
    act on.  MPAS-Ocean would prefer the duration and Omega used to do the
    same, but that rule went with the options it applied to, so rather than
    quietly honouring an order the models no longer share, refuse it.
    """
    with pytest.raises(ValueError, match='both set'):
        _map(
            config_stop_time='0001-01-02_00:00:00',
            config_run_duration='0000_00:20:00',
        )


def test_an_unset_criterion_is_not_both():
    """The usual case: a duration alongside an explicitly unset stop time"""
    options = _map(
        config_stop_time='none',
        config_run_duration='0000_00:20:00',
    )

    assert options['StopType'] == 'AfterDuration'
    assert options['StopCriterion'] == '0000_00:20:00'


@pytest.mark.parametrize('unset', ['none', 'None', ''])
def test_options_omega_cannot_read_are_never_written(unset):
    """
    Omega has no StopTime or RunDuration, so they must not survive the
    mapping, and an unset criterion must not be passed on as ``none``.
    """
    options = _map(
        config_start_time='0001-01-01_00:00:00',
        config_stop_time=unset,
        config_run_duration=unset,
    )

    assert 'StopTime' not in options
    assert 'RunDuration' not in options
    assert 'StopCriterion' not in options
    # with neither criterion set, Omega falls back to its own default
    assert 'StopType' not in options


def test_unmapped_time_options_are_left_alone():
    """A section without stop options passes through untouched"""
    step = _make_step()
    configs = step.map_yaml_configs(
        configs={'time_integration': {'config_dt': '0000_00:05:00'}},
        config_model='ocean',
    )

    assert configs['TimeIntegration'] == {'TimeStep': '0000_00:05:00'}
