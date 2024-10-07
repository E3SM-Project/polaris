from math import ceil
from typing import Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.manufactured_solution.analysis import Analysis
from polaris.ocean.tasks.manufactured_solution.forward import Forward
from polaris.ocean.tasks.manufactured_solution.init import Init
from polaris.ocean.tasks.manufactured_solution.viz import Viz


def add_manufactured_solution_tasks(component):
    """
    Add a task that defines a convergence test that uses the method of
    manufactured solutions

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    basedir = 'planar/manufactured_solution'
    config_filename = 'manufactured_solution.cfg'
    filepath = f'{basedir}/{config_filename}'
    config = PolarisConfigParser(filepath=filepath)
    for refinement in ['space', 'time', 'both']:
        component.add_task(ManufacturedSolution(component=component,
                                                config=config,
                                                refinement=refinement))


class ManufacturedSolution(Task):
    """
    The convergence test case using the method of manufactured solutions
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
        name = f'manufactured_solution_convergence_{refinement}'
        basedir = 'planar/manufactured_solution'
        subdir = f'{basedir}/convergence_{refinement}'
        config_filename = 'manufactured_solution.cfg'
        super().__init__(component=component, name=name, subdir=subdir)
        self.set_shared_config(config, link=config_filename)

        analysis_dependencies: Dict[str, Dict[float, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))

        refinement_factors = self.config.getlist(
            'convergence', 'refinement_factors', dtype=float)
        timesteps = list()
        resolutions = list()
        for refinement_factor in refinement_factors:
            resolution = get_resolution_for_task(
                self.config, refinement_factor, refinement=refinement)
            mesh_name = resolution_to_subdir(resolution)

            subdir = f'{basedir}/init/{mesh_name}'
            symlink = f'init/{mesh_name}'
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(component=component, resolution=resolution,
                                 subdir=subdir)
                init_step.set_shared_config(self.config, link=config_filename)
            if resolution not in resolutions:
                self.add_step(init_step, symlink=symlink)
                resolutions.append(resolution)

            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=refinement)
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
                    init=init_step)
                forward_step.set_shared_config(
                    config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)

            analysis_dependencies['mesh'][refinement_factor] = init_step
            analysis_dependencies['init'][refinement_factor] = init_step
            analysis_dependencies['forward'][refinement_factor] = forward_step

        self.add_step(Analysis(component=component,
                               subdir=f'{self.subdir}/analysis',
                               refinement=refinement,
                               dependencies=analysis_dependencies))
        self.add_step(Viz(component=component, resolutions=resolutions,
                          taskdir=self.subdir),
                      run_by_default=False)
        config.add_from_package('polaris.ocean.convergence',
                                'convergence.cfg')
        config.add_from_package(
            'polaris.ocean.tasks.manufactured_solution',
            config_filename)
