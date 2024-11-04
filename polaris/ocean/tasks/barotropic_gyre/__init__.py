from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.tasks.barotropic_gyre.analysis import Analysis
from polaris.ocean.tasks.barotropic_gyre.forward import Forward
from polaris.ocean.tasks.barotropic_gyre.init import Init


def add_barotropic_gyre_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    test_name = 'default'
    subdir = f'planar/barotropic_gyre/{test_name}'
    config_filename = 'barotropic_gyre.cfg'
    config = PolarisConfigParser(filepath=f'{subdir}/{config_filename}')
    config.add_from_package('polaris.ocean.tasks.barotropic_gyre',
                            config_filename)
    component.add_task(BarotropicGyre(component=component,
                                      test_name=test_name,
                                      config=config))


class BarotropicGyre(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component, test_name, config, smoke_test=False):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        group_name = 'barotropic_gyre'
        name = f'{group_name}_{test_name}'
        subdir = f'planar/{group_name}/{test_name}'
        super().__init__(component=component, name=name, subdir=subdir)

        config_filename = 'barotropic_gyre.cfg'

        init = Init(component=component, subdir=subdir)
        init.set_shared_config(config, link=config_filename)
        self.add_step(init)

        forward = Forward(component=component, indir=self.subdir, ntasks=None,
                          min_tasks=None, openmp_threads=1,
                          name='short_forward', run_time_steps=3,
                          graph_target=f'{init.path}/culled_graph.info')
        forward.set_shared_config(config, link=config_filename)
        self.add_step(forward)

        forward = Forward(component=component, indir=self.subdir, ntasks=None,
                          min_tasks=None, openmp_threads=1,
                          name='long_forward',
                          graph_target=f'{init.path}/culled_graph.info')
        forward.set_shared_config(config, link=config_filename)
        self.add_step(forward, run_by_default=False)

        analysis = Analysis(component=component, indir=self.subdir)
        analysis.set_shared_config(config, link=config_filename)
        self.add_step(analysis, run_by_default=False)
