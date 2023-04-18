from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.ocean.tests.global_convergence.cosine_bell.analysis import (
    Analysis,
)
from polaris.ocean.tests.global_convergence.cosine_bell.forward import Forward
from polaris.ocean.tests.global_convergence.cosine_bell.init import Init
from polaris.ocean.tests.global_convergence.cosine_bell.viz import Viz, VizMap
from polaris.testcase import TestCase
from polaris.validate import compare_variables


class CosineBell(TestCase):
    """
    A test case for creating a global MPAS-Ocean mesh

    Attributes
    ----------
    resolutions : list of int
        A list of mesh resolutions

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW meshes
    """
    def __init__(self, test_group, icosahedral):
        """
        Create test case for creating a global MPAS-Ocean mesh

        Parameters
        ----------
        test_group : polaris.ocean.tests.cosine_bell.GlobalOcean
            The global ocean test group that this test case belongs to

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes
        """
        if icosahedral:
            subdir = 'icos/cosine_bell'
        else:
            subdir = 'qu/cosine_bell'
        super().__init__(test_group=test_group, name='cosine_bell',
                         subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral

        # add the steps with default resolutions so they can be listed
        config = PolarisConfigParser()
        config.add_from_package(self.__module__, f'{self.name}.cfg')
        self._setup_steps(config)

    def configure(self):
        """
        Set config options for the test case
        """
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        config.set('spherical_mesh', 'mpas_mesh_filename', 'mesh.nc')

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps(config)

        init_options = dict()
        for option in ['temperature', 'salinity', 'lat_center', 'lon_center',
                       'radius', 'psi0', 'vel_pd']:
            init_options[f'config_cosine_bell_{option}'] = \
                config.get('cosine_bell', option)

    def validate(self):
        """
        Validate variables against a baseline
        """
        for resolution in self.resolutions:
            if self.icosahedral:
                mesh_name = f'Icos{resolution}'
            else:
                mesh_name = f'QU{resolution}'
            compare_variables(test_case=self,
                              variables=['normalVelocity', 'tracer1'],
                              filename1=f'{mesh_name}/forward/output.nc')

    def _setup_steps(self, config):
        """ setup steps given resolutions """
        if self.icosahedral:
            default_resolutions = '60, 120, 240, 480'
        else:
            default_resolutions = '60, 90, 120, 150, 180, 210, 240'

        # set the default values that a user may change before setup
        config.set('cosine_bell', 'resolutions', default_resolutions,
                   comment='a list of resolutions (km) to test')

        # get the resolutions back, perhaps with values set in the user's
        # config file, which takes priority over what we just set above
        resolutions = config.getlist('cosine_bell', 'resolutions', dtype=int)

        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        self.steps = dict()
        self.steps_to_run = list()

        self.resolutions = resolutions

        for resolution in resolutions:
            if self.icosahedral:
                mesh_name = f'Icos{resolution}'
            else:
                mesh_name = f'QU{resolution}'

            name = f'{mesh_name}_mesh'
            subdir = f'{mesh_name}/mesh'
            if self.icosahedral:
                self.add_step(IcosahedralMeshStep(
                    test_case=self, name=name, subdir=subdir,
                    cell_width=resolution))
            else:
                self.add_step(QuasiUniformSphericalMeshStep(
                    test_case=self, name=name, subdir=subdir,
                    cell_width=resolution))

            self.add_step(Init(test_case=self, mesh_name=mesh_name))

            self.add_step(Forward(test_case=self, resolution=resolution,
                                  mesh_name=mesh_name))

            name = f'{mesh_name}_map'
            subdir = f'{mesh_name}/map'
            viz_map = VizMap(test_case=self, name=name, subdir=subdir,
                             mesh_name=mesh_name)
            self.add_step(viz_map)

            name = f'{mesh_name}_viz'
            subdir = f'{mesh_name}/viz'
            self.add_step(Viz(test_case=self, name=name, subdir=subdir,
                              viz_map=viz_map, mesh_name=mesh_name))

        self.add_step(Analysis(test_case=self, resolutions=resolutions,
                               icosahedral=self.icosahedral))
