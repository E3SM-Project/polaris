import numpy as np
import xarray as xr
from matplotlib.figure import Figure
from mpas_tools.io import write_netcdf

from polaris.analysis.product_step import ProductStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    SECONDS_PER_YEAR,
    TIME_MEAN_FILENAME,
    TIME_SERIES_FILENAME,
    add_geometry_inputs,
    isomip_mesh,
    read_initial_condition,
)
from polaris.tasks.e3sm.analysis.misomip.plots import scale_with_units
from polaris.tasks.e3sm.analysis.misomip.yung2026 import YUNG2026_FILENAME
from polaris.viz import mplstyle_context, plot_horiz_field
from polaris.viz.time_series import Series, plot_time_series

#: The units of melt rates in plots and their data
MELT_RATE_UNITS = 'm yr$^{-1}$'

#: Labels of the runs, which use E3SM's physics rather than the protocol's
#: COM physics
LABELS = {'e3sm': 'E3SM (not COM)', 'standalone': 'standalone (not COM)'}

#: Colors of the runs
COLORS = {'e3sm': 'tab:blue', 'standalone': 'tab:orange'}

#: The model whose entry is marked, the one Polaris descends from
MARKED_MODEL = 'MPAS-Ocean'

#: The length (years) of each experiment in the protocol, the shortest
#: x axis of the time series
NOMINAL_YEARS = {'ocean0': 1.0, 'ocean1': 20.0, 'ocean2': 20.0}

#: The series compared: the variable, the file's stem, the title, the y
#: label and the scale
SERIES = [
    (
        'totalMeltFlux',
        'total_melt_flux',
        'Total melt flux',
        'melt flux (Gt yr$^{-1}$)',
        SECONDS_PER_YEAR * 1e-12,
    ),
    (
        'meanMeltRate',
        'mean_melt_rate',
        'Mean melt rate over the ice base',
        'melt rate (m yr$^{-1}$)',
        SECONDS_PER_YEAR,
    ),
    (
        'meanMeltRateDeep',
        'mean_melt_rate_deep',
        'Mean melt rate where the draft is below 300 m',
        'melt rate (m yr$^{-1}$)',
        SECONDS_PER_YEAR,
    ),
    (
        'meanTemperature',
        'mean_temperature',
        'Mean temperature',
        r'temperature ($^\circ$C)',
        1.0,
    ),
    (
        'meanSalinity',
        'mean_salinity',
        'Mean salinity',
        'salinity (PSU)',
        1.0,
    ),
]


