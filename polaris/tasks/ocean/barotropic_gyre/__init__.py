import os

from polaris import (
    Step as Step,
)
from polaris import (
    Task as Task,
)
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.barotropic_gyre.analysis import Analysis as Analysis
from polaris.tasks.ocean.barotropic_gyre.forward import Forward as Forward
from polaris.tasks.ocean.barotropic_gyre.init import Init as Init


def add_barotropic_gyre_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.tasks.ocean.Ocean
        the ocean component that the task will be added to
    """
    group_name = 'barotropic_gyre'
    group_dir = os.path.join('planar', group_name)
    config_filename = f'{group_name}.cfg'
    config_filepath = os.path.join(component.name, group_dir, config_filename)
    config = PolarisConfigParser(filepath=config_filepath)
    config.add_from_package(
        f'polaris.tasks.ocean.{group_name}', config_filename
    )

    for boundary_condition in ['free-slip', 'no-slip']:
        component.add_task(
            BarotropicGyre(
                component=component,
                subdir=group_dir,
                test_name='munk',
                boundary_condition=boundary_condition,
                config=config,
                config_filename=config_filename,
            )
        )


class BarotropicGyre(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(
        self,
        component,
        subdir,
        test_name,
        boundary_condition,
        config,
        config_filename,
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = f'{test_name}/{boundary_condition}'
        indir = f'{subdir}/{name}'
        super().__init__(component=component, name=name, subdir=indir)
        self.set_shared_config(config, link=config_filename)

        init_step = Init(
            component=component,
            indir=indir,
            boundary_condition=boundary_condition,
            test_name=test_name,
        )
        self.add_step(init_step)

        forward_step = Forward(
            component=component,
            indir=indir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            boundary_condition=boundary_condition,
            name='short_forward',
            run_time_steps=3,
            graph_target=os.path.join(init_step.path, 'culled_graph.info'),
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)

        forward = Forward(
            component=component,
            indir=indir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            boundary_condition=boundary_condition,
            name='long_forward',
            graph_target=os.path.join(init_step.path, 'culled_graph.info'),
        )
        forward.set_shared_config(config, link=config_filename)
        self.add_step(forward, run_by_default=False)

        analysis = Analysis(
            component=component,
            indir=indir,
            test_name=test_name,
            boundary_condition=boundary_condition,
        )
        analysis.set_shared_config(config, link=config_filename)
        self.add_step(analysis, run_by_default=False)
