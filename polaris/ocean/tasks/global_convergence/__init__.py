from polaris import TestGroup
from polaris.ocean.tasks.global_convergence.cosine_bell import CosineBell


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
            for include_viz in [False, True]:
                self.add_task(CosineBell(test_group=self,
                                         icosahedral=icosahedral,
                                         include_viz=include_viz))
