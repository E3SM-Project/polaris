import matplotlib
import numpy as np
import xarray as xr
from matplotlib.collections import QuadMesh
from matplotlib.colors import BoundaryNorm
from matplotlib.figure import Figure
from mpas_tools.io import write_netcdf
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.analysis.product_step import ProductStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    LANDICE_FILENAME,
    SECONDS_PER_YEAR,
    TIME_MEAN_FILENAME,
    TIME_SERIES_FILENAME,
    add_geometry_inputs,
    isomip_mesh,
    read_initial_condition,
)
from polaris.viz import mplstyle_context, plot_horiz_field
from polaris.viz.planar import plot_mask_boundary
from polaris.viz.time_series import Series, plot_time_series

#: The time series plotted for each run: the gallery, the file's stem, the
#: title, the y label, and each variable with its scale and label.  A
#: variable a run lacks, such as one only a coupled run has, is left out.
TIME_SERIES: list[tuple[str, str, str, str, list[tuple]]] = [
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
        'circulation',
        'open_ocean_ssh_residual',
        'SSH of the open ocean above the restoring region',
        'height (cm)',
        [
            ('openOceanSshAboveRestoring', 100.0, 'SSH'),
            ('openOceanDensityImpliedSsh', 100.0, 'implied by density'),
            ('openOceanSshResidual', 100.0, 'residual'),
        ],
    ),
    (
        'circulation',
        'open_ocean_ssh_offset',
        'Residual SSH of the open ocean: gyres and offset',
        'height (cm)',
        [
            ('openOceanSshResidual', 100.0, 'residual'),
            (
                'openOceanBottomGeostrophicSsh',
                100.0,
                'geostrophic height of the bottom flow',
            ),
            ('openOceanSshOffset', 100.0, 'offset'),
        ],
    ),
    (
        'circulation',
        'open_ocean_gyre_strength',
        'Gyres in the open ocean',
        'barotropic streamfunction (Sv)',
        [
            ('openOceanGyreMax', 1.0, 'largest'),
            ('openOceanGyreMin', 1.0, 'smallest'),
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
    (
        'thin_film',
        'grounding_line_band',
        'Floating ice the ocean treats as grounded',
        'fraction (%)',
        [
            (
                'bandFloatingAreaFraction',
                100.0,
                "of the land-ice model's floating area",
            ),
            ('bandMissedMeltFraction', 100.0, 'of the melt (estimate)'),
        ],
    ),
]

#: The maps of time means plotted for each run: the gallery, the variable,
#: the title, the scale, the color bar's label, the colormap, and where the
#: field is shown: ``floating`` under floating ice, ``open`` where there is
#: no land ice or ``all``
MAPS = [
    (
        'melt',
        'meltRate',
        'Melt rate',
        SECONDS_PER_YEAR,
        'm yr$^{-1}$',
        'cmo.amp',
        'floating',
    ),
    (
        'melt',
        'thermalDriving',
        'Thermal driving',
        1.0,
        r'$^\circ$C',
        'cmo.thermal',
        'floating',
    ),
    (
        'melt',
        'halineDriving',
        'Haline driving',
        1.0,
        'PSU',
        'cmo.haline',
        'floating',
    ),
    (
        'melt',
        'landIceFrictionVelocity',
        'Friction velocity',
        1.0,
        'm s$^{-1}$',
        'cmo.speed',
        'floating',
    ),
    (
        'circulation',
        'uBoundaryLayer',
        'Velocity in x in the top layer under the ice',
        1.0,
        'm s$^{-1}$',
        'cmo.balance',
        'floating',
    ),
    (
        'circulation',
        'vBoundaryLayer',
        'Velocity in y in the top layer under the ice',
        1.0,
        'm s$^{-1}$',
        'cmo.balance',
        'floating',
    ),
    (
        'circulation',
        'barotropicStreamfunction',
        'Barotropic streamfunction',
        1.0,
        'Sv',
        'cmo.curl',
        'all',
    ),
    (
        'water_masses',
        'temperatureBottom',
        'Bottom temperature',
        1.0,
        r'$^\circ$C',
        'cmo.thermal',
        'all',
    ),
    (
        'water_masses',
        'salinityBottom',
        'Bottom salinity',
        1.0,
        'PSU',
        'cmo.haline',
        'all',
    ),
    (
        'thin_film',
        'ssh',
        'Sea-surface height where there is no land ice',
        1.0,
        'm',
        'cmo.deep_r',
        'open',
    ),
    (
        'geometry',
        'iceDraft',
        'Ice draft',
        1.0,
        'm',
        'cmo.deep_r',
        'all',
    ),
    (
        'geometry',
        'bathymetry',
        'Bathymetry',
        1.0,
        'm',
        'cmo.deep_r',
        'all',
    ),
]

#: The option in ``[misomip_analysis_color_ranges]`` for each field plotted
#: in maps and sections
RANGE_OPTIONS = {
    'meltRate': 'melt_rate',
    'thermalDriving': 'thermal_driving',
    'halineDriving': 'haline_driving',
    'landIceFrictionVelocity': 'friction_velocity',
    'uBoundaryLayer': 'boundary_layer_velocity',
    'vBoundaryLayer': 'boundary_layer_velocity',
    'barotropicStreamfunction': 'barotropic_streamfunction',
    'overturningStreamfunction': 'overturning_streamfunction',
    'temperature': 'temperature',
    'temperatureBottom': 'temperature',
    'salinity': 'salinity',
    'salinityBottom': 'salinity',
    'ssh': 'ssh',
    'iceDraft': 'ice_draft',
    'bathymetry': 'bathymetry',
}

#: The fields whose color range, when it comes from the data, is centered
#: on zero
SYMMETRIC_FIELDS = {
    'uBoundaryLayer',
    'vBoundaryLayer',
    'overturningStreamfunction',
}

#: The time series of the ice sheet: the variable, the file's stem, the
#: title, the y label and the scale
LANDICE_SERIES = [
    ('iceVolume', 'ice_volume', 'Ice volume', 'volume (km$^3$)', 1e-9),
    (
        'iceVAF',
        'volume_above_flotation',
        'Volume above flotation',
        'volume (km$^3$)',
        1e-9,
    ),
    (
        'groundedArea',
        'grounded_area',
        'Grounded area',
        'area (km$^2$)',
        1e-6,
    ),
    (
        'xGL',
        'grounding_line_position',
        'Grounding line along the section',
        'x (km)',
        1e-3,
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

    has_landice : bool
        Whether the run has MALI output to plot
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
        add_geometry_inputs(self, diagnostics)
        for filename in [TIME_SERIES_FILENAME, TIME_MEAN_FILENAME]:
            self.add_input_file(
                filename=filename,
                work_dir_target=f'{diagnostics.path}/{filename}',
            )
        self.has_landice = bool(diagnostics.landice_filenames)
        if self.has_landice:
            self.add_input_file(
                filename=LANDICE_FILENAME,
                work_dir_target=f'{diagnostics.path}/{LANDICE_FILENAME}',
            )
        self.add_dependency(diagnostics)

    def run(self):
        """
        Plot the diagnostics
        """
        ds_series = xr.open_dataset(TIME_SERIES_FILENAME)
        ds_mean = xr.open_dataset(TIME_MEAN_FILENAME)
        ds_init = read_initial_condition()
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
        for gallery, name, title, scale, units, cmap, where in MAPS:
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
                where,
            )

        section = self.config['misomip_analysis']
        for axis, value in [
            ('y', section.getfloat('section_y')),
            ('x', section.getfloat('section_x')),
        ]:
            self._plot_sections(ds_mesh, ds_init, ds_mean, axis, value, months)
        self._plot_overturning(ds_mean, months)
        self._plot_melt_by_draft(ds_mean, months)
        if self.has_landice:
            # the times are days, not dates to decode
            ds_landice = xr.open_dataset(
                LANDICE_FILENAME, decode_times=False, decode_timedelta=False
            )
            self._plot_landice_series(ds_landice)
            self._plot_grounding_lines(ds_mesh, ds_mean, ds_landice, months)

    def _plot_series(self, ds_series, gallery, stem, title, ylabel, variables):
        """Plot one time series and describe it as a product"""
        series = []
        ds_data = xr.Dataset()
        for name, scale, line_label in variables:
            if name not in ds_series:
                continue
            values = scale * ds_series[name]
            ds_data[name] = values
            series.append(
                Series(
                    time=ds_series.time.values,
                    values=values.values,
                    label=line_label or self.label,
                )
            )
        if not series:
            return
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
        where,
    ):
        """Plot a map of a time mean and describe it as a product"""
        field = scale * ds_mean[name]
        field.name = name
        mask = None
        counted = None
        if 'nCells' in field.dims:
            mask = get_map_mask(ds_mean, where)
            counted = get_range_mask(ds_mean, mask)
        vmin, vmax = get_color_range(self.config, name, field, counted)
        norm, ticks = get_color_norm(self.config, name, cmap)
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
                vmin=vmin,
                vmax=vmax,
                norm=norm,
                cbar_ticks=ticks,
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
            start = x[0]
            distance_label = 'x (km)'
        else:
            y = [float(ds_mesh.yCell.min()), float(ds_mesh.yCell.max())]
            x = [value, value]
            where = f'x = {1e-3 * value:g} km'
            start = y[0]
            distance_label = 'y (km)'
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
        counted = get_range_mask(ds_mean)
        for name, title, units, cmap in SECTION_FIELDS:
            stem = f'{name}_section_{axis}'
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            field = ds_mean[name]
            vmin, vmax = get_color_range(self.config, name, field, counted)
            norm, ticks = get_color_norm(self.config, name, cmap)
            plot_section(
                ds_transect,
                field,
                plot,
                title=f'{title} at {where}, {months}, {self.label}',
                units=units,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                start=start,
                distance_label=distance_label,
                norm=norm,
                ticks=ticks,
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
        if osf.attrs.get('method') == 'normalLayerThicknessFlux':
            source = 'the layer thickness flux'
        else:
            source = 'the monthly means of velocity and thickness'
        self._plot_overturning_field(
            osf.x.values,
            osf.zInterface.values,
            osf,
            osf.to_dataset(),
            'overturning_streamfunction',
            f'Overturning streamfunction, {months}, {self.label},\n'
            f'from {source}, integrated up from the seafloor',
            'Overturning streamfunction',
        )

    def _plot_overturning_field(
        self, x, z, osf, ds_data, stem, title, product_title
    ):
        """Plot one overturning streamfunction and describe it as a
        product"""
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        vmin, vmax = get_color_range(
            self.config, 'overturningStreamfunction', osf
        )
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 4.0))
            ax = fig.add_subplot(111)
            mesh = ax.pcolormesh(
                x,
                z,
                osf.values,
                cmap='cmo.curl',
                vmin=vmin,
                vmax=vmax,
                shading='nearest',
            )
            ax.set_xlabel('x (km)')
            ax.set_ylabel('z (m)')
            ax.set_title(title)
            cbar = fig.colorbar(mesh, ax=ax)
            cbar.set_label('Sv')
            fig.savefig(plot, bbox_inches='tight')
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group=self.kind,
            gallery='circulation',
            title=product_title,
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

    def _plot_landice_series(self, ds_landice):
        """Plot MALI's volume, volume above flotation, grounded area and
        grounding line over time"""
        years = ds_landice.daysSinceStart.values / 365.0
        for name, stem, title, ylabel, scale in LANDICE_SERIES:
            values = scale * ds_landice[name]
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            plot_time_series(
                [Series(time=years, values=values.values, label=self.label)],
                plot,
                ylabel=ylabel,
                xlabel='time since the start of the run (years)',
                title=f'{title}, {self.label}',
            )
            write_netcdf(values.to_dataset(name=name), data)
            self.add_product(
                plot=plot,
                data=data,
                group=self.kind,
                gallery='ice_sheet',
                title=title,
            )

    def _plot_grounding_lines(self, ds_mesh, ds_mean, ds_landice, months):
        """Map the ocean's floating fraction with MALI's grounding line at
        the start and end of the period"""
        plot = 'grounding_lines.png'
        data = 'grounding_lines.nc'
        fraction = ds_mean.landIceFloatingFraction
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 2.6))
            ax = fig.add_subplot(111)
            plot_horiz_field(
                ds_mesh,
                fraction,
                ax=ax,
                vmin=0.0,
                vmax=1.0,
                cmap='cmo.ice_r',
                cmap_title='floating fraction',
            )
            for label, color in [('First', 'tab:orange'), ('Last', 'k')]:
                ax.plot(
                    ds_landice[f'xGroundingLine{label}'].values,
                    ds_landice[f'yGroundingLine{label}'].values,
                    '.',
                    color=color,
                    markersize=2,
                    label=f'MALI, {label.lower()} record',
                )
            ax.legend(loc='upper right', fontsize='small')
            ax.set_title(
                f"Ocean's floating fraction, {months}, and MALI's grounding "
                f'line,\n{self.label}'
            )
            fig.savefig(plot, bbox_inches='tight', pad_inches=0.2)
        ds_data = ds_landice[
            [
                'xGroundingLineFirst',
                'yGroundingLineFirst',
                'xGroundingLineLast',
                'yGroundingLineLast',
            ]
        ].copy()
        ds_data['landIceFloatingFraction'] = fraction
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group=self.kind,
            gallery='ice_sheet',
            title="The ocean's floating fraction and MALI's grounding line",
        )


