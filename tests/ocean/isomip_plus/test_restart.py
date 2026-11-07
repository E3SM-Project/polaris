import pytest

from polaris.ocean.model import get_time_interval_string
from polaris.tasks.ocean.isomip_plus.forward import _get_restart_replacements
from polaris.yaml import PolarisYaml


@pytest.mark.parametrize(
    'restart_test, do_restart, start_time',
    [
        ('full', 'false', '0001-01-01_00:00:00'),
        ('restart', 'true', '0001-01-01_01:00:00'),
    ],
)
def test_restart_replacements(restart_test, do_restart, start_time):
    # the full run starts at the beginning and the restart run halfway, and
    # both write restarts halfway through the full run
    replacements = _get_restart_replacements(restart_test, 3600.0)
    assert replacements == dict(
        do_restart=do_restart,
        start_time=start_time,
        restart_interval=get_time_interval_string(seconds=3600.0),
    )


@pytest.mark.parametrize('half_duration', [86400.0, 1800.5])
def test_restart_needs_whole_seconds_within_a_day(half_duration):
    with pytest.raises(ValueError):
        _get_restart_replacements('restart', half_duration)


def test_restart_yaml():
    replacements = _get_restart_replacements('restart', 5400.0)
    yaml = PolarisYaml.read(
        filename='restart.yaml',
        package='polaris.tasks.ocean.isomip_plus',
        replacements=replacements,
        model='mpas-ocean',
    )
    options = yaml.configs['time_management']
    assert options['config_do_restart'] is True
    assert options['config_start_time'] == '0001-01-01_01:30:00'
    # output at startup would add a record that the full run doesn't have
    assert yaml.configs['io']['config_write_output_on_startup'] is False
    restart = yaml.streams['restart']
    assert restart['output_interval'] == replacements['restart_interval']
    assert restart['filename_template'].startswith('../forward/restarts/')
