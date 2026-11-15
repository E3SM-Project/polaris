from importlib import import_module

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.isomip_plus.forward import Forward
from polaris.tasks.ocean.isomip_plus.ssh_forward import ThinFilmSshForward
from polaris.yaml import PolarisYaml

# polaris imports task packages lazily, so import the module itself
isomip_plus = import_module('polaris.tasks.ocean.isomip_plus')

THIN_FILM_EXPERIMENTS = ['inception', 'wetting', 'drying']


def _ramp(filename):
    yaml = PolarisYaml.read(
        filename=filename,
        package='polaris.tasks.ocean.isomip_plus',
        model='mpas-ocean',
    )
    return yaml.configs['wetting_drying']['config_zero_drying_velocity_ramp']


def test_ramp_only_with_a_thin_film():
    # every ISOMIP+ task uses physics.yaml, which keeps the ramp off
    assert _ramp('physics.yaml') is False
    assert _ramp('thin_film_wetting_drying.yaml') is True


def test_thin_film_ssh_adjustment_and_forward_use_the_ramp():
    component = Ocean()
    component.tasks = dict()
    isomip_plus.add_isomip_plus_tasks(component)
    for path, task in component.tasks.items():
        experiment = path.removesuffix('/with_restart').split('/')[-1]
        thin_film = experiment in THIN_FILM_EXPERIMENTS
        assert task.thin_film == thin_film

        # SSH adjustment has the same wetting and drying as the forward run
        ssh_forward = [
            step
            for name, step in task.steps.items()
            if name.startswith('ssh_forward')
        ]
        assert ssh_forward
        for step in ssh_forward:
            assert isinstance(step, ThinFilmSshForward) == thin_film

        forward = [
            step for step in task.steps.values() if isinstance(step, Forward)
        ]
        assert forward
        for step in forward:
            assert step.thin_film == thin_film
