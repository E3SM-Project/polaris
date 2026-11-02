import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.analysis.product_step import ProductStep
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    DAILY_FILENAME,
    MONTHLY_MAPS_FILENAME,
    SECONDS_PER_YEAR,
    TIME_SERIES_FILENAME,
    add_geometry_inputs,
    isomip_mesh,
    read_initial_condition,
)
from polaris.tasks.e3sm.analysis.misomip.plots import MAPS, TIME_SERIES
from polaris.viz.planar import plot_horiz_comparison
from polaris.viz.time_series import Series, plot_time_series

#: The runs compared, in the order they are drawn
KINDS = ['standalone', 'e3sm']

#: Labels of the runs
LABELS = {'standalone': 'standalone', 'e3sm': 'E3SM'}

#: The daily global statistics compared: the variable, the file's stem,
#: the title, the y label and the scale
DAILY = [
    (
        'landIceFreshwaterFluxTotalSum',
        'daily_melt_flux',
        'Total melt flux, daily',
        'melt flux (Gt yr$^{-1}$)',
        SECONDS_PER_YEAR * 1e-12,
    ),
    (
        'temperatureAvg',
        'daily_mean_temperature',
        'Mean temperature, daily',
        r'temperature ($^\circ$C)',
        1.0,
    ),
    (
        'salinityAvg',
        'daily_mean_salinity',
        'Mean salinity, daily',
        'salinity (PSU)',
        1.0,
    ),
    (
        'kineticEnergyCellAvg',
        'daily_mean_kinetic_energy',
        'Mean kinetic energy, daily',
        'kinetic energy (m$^2$ s$^{-2}$)',
        1.0,
    ),
]


