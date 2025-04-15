import os
from math import ceil as ceil
from typing import Dict as Dict

from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task as get_resolution_for_task,
)
from polaris.ocean.convergence import (
    get_timestep_for_task as get_timestep_for_task,
)
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.inertial_gravity_wave.analysis import (
    Analysis as Analysis,
)
from polaris.tasks.ocean.inertial_gravity_wave.forward import (
    Forward as Forward,
)
from polaris.tasks.ocean.inertial_gravity_wave.init import Init as Init
from polaris.tasks.ocean.inertial_gravity_wave.viz import Viz as Viz


def add_inertial_gravity_wave_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    basedir = 'planar/inertial_gravity_wave'
    config_filename = 'inertial_gravity_wave.cfg'
    filepath = os.path.join(component.name, basedir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.inertial_gravity_wave', config_filename
    )
    for refinement in ['space', 'time', 'both']:
        component.add_task(
            InertialGravityWave(
                component=component, config=config, refinement=refinement
            )
        )


class InertialGravityWave(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component, config, refinement='both'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        name = f'inertial_gravity_wave_convergence_{refinement}'
        basedir = 'planar/inertial_gravity_wave'
        subdir = f'{basedir}/convergence_{refinement}'
        config_filename = 'inertial_gravity_wave.cfg'
        super().__init__(component=component, name=name, subdir=subdir)
        self.set_shared_config(config, link=config_filename)

        analysis_dependencies: Dict[str, Dict[float, Step]] = dict(
            mesh=dict(), init=dict(), forward=dict()
        )

        if refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = self.config.getlist(
            'convergence', option, dtype=float
        )
        timesteps = list()
        resolutions = list()
        for refinement_factor in refinement_factors:
            resolution = get_resolution_for_task(
                self.config, refinement_factor, refinement=refinement
            )
            mesh_name = resolution_to_string(resolution)

            subdir = f'{basedir}/init/{mesh_name}'
            symlink = f'init/{mesh_name}'
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(
                    component=component, resolution=resolution, subdir=subdir
                )
                init_step.set_shared_config(self.config, link=config_filename)
            if resolution not in resolutions:
                self.add_step(init_step, symlink=symlink)
                resolutions.append(resolution)

            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=refinement
            )
            timestep = ceil(timestep)
            timesteps.append(timestep)

            subdir = f'{basedir}/forward/{mesh_name}_{timestep}s'
            symlink = f'forward/{mesh_name}_{timestep}s'
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                forward_step = Forward(
                    component=component,
                    refinement=refinement,
                    refinement_factor=refinement_factor,
                    name=f'forward_{mesh_name}_{timestep}s',
                    subdir=subdir,
                    init=init_step,
                )
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)

            analysis_dependencies['mesh'][refinement_factor] = init_step
            analysis_dependencies['init'][refinement_factor] = init_step
            analysis_dependencies['forward'][refinement_factor] = forward_step

        self.add_step(
            Analysis(
                component=component,
                subdir=f'{self.subdir}/analysis',
                refinement=refinement,
                dependencies=analysis_dependencies,
            )
        )
        self.add_step(
            Viz(
                component=component,
                taskdir=self.subdir,
                refinement=refinement,
                dependencies=analysis_dependencies,
            ),
            run_by_default=False,
        )
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.inertial_gravity_wave', config_filename
        )