def get_map_mask(ds, where):
    """
    Get where a map shows its field

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``landIceFraction`` and ``landIceFloatingFraction``

    where : {'floating', 'open', 'all'}
        Under floating ice, where there is no land ice, or everywhere

    Returns
    -------
    mask : xarray.DataArray or None
        Where the field is shown, or ``None`` to show it everywhere
    """
    if where == 'all':
        return None
    if where == 'floating':
        return ds.landIceFloatingFraction > 0.0
    if where == 'open':
        return ds.landIceFraction == 0.0
    raise ValueError(f'Unexpected place to show a field: {where}')


def get_range_mask(ds, mask=None):
    """
    Get the cells whose values count toward a color range taken from the
    data: those shown, less the columns that hold only the thin film

    The film keeps the initial condition's water, so its values would set
    the range of the cavity's.  It is still drawn.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with ``landIceFraction`` and ``landIceFloatingFraction``
        and, from a time mean, ``filmColumn``.  Without ``filmColumn``, the
        film is the columns under grounded ice.

    mask : xarray.DataArray, optional
        Where the field is shown, everywhere by default

    Returns
    -------
    counted : xarray.DataArray
        The cells whose values set the range
    """
    if 'filmColumn' in ds:
        film = ds.filmColumn > 0
    else:
        film = np.logical_and(
            ds.landIceFraction > 0.0, ds.landIceFloatingFraction == 0.0
        )
    counted = np.logical_not(film)
    if mask is not None:
        counted = np.logical_and(counted, mask)
    return counted


