import os

from polaris.config import PolarisConfigParser
from polaris.step import Step

from .stress import Jra55StressStep
from .viz import Jra55VizStep

JRA55_SUBDIR = 'spherical/realistic_global/forcing/jra55'


def get_jra55_steps(component, include_viz=False):
    """
    Get the shared steps for building the reusable JRA55-do wind-stress
    product.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the steps belong to.

    include_viz : bool, optional
        Whether to include the :py:class:`.Jra55VizStep` in the returned
        steps.  The step is always created as a shared component step so it is
        part of the workflow, but it is only added to the returned dict (and
        therefore to a task's ``steps_to_run``) when this is ``True``.  The
        standalone :py:class:`.Jra55` task passes ``include_viz=True``; other
        consumers that reuse the wind-stress product as a dependency leave it
        ``False`` so the plots are not regenerated.

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

    if include_viz:
        viz_step = component.get_or_create_shared_step(
            step_cls=Jra55VizStep,
            subdir=os.path.join(JRA55_SUBDIR, 'viz'),
            config=config,
            config_filename=config_filename,
            stress_step=stress_step,
        )
        steps['jra55_viz'] = viz_step

    return steps, config
