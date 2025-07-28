import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for merry-go-round task

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, component, name, resolution, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        subdir : str
            The directory the task is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolution = resolution

    def setup(self):
        super().setup()
        output_filenames = ['culled_mesh.nc', 'initial_state.nc']
        model = self.config.get('ocean', 'model')
        if model == 'mpas-ocean':
            output_filenames.append('culled_graph.info')

        for file in output_filenames:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger

        section = config['merry_go_round']
        temperature_left = section.getfloat('temperature_left')
        temperature_right = section.getfloat('temperature_right')
        tracer2_background = section.getfloat('tracer2_background')
        tracer3_background = section.getfloat('tracer3_background')
        salinity_background = section.getfloat('salinity_background')

        vert_coord = config.get('vertical_grid', 'coord_type')
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        # if not (vert_coord == 'z-level' or vert_coord == 'sigma'):
        #    raise ValueError('Vertical coordinate {vert_coord} not supported')

        # get reference resolution and number of layers
        ref_nz = config.getint('vertical_grid', 'vert_levels')
        ref_dc = config.getfloat('convergence', 'base_resolution') * 1e3

        dc = self.resolution * 1e3
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        nz = int(ref_nz / (dc / ref_dc))

        ds_mesh = make_planar_hex_mesh(
            nx=nx,
            ny=ny,
            dc=dc,
            nonperiodic_x=True,
            nonperiodic_y=False,
        )
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        ds = ds_mesh.copy()

        ds['ssh'] = xr.zeros_like(ds.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds.xCell)

        config.set('vertical_grid', 'vert_levels', str(nz))
        init_vertical_coord(config, ds)

        # Only the top layer moves in this test case
        ds['vertCoordMovementWeights'] = xr.ones_like(ds.refZMid)

        if vert_coord == 'z-level':
            ds['vertCoordMovementWeights'][:] = 0.0
            ds['vertCoordMovementWeights'][0] = 1.0

        # Fix the x-offset for initial condition functions
        x_min_edge = ds.xEdge.min()
        x_cell_adjusted = ds.xCell - x_min_edge
        x_edge_adjusted = ds.xEdge - x_min_edge
        x_min = x_cell_adjusted.min()
        x_max = x_cell_adjusted.max()
        lx_model = x_max - x_min

        x_cell_2D, _ = xr.broadcast(x_cell_adjusted, ds.refBottomDepth)
        x_edge_2D, _ = xr.broadcast(x_edge_adjusted, ds.refBottomDepth)

        # Initialize temperature
        x_mid = 0.5 * lx_model
        temperature = temperature_right * xr.ones_like(x_cell_2D)
        temperature = xr.where(
            x_cell_2D < x_mid, temperature_left, temperature_right
        )
        temperature = temperature.expand_dims(dim='Time', axis=0)
        ds['temperature'] = temperature

        # Initialize temperature
        ds['salinity'] = salinity_background * xr.ones_like(temperature)

        # Initialize normalVelocity
        z_mid = ds.zMid.squeeze('Time')
        z_mid_edge = z_mid.isel(nCells=ds.cellsOnEdge - 1).mean('TWO')

        # Define the streamfunctions for the velocity field
        # (we include the vertical streamfunction and velocity for reference)
        psi1 = 1 - ((x_edge_2D - 0.5 * lx_model) ** 4 / (0.5 * lx_model) ** 4)
        # psi2 = 1 - ((z_mid_edge + 0.5 * bottom_depth) ** 2 /
        #             (0.5 * bottom_depth) ** 2)

        # dpsi1 = - ((4 * x_edge_2D - 2. * lx_model) ** 3 /
        #            (0.5 * lx_model) ** 4)
        dpsi2 = -(2.0 * z_mid_edge + bottom_depth) / (0.5 * bottom_depth) ** 2

        u = psi1 * dpsi2
        # w = dpsi1 * psi2

        normal_velocity = u * np.cos(ds.angleEdge)
        # We set the normal velocity to zero at the horizontal boundaries
        normal_velocity = xr.where(
            (x_edge_2D <= x_min) | (x_edge_2D >= x_max), 0, normal_velocity
        )
        ds['normalVelocity'] = normal_velocity.expand_dims(dim='Time', axis=0)

        # Initialize debug tracers
        psi1_cell = 1.0 - (
            (x_cell_2D - 0.5 * lx_model) ** 4 / (0.5 * lx_model) ** 4
        )
        psi2_cell = 1.0 - (
            (z_mid + 0.5 * bottom_depth) ** 2 / (0.5 * bottom_depth) ** 2
        )
        psi = psi1_cell * psi2_cell

        ds['tracer1'] = xr.zeros_like(temperature)
        ds['tracer1'].isel(Time=0)[:] = 0.5 * (1 + np.tanh(2 * psi - 1))
        ds['tracer2'] = tracer2_background * xr.ones_like(temperature)
        ds['tracer3'] = tracer3_background * xr.ones_like(temperature)

        write_netcdf(ds, 'initial_state.nc')
