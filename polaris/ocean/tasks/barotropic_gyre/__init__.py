from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.tasks.barotropic_gyre.forward import Forward
from polaris.ocean.tasks.barotropic_gyre.init import Init


def add_barotropic_gyre_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(BarotropicGyre(component=component))


class BarotropicGyre(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'barotropic_gyre'
        subdir = f'planar/{name}'
        super().__init__(component=component, name=name, subdir=subdir)
        init_step = Init(component=component, subdir=self.subdir)
        self.add_step(init_step)

        config_filename = 'barotropic_gyre.cfg'
        self.config.add_from_package('polaris.ocean.tasks.barotropic_gyre',
                                     config_filename)
        self.add_step(
            Forward(component=component, indir=self.subdir, ntasks=None,
                    min_tasks=None, openmp_threads=1,
                    run_time_steps=3,
                    graph_target=f'{init_step.path}/culled_graph.info'))
