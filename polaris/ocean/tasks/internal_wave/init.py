import cmocean  # noqa: F401
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
    A step for creating a mesh and initial condition for internal wave test
    cases
    """
    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='init', indir=indir)

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info']:
            self.add_output_file(file)
        self.add_output_file('initial_state.nc',
                             validate_vars=['temperature', 'salinity',
                                            'layerThickness'])

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger

        section = config['internal_wave']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        use_distances = section.getboolean('use_distances')
        amplitude_width_dist = section.getfloat('amplitude_width_dist')
        amplitude_width_frac = section.getfloat('amplitude_width_frac')
        bottom_temperature = section.getfloat('bottom_temperature')
        surface_temperature = section.getfloat('surface_temperature')
        temperature_difference = section.getfloat('temperature_difference')
        salinity = section.getfloat('salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

        section = config['vertical_grid']
        vert_levels = section.getint('vert_levels')
        bottom_depth = section.getfloat('bottom_depth')

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

        ds = ds_mesh.copy()


        y_cell = ds.yCell
        ds['maxLevelCell'] = vert_levels * xr.ones_like(y_cell)
        ds['bottomDepth'] = bottom_depth * xr.ones_like(y_cell)
        ds['ssh'] = xr.zeros_like(y_cell)

        init_vertical_coord(config, ds)

        y_min = y_cell.min().values
        y_max = y_cell.max().values

        y_mid = 0.5 * (y_min + y_max)

        if use_distances:
            perturb_width = amplitude_width_dist
        else:
            perturb_width = (y_max - y_min) * amplitude_width_frac

        # Set stratified temperature
        temp_vert = (bottom_temperature +
                     (surface_temperature - bottom_temperature) *
                     ((ds.refZMid + bottom_depth) / bottom_depth))

        depth_frac = xr.zeros_like(temp_vert)
        ref_bottom_depth = ds['refBottomDepth']
        for k in range(1, vert_levels):
            depth_frac[k] = (ref_bottom_depth[k - 1] /
                             ref_bottom_depth[vert_levels - 1])

        # If cell is in the southern half, outside the sin width, subtract
        # temperature difference
        frac = xr.where(
            np.abs(y_cell - y_mid) < perturb_width,
            np.cos(0.5 * np.pi * (y_cell - y_mid) / perturb_width) *
            np.sin(np.pi * depth_frac),
            0.)

        temperature = temp_vert - temperature_difference * frac
        temperature = temperature.transpose('nCells', 'nVertLevels')
        temperature = temperature.expand_dims(dim='Time', axis=0)

        normal_velocity = xr.zeros_like(ds.xEdge)
        normal_velocity, _ = xr.broadcast(normal_velocity, ref_bottom_depth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)

        ds['temperature'] = temperature
        ds['salinity'] = salinity * xr.ones_like(temperature)
        ds['normalVelocity'] = normal_velocity
        ds['fCell'] = coriolis_parameter * xr.ones_like(y_cell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        write_netcdf(ds, 'initial_state.nc')
