import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.constants import get_constant
from polaris.ocean.model import OceanIOStep
from polaris.viz import mplstyle_context, plot_horiz_field


class Viz(OceanIOStep):
    """
    A step for plotting the initial condition and the end of the forward run
    of an ISOMIP+ task

    Attributes
    ----------
    thin_film : bool
        Whether a thin film is present under grounded ice, in which case the
        water column is also plotted over the forward run
    """

    def __init__(self, component, indir, init, forward, thin_film):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        init : polaris.Step
            The step that produced the mesh and initial condition

        forward : polaris.Step
            The forward step

        thin_film : bool
            Whether a thin film is present under grounded ice, in which case
            the water column is also plotted over the forward run
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.thin_film = thin_film
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )
        self.add_input_file(
            filename='land_ice_fluxes.nc',
            work_dir_target=f'{forward.path}/land_ice_fluxes.nc',
        )

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        section = config['isomip_plus_viz']
        section_y = section.getfloat('section_y')
        min_column_thickness = config.getfloat(
            'isomip_plus', 'min_column_thickness'
        )
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds_mesh = self.open_model_dataset('mesh.nc', config)
        ds_mesh = _use_isomip_coords(ds_mesh)
        ds_init = self.open_model_dataset('init.nc', config).isel(Time=0)
        ds_vert_coord = self.open_vert_coord_dataset(ds_init)
        ds_out = self.open_model_dataset('output.nc', config).isel(Time=-1)
        ds_ice = self.open_model_dataset('land_ice_fluxes.nc', config).isel(
            Time=-1
        )

        x = xr.DataArray(
            data=[ds_mesh.xCell.min().values, ds_mesh.xCell.max().values],
            dims=('nPoints',),
        )
        y = xr.DataArray(data=[section_y, section_y], dims=('nPoints',))

        min_level_cell = ds_vert_coord.minLevelCell - 1
        max_level_cell = ds_vert_coord.maxLevelCell - 1

        figsize = (10, 3)
        plots = _PlotHelper(
            ds_mesh=ds_mesh,
            max_level_cell=max_level_cell,
            figsize=figsize,
            transect_x=x,
            transect_y=y,
        )

        # the initial geometry
        column_thickness = ds_init.ssh + ds_vert_coord.bottomDepth
        tol = 1e-10
        plots.horiz(ds_vert_coord.maxLevelCell, 'maxLevelCell')
        plots.horiz(
            ds_vert_coord.bottomDepth,
            'bottomDepth',
            vmin=0.0,
            vmax=bottom_depth,
            cmap='cmo.deep',
        )
        plots.horiz(
            ds_init.ssh, 'ssh', vmin=-bottom_depth, vmax=0.0, cmap='cmo.deep_r'
        )
        plots.horiz(
            column_thickness,
            'columnThickness',
            vmin=min_column_thickness + tol,
            vmax=bottom_depth,
            cmap='cmo.deep',
            cmap_scale='log',
            cmap_set_under='r',
        )
        plots.horiz(
            ds_init.landIcePressure,
            'landIcePressure',
            vmin=1e4,
            vmax=1e7,
            cmap_scale='log',
        )
        plots.horiz(ds_init.landIceMask, 'landIceMask')
        for name in [
            'landIceFraction',
            'landIceFloatingFraction',
            'landIceGroundedFraction',
        ]:
            plots.horiz(
                ds_init[name],
                name,
                vmin=0.0 + tol,
                vmax=1.0 - tol,
                cmap='cmo.balance',
                cmap_set_under='k',
                cmap_set_over='r',
            )

        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_init.layerThickness,
            bottom_depth=ds_vert_coord.bottomDepth,
            min_level_cell=min_level_cell,
            max_level_cell=max_level_cell,
            spherical=False,
        )
        plot_transect(
            ds_transect=ds_transect,
            title=f'layer interfaces at y={1e-3 * section_y:g} km',
            out_filename='layer_interfaces_section.png',
            figsize=figsize,
            interface_color='black',
            ssh_color='blue',
            seafloor_color='red',
        )

        # temperature and salinity at the start and end of the forward run
        ds_final_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_out.layerThickness,
            bottom_depth=ds_vert_coord.bottomDepth,
            min_level_cell=min_level_cell,
            max_level_cell=max_level_cell,
            spherical=False,
        )
        for suffix, ds, transect in [
            ('init', ds_init, ds_transect),
            ('final', ds_out, ds_final_transect),
        ]:
            plots.top_bot_section(
                ds.temperature,
                f'temperature_{suffix}',
                transect,
                vmin=-2.0,
                vmax=1.0,
                cmap='cmo.thermal',
                units=r'$^\circ$C',
            )
            plots.top_bot_section(
                ds.salinity,
                f'salinity_{suffix}',
                transect,
                vmin=33.8,
                vmax=34.7,
                cmap='cmo.haline',
                units='PSU',
            )

        # melt diagnostics at the end of the forward run
        fresh_water_density = get_constant('pure_water_density_reference')
        s_per_year = 365.0 * get_constant('day_to_s')
        melt_rate = (
            ds_ice.landIceFreshwaterFlux / fresh_water_density * s_per_year
        )
        thermal_driving = (
            ds_ice.landIceBoundaryLayerTemperature
            - ds_ice.landIceInterfaceTemperature
        )
        mask = ds_init.landIceFloatingMask == 1
        plots.horiz(
            melt_rate,
            'meltRate',
            field_mask=mask,
            cmap='cmo.amp',
            cmap_title='m/yr',
        )
        plots.horiz(
            thermal_driving,
            'thermalDriving',
            field_mask=mask,
            cmap='cmo.thermal',
            cmap_title=r'$^\circ$C',
        )
        plots.horiz(
            ds_ice.landIceFrictionVelocity,
            'frictionVelocity',
            field_mask=mask,
            cmap='cmo.speed',
            cmap_title='m/s',
        )

        if self.thin_film:
            self._plot_thin_film(plots, ds_mesh, ds_init, ds_vert_coord)

    def _plot_thin_film(self, plots, ds_mesh, ds_init, ds_vert_coord):
        """
        Plot where the water column is near its minimum thickness at each
        output time, the area of those cells under the ice, and the mean SSH
        in the open ocean
        """
        config = self.config
        layer_thickness = config.getfloat(
            'isomip_plus', 'thin_film_layer_thickness'
        )
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        ds_out = self.open_model_dataset('output.nc', config)

        # a column is "dry" if it is less than twice the thin film, which has
        # the minimum thickness in each active layer
        level_count = (
            ds_vert_coord.maxLevelCell - ds_vert_coord.minLevelCell + 1
        )
        dry_thickness = 2.0 * layer_thickness * level_count
        under_ice = ds_init.landIceMask == 1
        area = ds_mesh.areaCell
        open_area = float(area.where(~under_ice).sum())

        hours = 24.0 * ds_out.daysSinceStartOfSim.values
        dry_area = []
        open_ocean_ssh = []
        for t_index, hour in enumerate(hours):
            ssh = ds_out.ssh.isel(Time=t_index)
            column_thickness = ssh + ds_vert_coord.bottomDepth
            dry = column_thickness < dry_thickness
            dry_area.append(1e-6 * float(area.where(dry & under_ice).sum()))
            open_ocean_ssh.append(
                float((ssh * area).where(~under_ice).sum()) / open_area
            )
            # dry columns are below the color range, so they are red (zero
            # would be masked on the log scale)
            vmin = 1e-2
            plots.horiz(
                xr.where(dry, 0.5 * vmin, column_thickness),
                f'columnThickness_{hour:03.0f}h',
                vmin=vmin,
                vmax=bottom_depth,
                cmap='cmo.deep',
                cmap_scale='log',
                cmap_set_under='r',
            )

        with mplstyle_context():
            _plot_time_series(
                hours,
                dry_area,
                r'dry area under ice (km$^2$)',
                'dryAreaUnderIce.png',
            )
            _plot_time_series(
                hours,
                open_ocean_ssh,
                'mean open-ocean SSH (m)',
                'openOceanSsh.png',
            )


