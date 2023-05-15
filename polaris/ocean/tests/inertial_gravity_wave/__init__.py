from polaris import TestGroup
from polaris.ocean.tests.inertial_gravity_wave.convergence import Convergence


class InertialGravityWave(TestGroup):
    """
    A test group for inertial gravity wave test cases
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='inertial_gravity_wave')

        self.add_test_case(Convergence(test_group=self))
