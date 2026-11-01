import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.analysis.product_step import ProductStep
from polaris.e3sm.analysis.budgets import (
    budget_time_series,
    read_budget_tables,
    read_initial_start,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    TIME_SERIES_FILENAME,
)
from polaris.viz.time_series import Series, plot_time_series

#: The exchanges checked: the budget, its row, the file's stem, the title,
#: the y label and the scale from the budget's total
EXCHANGES = [
    (
        'WATER',
        'wpolar',
        'melt_exchange',
        'Ice-shelf water exchange',
        'water flux (Gt yr$^{-1}$)',
        365.0 * 86400.0 * 1e-12,
    ),
    (
        'HEAT',
        'hpolar',
        'heat_exchange',
        'Ice-shelf heat exchange',
        'heat flux (GW)',
        1e-9,
    ),
]

#: The budget and period beside which the ocean's own monthly melt and
#: frazil are plotted
OCEAN_SERIES = ('WATER', 'monthly')

#: The local name of the run's monthly time series
OCEAN_SERIES_FILENAME = 'ocean_time_series.nc'

#: The days in each month of the 365-day calendar
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

#: The periods checked, where the case prints them: daily budgets need
#: budget_daily in user_nl_cpl, but show when within a month a residual
#: arises
PERIODS = ['daily', 'monthly', 'annual']


class CouplerConservation(ProductStep):
    """
    A step that checks that the coupler's budgets close for the water and
    heat exchanged between the ocean and MALI

    Attributes
    ----------
    log_filenames : list of str
        The local names of the coupler's logs, in the order they were written

    has_ocean_series : bool
        Whether the ocean's monthly melt and frazil, from the run's
        diagnostics, are plotted beside the monthly water budget
    """

    def __init__(self, component, subdir, case, diagnostics=None):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        case : polaris.e3sm.analysis.case.E3smCase
            The case whose coupler logs are read

        diagnostics : RunDiagnostics, optional
            The diagnostics step of the case's run, whose monthly melt and
            frazil are plotted beside the monthly water budget
        """
        super().__init__(
            component=component,
            name='conservation',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.log_filenames = []
        for path in case.find_logs('cpl'):
            filename = os.path.join('logs', os.path.basename(path))
            self.add_input_file(filename=filename, target=path)
            self.log_filenames.append(filename)
        self.has_ocean_series = diagnostics is not None
        if diagnostics is not None:
            self.add_input_file(
                filename=OCEAN_SERIES_FILENAME,
                work_dir_target=f'{diagnostics.path}/{TIME_SERIES_FILENAME}',
            )
            self.add_dependency(diagnostics)
        self.add_output_file(filename='exchange_residuals.csv')

    def run(self):
        """
        Check the budgets
        """
        tables = read_budget_tables(self.log_filenames)
        start = read_initial_start(self.log_filenames)
        if start is not None:
            self.logger.info(
                f'The run started at {start}.  The budgets containing the '
                f"start book the ocean's initial export, which glc never "
                f'receives, and are reported apart.'
            )
        ds_ocean = None
        if self.has_ocean_series:
            ds_ocean = xr.open_dataset(OCEAN_SERIES_FILENAME)
        rows = []
        for budget, row, stem, title, ylabel, scale in EXCHANGES:
            for period in PERIODS:
                found = [
                    table
                    for table in tables
                    if table.budget == budget and table.period == period
                ]
                if not found:
                    self.logger.info(f'No {period} {budget} budget yet.')
                    continue
                ds = budget_time_series(tables, budget, period)
                rows.extend(
                    self._plot_exchange(
                        ds,
                        row,
                        f'{stem}_{period}',
                        title,
                        ylabel,
                        scale,
                        period,
                        start,
                        ds_ocean if (budget, period) == OCEAN_SERIES else None,
                    )
                )
        largest: dict[tuple[str, str], float] = dict()
        with open('exchange_residuals.csv', 'w') as csv:
            csv.write(
                'budget,period,date,ocn,glc,sum,relative_residual,'
                'initial_start\n'
            )
            for budget, period, date, ocn, glc, total, initial in rows:
                relative = abs(total) / abs(ocn) if ocn != 0.0 else np.nan
                csv.write(
                    f'{budget},{period},{date},{ocn:.8g},{glc:.8g},'
                    f'{total:.8g},{relative:.3g},{initial}\n'
                )
                note = ', with the initial start' if initial else ''
                self.logger.info(
                    f'{budget} {period} {date}: ocn {ocn:.6g}, glc '
                    f'{glc:.6g}, sum {total:.3g} ({relative:.2g} of ocn)'
                    f'{note}'
                )
                if not initial:
                    key = (budget, period)
                    largest[key] = np.nanmax(
                        [largest.get(key, np.nan), relative]
                    )
        for (budget, period), relative in largest.items():
            self.logger.info(
                f'The largest relative residual of the other {budget} '
                f'{period} budgets is {relative:.2g}.'
            )

    def _plot_exchange(
        self, ds, row, stem, title, ylabel, scale, period, start, ds_ocean
    ):
        """Plot the ocean's and glc's columns of one row and their sum,
        and the ocean's own monthly melt and frazil if given"""
        values = scale * ds.budget.sel(row=row)
        dates = [str(date) for date in ds.date.values]
        time = _end_years(dates)
        lines = [
            Series(time, values.sel(component=component).values, label)
            for component, label in [
                ('ocn', 'ocean'),
                ('glc', 'glc'),
                ('*SUM*', 'sum'),
            ]
        ]
        ds_data = xr.Dataset()
        ds_data[row] = values
        if ds_ocean is not None:
            ocean = _ocean_series(ds_ocean, dates, scale)
            for name, label in [
                ('totalMeltFlux', "ocean's melt"),
                ('totalFrazilFlux', "ocean's frazil under the ice"),
                ('meltPlusFrazil', "ocean's melt + frazil"),
            ]:
                if name in ocean:
                    lines.append(
                        Series(
                            time,
                            ocean[name],
                            label,
                            linestyle='--',
                            marker='.',
                        )
                    )
                    ds_data[name] = ('Time', ocean[name])
                    ds_data[name].attrs = dict(
                        long_name=f'{label}, from its monthly means',
                        units=values.attrs.get('units', ''),
                    )
            self._log_ocean_series(dates, values, ocean)
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(
            lines,
            plot,
            ylabel=ylabel,
            xlabel='end of the period (years)',
            title=f'{title}, {period}',
            legend_outside=True,
        )
        ds_data.coords['date'] = ds.date
        write_netcdf(ds_data, data)
        self.add_product(
            plot=plot,
            data=data,
            group='conservation',
            gallery='coupler_budgets',
            title=f'{title}, {period}',
        )
        budget = str(ds.budget.attrs['long_name']).split()[0].upper()
        initial = _index_with_start(dates, start)
        return [
            (
                budget,
                period,
                date,
                float(values.sel(component='ocn').isel(Time=index)),
                float(values.sel(component='glc').isel(Time=index)),
                float(values.sel(component='*SUM*').isel(Time=index)),
                index == initial,
            )
            for index, date in enumerate(dates)
        ]

    def _log_ocean_series(self, dates, values, ocean):
        """Log the ocean's monthly melt and frazil beside its column"""
        for index, date in enumerate(dates):
            melt = ocean['totalMeltFlux'][index]
            if np.isnan(melt):
                continue
            frazil = ocean.get('totalFrazilFlux', np.zeros(len(dates)))[index]
            column = float(values.sel(component='ocn').isel(Time=index))
            self.logger.info(
                f'WATER monthly {date}: ocean melt {melt:.6g}, frazil '
                f'{frazil:.6g}, melt + frazil {melt + frazil:.6g}, ocean '
                f'column {column:.6g}'
            )


