import os
import shutil

from mpas_tools.io import open_dataset, write_netcdf

from polaris.landice.mismip_plus.geometry import DOMAIN_WIDTH
from polaris.step import Step
from polaris.tasks.e3sm.init.misomip.projection import (
    SPHERE_RADIUS,
    add_lat_lon,
)
from polaris.tasks.e3sm.init.misomip.scrip import write_scrip


class OceanMeshStep(Step):
    """
    A step for giving the ISOMIP+ ocean mesh the projection's latitude and
    longitude, and for writing its SCRIP file and graph

    The ISOMIP+ tasks' ``xIsomipCell`` and ``yIsomipCell`` are kept, since
    the ISOMIP+ restoring reads them.
    """

    def __init__(self, component, subdir, cull_mesh_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        cull_mesh_step : polaris.tasks.ocean.isomip_plus.mesh.CullMesh
            The ISOMIP+ step that makes the culled ocean mesh
        """
        super().__init__(component=component, name='ocean_mesh', subdir=subdir)
        for filename in ['culled_mesh.nc', 'culled_graph.info']:
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(cull_mesh_step.path, filename),
            )
        for filename in ['ocean_mesh.nc', 'ocean_scrip.nc', 'graph.info']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        ds_mesh = open_dataset('culled_mesh.nc')
        add_lat_lon(ds_mesh)
        ds_mesh.attrs['sphere_radius'] = SPHERE_RADIUS
        write_netcdf(ds_mesh, 'ocean_mesh.nc')
        write_scrip(ds_mesh, 'ocean_scrip.nc')
        shutil.copyfile('culled_graph.info', 'graph.info')


class LandiceMeshStep(Step):
    """
    A step for giving the MISMIP+ MALI mesh the projection's latitude and
    longitude, and for writing its SCRIP file

    The cells on the domain's walls are halved in the mesh, so their
    polygons are trimmed to the walls in the SCRIP file.
    """

    def __init__(self, component, subdir, mesh_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        mesh_step : polaris.tasks.mesh.planar.mismip_plus.MismipPlusMesh
            The MISMIP+ step that makes MALI's mesh
        """
        super().__init__(
            component=component, name='landice_mesh', subdir=subdir
        )
        self.add_input_file(
            filename='mali_mesh.nc',
            work_dir_target=os.path.join(mesh_step.path, 'mali_mesh.nc'),
        )
        for filename in ['landice_mesh.nc', 'landice_scrip.nc']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step
        """
        ds_mesh = open_dataset('mali_mesh.nc')
        add_lat_lon(ds_mesh)
        write_netcdf(ds_mesh, 'landice_mesh.nc')
        write_scrip(ds_mesh, 'landice_scrip.nc', y_min=0.0, y_max=DOMAIN_WIDTH)
