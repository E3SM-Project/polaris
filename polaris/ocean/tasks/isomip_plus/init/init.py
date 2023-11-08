import os
import shutil

import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.ocean.ice_shelf import (
    compute_freezing_temperature,
    compute_land_ice_draft_from_pressure,
    compute_land_ice_pressure_from_draft,
)
from polaris.ocean.vertical import init_vertical_coord
from polaris.ocean.viz import compute_transect, plot_transect
from polaris.step import Step
from polaris.viz import plot_horiz_field


class Init(Step):
    """
    A step for creating an initial condition for ISOMIP+ experiments

    Attributes
    ----------
    experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
        The ISOMIP+ experiment

    vertical_coordinate : str
        The type of vertical coordinate (``z-star``, ``z-level``, etc.)

    thin_film: bool
        Whether the run includes a thin film below grounded ice
    """
    def __init__(self, component, indir, culled_mesh, topo, experiment,
                 vertical_coordinate, thin_film):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component this step belongs to

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        culled_mesh : polaris.Step
            The step that culled the MPAS mesh

        topo : polaris.Step
            The step with topography data on the culled mesh

        experiment : {'ocean0', 'ocean1', 'ocean2', 'ocean3', 'ocean4'}
            The ISOMIP+ experiment

        vertical_coordinate : str
            The type of vertical coordinate (``z-star``, ``z-level``, etc.)

        thin_film: bool
            Whether the run includes a thin film below grounded ice
        """
        super().__init__(component=component, name='init', indir=indir)
        self.experiment = experiment
        self.vertical_coordinate = vertical_coordinate
        self.thin_film = thin_film

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=os.path.join(culled_mesh.path, 'culled_mesh.nc'))

        self.add_input_file(
            filename='topo.nc',
            work_dir_target=os.path.join(topo.path, 'topography_remapped.nc'))

        self.add_output_file('init.nc')

    def run(self):
        """
        Create and plot the initial condition
        """
        config = self.config
        self._compute_init_topo()

        with xr.open_dataset('init_topo.nc') as ds_init:
            init_vertical_coord(config, ds_init)
            write_netcdf(ds_init, 'init_vert_coord.nc')

        self._compute_t_s_vel_coriolis()
        self._plot()

    def _compute_init_topo(self):
        """ Compute fractions, masks, draft, land-ice pressure, bot. depth """
        config = self.config
        logger = self.logger
        thin_film = self.thin_film

        section = config['isomip_plus_init']
        min_levels = section.getint('minimum_levels')
        min_layer_thickness = section.getfloat('min_layer_thickness')
        min_column_thickness = section.getfloat('min_column_thickness')
        min_land_ice_fraction = section.getfloat('min_land_ice_fraction')

        ds_topo = xr.open_dataset('topo.nc')
        if 'Time' in ds_topo.dims:
            ds_topo = ds_topo.isel(Time=0)
        ds_mesh = xr.open_dataset('mesh.nc')

        ds_init = xr.Dataset(ds_mesh)
        ds_init.attrs = ds_mesh.attrs

        ds_init['landIceFraction'] = ds_topo['landIceFraction']
        ds_init['landIceFloatingFraction'] = ds_topo['landIceFloatingFraction']

        # This inequality needs to be > rather than >= to ensure correctness
        # when min_land_ice_fraction = 0
        land_ice_mask = ds_init.landIceFraction > min_land_ice_fraction

        floating_mask = np.logical_and(
            land_ice_mask,
            ds_init.landIceFloatingFraction > 0)

        ds_init['landIceMask'] = land_ice_mask.astype(int)
        ds_init['landIceFloatingMask'] = floating_mask.astype(int)

        ds_init['landIceFraction'] = \
            xr.where(land_ice_mask, ds_init.landIceFraction, 0.)
        ds_init['landIceFloatingFraction'] = \
            xr.where(land_ice_mask, ds_init.landIceFloatingFraction, 0.)

        ds_init['landIceGroundedFraction'] = ds_topo['landIceGroundedFraction']

        if thin_film:
            # start from landIcePressure and compute landIceDraft
            ds_init['landIcePressure'] = ds_topo['landIcePressure']

            land_ice_draft = compute_land_ice_draft_from_pressure(
                land_ice_pressure=ds_topo.landIcePressure,
                modify_mask=ds_topo.landIcePressure > 0.)

            land_ice_draft = np.maximum(ds_topo.bedrockTopography,
                                        land_ice_draft)

            ds_init['landIceDraft'] = land_ice_draft

        else:
            # start form landIceDraft and compute landIcePressure
            ds_init['landIceDraft'] = ds_topo['landIceDraft']

            land_ice_pressure = compute_land_ice_pressure_from_draft(
                land_ice_draft=ds_topo.landIceDraft,
                modify_mask=ds_topo.landIceDraft < 0.)

            ds_init['landIcePressure'] = land_ice_pressure

        ds_init['ssh'] = ds_init.landIceDraft

        ds_init['bottomDepth'] = -ds_topo.bedrockTopography

        thin_film_mask = np.logical_and(land_ice_mask,
                                        np.logical_not(floating_mask))

        if thin_film:
            active_ocean = xr.ones_like(ds_init.bottomDepth)
        else:
            active_ocean = np.logical_not(thin_film_mask)

            logger.info(
                f'Not using a thin film so {np.sum(thin_film_mask).values} '
                f'cells are being deactivated.')

            # need to move bottomDepth and ssh up to the sea surface where we
            # are grounded so we will get maxLevelCell == 0
            ds_init['bottomDepth'] = \
                xr.where(thin_film_mask, 0., ds_init.bottomDepth)
            ds_init['ssh'] = \
                xr.where(thin_film_mask, 0., ds_init.ssh)

        # Deepen the bottom depth to maintain the minimum water-column
        # thickness
        min_column_thickness = max(min_column_thickness,
                                   min_levels * min_layer_thickness)
        min_depth = -ds_init.ssh + min_column_thickness
        too_thin = np.logical_and(
            active_ocean,
            ds_init.bottomDepth < min_depth)
        ds_init['bottomDepth'] = \
            xr.where(too_thin, min_depth, ds_init.bottomDepth)
        too_thin_count = np.sum(too_thin).values
        if too_thin_count > 0:
            logger.info(
                f'Adjusted bottomDepth for {too_thin_count} cells to achieve '
                f'minimum column thickness of {min_column_thickness}')

        ds_init['activeOcean'] = active_ocean.astype(int)
        ds_init['thinFilmMask'] = thin_film_mask.astype(int)

        write_netcdf(ds_init, 'init_topo.nc')

    def _compute_t_s_vel_coriolis(self):
        config = self.config
        experiment = self.experiment
        thin_film = self.thin_film

        section = config['isomip_plus_init']

        if experiment in ['ocean0', 'ocean3']:
            top_temp = config.getfloat('isomip_plus', 'warm_top_temp')
            bot_temp = config.getfloat('isomip_plus', 'warm_bot_temp')
            top_sal = config.getfloat('isomip_plus', 'warm_top_sal')
            bot_sal = config.getfloat('isomip_plus', 'warm_bot_sal')
        else:
            top_temp = config.getfloat('isomip_plus', 'cold_top_temp')
            bot_temp = config.getfloat('isomip_plus', 'cold_bot_temp')
            top_sal = config.getfloat('isomip_plus', 'cold_top_sal')
            bot_sal = config.getfloat('isomip_plus', 'cold_bot_sal')

        if self.vertical_coordinate == 'single_layer':
            config.set('vertical_grid', 'vert_levels', '1',
                       comment='Number of vertical levels')
            config.set('vertical_grid', 'coord_type', 'z-level')

        ds_mesh = xr.open_dataset('mesh.nc')
        ds_init = xr.open_dataset('init_vert_coord.nc')

        active_ocean = ds_init.activeOcean == 1
        thin_film_mask = ds_init.thinFilmMask == 1

        if not thin_film:
            # need to set maxLevelCell == 0 where ocean isn't active
            ds_init['maxLevelCell'] = \
                ds_init.maxLevelCell.where(active_ocean, 0)

        max_bottom_depth = -config.getfloat('vertical_grid', 'bottom_depth')
        frac = (0. - ds_init.zMid) / (0. - max_bottom_depth)

        # compute T, S
        if self.vertical_coordinate == 'single-layer':
            ds_init['temperature'] = bot_temp * xr.ones_like(frac)
            ds_init['salinity'] = bot_sal * xr.ones_like(frac)
        else:
            ds_init['temperature'] = (1.0 - frac) * top_temp + frac * bot_temp
            ds_init['salinity'] = (1.0 - frac) * top_sal + frac * bot_sal

        # Note that using the land ice pressure rather than the pressure at
        # floatation will mean that there is a small amount of cooling from
        # grounding line retreat. However, the thin film should be thin enough
        # that this effect isn't significant.

        freezing_temp = compute_freezing_temperature(
            config=config,
            salinity=ds_init.salinity,
            pressure=ds_init.landIcePressure)
        ds_init['temperature'] = ds_init.temperature.where(
            np.logical_not(thin_film_mask), freezing_temp)

        # compute coriolis
        coriolis_parameter = section.getfloat('coriolis_parameter')

        ds_init['fCell'] = coriolis_parameter * xr.ones_like(ds_mesh.xCell)
        ds_init['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds_init['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        normalVelocity = xr.zeros_like(ds_mesh.xEdge)
        normalVelocity = normalVelocity.broadcast_like(ds_init.refBottomDepth)
        normalVelocity = normalVelocity.transpose('nEdges', 'nVertLevels')
        ds_init['normalVelocity'] = \
            normalVelocity.expand_dims(dim='Time', axis=0)

        write_netcdf(ds_init, 'init.nc')

    def _plot(self):
        """
        Plot several fields from the initial condition
        """
        section = self.config['isomip_plus_init']
        min_column_thickness = section.getfloat('min_column_thickness')
        min_layer_thickness = section.getfloat('min_layer_thickness')

        tol = 1e-10

        plot_folder = 'plots'
        try:
            shutil.rmtree(plot_folder)
        except FileNotFoundError:
            pass

        ds = xr.open_dataset('init.nc').isel(Time=0)
        ds_mesh = xr.open_dataset('mesh.nc')

        for ds_fix in [ds, ds_mesh]:
            # use the planar projection coordinates for horizontal plots
            ds_fix['xCell'] = ds_fix['xIsomipCell']
            ds_fix['yCell'] = ds_fix['yIsomipCell']
            ds_fix['zCell'] = xr.zeros_like(ds_fix.xCell)
            ds_fix['xVertex'] = ds_fix['xIsomipVertex']
            ds_fix['yVertex'] = ds_fix['yIsomipVertex']
            ds_fix['zVertex'] = xr.zeros_like(ds_fix.xVertex)

        x = np.linspace(320e3, 800e3, 2)
        y = 40.0e3 * np.ones_like(x)

        x = xr.DataArray(data=x, dims=('nPoints',))
        y = xr.DataArray(data=y, dims=('nPoints',))

        ds_transect = compute_transect(x=x, y=y, ds_3d_mesh=ds,
                                       spherical=False)

        ds['totalColThickness'] = ds['layerThickness'].sum(dim='nVertLevels')

        ds['H'] = ds.ssh + ds.bottomDepth

        figsize = (8, 4.5)

        cell_mask = ds.maxLevelCell >= 1
        patches, patch_mask = plot_horiz_field(
            ds=ds, ds_mesh=ds_mesh, field_name='maxLevelCell',
            out_file_name='plots/maxLevelCell.png', figsize=figsize,
            cell_mask=cell_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIceMask',
                         out_file_name='plots/landIceMask.png',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIceFloatingMask',
                         out_file_name='plots/landIceFloatingMask.png',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIcePressure',
                         out_file_name='plots/landIcePressure.png',
                         vmin=1e4, vmax=1e7, cmap_scale='log',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='ssh',
                         out_file_name='plots/ssh.png',
                         vmin=-720, vmax=0,
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='bottomDepth',
                         out_file_name='plots/bottomDepth.png',
                         vmin=0, vmax=720,
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='totalColThickness',
                         out_file_name='plots/totalColThickness.png',
                         vmin=min_column_thickness + tol, vmax=720,
                         cmap_set_under='r',
                         cmap_scale='log',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='H',
                         out_file_name='plots/H.png',
                         vmin=min_column_thickness + tol, vmax=720,
                         cmap_set_under='r',
                         cmap_scale='log',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIceFraction',
                         out_file_name='plots/landIceFraction.png',
                         vmin=0 + tol, vmax=1 - tol,
                         cmap='cmo.balance',
                         cmap_set_under='k', cmap_set_over='r',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIceFloatingFraction',
                         out_file_name='plots/landIceFloatingFraction.png',
                         vmin=0 + tol, vmax=1 - tol,
                         cmap='cmo.balance',
                         cmap_set_under='k', cmap_set_over='r',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name='landIceGroundedFraction',
                         out_file_name='plots/landIceGroundedFraction.png',
                         vmin=0 + tol, vmax=1 - tol,
                         cmap='cmo.balance',
                         cmap_set_under='k', cmap_set_over='r',
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask)

        plot_transect(ds_transect=ds_transect,
                      title='layer interfaces at y=40 km',
                      out_filename='plots/layerInterfacesSection.png',
                      figsize=figsize, interface_color='black',
                      ssh_color='blue', seafloor_color='red')

        _plot_top_bot_slice(ds=ds, ds_mesh=ds_mesh, ds_transect=ds_transect,
                            patches=patches, patch_mask=patch_mask,
                            field_name='layerThickness',
                            figsize=figsize,
                            vmin=min_layer_thickness + tol, vmax=50,
                            cmap='cmo.deep_r', units='m', transect_x=x,
                            transect_y=y, under='r', over='r')

        _plot_top_bot_slice(ds=ds, ds_mesh=ds_mesh, ds_transect=ds_transect,
                            patches=patches, patch_mask=patch_mask,
                            field_name='zMid',
                            figsize=figsize,
                            vmin=-720., vmax=0.,
                            cmap='cmo.deep_r', units='m', transect_x=x,
                            transect_y=y, under='r', over='r')

        _plot_top_bot_slice(ds=ds, ds_mesh=ds_mesh, ds_transect=ds_transect,
                            patches=patches, patch_mask=patch_mask,
                            field_name='temperature',
                            figsize=figsize,
                            vmin=-2., vmax=1.,
                            cmap='cmo.thermal', units=r'$^\circ$C',
                            transect_x=x, transect_y=y)

        _plot_top_bot_slice(ds=ds, ds_mesh=ds_mesh, ds_transect=ds_transect,
                            patches=patches, patch_mask=patch_mask,
                            field_name='salinity',
                            figsize=figsize,
                            vmin=33.8, vmax=34.7,
                            cmap='cmo.haline', units='PSU', transect_x=x,
                            transect_y=y)


def _plot_top_bot_slice(ds, ds_mesh, ds_transect, patches, patch_mask,
                        field_name, figsize, vmin, vmax, cmap, units,
                        transect_x, transect_y, under=None, over=None):
    for suffix, z_index in [['Top', 0], ['Bot', ds.maxLevelCell - 1]]:
        plot_horiz_field(ds=ds, ds_mesh=ds_mesh,
                         field_name=field_name,
                         title=f'{field_name} {suffix}',
                         z_index=z_index,
                         out_file_name=f'plots/{field_name}{suffix}.png',
                         vmin=vmin, vmax=vmax, cmap=cmap,
                         cmap_set_under=under, cmap_set_over=over,
                         figsize=figsize, patches=patches,
                         patch_mask=patch_mask, transect_x=transect_x,
                         transect_y=transect_y)

    plot_transect(ds_transect=ds_transect, mpas_field=ds[field_name],
                  title=f'{field_name} at y=40 km',
                  out_filename=f'plots/{field_name}Section.png',
                  vmin=vmin, vmax=vmax, cmap=cmap, figsize=figsize,
                  colorbar_label=units)
