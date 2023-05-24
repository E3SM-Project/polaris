from polaris.mesh.spherical import IcosahedralMeshStep
from polaris.ocean.tests.galewsky_jet.barotropic_instability.forward import (
    Forward,
)
from polaris.ocean.tests.galewsky_jet.barotropic_instability.initial_state import (
    InitialState,
)
from polaris.ocean.tests.galewsky_jet.barotropic_instability.viz import Viz
from polaris.testcase import TestCase


class BarotropicInstability(TestCase):
    """
    A class to define the Galewsky jet barotropic instability
    test case (6 days for instbaility development)

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

        resolution : float
            The resolution of the test case (in km)
        """
        name = 'barotropic_instability'
        self.resolution = resolution
        res = int(resolution)
        subdir = f'{res}km/{name}'
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        self.add_step(IcosahedralMeshStep(
            test_case=self, cell_width=resolution))
        self.add_step(
            InitialState(test_case=self, resolution=resolution))
        self.add_step(
            Forward(test_case=self, resolution=resolution))

        mesh_name = f'Icos{res}'
        name = f'{mesh_name}_viz'
        subdir = 'viz'
        self.add_step(Viz(test_case=self, name=name, subdir=subdir,
                          mesh_name=mesh_name))

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        config.set('spherical_mesh', 'mpas_mesh_filename',
                   'mesh.nc')
