import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
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
    def __init__(self, component, resolution, indir, baroclinic=False):
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

        baroclinic: bool, optional
            whether the test case is baroclinic
        """
        super().__init__(component=component, name='init', indir=indir)
        self.resolution = resolution
        self.baroclinic = baroclinic

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'culled_graph.info',
                     'forcing.nc']:
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
        resolution = self.resolution

        section = config['vertical_grid']
        vert_levels = section.getint('vert_levels')
        section = config['drying_slope']
        thin_film_thickness = section.getfloat('thin_film_thickness') + 1.0e-9
        nx = section.getint('nx')
        domain_length = section.getfloat('ly') * 1e3
        drying_length = section.getfloat('ly_analysis') * 1e3
        plug_width_frac = section.getfloat('plug_width_frac')
        right_bottom_depth = section.getfloat('right_bottom_depth')
        left_bottom_depth = section.getfloat('left_bottom_depth')
        plug_temperature = section.getfloat('plug_temperature')
        background_temperature = section.getfloat('background_temperature')
        background_salinity = section.getfloat('background_salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')
        right_tidal_height = section.getfloat('right_tidal_height')

        # Check config options
        if domain_length < drying_length:
            raise ValueError('Domain is not long enough to capture wetting '
                             'front')
        if right_bottom_depth < left_bottom_depth:
            raise ValueError('Right boundary must be deeper than left '
                             'boundary')

        dc = 1e3 * resolution
        ny = round(domain_length / dc)
        # This is just for consistency with previous implementations and could
        # be removed
        if resolution < 1.:
            ny += 2
        ny = 2 * round(ny / 2)

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
                                       nonperiodic_x=False,
                                       nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        ds = ds_mesh.copy()
        ds_forcing = ds_mesh.copy()

        y_cell = ds.yCell
        y_min = y_cell.min()
        y_max = y_cell.max()
        dc_edge_min = ds.dcEdge.min()

        bottom_depth = (right_bottom_depth - (y_max - y_cell) / drying_length *
                        (right_bottom_depth - left_bottom_depth))
        ds['bottomDepth'] = bottom_depth
        # Set the water column to dry everywhere
        ds['ssh'] = np.maximum(
            right_tidal_height,
            -bottom_depth + thin_film_thickness * vert_levels)
        # We don't use config_tidal_forcing_monochromatic_baseline because the
        # default value doesn't alter the initial state
        init_vertical_coord(config, ds)

        plug_width = domain_length * plug_width_frac
        y_plug_boundary = y_min + plug_width
        temperature = xr.where(y_cell < y_plug_boundary,
                               plug_temperature, background_temperature)
        temperature, _ = xr.broadcast(temperature, ds.refBottomDepth)
        ds['temperature'] = temperature.expand_dims(dim='Time', axis=0)
        if self.baroclinic:
            section = config['drying_slope_baroclinic']
            right_salinity = section.getfloat('right_salinity')
            left_salinity = section.getfloat('left_salinity')
            salinity = (right_salinity - (y_max - y_cell) / drying_length *
                        (right_salinity - left_salinity))
            # Use a debug tracer for validation
            ds['tracer1'] = xr.ones_like(ds.temperature)
        else:
            salinity = background_salinity * xr.ones_like(y_cell)
        salinity, _ = xr.broadcast(salinity, ds.refBottomDepth)
        ds['salinity'] = salinity.expand_dims(dim='Time', axis=0)

        normalVelocity = xr.zeros_like(ds_mesh.xEdge)
        normalVelocity, _ = xr.broadcast(normalVelocity, ds.refBottomDepth)
        normalVelocity = normalVelocity.transpose('nEdges', 'nVertLevels')
        ds['normalVelocity'] = normalVelocity.expand_dims(dim='Time', axis=0)
        ds['fCell'] = coriolis_parameter * xr.ones_like(ds.xCell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds.xVertex)

        write_netcdf(ds, 'initial_state.nc')

        # Define the tidal boundary condition over 1-cell width
        y_tidal_boundary = y_max - dc_edge_min / 2.
        tidal_forcing_mask = xr.where(y_cell > y_tidal_boundary, 1.0, 0.0)
        if tidal_forcing_mask.sum() <= 0:
            raise ValueError('Input mask for tidal case is not set!')
        ds_forcing['tidalInputMask'] = tidal_forcing_mask
        write_netcdf(ds_forcing, 'forcing.nc')

        cell_mask = ds.maxLevelCell >= 1
        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'initial_temperature.png', cell_mask=cell_mask)

        x_mid = ds_mesh.xCell.median()
        y_min = ds_mesh.yCell.min()
        y_max = ds_mesh.yCell.max()
        x = xr.DataArray(data=[x_mid, x_mid], dims=('nPoints',))
        y = xr.DataArray(data=[y_min, y_max], dims=('nPoints',))
        ds_transect = compute_transect(x, y, ds_mesh.isel(Time=0),
                                       spherical=False)
        plot_transect(ds_transect,
                      mpas_field=ds.temperature.isel(Time=0),
                      out_filename='temperature_depth_init.png',
                      title='temperature',
                      colorbar_label=r'$^{\circ}$C', cmap='cmo.thermal')
