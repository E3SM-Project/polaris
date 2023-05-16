from polaris import TestCase
from polaris.ocean.tests.inertial_gravity_wave.initial_state import (
    InitialState,
)


class Convergence(TestCase):
    """
    The convergence test case for the inertial gravity wave test group
    """

    def __init__(self, test_group):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.inertial_gravity_wave.
                     InertialGravityWave
            The test group that this test case belongs to
        """
        name = 'convergence'
        super().__init__(test_group=test_group, name=name)

        for res in [200.0, 100.0, 50.0]:
            self.add_step(InitialState(test_case=self, resolution=res))
