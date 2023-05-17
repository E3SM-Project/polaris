import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.tests.inertial_gravity_wave.exact_solution import (
    ExactSolution,
)
from polaris.ocean.vertical import init_vertical_coord
from polaris.viz import plot_horiz_field


class InitialState(Step):
    """
    A step for creating a mesh and initial condition for the
    inertial gravity wave test cases

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, test_case, resolution):
        """
        Create the step

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        resolution : float
            The resolution of the test case in km
        """
        super().__init__(test_case=test_case,
                         name=f'initial_state_{resolution}km',
                         subdir=f'{resolution}km/initial_state')
        self.resolution = float(resolution)

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        config = self.config

        section = config['inertial_gravity_wave']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        f0 = section.getfloat('f0')
        eta0 = section.getfloat('eta0')
        npx = section.getfloat('nx')
        npy = section.getfloat('ny')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
                                       nonperiodic_x=False,
                                       nonperiodic_y=False)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds = ds_mesh.copy()

        ds['ssh'] = xr.zeros_like(ds.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds.xCell)

        init_vertical_coord(config, ds)

        ds['fCell'] = f0 * xr.ones_like(ds.xCell)
        ds['fEdge'] = f0 * xr.ones_like(ds.xEdge)
        ds['fVertex'] = f0 * xr.ones_like(ds.xVertex)

        ds_mesh['maxLevelCell'] = ds.maxLevelCell
        exact_solution = ExactSolution(ds, eta0, npx, npy, lx, ly)

        ssh = exact_solution.eta(0.0)
        ssh = ssh.expand_dims(dim='Time', axis=0)
        ds['ssh'] = ssh

        plot_horiz_field(ds, ds_mesh, 'ssh',
                         'initial_ssh.png', t_index=0)

        layerThickness = ssh + bottom_depth
        layerThickness, _ = xr.broadcast(layerThickness, ds.refBottomDepth)
        layerThickness = layerThickness.transpose('Time', 'nCells',
                                                  'nVertLevels')
        ds['layerThickness'] = layerThickness

        normal_velocity = exact_solution.normalVelocity(0.0)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)
        ds['normalVelocity'] = normal_velocity
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'initial_normalVelocity.png', t_index=0)

        write_netcdf(ds, 'initial_state.nc')
