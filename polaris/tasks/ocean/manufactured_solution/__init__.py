import os
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

    component : polaris.tasks.ocean.Ocean
        the ocean component that the task will be added to
    """
    basedir = 'planar/manufactured_solution'
    config_filename = 'manufactured_solution.cfg'
    filepath = os.path.join(component.name, basedir, config_filename)
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
        component : polaris.tasks.ocean.Ocean
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
            init_step = component.get_or_create_shared_step(
                step_cls=Init,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                resolution=resolution,
                name=f'init_{mesh_name}',
            )
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
            forward_step = component.get_or_create_shared_step(
                step_cls=Forward,
                subdir=subdir,
                config=config,
                config_filename=config_filename,
                refinement=refinement,
                refinement_factor=refinement_factor,
                name=f'forward_{mesh_name}_{timestep}s',
                init=init_step,
                del2=del2,
                del4=del4,
            )
            self.add_step(forward_step, symlink=symlink)

            analysis_dependencies['mesh'][refinement_factor] = init_step
            analysis_dependencies['init'][refinement_factor] = init_step
            analysis_dependencies['forward'][refinement_factor] = forward_step

        self.add_step(
            component.get_or_create_shared_step(
                step_cls=Analysis,
                subdir=f'{self.subdir}/analysis',
                config=config,
                config_filename=config_filename,
                dependencies=analysis_dependencies,
                refinement=refinement,
            )
        )
        self.add_step(
            component.get_or_create_shared_step(
                step_cls=Viz,
                subdir=f'{self.subdir}/viz',
                config=config,
                config_filename=config_filename,
                dependencies=analysis_dependencies,
                refinement=refinement,
            ),
            run_by_default=False,
        )
        config.add_from_package('polaris.ocean.convergence', 'convergence.cfg')
        config.add_from_package(
            'polaris.tasks.ocean.manufactured_solution', config_filename
        )
