from polaris import TestCase
from polaris.ocean.tests.manufactured_solution.analysis import Analysis
from polaris.ocean.tests.manufactured_solution.forward import Forward
from polaris.ocean.tests.manufactured_solution.initial_state import (
    InitialState,
)
from polaris.ocean.tests.manufactured_solution.viz import Viz


class Convergence(TestCase):
    """
    The convergence test case for the manufactured solution test group
    """
    def __init__(self, test_group):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.manufactured_solution.
                     ManufacturedSolution
            The test group that this test case belongs to
        """
        name = 'convergence'
        super().__init__(test_group=test_group, name=name)

        resolutions = [200, 100, 50, 25]
        for res in resolutions:
            self.add_step(InitialState(test_case=self, resolution=res))
            self.add_step(Forward(test_case=self, resolution=res))

        self.add_step(Analysis(test_case=self, resolutions=resolutions))
        self.add_step(Viz(test_case=self, resolutions=resolutions),
                      run_by_default=False)
