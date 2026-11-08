from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.landice.mesh import make_mali_mesh
from polaris.landice.mismip_plus.geometry import DOMAIN_LENGTH
from polaris.landice.mismip_plus.mesh import make_mismip_plus_mesh


class MismipPlusMesh(Step):
    """
    A step for making the planar mesh of MISMIP+ and the MALI mesh from it

    Attributes
    ----------
    resolution : float
        The nominal resolution of the mesh in km

    length : float
        The length in m that the cells span in x, before the gutter
    """

    def __init__(self, component, subdir, resolution, length=DOMAIN_LENGTH):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The mesh component the step belongs to

        subdir : str
            The subdirectory for the step

        resolution : float
            The nominal resolution of the mesh in km

        length : float, optional
            The length in m that the cells span in x, before the gutter:
            the domain's length, or more for a mesh that extends past the
            calving front
        """
        super().__init__(component=component, name='mesh', subdir=subdir)
        self.resolution = resolution
        self.length = length

        for filename in ['planar_mesh.nc', 'mali_mesh.nc', 'graph.info']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        logger = self.logger
        section = self.config['mismip_plus_mesh']

        ds_mesh = make_mismip_plus_mesh(
            resolution=self.resolution, logger=logger, length=self.length
        )
        write_netcdf(ds_mesh, 'planar_mesh.nc')

        make_mali_mesh(
            in_filename='planar_mesh.nc',
            out_filename='mali_mesh.nc',
            levels=section.getint('levels'),
            logger=logger,
            vertical_spacing=section.get('vertical_spacing'),
            thermal=True,
            dirichlet=True,
            graph_filename='graph.info',
        )