def get_color_range(config, name, field=None, counted=None):
    """
    Get the color range of a field's map or section

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options, with ``[misomip_analysis_color_ranges]``

    name : str
        The field's variable name

    field : xarray.DataArray, optional
        The field, whose range is used when the config option is blank

    counted : xarray.DataArray, optional
        The cells whose values count toward the range, every cell by
        default

    Returns
    -------
    vmin, vmax : float or None
        The range, or ``None`` if neither the config nor a field gives one
    """
    section = 'misomip_analysis_color_ranges'
    option = RANGE_OPTIONS.get(name)
    value = ''
    if option is not None and config.has_option(section, option):
        value = config.get(section, option).strip()
    if value:
        vmin, vmax = (float(bound) for bound in value.split(','))
        return vmin, vmax
    if field is None:
        return None, None
    values = field if counted is None else field.where(counted)
    vmin = float(np.nanmin(values.values))
    vmax = float(np.nanmax(values.values))
    if name in SYMMETRIC_FIELDS:
        limit = max(abs(vmin), abs(vmax))
        limit = limit if limit > 0.0 else 1.0
        vmin, vmax = -limit, limit
    return vmin, vmax


def get_color_norm(config, name, cmap):
    """
    Get the norm of a field whose colors are in uneven bins, as salinity's
    are, so the fresh film and the cavity both show

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options, with ``[misomip_analysis_color_ranges]``

    name : str
        The field's variable name

    cmap : str
        The colormap, whose number of colors the bins share

    Returns
    -------
    norm : matplotlib.colors.BoundaryNorm or None
        The norm, or ``None`` if the field's ``_bounds`` option is blank or
        absent

    ticks : list of float or None
        The color bar's ticks, from the ``_ticks`` option
    """
    section = 'misomip_analysis_color_ranges'
    option = RANGE_OPTIONS.get(name)
    if option is None or not _has_value(config, section, f'{option}_bounds'):
        return None, None
    bounds = config.getlist(section, f'{option}_bounds', dtype=float)
    ticks = None
    if _has_value(config, section, f'{option}_ticks'):
        ticks = config.getlist(section, f'{option}_ticks', dtype=float)
    colors = matplotlib.colormaps[cmap].N
    norm = BoundaryNorm(bounds, ncolors=colors, extend='both')
    return norm, ticks


