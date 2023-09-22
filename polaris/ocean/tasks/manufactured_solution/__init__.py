from polaris import Task
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
    component.add_task(ManufacturedSolution(component=component))


class ManufacturedSolution(Task):
    """
    The convergence test case using the method of manufactured solutions

    Attributes
    ----------
    resolutions : list of floats
        The resolutions of the test case in km
    """
    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'manufactured_solution'
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
        Add the config file common to manufactured solution tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.manufactured_solution',
            'manufactured_solution.cfg')
