from polaris import TestCase
from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.validate import compare_variables


class Meshes(TestCase):
    """
    A test case for creating a global MPAS-Ocean mesh

    Attributes
    ----------
    resolutions : dict
        A dictionary with mesh names as the keys and resolutions in km as the
        values

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes
    """
    def __init__(self, test_group, icosahedral):
        """
        Create test case for creating a global MPAS-Ocean mesh

        Parameters
        ----------
        test_group : polaris.ocean.tests.global_convergence.GlobalConvergence
            The global ocean test group that this test case belongs to

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes
        """
        if icosahedral:
            subdir = 'icos/meshes'
        else:
            subdir = 'qu/meshes'
        super().__init__(test_group=test_group, name='meshes',
                         subdir=subdir)
        self.resolutions = dict()
        self.icosahedral = icosahedral

        # add the steps with default resolutions so they can be listed
        config = PolarisConfigParser()
        package = 'polaris.ocean.tests.global_convergence.meshes'
        config.add_from_package(package, 'meshes.cfg')
        self._setup_steps(config)

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        config.set('spherical_mesh', 'mpas_mesh_filename', 'mesh.nc')

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(config)

    def _setup_steps(self, config):
        """ setup steps given resolutions """
        resolutions = self._get_resolutions(config)
        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        self.steps = dict()
        self.steps_to_run = list()

        self.resolutions = resolutions

        for mesh_name, resolution in resolutions.items():
            if self.icosahedral:
                self.add_step(IcosahedralMeshStep(
                    test_case=self, name=mesh_name, cell_width=resolution))
            else:
                self.add_step(QuasiUniformSphericalMeshStep(
                    test_case=self, name=mesh_name, cell_width=resolution))

    def _get_resolutions(self, config):
        """ get a dictionary of resolutions """
        if self.icosahedral:
            default_resolutions = '60, 120, 240, 480'
        else:
            default_resolutions = '60, 90, 120, 150, 180, 210, 240'

        # set the default values that a user may change before setup
        config.set('global_convergence', 'resolutions', default_resolutions,
                   comment='a list of resolutions (km) to test')

        # get the resolutions back, perhaps with values set in the user's
        # config file, which takes priority over what we just set above
        res_list = config.getlist('global_convergence', 'resolutions',
                                  dtype=float)

        resolutions = dict()
        for resolution in res_list:
            if self.icosahedral:
                mesh_name = f'Icos{resolution:g}'
            else:
                mesh_name = f'QU{resolution:g}'
            resolutions[mesh_name] = resolution

        return resolutions
