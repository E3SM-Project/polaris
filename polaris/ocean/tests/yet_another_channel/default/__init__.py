import os

from polaris import TestCase
from polaris.ocean.tests.yet_another_channel.initial_state import InitialState

class Default(TestCase):
    """
    The default test case for the "yet another channel" test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.yet_another_channel.YetAnotherChannel
            The test group that this test case belongs to
        resolution : float
            The resolution of the test case in km
        """
        name = 'default'
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name, subdir=subdir)

        self.add_step(
            InitialState(test_case=self, resolution=resolution))
