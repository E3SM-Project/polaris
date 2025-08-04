import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord
from polaris.viz import plot_horiz_field


class Init(Step):
    """
    A step for creating a mesh and initial condition for baroclinic channel
    tasks

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, component, subdir, name='init'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to
        """
        super().__init__(component=component, name=name, indir=subdir)

        for file in [
            'base_mesh.nc',
            'culled_mesh.nc',
            'culled_graph.info',
            'forcing.nc',
        ]:
            self.add_output_file(file)
        self.name = name
        self.add_output_file('init.nc', validate_vars=['layerThickness'])

    def setup(self):
        super().setup()

    def run(self):
        """
        Create the at rest inital condition for the barotropic gyre testcase
        """
        config = self.config
        logger = self.logger
        # domain parameters
        lx = config.getfloat('barotropic_gyre', 'lx')
        ly = config.getfloat('barotropic_gyre', 'ly')
        resolution = config.getfloat('barotropic_gyre', 'resolution')

        # convert cell spacing to meters
        dc = resolution * 1e3

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=True
        )
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        # vertical coordinate parameters
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        # coriolis parameters
        f0 = config.getfloat('barotropic_gyre', 'f_0')
        beta = config.getfloat('barotropic_gyre', 'beta')
        # surface (wind) forcing parameters
        tau_0 = config.getfloat('barotropic_gyre', 'tau_0')

        # create a copy of the culled mesh to place the IC's into
        ds = ds_mesh.copy()

        # set the ssh initial condition to zero
        ds['ssh'] = xr.zeros_like(ds.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds.xCell)

        # use polaris framework functions to initialize the vertical coordinate
        init_vertical_coord(config, ds)

        # set the coriolis values
        for loc in ['Cell', 'Edge', 'Vertex']:
            ds[f'f{loc}'] = f0 + beta * ds[f'y{loc}']
        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        # set the initial condition for normalVelocity
        normal_velocity, _ = xr.broadcast(
            xr.zeros_like(ds_mesh.xEdge), ds.refBottomDepth
        )
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)
        ds['normalVelocity'] = normal_velocity

        # write the initial condition file
        write_netcdf(ds, 'init.nc')

        # set the wind stress forcing
        ds_forcing = xr.Dataset()
        # Convert from km to m
        ly = ly * 1e3
        wind_stress_zonal = -tau_0 * np.cos(
            np.pi * (ds.yCell - ds.yCell.min()) / ly
        )
        wind_stress_meridional = xr.zeros_like(ds.xCell)
        ds_forcing['windStressZonal'] = wind_stress_zonal.expand_dims(
            dim='Time', axis=0
        )
        ds_forcing['windStressMeridional'] = (
            wind_stress_meridional.expand_dims(dim='Time', axis=0)
        )
        write_netcdf(ds_forcing, 'forcing.nc')

        cell_mask = ds.maxLevelCell >= 1

        plot_horiz_field(
            ds_mesh,
            ds_forcing['windStressZonal'],
            'forcing_wind_stress_zonal.png',
            cmap='cmo.balance',
            show_patch_edges=True,
            field_mask=cell_mask,
            vmin=-0.1,
            vmax=0.1,
        )
