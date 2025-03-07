import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):
    """
    A step for creating a mesh and initial condition for merry-go-round task

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, component, resolution, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='init', indir=indir)
        self.resolution = resolution

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info']:
            self.add_output_file(file)

        self.add_output_file('initial_state.nc',
                             validate_vars=['temperature', 'salinity',
                                            'layerThickness'])

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

        if not (vert_coord == 'z-level' or vert_coord == 'sigma'):
            raise ValueError('Vertical coordinate {vert_coord} not supported')

        lx, ly = (500, 5)
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        nz = int(50 / (self.resolution / 5))

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=1e3 * self.resolution,
                                       nonperiodic_x=False,
                                       nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        ds = ds_mesh.copy()
        x_cell_adjusted = ds.xCell - ds.xEdge.min()
        x_edge_adjusted = ds.xEdge - ds.xEdge.min()

        ds['ssh'] = xr.ones_like(ds.xCell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(ds.xCell)

        config.set('vertical_grid', 'vert_levels', str(nz))
        init_vertical_coord(config, ds)

        x_min = x_cell_adjusted.min()
        x_max = x_cell_adjusted.max()
        x_mid = 0.5 * (x_min + x_max)
        z_mid = ds.zMid.squeeze("Time")

        # Only the top layer moves in this test case
        ds["vertCoordMovementWeights"] = xr.ones_like(ds.refZMid)

        if vert_coord == 'z-level':
            ds["vertCoordMovementWeights"][:] = 0.0
            ds["vertCoordMovementWeights"][1] = 1.0

        # ...
        x_cell_2D, _ = xr.broadcast(x_cell_adjusted, ds.refBottomDepth)
        x_edge_2D, _ = xr.broadcast(x_edge_adjusted, ds.refBottomDepth)
        angle_edge_2D, _ = xr.broadcast(ds.angleEdge, ds.refBottomDepth)

        # Initialize temperature
        temperature = temperature_right * xr.ones_like(x_cell_2D)
        temperature = xr.where(
            x_cell_2D < x_mid, temperature_left, temperature_right
        )
        temperature = temperature.expand_dims(dim='Time', axis=0)
        ds['temperature'] = temperature

        # Initialize temperature
        ds['salinity'] = salinity_background * xr.ones_like(temperature)

        # Initialize normalVelocity
        z_mid_edge = z_mid.isel(nCells=ds.cellsOnEdge - 1).mean("TWO")

        x_one_quarters = 0.75 * x_min + 0.25 * x_max
        x_three_quarters = 0.25 * x_min + 0.75 * x_max
        x_cell_on_edge = ds.xCell.isel(nCells=ds.cellsOnEdge - 1)

        condition_1 = (x_cell_on_edge > x_three_quarters).all("TWO")
        condition_2 = (
            (x_cell_on_edge < x_mid) & (x_cell_on_edge >= x_one_quarters)
        ).all("TWO")

        mask_2D, _ = xr.broadcast(condition_1 | condition_2, ds.refBottomDepth)

        d_psi = - (2.0 * z_mid_edge + bottom_depth) / (0.5 * bottom_depth)**2

        den = (0.5 * (x_max - x_min))**4
        num = xr.where(mask_2D,
                       (x_edge_2D - x_min - 0.5 * (x_max + x_min))**4,
                       (x_edge_2D - 0.5 * x_max)**4)

        normal_velocity = (1 - (num / den)) * (d_psi * np.cos(angle_edge_2D))
        normal_velocity = xr.where(
            (x_edge_2D <= x_min) | (x_edge_2D >= x_max), 0, normal_velocity
        )
        ds['normalVelocity'] = normal_velocity.expand_dims(dim='Time', axis=0)

        # Initialize debug tracers
        half_depth = 0.5 * bottom_depth
        psi1 = 1.0 - ((x_cell_2D - 0.5 + x_max)**4 / (0.5 * x_max)**4)
        psi2 = 1.0 - ((z_mid + half_depth)**2 / (0.5 * half_depth)**2)
        psi = psi1 * psi2

        ds["tracer1"] = xr.zeros_like(temperature)
        ds["tracer1"].isel(Time=0)[:] = 0.5 * (1 + np.tanh(2 * psi - 1))
        ds["tracer2"] = tracer2_background * xr.zeros_like(temperature)
        ds["tracer3"] = tracer3_background * xr.zeros_like(temperature)

        write_netcdf(ds, 'initial_state.nc')
