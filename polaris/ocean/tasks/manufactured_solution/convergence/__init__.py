from polaris import Task
from polaris.ocean.tasks.manufactured_solution.analysis import Analysis
from polaris.ocean.tasks.manufactured_solution.forward import Forward
from polaris.ocean.tasks.manufactured_solution.init import Init
from polaris.ocean.tasks.manufactured_solution.viz import Viz
from polaris.validate import compare_variables


class Convergence(Task):
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
        name = 'convergence'
        subdir = f'manufactured_solution/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        self.resolutions = [200, 100, 50, 25]
        for res in self.resolutions:
            self.add_step(Init(task=self, resolution=res))
            self.add_step(Forward(task=self, resolution=res))

        self.add_step(Analysis(task=self, resolutions=self.resolutions))
        self.add_step(Viz(task=self, resolutions=self.resolutions),
                      run_by_default=False)

    def configure(self):
        """
        Add the config file common to manufactured solution tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.manufactured_solution',
            'manufactured_solution.cfg')
