from configparser import ConfigParser
from importlib import resources

import pytest

from polaris.yaml import PolarisYaml


def _read_ssh_adjustment_config():
    """Read the SSH-adjustment config options shipped with polaris."""
    config = ConfigParser()
    text = (
        resources.files('polaris.ocean.ice_shelf')
        .joinpath('ssh_adjustment.cfg')
        .read_text()
    )
    config.read_string(text)
    return config


def test_default_time_integrator():
    # ice_shelf_2d relies on this default to keep adjusting SSH with the
    # scheme MPAS-Ocean used before the option reached the namelist
    config = _read_ssh_adjustment_config()
    assert config.get('ssh_adjustment', 'time_integrator') == (
        'split_explicit_ab2'
    )


@pytest.mark.parametrize(
    'time_integrator', ['split_explicit_ab2', 'split_explicit', 'RK4']
)
def test_time_integrator_reaches_namelist(time_integrator):
    replacements = dict(
        dt='0000_00:00:10',
        btr_dt='0000_00:00:01',
        time_integrator=time_integrator,
        run_duration='0000_01:00:00',
        output_interval='0000_01:00:00',
    )
    yaml = PolarisYaml.read(
        filename='ssh_forward.yaml',
        package='polaris.ocean.ice_shelf',
        replacements=replacements,
        model='mpas-ocean',
    )
    options = yaml.configs['time_integration']
    assert options['config_time_integrator'] == time_integrator
