import numpy as np
import pyproj
from mpas_tools.io import write_netcdf
from mpas_tools.planar_hex import make_planar_hex_mesh
from mpas_tools.translate import translate

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.tasks.isomip_plus.projection import get_projections


class PlanarMesh(Step):
    """
    A step for creating a planar ISOMIP+ mesh

    Attributes
    ----------
    resolution : float
        The resolution in km of the mesh

    """
    def __init__(self, component, resolution, subdir, config):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The resolution in km of the mesh

        subdir : str
            the subdirectory for the step

        config : polaris.config.PolarisConfigParser
            A shared config parser
        """
        super().__init__(component=component, name='base_mesh', subdir=subdir)

        self.resolution = resolution
        self.set_shared_config(config, link='isomip_plus.cfg')

        self.add_output_file('base_mesh.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        section = config['isomip_plus']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        lat0 = section.getfloat('lat0')
        buffer = section.getfloat('buffer')

        resolution = self.resolution

        nx, ny = compute_planar_hex_nx_ny(lx + 2 * buffer, ly + 2 * buffer,
                                          resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc, nonperiodic_x=True,
                                       nonperiodic_y=True)

        translate(mesh=ds_mesh, xOffset=-1e3 * buffer, yOffset=-1e3 * buffer)

        ds_mesh['xIsomipCell'] = ds_mesh.xCell
        ds_mesh['yIsomipCell'] = ds_mesh.yCell
        ds_mesh['xIsomipVertex'] = ds_mesh.xVertex
        ds_mesh['yIsomipVertex'] = ds_mesh.yVertex

        # add latitude and longitude using a stereographic projection
        projection, lat_lon_projection = get_projections(lat0)
        transformer = pyproj.Transformer.from_proj(projection,
                                                   lat_lon_projection)

        for suffix in ['Cell', 'Edge', 'Vertex']:
            x = ds_mesh[f'x{suffix}'].values
            y = ds_mesh[f'y{suffix}'].values
            lon, lat = transformer.transform(x, y)
            ds_mesh[f'lat{suffix}'] = (f'n{suffix}', np.deg2rad(lat))
            ds_mesh[f'lon{suffix}'] = (f'n{suffix}', np.deg2rad(lon))

        write_netcdf(ds_mesh, 'base_mesh.nc')
