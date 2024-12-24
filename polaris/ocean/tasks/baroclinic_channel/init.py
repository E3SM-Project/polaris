import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.mpas import cell_mask_2_edge_mask
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.viz import compute_transect, plot_transect
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
    def __init__(self, component, resolution, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The resolution of the task in km

        indir : str
            the directory the step is in, to which ``name`` will be appended
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

        cell_mask = ds.maxLevelCell >= 1
        edge_mask = cell_mask_2_edge_mask(ds, cell_mask)

        plot_horiz_field(ds_mesh, ds['normalVelocity'],
                         'initial_normal_velocity.png', cmap='cmo.balance',
                         show_patch_edges=True, field_mask=edge_mask)

        y_min = ds_mesh.yVertex.min().values
        y_max = ds_mesh.yVertex.max().values
        x_mid = ds_mesh.xCell.median().values

        y = xr.DataArray(data=np.linspace(y_min, y_max, 2), dims=('nPoints',))
        x = x_mid * xr.ones_like(y)

        ds_transect = compute_transect(
            x=x, y=y, ds_horiz_mesh=ds_mesh,
            layer_thickness=ds.layerThickness.isel(Time=0),
            bottom_depth=ds.bottomDepth, min_level_cell=ds.minLevelCell - 1,
            max_level_cell=ds.maxLevelCell - 1, spherical=False)

        field_name = 'temperature'
        vmin = ds[field_name].min().values
        vmax = ds[field_name].max().values
        plot_transect(ds_transect=ds_transect,
                      mpas_field=ds[field_name].isel(Time=0),
                      title=f'{field_name} at x={1e-3 * x_mid:.1f} km',
                      out_filename=f'initial_{field_name}_section.png',
                      vmin=vmin, vmax=vmax, cmap='cmo.thermal',
                      colorbar_label=r'$^\circ$C', color_start_and_end=True)

        plot_horiz_field(ds_mesh, ds['temperature'], 'initial_temperature.png',
                         vmin=vmin, vmax=vmax, cmap='cmo.thermal',
                         field_mask=cell_mask, transect_x=x, transect_y=y)
