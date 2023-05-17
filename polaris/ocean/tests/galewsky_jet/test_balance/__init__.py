from polaris.mesh.spherical import IcosahedralMeshStep
# from polaris.ocean.tests.galewsky_jet.forward import Forward
# from polaris.ocean.tests.galewsky_jet.initial_state import InitialState
from polaris.testcase import TestCase


class TestBalance(TestCase):
    """
    A class to define the Galewsky jet test balance test cases

    Attributes
    ----------
    resolution : str
        The resolution of the test case
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group :
        polaris.ocean.tests.galewsky_jet.GalewskyJet
            The test group that this test case belongs to

        resolution : str
            The resolution of the test case
        """
        name = 'balanced'
        self.resolution = resolution

        subdir = f'{resolution}/{name}'
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        self.add_step(IcosahedralMeshStep(
            test_case=self, cell_width=int(resolution[:-2])))
        # self.add_step(
        #    InitialState(test_case=self, resolution=resolution))
        # self.add_step(
        #    Forward(test_case=self, resolution=resolution,
        #            long=long))

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        config.set('spherical_mesh', 'mpas_mesh_filename', 'mesh.nc')
