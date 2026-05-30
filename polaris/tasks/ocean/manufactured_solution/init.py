import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.coriolis import add_coriolis_to_dataset
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.manufactured_solution.exact_solution import (
    ExactSolution,
)


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for the
    manufactured solution test cases

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """

    def __init__(self, component, resolution, subdir, name):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The resolution of the test case in km

        taskdir : str
            The subdirectory that the task belongs to
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolution = resolution

    def setup(self):
        super().setup()
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='culled_mesh.nc',
            base_mesh_filename='base_mesh.nc',
            graph_filename='culled_graph.info',
        )

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

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=False, nonperiodic_y=False
        )
        self.write_model_dataset(ds_mesh, 'base_mesh.nc', config)

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(ds_mesh, 'culled_mesh.nc', config)

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds = ds_mesh.copy()

        ds['ssh'] = xr.zeros_like(ds_mesh.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds_mesh.xCell)

        init_vertical_coord(config, ds)

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
        layer_thickness = layer_thickness.transpose(
            'Time', 'nCells', 'nVertLevels'
        )
        ds['layerThickness'] = layer_thickness
        ds['temperature'] = xr.zeros_like(layer_thickness)
        ds['salinity'] = xr.ones_like(layer_thickness)

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)
