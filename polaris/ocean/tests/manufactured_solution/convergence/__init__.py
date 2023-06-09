from polaris import TestCase
from polaris.ocean.tests.manufactured_solution.analysis import Analysis
from polaris.ocean.tests.manufactured_solution.forward import Forward
from polaris.ocean.tests.manufactured_solution.initial_state import (
    InitialState,
)
from polaris.ocean.tests.manufactured_solution.viz import Viz
from polaris.validate import compare_variables


class Convergence(TestCase):
    """
    The convergence test case for the manufactured solution test group

    Attributes
    ----------
    resolutions : list of floats
        The resolutions of the test case in km
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

        self.resolutions = [200, 100, 50, 25]
        for res in self.resolutions:
            self.add_step(InitialState(test_case=self, resolution=res))
            self.add_step(Forward(test_case=self, resolution=res))

        self.add_step(Analysis(test_case=self, resolutions=self.resolutions))
        self.add_step(Viz(test_case=self, resolutions=self.resolutions),
                      run_by_default=False)

    def validate(self):
        """
        Compare ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()
        variables = ['layerThickness', 'normalVelocity']
        for res in self.resolutions:
            compare_variables(test_case=self, variables=variables,
                              filename1=f'{res}km/forward/output.nc')
