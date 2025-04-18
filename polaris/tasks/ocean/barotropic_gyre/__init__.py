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
    test_name = 'default'
    component.add_task(
        BarotropicGyre(component=component, test_name=test_name)
    )


class BarotropicGyre(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component, test_name):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        group_name = 'barotropic_gyre'
        name = f'{group_name}_{test_name}'
        subdir = os.path.join('planar', group_name, test_name)
        super().__init__(component=component, name=name, subdir=subdir)

        config = self.config
        config_filename = f'{group_name}.cfg'
        config.filepath = os.path.join(component.name, subdir, config_filename)
        config.add_from_package(
            f'polaris.tasks.ocean.{group_name}', config_filename
        )
        self.set_shared_config(config, link=config_filename)

        init = Init(component=component, subdir=subdir)
        init.set_shared_config(config, link=config_filename)
        self.add_step(init)

        forward = Forward(
            component=component,
            indir=self.subdir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            name='short_forward',
            run_time_steps=3,
            graph_target=os.path.join(init.path, 'culled_graph.info'),
        )
        forward.set_shared_config(config, link=config_filename)
        self.add_step(forward)

        forward = Forward(
            component=component,
            indir=self.subdir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            name='long_forward',
            graph_target=os.path.join(init.path, 'culled_graph.info'),
        )
        forward.set_shared_config(config, link=config_filename)
        self.add_step(forward, run_by_default=False)

        analysis = Analysis(
            component=component,
            indir=self.subdir,
            boundary_condition='free slip',
        )
        analysis.set_shared_config(config, link=config_filename)
        self.add_step(analysis, run_by_default=False)
