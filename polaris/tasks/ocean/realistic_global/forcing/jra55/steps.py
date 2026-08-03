import os

from polaris.config import PolarisConfigParser
from polaris.step import Step

from .stress import Jra55StressStep

JRA55_SUBDIR = 'spherical/realistic_global/forcing/jra55'


def get_jra55_steps(component):
    """
    Get the shared steps for building the reusable JRA55-do wind-stress
    product.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    Returns
    -------
    steps : dict of {str: polaris.Step}
        All shared steps keyed by their suggested symlink names for use in a
        task.

    config : polaris.config.PolarisConfigParser
        The shared config options for the task and its steps.
    """
    config_filename = 'jra55.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, JRA55_SUBDIR, config_filename)
    )
    config.add_from_package(
        'polaris.tasks.ocean.realistic_global.forcing.jra55',
        config_filename,
    )

    stress_step = component.get_or_create_shared_step(
        step_cls=Jra55StressStep,
        subdir=os.path.join(JRA55_SUBDIR, 'stress'),
        config=config,
        config_filename=config_filename,
    )

    steps: dict[str, Step] = {'jra55_stress': stress_step}

    return steps, config
