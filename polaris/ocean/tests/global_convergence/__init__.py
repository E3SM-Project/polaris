from polaris.ocean.tests.global_convergence.cosine_bell import CosineBell
from polaris.testgroup import TestGroup


class GlobalConvergence(TestGroup):
    """
    A test group for setting up global initial conditions and performing
    regression testing and dynamic adjustment for MPAS-Ocean
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='global_convergence')

        for icosahedral in [False, True]:
            self.add_test_case(CosineBell(test_group=self,
                                          icosahedral=icosahedral))
