import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.tests.manufactured_solution.exact_solution import (
    ExactSolution,
)
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):
    """
    A step for creating a mesh and initial condition for the
    manufactured solution test cases

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
                         name=f'init_{resolution}km',
                         subdir=f'{resolution}km/init')
        self.resolution = float(resolution)

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        config = self.config

        section = config['manufactured_solution']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        coriolis_parameter = section.getfloat('coriolis_parameter')

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

        ds['ssh'] = xr.zeros_like(ds_mesh.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds_mesh.xCell)

        init_vertical_coord(config, ds)

        ds['fCell'] = coriolis_parameter * xr.ones_like(ds_mesh.xCell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        # Evaluate the exact solution at time=0
        exact_solution = ExactSolution(config, ds)
        ssh = exact_solution.ssh(0.0)
        normal_velocity = exact_solution.normal_velocity(0.0)

        ssh = ssh.expand_dims(dim='Time', axis=0)
        ds['ssh'] = ssh

        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)
        ds['normalVelocity'] = normal_velocity

        layer_thickness = ssh + bottom_depth
        layer_thickness, _ = xr.broadcast(layer_thickness, ds.refBottomDepth)
        layer_thickness = layer_thickness.transpose('Time', 'nCells',
                                                    'nVertLevels')
        ds['layerThickness'] = layer_thickness

        write_netcdf(ds, 'initial_state.nc')
