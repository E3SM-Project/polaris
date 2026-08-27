import xarray as xr

from polaris.ocean.analysis_plots import plot_global_stats
from polaris.ocean.global_stats_names import (
    STAT_DESCRIPTIONS,
    discover_fields,
    select_global_stats,
)
from polaris.ocean.model.time import get_simulation_years
from polaris.tasks.ocean.analysis.analysis_step import AnalysisStep


class GlobalStatsTimeSeries(AnalysisStep):
    """
    A step that plots time series of the quantities in the simulation's global
    statistics output

    Attributes
    ----------
    time_mean_period : str or None
        The period the statistics were averaged over, if the simulation wrote
        time means, or ``None`` if it wrote snapshots.  The two are spelled
        differently in the file, so which one it is has to be known before the
        variables can be looked up.
    """

    def __init__(self, component, subdir, start_year, end_year):
        """
        Create the global statistics time series step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        start_year : int
            The first year of the time series, inclusive

        end_year : int
            The last year of the time series, inclusive
        """
        super().__init__(
            component=component,
            name='global_stats',
            subdir=subdir,
            start_year=start_year,
            end_year=end_year,
            ntasks=1,
            cpus_per_task=1,
        )
        self.time_mean_period = None

    def setup(self):
        """
        Link the simulation's global statistics output
        """
        sim_files = self.get_sim_files()
        self.add_sim_input_files(
            sim_files.global_stats_files(self.start_year, self.end_year)
        )
        stream = sim_files.global_stats_stream()
        assert stream is not None
        self.time_mean_period = stream.period if stream.is_reduction else None

    def run(self):
        """
        Plot a time series of each field's global statistics, and write the
        data behind each plot beside it
        """
        self.log_inputs()

        section = 'ocean_analysis_time_series'
        stats = self.config.getlist(section, 'stats')

        ds = self._open_stats()
        fields = self._fields(ds)
        found = select_global_stats(
            ds=ds,
            fields=fields,
            stats=stats,
            model='omega',
            field_map=self._field_map(fields),
            time_mean_period=self.time_mean_period,
            log=self.logger.info,
            source=', '.join(self.input_filenames),
            hint=(
                f'A simulation writes some subset of the fields and '
                f'statistics [{section}] asks for, but none of them usually '
                f'means that years {self.start_year} through '
                f'{self.end_year} are not years the simulation covers, or '
                f'that its GlobalStats analysis group named a stream other '
                f'than the one it wrote.'
            ),
        )

        time = get_simulation_years(ds)
        for field, field_stats in found.items():
            self._plot_field(ds, field, field_stats, time)

    def _open_stats(self):
        """
        Open the global statistics files as one series

        The variables keep the names Omega gave them, since those are the
        names the analysis builds and looks for.
        """
        ds = xr.open_mfdataset(
            [self.work_path(filename) for filename in self.input_filenames],
            combine='nested',
            concat_dim='time',
        )
        if 'Scalar' in ds.dims:
            # Omega writes each global statistic as a field of one point
            ds = ds.isel(Scalar=0)
        # the rest of Polaris spells the time dimension the MPAS-Ocean way
        return ds.rename({'time': 'Time'})

    def _fields(self, ds):
        """Get the fields to plot, in Polaris-standard names"""
        fields = self.config.getlist('ocean_analysis_time_series', 'fields')
        if fields:
            return fields
        # an empty option asks for whatever the simulation wrote
        return self.component.map_var_list_from_native_model(
            discover_fields(
                ds, model='omega', time_mean_period=self.time_mean_period
            )
        )

    def _field_map(self, fields):
        """Get the name Omega gave each configured field"""
        native = self.component.map_var_list_to_native_model(fields)
        return dict(zip(fields, native, strict=True))

    def _plot_field(self, ds, field, field_stats, time):
        """Plot one field's statistics and write the data beside the plot"""
        values = {
            stat: ds[var_name].values.astype(float)
            for stat, var_name in field_stats.items()
        }
        prefix = f'global_stats_{field}'
        simulation_name = self.config.get('ocean_analysis', 'simulation_name')

        plot_global_stats(
            time=time,
            stats=values,
            field_name=_axis_label(ds, field, field_stats),
            out_filename=self.work_path(f'{prefix}.png'),
            x_label='Simulation years',
            title=f'{simulation_name}: global {field}',
        )
        self.add_produced_file(f'{prefix}.png')

        self._write_plot_data(
            ds=ds,
            field=field,
            field_stats=field_stats,
            time=time,
            values=values,
            out_filename=self.work_path(f'{prefix}.nc'),
        )
        self.add_produced_file(f'{prefix}.nc')

        self.logger.info(
            f'  {field}: plotted the {", ".join(field_stats)} in {prefix}.png'
        )

    def _write_plot_data(
        self, ds, field, field_stats, time, values, out_filename
    ):
        """Write exactly what was plotted, so it can be checked again"""
        units = _units(ds, field_stats)
        ds_out = xr.Dataset()
        ds_out['simulationYears'] = xr.DataArray(
            time,
            dims=('Time',),
            attrs={
                'long_name': 'simulation year, from the calendar date',
                'units': 'years',
            },
        )
        ds_out['Time'] = ds['Time']
        for stat, var_name in field_stats.items():
            ds_out[stat] = xr.DataArray(
                values[stat],
                dims=('Time',),
                attrs={
                    'long_name': f'{STAT_DESCRIPTIONS[stat]} of {field}',
                    'units': units,
                    'omega_name': var_name,
                },
            )
        ds_out.attrs = {
            'field': field,
            'statistics': ', '.join(field_stats),
            'simulation_name': self.config.get(
                'ocean_analysis', 'simulation_name'
            ),
            'start_year': self.start_year,
            'end_year': self.end_year,
            'time_mean_period': (
                'none; these are snapshots'
                if self.time_mean_period is None
                else self.time_mean_period
            ),
            'source_files': ', '.join(self.input_filenames),
        }
        ds_out.to_netcdf(out_filename)


def _axis_label(ds, field, field_stats):
    """Label the vertical axes with the field and its units, if it has any"""
    units = _units(ds, field_stats)
    if units:
        return f'{field} ({units})'
    return field


def _units(ds, field_stats):
    """Get the units the statistics of a field were written with"""
    for var_name in field_stats.values():
        units = ds[var_name].attrs.get('units', '')
        if units:
            return str(units)
    return ''
