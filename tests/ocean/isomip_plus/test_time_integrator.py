from configparser import ConfigParser
from importlib import resources

import pytest

from polaris.yaml import PolarisYaml


def _read_isomip_plus_config():
    """Read the ISOMIP+ config options shipped with polaris."""
    config = ConfigParser()
    text = (
        resources.files('polaris.tasks.ocean.isomip_plus')
        .joinpath('isomip_plus.cfg')
        .read_text()
    )
    config.read_string(text)
    return config


def test_default_time_integrators():
    # the default tasks run RK4 in both SSH adjustment and the forward run
    config = _read_isomip_plus_config()
    assert config.get('isomip_plus_forward', 'time_integrator') == 'RK4'
    assert config.get('ssh_adjustment', 'time_integrator') == 'RK4'


def test_physics_does_not_set_time_integrator():
    # physics.yaml is added after the forward and SSH-adjustment yaml files,
    # so it would override the time integrator chosen by config options
    yaml = PolarisYaml.read(
        filename='physics.yaml',
        package='polaris.tasks.ocean.isomip_plus',
        model='mpas-ocean',
    )
    options = yaml.configs.get('time_integration', {})
    assert 'config_time_integrator' not in options


@pytest.mark.parametrize('time_integrator', ['RK4', 'split_explicit'])
def test_time_integrator_reaches_namelist(time_integrator):
    replacements = dict(
        time_integrator=time_integrator,
        dt='0000_00:00:24',
        btr_dt='0000_00:00:06',
        run_duration='0000_01:00:00',
        output_interval='0000_01:00:00',
    )
    yaml = PolarisYaml.read(
        filename='forward.yaml',
        package='polaris.tasks.ocean.isomip_plus',
        replacements=replacements,
        model='mpas-ocean',
    )
    assert (
        yaml.configs['time_integration']['config_time_integrator']
        == time_integrator
    )
    assert yaml.configs['split_explicit_ts']['config_btr_dt'] == (
        '0000_00:00:06'
    )
