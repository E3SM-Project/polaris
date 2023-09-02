import cmocean  # noqa: F401
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
    def __init__(self, task, resolution):
        """
        Create the step

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to

        resolution : float
            The resolution of the task in km
        """
        super().__init__(task=task, name='init')
        self.resolution = resolution

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info',
                     'initial_state.nc']:
            self.add_output_file(file)

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger

        section = config['baroclinic_channel']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
                                       nonperiodic_x=False,
                                       nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        section = config['baroclinic_channel']
        use_distances = section.getboolean('use_distances')
        gradient_width_dist = section.getfloat('gradient_width_dist')
        gradient_width_frac = section.getfloat('gradient_width_frac')
        bottom_temperature = section.getfloat('bottom_temperature')
        surface_temperature = section.getfloat('surface_temperature')
        temperature_difference = section.getfloat('temperature_difference')
        salinity = section.getfloat('salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

        ds = ds_mesh.copy()
        x_cell = ds.xCell
        y_cell = ds.yCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)

        init_vertical_coord(config, ds)

        x_min = x_cell.min().values
        x_max = x_cell.max().values
        y_min = y_cell.min().values
        y_max = y_cell.max().values

        y_mid = 0.5 * (y_min + y_max)
        x_perturb_min = x_min + 4.0 * (x_max - x_min) / 6.0
        x_perturb_max = x_min + 5.0 * (x_max - x_min) / 6.0

        if use_distances:
            perturb_width = gradient_width_dist
        else:
            perturb_width = (y_max - y_min) * gradient_width_frac

        y_offset = perturb_width * np.sin(
            6.0 * np.pi * (x_cell - x_min) / (x_max - x_min))

        temp_vert = (bottom_temperature +
                     (surface_temperature - bottom_temperature) *
                     ((ds.refZMid + bottom_depth) / bottom_depth))

        frac = xr.where(y_cell < y_mid - y_offset, 1., 0.)

        mask = np.logical_and(y_cell >= y_mid - y_offset,
                              y_cell < y_mid - y_offset + perturb_width)
        frac = xr.where(mask,
                        1. - (y_cell - (y_mid - y_offset)) / perturb_width,
                        frac)

        temperature = temp_vert - temperature_difference * frac
        temperature = temperature.transpose('nCells', 'nVertLevels')

        # Determine y_offset for 3rd crest in sin wave
        y_offset = 0.5 * perturb_width * np.sin(
            np.pi * (x_cell - x_perturb_min) / (x_perturb_max - x_perturb_min))

        mask = np.logical_and(
            np.logical_and(y_cell >= y_mid - y_offset - 0.5 * perturb_width,
                           y_cell <= y_mid - y_offset + 0.5 * perturb_width),
            np.logical_and(x_cell >= x_perturb_min,
                           x_cell <= x_perturb_max))

        temperature = (temperature +
                       mask * 0.3 * (1. - ((y_cell - (y_mid - y_offset)) /
                                           (0.5 * perturb_width))))

        temperature = temperature.expand_dims(dim='Time', axis=0)

        normal_velocity = xr.zeros_like(ds_mesh.xEdge)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)

        ds['temperature'] = temperature
        ds['salinity'] = salinity * xr.ones_like(temperature)
        ds['normalVelocity'] = normal_velocity
        ds['fCell'] = coriolis_parameter * xr.ones_like(x_cell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        write_netcdf(ds, 'initial_state.nc')

        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'initial_temperature.png')
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'initial_normal_velocity.png', cmap='cmo.balance',
                         show_patch_edges=True)
