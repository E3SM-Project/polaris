import numpy as np
import xarray as xr
from matplotlib.figure import Figure
from mpas_tools.io import write_netcdf
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.analysis.product_step import ProductStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    INIT_FILENAME,
    SECONDS_PER_YEAR,
    TIME_MEAN_FILENAME,
    TIME_SERIES_FILENAME,
    isomip_mesh,
    read_initial_condition,
)
from polaris.viz import mplstyle_context, plot_horiz_field
from polaris.viz.planar import plot_mask_boundary
from polaris.viz.time_series import Series, plot_time_series

#: The time series plotted for each run: the gallery, the file's stem, the
#: title, the y label, and each variable with its scale and label
TIME_SERIES = [
    (
        'melt',
        'total_melt_flux',
        'Total melt flux',
        'melt flux (Gt yr$^{-1}$)',
        [('totalMeltFlux', SECONDS_PER_YEAR * 1e-12, None)],
    ),
    (
        'melt',
        'mean_melt_rate',
        'Mean melt rate over the ice base',
        'melt rate (m yr$^{-1}$)',
        [
            ('meanMeltRate', SECONDS_PER_YEAR, 'all of the ice base'),
            ('meanMeltRateDeep', SECONDS_PER_YEAR, 'draft below 300 m'),
        ],
    ),
    (
        'melt',
        'mean_thermal_driving',
        'Mean thermal driving',
        r'thermal driving ($^\circ$C)',
        [('meanThermalDriving', 1.0, None)],
    ),
    (
        'melt',
        'mean_friction_velocity',
        'Mean friction velocity',
        'friction velocity (m s$^{-1}$)',
        [('meanFrictionVelocity', 1.0, None)],
    ),
    (
        'circulation',
        'streamfunction_strengths',
        'Range of the streamfunctions under the ice',
        'range (Sv)',
        [
            ('barotropicStrength', 1.0, 'barotropic'),
            ('overturningStrength', 1.0, 'overturning'),
        ],
    ),
    (
        'water_masses',
        'mean_temperature',
        'Mean temperature',
        r'temperature ($^\circ$C)',
        [('meanTemperature', 1.0, None)],
    ),
    (
        'water_masses',
        'mean_salinity',
        'Mean salinity',
        'salinity (PSU)',
        [('meanSalinity', 1.0, None)],
    ),
    (
        'water_masses',
        'ocean_volume',
        'Ocean volume',
        'volume (km$^3$)',
        [('oceanVolume', 1e-9, None)],
    ),
    (
        'thin_film',
        'dry_area',
        'Area of dry columns under grounded ice',
        'area (km$^2$)',
        [('dryAreaUnderGroundedIce', 1e-6, None)],
    ),
    (
        'thin_film',
        'open_ocean_ssh',
        'Mean sea-surface height of the open ocean',
        'SSH (m)',
        [('openOceanMeanSsh', 1.0, None)],
    ),
]

#: The maps of time means plotted for each run: the gallery, the variable,
#: the title, the scale, the color bar's label, the colormap, and whether
#: the field is only valid under floating ice
MAPS = [
    (
        'melt',
        'meltRate',
        'Melt rate',
        SECONDS_PER_YEAR,
        'm yr$^{-1}$',
        'cmo.amp',
        True,
    ),
    (
        'melt',
        'thermalDriving',
        'Thermal driving',
        1.0,
        r'$^\circ$C',
        'cmo.thermal',
        True,
    ),
    (
        'melt',
        'halineDriving',
        'Haline driving',
        1.0,
        'PSU',
        'cmo.haline',
        True,
    ),
    (
        'melt',
        'landIceFrictionVelocity',
        'Friction velocity',
        1.0,
        'm s$^{-1}$',
        'cmo.speed',
        True,
    ),
    (
        'circulation',
        'barotropicStreamfunction',
        'Barotropic streamfunction',
        1.0,
        'Sv',
        'cmo.curl',
        False,
    ),
    (
        'water_masses',
        'temperatureBottom',
        'Bottom temperature',
        1.0,
        r'$^\circ$C',
        'cmo.thermal',
        False,
    ),
    (
        'water_masses',
        'salinityBottom',
        'Bottom salinity',
        1.0,
        'PSU',
        'cmo.haline',
        False,
    ),
    (
        'thin_film',
        'ssh',
        'Sea-surface height',
        1.0,
        'm',
        'cmo.deep_r',
        False,
    ),
]

