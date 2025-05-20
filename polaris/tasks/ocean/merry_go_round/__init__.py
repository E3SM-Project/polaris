import os
from math import ceil as ceil
from typing import Dict as Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.merry_go_round.analysis import Analysis
from polaris.tasks.ocean.merry_go_round.default import Default
from polaris.tasks.ocean.merry_go_round.forward import Forward
from polaris.tasks.ocean.merry_go_round.init import Init
from polaris.tasks.ocean.merry_go_round.viz import Viz


def add_merry_go_round_tasks(component):
    basedir = 'planar/merry_go_round'

    config_filename = 'merry_go_round.cfg'
    filepath = os.path.join(component.name, basedir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.merry_go_round', config_filename
    )

    base_resolution = get_resolution_for_task(config, 1.0, refinement='both')
    base_timestep, _ = get_timestep_for_task(config, 1.0, refinement='both')
    base_timestep = ceil(base_timestep)

    component.add_task(
        Default(
            component=component,
            config=config,
            resolution=base_resolution,
            timestep=base_timestep,
            indir=basedir,
        )
    )

    for refinement in ['space', 'time', 'both']:
        component.add_task(
            MerryGoRound(
                component=component,
                config=config,
                basedir=basedir,
                refinement=refinement,
            )
        )


class MerryGoRound(Task):
    """
    A test group for tracer advection test cases "merry-go-round"
    """

    def __init__(self, component, config, basedir, refinement='both'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser

        basedir : str
            The directory from which all steps will decend from. The task
            ``name`` will be appended to this path

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        name = f'merry_go_round_convergence_{refinement}'
        subdir = f'{basedir}/convergence_{refinement}/'
        config_filename = 'merry_go_round.cfg'

        super().__init__(component=component, name=name, subdir=subdir)
        self.set_shared_config(config, link=config_filename)

        analysis_dependencies: Dict[str, Dict[float, Step]] = dict(
            mesh=dict(), init=dict(), forward=dict()
        )

        if refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = config.getlist('convergence', option, dtype=float)

        timesteps = list()
        resolutions = list()
        for refinement_factor in refinement_factors:
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=refinement
            )
            mesh_name = resolution_to_string(resolution)

            subdir = f'{basedir}/init/{mesh_name}'
            symlink = f'init/{mesh_name}'
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(
                    component=component,
                    resolution=resolution,
                    name=f'init_{mesh_name}',
                    subdir=subdir,
                )
                init_step.set_shared_config(config, link=config_filename)
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
                dependencies=analysis_dependencies,
                refinement=refinement,
            )
        )
        self.add_step(
            Viz(
                component=component,
                dependencies=analysis_dependencies,
                taskdir=self.subdir,
                refinement=refinement,
            ),
            run_by_default=True,
        )
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.merry_go_round', config_filename
        )
