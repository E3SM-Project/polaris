from math import ceil as ceil
from typing import Dict as Dict

from polaris import Step, Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.convergence import (
    get_resolution_for_task as get_resolution_for_task,
)
from polaris.ocean.convergence import (
    get_timestep_for_task as get_timestep_for_task,
)
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.manufactured_solution.analysis import (
    Analysis as Analysis,
)
from polaris.tasks.ocean.manufactured_solution.forward import (
    Forward as Forward,
)
from polaris.tasks.ocean.manufactured_solution.init import Init as Init
from polaris.tasks.ocean.manufactured_solution.viz import Viz as Viz


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
    config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
    config.add_from_package(
        'polaris.tasks.ocean.manufactured_solution', config_filename
    )
    for refinement in ['space', 'time', 'both']:
        component.add_task(
            ManufacturedSolution(
                component=component, config=config, refinement=refinement
            )
        )
    component.add_task(
        ManufacturedSolution(
            component=component, config=config, refinement='both', del2=True
        )
    )
    component.add_task(
        ManufacturedSolution(
            component=component, config=config, refinement='both', del4=True
        )
    )


class ManufacturedSolution(Task):
    """
    The convergence test case using the method of manufactured solutions
    """

    def __init__(
        self, component, config, refinement='both', del2=False, del4=False
    ):
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

        del2 : bool
            Whether to evaluate the momentum del2 operator

        del4 : bool
            Whether to evaluate the momentum del4 operator
        """
        basedir = 'planar/manufactured_solution'
        subdir = f'{basedir}/convergence_{refinement}'
        name = f'manufactured_solution_convergence_{refinement}'

        if del2:
            test_name = 'del2'
            if del4:
                del4 = False
                print(
                    'Manufactured solution test does not currently support'
                    'both del2 and del4 convergence; testing del2 alone.'
                )
        elif del4:
            test_name = 'del4'
        else:
            test_name = 'default'

        name = f'{name}_{test_name}'
        subdir = f'{subdir}/{test_name}'

        config_filename = 'manufactured_solution.cfg'

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
                    component=component,
                    resolution=resolution,
                    name=f'init_{mesh_name}',
                    subdir=subdir,
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

            subdir = f'{basedir}/{test_name}/forward/{mesh_name}_{timestep}s'
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
                    del2=del2,
                    del4=del4,
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
            run_by_default=False,
        )
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.manufactured_solution', config_filename
        )
