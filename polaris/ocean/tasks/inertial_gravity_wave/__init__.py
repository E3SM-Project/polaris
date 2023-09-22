from polaris import Task
from polaris.ocean.tasks.inertial_gravity_wave.analysis import Analysis
from polaris.ocean.tasks.inertial_gravity_wave.forward import Forward
from polaris.ocean.tasks.inertial_gravity_wave.init import Init
from polaris.ocean.tasks.inertial_gravity_wave.viz import Viz


def add_inertial_gravity_wave_tasks(component):
    """
    Add a task that defines a convergence test for inertial gravity waves

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    component.add_task(InertialGravityWave(component=component))


class InertialGravityWave(Task):
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
        name = 'inertial_gravity_wave'
        subdir = f'planar/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        self.resolutions = [200., 100., 50., 25.]
        for res in self.resolutions:
            self.add_step(Init(component=component, resolution=res,
                               taskdir=self.subdir))
            self.add_step(Forward(component=component, resolution=res,
                                  taskdir=self.subdir))

        self.add_step(Analysis(component=component,
                               resolutions=self.resolutions,
                               taskdir=self.subdir))
        self.add_step(Viz(component=component, resolutions=self.resolutions,
                          taskdir=self.subdir),
                      run_by_default=False)

    def configure(self):
        """
        Add the config file common to inertial gravity wave tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.inertial_gravity_wave',
            'inertial_gravity_wave.cfg')
