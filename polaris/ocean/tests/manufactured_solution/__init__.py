from polaris import TestGroup
from polaris.ocean.tests.manufactured_solution.convergence import Convergence


class ManufacturedSolution(TestGroup):
    """
    A test group for manufactured solution test cases
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='manufactured_solution')

        self.add_test_case(Convergence(test_group=self))