def _ocean_series(ds_ocean, dates, scale):
    """The ocean's monthly melt and frazil, scaled, at the monthly budgets
    whose months the run's diagnostics have, NaN elsewhere"""
    times = ds_ocean.time.values
    names = [
        name
        for name in ['totalMeltFlux', 'totalFrazilFlux']
        if name in ds_ocean
    ]
    ocean = {name: np.full(len(dates), np.nan) for name in names}
    for index, date in enumerate(dates):
        matches = np.nonzero(np.abs(times - _month_middle(date)) < 1e-6)[0]
        if len(matches) == 0:
            continue
        for name in names:
            ocean[name][index] = scale * float(
                ds_ocean[name].isel(Time=matches[0])
            )
    if 'totalFrazilFlux' in ocean:
        ocean['meltPlusFrazil'] = (
            ocean['totalMeltFlux'] + ocean['totalFrazilFlux']
        )
    return ocean


def _end_years(dates):
    """The end of each budget's period, in years since the start of year 1
    of the 365-day calendar"""
    years = []
    for date in dates:
        year, month, day = int(date[:4]), int(date[5:7]), int(date[8:10])
        seconds = int(date[11:16])
        days = sum(DAYS_IN_MONTH[: month - 1]) + day - 1 + seconds / 86400.0
        years.append(year - 1 + days / 365.0)
    return np.array(years)


def _month_middle(date):
    """The middle of the month a monthly budget covers, in years since the
    start of year 1, as the diagnostics' time: the budget is dated at the
    end of its month"""
    year, month = int(date[:4]), int(date[5:7])
    month -= 1
    if month == 0:
        year, month = year - 1, 12
    return year - 1 + (month - 0.5) / 12.0


def _index_with_start(dates, start):
    """The index of the budget whose period contains the start, the first
    to end after it, or None"""
    if start is None:
        return None
    later = [index for index, date in enumerate(dates) if date > start]
    return later[0] if later else None