class RunComparison(ProductStep):
    """
    A step that compares E3SM's run of a MISOMIP experiment with the
    standalone run on the same inputs
    """

    def __init__(self, component, subdir, diagnostics):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        diagnostics : dict of str to RunDiagnostics
            The diagnostics steps of the E3SM and standalone runs
        """
        super().__init__(
            component=component,
            name='comparison',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        for kind in KINDS:
            step = diagnostics[kind]
            for filename in [
                TIME_SERIES_FILENAME,
                MONTHLY_MAPS_FILENAME,
                DAILY_FILENAME,
            ]:
                self.add_input_file(
                    filename=f'{kind}_{filename}',
                    work_dir_target=f'{step.path}/{filename}',
                )
            self.add_dependency(step, name=f'{kind}_diagnostics')
        add_geometry_inputs(self, diagnostics['e3sm'])

    def run(self):
        """
        Compare the runs
        """
        series = {
            kind: xr.open_dataset(f'{kind}_{TIME_SERIES_FILENAME}')
            for kind in KINDS
        }
        for _gallery, stem, title, ylabel, variables in TIME_SERIES:
            self._compare_series(series, stem, title, ylabel, variables)

        daily = {
            kind: xr.open_dataset(f'{kind}_{DAILY_FILENAME}') for kind in KINDS
        }
        for name, stem, title, ylabel, scale in DAILY:
            if all(name in daily[kind] for kind in KINDS):
                self._compare_daily(daily, name, stem, title, ylabel, scale)

        self._compare_maps()

    def _compare_series(self, series, stem, title, ylabel, variables):
        """Overlay a monthly time series of both runs"""
        lines = []
        ds_data = xr.Dataset()
        for kind in KINDS:
            for name, scale, label in variables:
                if name not in series[kind]:
                    continue
                values = scale * series[kind][name]
                ds_data[f'{kind}_{name}'] = values.rename(
                    {'Time': f'{kind}_Time'}
                )
                full_label = LABELS[kind]
                if label is not None:
                    full_label = f'{full_label}, {label}'
                lines.append(
                    Series(
                        time=series[kind].time.values,
                        values=values.values,
                        label=full_label,
                        linestyle='-' if kind == 'e3sm' else '--',
                    )
                )
        if not lines:
            return
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(lines, plot, ylabel=ylabel, title=title)
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='comparison',
            gallery='time_series',
            title=title,
        )

    def _compare_daily(self, daily, name, stem, title, ylabel, scale):
        """Overlay a daily global statistic of both runs"""
        lines = []
        ds_data = xr.Dataset()
        for kind in KINDS:
            ds = daily[kind]
            values = scale * ds[name]
            ds_data[f'{kind}_{name}'] = values.rename({'Time': f'{kind}_Time'})
            lines.append(
                Series(
                    time=ds.daysSinceStartOfSim.values,
                    values=values.values,
                    label=LABELS[kind],
                    linestyle='-' if kind == 'e3sm' else '--',
                )
            )
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(
            lines, plot, ylabel=ylabel, xlabel='time (days)', title=title
        )
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='comparison',
            gallery='daily',
            title=title,
        )

    def _compare_maps(self):
        """Map each field's mean over the months both runs have, and its
        difference"""
        maps = {
            kind: xr.open_dataset(f'{kind}_{MONTHLY_MAPS_FILENAME}')
            for kind in KINDS
        }
        common = np.intersect1d(
            np.round(maps['e3sm'].time.values, 6),
            np.round(maps['standalone'].time.values, 6),
        )
        if len(common) == 0:
            self.logger.info('The runs share no months, so no maps.')
            return
        means = dict()
        for kind in KINDS:
            times = np.round(maps[kind].time.values, 6)
            indices = np.nonzero(np.isin(times, common))[0]
            means[kind] = maps[kind].isel(Time=indices).mean(dim='Time')
        months = f'{len(common)} month{"s" if len(common) > 1 else ""}'

        ds_init = read_initial_condition()
        ds_mesh = isomip_mesh(ds_init)
        area = ds_init.areaCell
        floating = ds_init.landIceFloatingFraction > 0.0
        rows = []
        for _gallery, name, title, scale, units, cmap, under_ice in MAPS:
            if name not in means['e3sm']:
                continue
            fields = [scale * means[kind][name] for kind in KINDS]
            mask = floating if under_ice else None
            stem = f'{name}_comparison'
            plot = f'{stem}.png'
            data = f'{stem}.nc'
            plot_horiz_comparison(
                [ds_mesh, ds_mesh],
                fields,
                [LABELS[kind] for kind in KINDS],
                plot,
                cmap=cmap,
                cmap_title=units,
                field_masks=None if mask is None else [mask, mask],
                boundaries=[floating],
                suptitle=f'{title}, mean of {months}',
            )
            difference = fields[1] - fields[0]
            weights = area if mask is None else area.where(mask, 0.0)
            rms = float(
                np.sqrt((weights * difference**2).sum() / weights.sum())
            )
            valid = difference if mask is None else difference.where(mask)
            largest = float(np.abs(valid).max())
            rows.append((name, units, rms, largest))
            ds_data = xr.Dataset()
            for kind, field in zip(KINDS, fields, strict=True):
                ds_data[kind] = field
            ds_data['difference'] = difference
            write_netcdf(ds_data, data)
            self.add_product(
                plot=plot,
                data=data,
                group='comparison',
                gallery='maps',
                title=f'{title}, E3SM and standalone',
            )
        self._write_table(rows, months)

    def _write_table(self, rows, months):
        """Write the area-weighted RMS and largest difference of each map"""
        filename = 'map_differences.csv'
        with open(filename, 'w') as table:
            table.write(f'# E3SM minus standalone, mean of {months}\n')
            table.write('field,units,rms_difference,max_abs_difference\n')
            for name, units, rms, largest in rows:
                table.write(f'{name},"{units}",{rms:.6g},{largest:.6g}\n')
        for name, units, rms, largest in rows:
            self.logger.info(
                f'{name}: RMS difference {rms:.3g}, largest {largest:.3g} '
                f'({units})'
            )