def plot_section(
    ds_transect,
    field,
    out_filename,
    title,
    units,
    cmap,
    vmin,
    vmax,
    start,
    distance_label,
    norm=None,
    ticks=None,
):
    """
    Plot a section along a line of constant x or y, against the position
    along it

    Parameters
    ----------
    ds_transect : xarray.Dataset
        The transect from ``mpas_tools.ocean.viz.transect.compute_transect``

    field : xarray.DataArray
        The field on cells and layers

    out_filename : str
        The image file to write

    title : str
        The title

    units : str
        The color bar's label

    cmap : str
        The colormap

    vmin, vmax : float or None
        The color range, from the data if ``None``

    start : float
        The x or y (m) of the transect's start, from which ``dNode``
        measures distance

    distance_label : str
        The label of the horizontal axis

    norm : matplotlib.colors.Normalize, optional
        A norm mapping values to colors, in place of ``vmin`` and ``vmax``

    ticks : list of float, optional
        The color bar's ticks
    """
    ds_plot = ds_transect.copy()
    ds_plot['dNode'] = ds_transect.dNode + start
    with mplstyle_context():
        fig = Figure(figsize=(10.0, 4.0))
        ax = fig.add_subplot(111)
        plot_transect(
            ds_transect=ds_plot,
            mpas_field=field,
            ax=ax,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        mesh = next(
            child for child in ax.collections if isinstance(child, QuadMesh)
        )
        if norm is not None:
            mesh.set_norm(norm)
        fig.colorbar(
            mesh, ax=ax, extend='both', shrink=0.7, label=units, ticks=ticks
        )
        ax.set_xlabel(distance_label)
        ax.set_title(title)
        fig.savefig(out_filename, bbox_inches='tight', pad_inches=0.2)


def _has_value(config, section, option):
    """Whether a config option is present and not blank"""
    return (
        config.has_option(section, option)
        and config.get(section, option).strip() != ''
    )