#: The sections plotted: the variable, the title, the color bar's label and
#: the colormap
SECTION_FIELDS = [
    ('temperature', 'Temperature', r'$^\circ$C', 'cmo.thermal'),
    ('salinity', 'Salinity', 'PSU', 'cmo.haline'),
]


class RunPlots(ProductStep):
    """
    A step that plots the diagnostics of one run of a MISOMIP experiment

    Attributes
    ----------
    kind : str
        The kind of run, ``e3sm`` or ``standalone``, which is the products'
        group

    label : str
        A short description of the run for plot titles
    """

    def __init__(self, component, subdir, diagnostics, kind, label):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        diagnostics : RunDiagnostics
            The step whose diagnostics are plotted

        kind : str
            The kind of run

        label : str
            A short description of the run for plot titles
        """
        super().__init__(
            component=component,
            name=f'{kind}_plots',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.kind = kind
        self.label = label
        for filename in [
            TIME_SERIES_FILENAME,
            TIME_MEAN_FILENAME,
            INIT_FILENAME,
        ]:
            self.add_input_file(
                filename=filename,
                work_dir_target=f'{diagnostics.path}/{filename}',
            )
        self.add_dependency(diagnostics)

    def run(self):
        """
        Plot the diagnostics
        """
        ds_series = xr.open_dataset(TIME_SERIES_FILENAME)
        ds_mean = xr.open_dataset(TIME_MEAN_FILENAME)
        ds_init = read_initial_condition(INIT_FILENAME)
        ds_mesh = isomip_mesh(ds_init)
        months = (
            f'{ds_mean.attrs["first_month"]} to {ds_mean.attrs["last_month"]}'
        )

        for gallery, stem, title, ylabel, variables in TIME_SERIES:
            self._plot_series(
                ds_series, gallery, stem, title, ylabel, variables
            )

        floating = ds_mean.landIceFloatingFraction > 0.0
        descriptor = None
        for gallery, name, title, scale, units, cmap, under_ice in MAPS:
            descriptor = self._plot_map(
                ds_mesh,
                ds_mean,
                floating,
                descriptor,
                gallery,
                name,
                f'{title}, {months}',
                scale,
                units,
                cmap,
                under_ice,
            )

        section = self.config['misomip_analysis']
        for axis, value in [
            ('y', section.getfloat('section_y')),
            ('x', section.getfloat('section_x')),
        ]:
            self._plot_sections(ds_mesh, ds_init, ds_mean, axis, value, months)
        self._plot_overturning(ds_mean, months)
        self._plot_melt_by_draft(ds_mean, months)

    def _plot_series(self, ds_series, gallery, stem, title, ylabel, variables):
        """Plot one time series and describe it as a product"""
        series = []
        ds_data = xr.Dataset()
        for name, scale, line_label in variables:
            values = scale * ds_series[name]
            ds_data[name] = values
            series.append(
                Series(
                    time=ds_series.time.values,
                    values=values.values,
                    label=line_label or self.label,
                )
            )
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(
            series, plot, ylabel=ylabel, title=f'{title}, {self.label}'
        )
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot, data=data, group=self.kind, gallery=gallery, title=title
        )

    def _plot_map(
        self,
        ds_mesh,
        ds_mean,
        floating,
        descriptor,
        gallery,
        name,
        title,
        scale,
        units,
        cmap,
        under_ice,
    ):
        """Plot a map of a time mean and describe it as a product"""
        field = scale * ds_mean[name]
        field.name = name
        mask = floating if under_ice and 'nCells' in field.dims else None
        plot = f'{name}_map.png'
        data = f'{name}_map.nc'
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 2.6))
            ax = fig.add_subplot(111)
            descriptor = plot_horiz_field(
                ds_mesh,
                field,
                ax=ax,
                cmap=cmap,
                cmap_title=units,
                field_mask=mask,
                descriptor=descriptor,
            )
            plot_mask_boundary(ax, ds_mesh, floating, linewidth=0.75)
            ax.set_title(f'{title}, {self.label}')
            fig.savefig(plot, bbox_inches='tight', pad_inches=0.2)
        write_netcdf(field.to_dataset(), data)
        self.add_product(
            plot=plot, data=data, group=self.kind, gallery=gallery, title=title
        )
        return descriptor

    def _plot_sections(self, ds_mesh, ds_init, ds_mean, axis, value, months):
        """Plot temperature and salinity along a line of constant x or y"""
        if axis == 'y':
            x = [float(ds_mesh.xCell.min()), float(ds_mesh.xCell.max())]
            y = [value, value]
            where = f'y = {1e-3 * value:g} km'
        else:
            y = [float(ds_mesh.yCell.min()), float(ds_mesh.yCell.max())]
            x = [value, value]
            where = f'x = {1e-3 * value:g} km'
        ds_transect = compute_transect(
            x=xr.DataArray(x, dims=('nPoints',)),
            y=xr.DataArray(y, dims=('nPoints',)),
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds_mean.layerThickness,
            bottom_depth=ds_init.bottomDepth,
            min_level_cell=ds_init.minLevelCell - 1,
            max_level_cell=ds_init.maxLevelCell - 1,
            spherical=False,
        )
        for name, title, units, cmap in SECTION_FIELDS:
            stem = f'{name}_section_{axis}'
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds_mean[name],
                title=f'{title} at {where}, {months}, {self.label}',
                out_filename=plot,
                colorbar_label=units,
                cmap=cmap,
                figsize=(10.0, 4.0),
            )
            ds_data = ds_transect.copy()
            ds_data[name] = ds_mean[name]
            write_netcdf(ds_data, data)
            self.add_product(
                plot=plot,
                data=data,
                group=self.kind,
                gallery='water_masses',
                title=f'{title} at {where}',
            )

    def _plot_overturning(self, ds_mean, months):
        """Plot the overturning streamfunction in x and z"""
        osf = ds_mean.overturningStreamfunction
        plot = 'overturning_streamfunction.png'
        data = 'overturning_streamfunction.nc'
        limit = float(np.nanmax(np.abs(osf.values)))
        limit = limit if limit > 0.0 else 1.0
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 4.0))
            ax = fig.add_subplot(111)
            mesh = ax.pcolormesh(
                osf.x.values,
                osf.zInterface.values,
                osf.values,
                cmap='cmo.curl',
                vmin=-limit,
                vmax=limit,
                shading='nearest',
            )
            ax.set_xlabel('x (km)')
            ax.set_ylabel('z (m)')
            ax.set_title(f'Overturning streamfunction, {months}, {self.label}')
            cbar = fig.colorbar(mesh, ax=ax)
            cbar.set_label('Sv')
            fig.savefig(plot, bbox_inches='tight')
        write_netcdf(osf.to_dataset(), data)
        self.add_product(
            plot=plot,
            data=data,
            group=self.kind,
            gallery='circulation',
            title='Overturning streamfunction',
        )

    def _plot_melt_by_draft(self, ds_mean, months):
        """Plot the mean melt rate in bins of draft"""
        melt = SECONDS_PER_YEAR * ds_mean.meltRateByDraft
        plot = 'melt_rate_by_draft.png'
        data = 'melt_rate_by_draft.nc'
        with mplstyle_context():
            fig = Figure(figsize=(5.0, 5.0))
            ax = fig.add_subplot(111)
            ax.plot(melt.values, ds_mean.draft.values, 'k.-')
            ax.set_xlabel('melt rate (m yr$^{-1}$)')
            ax.set_ylabel('draft (m)')
            ax.set_title(f'Melt rate by draft, {months},\n{self.label}')
            ax.grid(True, alpha=0.3)
            fig.savefig(plot, bbox_inches='tight')
        ds_data = xr.Dataset()
        ds_data['meltRateByDraft'] = melt
        ds_data.meltRateByDraft.attrs['units'] = 'm yr-1'
        ds_data['floatingAreaByDraft'] = ds_mean.floatingAreaByDraft
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group=self.kind,
            gallery='melt',
            title='Melt rate by draft',
        )