class PublishedComparison(ProductStep):
    """
    A step that compares the runs of Ocean0, Ocean1 or Ocean2 with the COM
    results of Yung et al. (2026)

    The runs use E3SM's physics, not the protocol's COM physics, so the
    comparison places them in the ensemble's range rather than validating
    them.

    Attributes
    ----------
    kinds : list of str
        The runs compared, ``e3sm`` and ``standalone``

    experiment : str
        The experiment
    """

    def __init__(self, component, subdir, yung2026, diagnostics):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        yung2026 : polaris.tasks.e3sm.analysis.misomip.yung2026.Yung2026
            The step with the published results

        diagnostics : dict of str to RunDiagnostics
            The diagnostics steps of the runs
        """
        super().__init__(
            component=component,
            name='published',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.kinds = list(diagnostics)
        self.experiment = yung2026.experiment
        self.add_input_file(
            filename=YUNG2026_FILENAME,
            work_dir_target=f'{yung2026.path}/{YUNG2026_FILENAME}',
        )
        self.add_dependency(yung2026)
        for kind, step in diagnostics.items():
            for filename in [TIME_SERIES_FILENAME, TIME_MEAN_FILENAME]:
                self.add_input_file(
                    filename=f'{kind}_{filename}',
                    work_dir_target=f'{step.path}/{filename}',
                )
            self.add_dependency(step, name=f'{kind}_diagnostics')
        add_geometry_inputs(self, diagnostics[self.kinds[0]])

    def run(self):
        """
        Compare the runs with the published results
        """
        ds_pub = xr.open_dataset(YUNG2026_FILENAME)
        series = {
            kind: xr.open_dataset(f'{kind}_{TIME_SERIES_FILENAME}')
            for kind in self.kinds
        }
        means = {
            kind: xr.open_dataset(f'{kind}_{TIME_MEAN_FILENAME}')
            for kind in self.kinds
        }
        for name, stem, title, ylabel, scale in SERIES:
            self._plot_series(ds_pub, series, name, stem, title, ylabel, scale)
        self._plot_melt_by_draft(ds_pub, means)
        self._plot_strengths(ds_pub, series, means)
        self._plot_melt_maps(ds_pub, means)

    def _plot_series(self, ds_pub, series, name, stem, title, ylabel, scale):
        """Plot a series of the runs over the ensemble"""
        time = ds_pub.time.values
        ensemble = []
        lines = []
        for index, model in enumerate(_model_names(ds_pub)):
            values = scale * ds_pub[name].isel(nModels=index).values
            if model == MARKED_MODEL:
                lines.append(
                    Series(
                        time,
                        values,
                        f'{model} (Yung et al. 2026)',
                        color='k',
                        linestyle='--',
                    )
                )
            else:
                ensemble.append(Series(time, values, model))
        ds_data = xr.Dataset()
        ds_data['published'] = scale_with_units(ds_pub[name], scale, ylabel)
        for kind in self.kinds:
            values = scale_with_units(series[kind][name], scale, ylabel)
            ds_data[kind] = values.rename({'Time': f'{kind}_Time'})
            lines.append(
                Series(
                    series[kind].time.values,
                    values.values,
                    LABELS[kind],
                    color=COLORS[kind],
                    linewidth=2.0,
                    marker='o',
                )
            )
        ends = [
            float(series[kind].time.max()) + 1.0 / 12.0 for kind in self.kinds
        ]
        end = max([NOMINAL_YEARS[self.experiment]] + ends)
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(
            lines,
            plot,
            ylabel=ylabel,
            title=f'{title} and the COM results of Yung et al. (2026)',
            ensemble=ensemble,
            ensemble_label='other COM models',
            xlim=(0.0, end),
        )
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='published',
            gallery='time_series',
            title=title,
        )

    def _plot_melt_by_draft(self, ds_pub, means):
        """Plot the time-mean melt rate in bins of draft"""
        plot = 'melt_rate_by_draft.png'
        data = 'melt_rate_by_draft.nc'
        with mplstyle_context():
            fig = Figure(figsize=(6.0, 6.0))
            ax = fig.add_subplot(111)
            for index, model in enumerate(_model_names(ds_pub)):
                melt = SECONDS_PER_YEAR * ds_pub.meltRateByDraft.isel(
                    nModels=index
                )
                marked = model == MARKED_MODEL
                ax.plot(
                    melt.values,
                    ds_pub.draftBin.values,
                    color='k' if marked else '0.7',
                    linestyle='--' if marked else '-',
                    linewidth=1.0,
                    label=f'{model} (Yung et al. 2026)' if marked else None,
                )
            for kind in self.kinds:
                melt = SECONDS_PER_YEAR * means[kind].meltRateByDraft
                ax.plot(
                    melt.values,
                    means[kind].draft.values,
                    color=COLORS[kind],
                    linewidth=2.0,
                    label=LABELS[kind],
                )
            ax.set_xlabel('melt rate (m yr$^{-1}$)')
            ax.set_ylabel('draft (m)')
            ax.set_title(
                'Melt rate by draft, other COM models in grey\n'
                + _periods(ds_pub, means, self.experiment, separator='\n')
            )
            ax.legend(loc='lower right')
            ax.grid(True, alpha=0.3)
            fig.savefig(plot, bbox_inches='tight')
        ds_data = xr.Dataset()
        ds_data['published'] = scale_with_units(
            ds_pub.meltRateByDraft, SECONDS_PER_YEAR, MELT_RATE_UNITS
        )
        for kind in self.kinds:
            ds_data[kind] = scale_with_units(
                means[kind].meltRateByDraft, SECONDS_PER_YEAR, MELT_RATE_UNITS
            ).rename({'nDraftBins': f'{kind}_nDraftBins'})
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='published',
            gallery='melt',
            title='Melt rate by draft',
        )

    def _plot_strengths(self, ds_pub, series, means):
        """Plot the streamfunctions' strengths against the mean melt rate,
        as Yung et al. (2026) do"""
        plot = 'streamfunction_strengths.png'
        data = 'streamfunction_strengths.nc'
        count = int(ds_pub.attrs['mean_months'])
        melt_pub = SECONDS_PER_YEAR * ds_pub.meanMeltRateEnd.values
        ours = {
            kind: dict(
                melt=SECONDS_PER_YEAR
                * float(series[kind].meanMeltRate[-count:].mean()),
                barotropic=float(
                    series[kind].barotropicStrength[-count:].mean()
                ),
                overturning=float(
                    series[kind].overturningStrength[-count:].mean()
                ),
            )
            for kind in self.kinds
        }
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 4.5))
            for index, name in enumerate(['barotropic', 'overturning']):
                ax = fig.add_subplot(1, 2, index + 1)
                strength = ds_pub[f'{name}Strength'].values
                ax.scatter(melt_pub, strength, color='0.6', label='COM models')
                for model_index, model in enumerate(_model_names(ds_pub)):
                    ax.annotate(
                        model,
                        (melt_pub[model_index], strength[model_index]),
                        fontsize='x-small',
                        color='0.4',
                    )
                for kind in self.kinds:
                    ax.scatter(
                        ours[kind]['melt'],
                        ours[kind][name],
                        color=COLORS[kind],
                        s=60,
                        label=LABELS[kind],
                    )
                ax.set_xlabel('mean melt rate (m yr$^{-1}$)')
                ax.set_ylabel(f'{name} range under the ice (Sv)')
                ax.grid(True, alpha=0.3)
                ax.legend(loc='best', fontsize='small')
            fig.suptitle(
                'Circulation and melt, '
                f'{_periods(ds_pub, means, self.experiment)}'
            )
            fig.savefig(plot, bbox_inches='tight')
        ds_data = xr.Dataset()
        ds_data['publishedMeanMeltRate'] = ('nModels', melt_pub)
        for name in ['barotropic', 'overturning']:
            ds_data[f'published{name.capitalize()}Strength'] = ds_pub[
                f'{name}Strength'
            ]
        ds_data.coords['model'] = ds_pub.model
        for kind in self.kinds:
            for key, value in ours[kind].items():
                ds_data[f'{kind}_{key}'] = value
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='published',
            gallery='circulation',
            title='Circulation strengths against melt',
        )

    def _plot_melt_maps(self, ds_pub, means):
        """Map each run's time-mean melt rate beside the ensemble mean"""
        plot = 'melt_rate_maps.png'
        data = 'melt_rate_maps.nc'
        ds_init = read_initial_condition()
        ds_mesh = isomip_mesh(ds_init)
        ensemble = scale_with_units(
            ds_pub.meltRate.mean(dim='nModels'),
            SECONDS_PER_YEAR,
            MELT_RATE_UNITS,
        )
        fields = {
            kind: scale_with_units(
                means[kind].meltRate, SECONDS_PER_YEAR, MELT_RATE_UNITS
            )
            for kind in self.kinds
        }
        vmax = max(
            [float(np.nanpercentile(ensemble.values, 99))]
            + [float(field.max()) for field in fields.values()]
        )
        count = len(self.kinds) + 1
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 2.6 * count))
            ax = fig.add_subplot(count, 1, 1)
            # the centers of the protocol's 2 km output grid (Sect. 3.3)
            x = 321.0e3 + 2.0e3 * np.arange(ensemble.sizes['nx'])
            y = 1.0e3 + 2.0e3 * np.arange(ensemble.sizes['ny'])
            mesh = ax.pcolormesh(
                x,
                y,
                ensemble.values,
                cmap='cmo.amp',
                vmin=0.0,
                vmax=vmax,
                shading='nearest',
            )
            ax.set_aspect('equal')
            ax.set_xlim(320.0e3, 800.0e3)
            ax.xaxis.set_major_formatter(lambda value, pos: f'{value / 1e3:g}')
            ax.yaxis.set_major_formatter(lambda value, pos: f'{value / 1e3:g}')
            ax.set_ylabel('y (km)')
            ax.set_title(
                'Mean of the COM models (Yung et al. 2026), '
                f'{_com_period(ds_pub, self.experiment)}'
            )
            fig.colorbar(mesh, ax=ax, shrink=0.7).set_label('m yr$^{-1}$')
            floating = ds_init.landIceFloatingFraction > 0.0
            descriptor = None
            for index, kind in enumerate(self.kinds):
                ax = fig.add_subplot(count, 1, index + 2)
                descriptor = plot_horiz_field(
                    ds_mesh,
                    fields[kind],
                    ax=ax,
                    vmin=0.0,
                    vmax=vmax,
                    cmap='cmo.amp',
                    cmap_title='m yr$^{-1}$',
                    field_mask=floating,
                    descriptor=descriptor,
                )
                ax.set_title(f'{LABELS[kind]}, {_run_period(means[kind])}')
            fig.suptitle('Time-mean melt rate')
            fig.savefig(plot, bbox_inches='tight', pad_inches=0.2)
        ds_data = xr.Dataset()
        ds_data['publishedMeanMeltRate'] = ensemble
        for kind, field in fields.items():
            ds_data[kind] = field
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='published',
            gallery='melt',
            title='Time-mean melt rate and the COM models',
        )


def _model_names(ds_pub):
    """The models' names, which come back from netCDF as bytes"""
    return [
        name.decode() if isinstance(name, bytes) else str(name)
        for name in ds_pub.model.values
    ]


def _run_period(ds_mean):
    """The months a run's time means cover"""
    return f'{ds_mean.attrs["first_month"]} to {ds_mean.attrs["last_month"]}'


def _com_period(ds_pub, experiment):
    """The months the COM models' time means cover"""
    count = int(ds_pub.attrs['mean_months'])
    years = NOMINAL_YEARS[experiment]
    return f'last {count} months of {years:g}-year runs'


def _periods(ds_pub, means, experiment, separator='; '):
    """The months that the runs' and the COM models' time means cover"""
    periods = [
        f'{LABELS[kind]} {_run_period(ds_mean)}'
        for kind, ds_mean in means.items()
    ]
    periods.append(f'COM models {_com_period(ds_pub, experiment)}')
    return separator.join(periods)
