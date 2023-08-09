from polaris import TestCase
from polaris.ocean.tests.global_convergence.cosine_bell.analysis import (
    Analysis,
)
from polaris.ocean.tests.global_convergence.cosine_bell.forward import Forward
from polaris.ocean.tests.global_convergence.cosine_bell.init import Init
from polaris.ocean.tests.global_convergence.cosine_bell.viz import Viz, VizMap
from polaris.validate import compare_variables


class CosineBell(TestCase):
    """
    A test case for creating a global MPAS-Ocean mesh

    Attributes
    ----------
    resolutions : list of int
        A list of mesh resolutions

    meshes : polaris.ocean.tests.global_convergence.meshes.Meshes
        The test case defining the meshes for this test case to use

    include_viz : bool
        Include VizMap and Viz steps for each resolution
    """
    def __init__(self, test_group, meshes, include_viz):
        """
        Create test case for creating a global MPAS-Ocean mesh

        Parameters
        ----------
        test_group : polaris.ocean.tests.global_convergence.GlobalConvergence
            The global ocean test group that this test case belongs to

        meshes : polaris.ocean.tests.global_convergence.meshes.Meshes
            The test case defining the meshes for this test case to use

        include_viz : bool
            Include VizMap and Viz steps for each resolution
        """
        self.meshes = meshes
        icosahedral = meshes.icosahedral

        if icosahedral:
            subdir = 'icos/cosine_bell'
        else:
            subdir = 'qu/cosine_bell'
        if include_viz:
            subdir = f'{subdir}_with_viz'
        super().__init__(test_group=test_group, name='cosine_bell',
                         subdir=subdir)
        self.include_viz = include_viz

        self.resolutions = dict()
        self._setup_steps()

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()
        config = self.config
        config.add_from_package('polaris.mesh', 'mesh.cfg')

        config.set('spherical_mesh', 'mpas_mesh_filename', 'mesh.nc')

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()

    def validate(self):
        """
        Validate variables against a baseline
        """
        for mesh_name, resolution in self.resolutions.items():
            compare_variables(test_case=self,
                              variables=['normalVelocity', 'tracer1'],
                              filename1=f'{mesh_name}/forward/output.nc')

    def _setup_steps(self):
        """ setup steps given resolutions """
        resolutions = self.meshes.resolutions
        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        self.steps = dict()
        self.steps_to_run = list()

        self.resolutions = resolutions

        for mesh_name, resolution in self.resolutions.items():
            mesh_step = self.meshes.steps[mesh_name]
            self.add_step(Init(test_case=self, mesh_step=mesh_step))

            self.add_step(Forward(test_case=self, resolution=resolution,
                                  mesh_name=mesh_name))

            if self.include_viz:
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
                               icosahedral=self.meshes.icosahedral))
