import os

from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.mixed_layer_eddies.coarse import Coarse
from polaris.tasks.ocean.mixed_layer_eddies.comparison import Comparison
from polaris.tasks.ocean.mixed_layer_eddies.forward import (
    MLE_SETTINGS,
    Forward,
)
from polaris.tasks.ocean.mixed_layer_eddies.init import Init
from polaris.tasks.ocean.mixed_layer_eddies.resolved import Resolved

# the resolution (km) of the eddy-resolving reference run
RESOLVED_RESOLUTION = 0.5

# the resolutions (km) of the coarse runs
COARSE_RESOLUTIONS = [8.0, 16.0]


def add_mixed_layer_eddies_tasks(component):
    """
    Add the mixed-layer eddies tasks to the ocean component

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    indir = 'planar/mixed_layer_eddies'
    config_filename = 'mixed_layer_eddies.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, indir, config_filename)
    )
    config.add_from_package('polaris.ocean.eos', 'linear.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.mixed_layer_eddies', config_filename
    )

    resolved_steps = _get_resolved_steps(
        component, indir, config, config_filename
    )
    coarse_steps = {
        resolution_to_string(resolution): _get_coarse_steps(
            component, indir, config, config_filename, resolution
        )
        for resolution in COARSE_RESOLUTIONS
    }

    tasks = [
        Resolved(component, indir, resolved_steps),
        Coarse(component, indir, coarse_steps),
        Comparison(component, indir, resolved_steps, coarse_steps),
    ]
    for task in tasks:
        task.set_shared_config(config, link=config_filename)
        component.add_task(task)


def _get_resolved_steps(component, indir, config, config_filename):
    """
    Get the shared steps of the resolved run: the initial state, the
    spin-up, the eddy diagnosis window and the rest of the run, each run
    continuing from the previous one's restart
    """
    resolution = RESOLVED_RESOLUTION
    res_str = resolution_to_string(resolution)
    resdir = f'{indir}/{res_str}'
    init = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'{resdir}/init',
        config=config,
        config_filename=config_filename,
        name=f'init_{res_str}',
        resolution=resolution,
    )
    steps = dict(init=init)
    segments = ['spinup', 'eddies', 'extended']
    for segment in segments:
        steps[segment] = component.get_or_create_shared_step(
            step_cls=Forward,
            subdir=f'{resdir}/{segment}',
            config=config,
            config_filename=config_filename,
            name=f'{segment}_{res_str}',
            resolution=resolution,
            init=init,
            segment=segment,
        )
    for previous, segment in zip(segments[:-1], segments[1:], strict=True):
        steps[segment].add_dependency(steps[previous], steps[previous].name)
    return steps


def _get_coarse_steps(component, indir, config, config_filename, resolution):
    """
    Get the shared steps of the coarse runs at one resolution: the initial
    state and a run for each setting of the parameterization
    """
    res_str = resolution_to_string(resolution)
    resdir = f'{indir}/{res_str}'
    init = component.get_or_create_shared_step(
        step_cls=Init,
        subdir=f'{resdir}/init',
        config=config,
        config_filename=config_filename,
        name=f'init_{res_str}',
        resolution=resolution,
    )
    steps = dict(init=init)
    for mle in MLE_SETTINGS:
        name = f'forward_{mle}'
        steps[name] = component.get_or_create_shared_step(
            step_cls=Forward,
            subdir=f'{resdir}/{name}',
            config=config,
            config_filename=config_filename,
            name=f'{name}_{res_str}',
            resolution=resolution,
            init=init,
            mle=mle,
        )
    return steps