class _PlotHelper:
    """
    Settings shared by the horizontal and transect plots
    """

    def __init__(
        self, ds_mesh, max_level_cell, figsize, transect_x, transect_y
    ):
        self.ds_mesh = ds_mesh
        self.max_level_cell = max_level_cell
        self.figsize = figsize
        self.transect_x = transect_x
        self.transect_y = transect_y
        self.descriptor = None

    def horiz(self, field, name, **kwargs):
        """
        Plot a horizontal field
        """
        self.descriptor = plot_horiz_field(
            ds_mesh=self.ds_mesh,
            field=field,
            out_file_name=f'{name}.png',
            title=name,
            figsize=self.figsize,
            descriptor=self.descriptor,
            **kwargs,
        )

    def top_bot_section(
        self, field, name, ds_transect, vmin, vmax, cmap, units
    ):
        """
        Plot a 3D field at the top and bottom of the ocean and in a transect
        """
        for suffix, z_index in [
            ('top', 0),
            ('bot', self.max_level_cell),
        ]:
            self.descriptor = plot_horiz_field(
                ds_mesh=self.ds_mesh,
                field=field,
                out_file_name=f'{name}_{suffix}.png',
                title=f'{name} {suffix}',
                z_index=z_index,
                vmin=vmin,
                vmax=vmax,
                cmap=cmap,
                cmap_title=units,
                figsize=self.figsize,
                descriptor=self.descriptor,
                transect_x=self.transect_x,
                transect_y=self.transect_y,
            )

        plot_transect(
            ds_transect=ds_transect,
            mpas_field=field,
            title=name,
            out_filename=f'{name}_section.png',
            vmin=vmin,
            vmax=vmax,
            cmap=cmap,
            figsize=self.figsize,
            colorbar_label=units,
        )


def _plot_time_series(hours, values, ylabel, filename):
    """
    Plot a quantity against time in hours
    """
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(hours, values, 'k.-')
    ax.set_xlabel('time (hours)')
    ax.set_ylabel(ylabel)
    fig.savefig(filename, bbox_inches='tight')
    plt.close(fig)


def _use_isomip_coords(ds_mesh):
    """
    Use the ISOMIP+ x and y coordinates as the mesh coordinates so planar and
    spherical meshes are plotted the same way
    """
    ds_mesh = ds_mesh.copy()
    ds_mesh['xCell'] = ds_mesh.xIsomipCell
    ds_mesh['yCell'] = ds_mesh.yIsomipCell
    ds_mesh['zCell'] = xr.zeros_like(ds_mesh.xCell)
    ds_mesh['xVertex'] = ds_mesh.xIsomipVertex
    ds_mesh['yVertex'] = ds_mesh.yIsomipVertex
    ds_mesh['zVertex'] = xr.zeros_like(ds_mesh.xVertex)
    ds_mesh.attrs['on_a_sphere'] = 'NO'
    ds_mesh.attrs['is_periodic'] = 'NO'
    return ds_mesh
