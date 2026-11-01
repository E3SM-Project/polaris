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
    """

    def __init__(self, component, subdir, case):
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
        self, ds, row, stem, title, ylabel, scale, period, start
    ):
        """Plot the ocean's and glc's columns of one row and their sum"""
        values = scale * ds.budget.sel(row=row)
        time = np.arange(ds.sizes['Time'])
        lines = [
            Series(time, values.sel(component=component).values, label)
            for component, label in [
                ('ocn', 'ocean'),
                ('glc', 'glc'),
                ('*SUM*', 'sum'),
            ]
        ]
        plot = f'{stem}.png'
        data = f'{stem}.nc'
        plot_time_series(
            lines,
            plot,
            ylabel=ylabel,
            xlabel=f'{period} budgets, in order',
            title=f'{title}, {period}',
        )
        ds_data = xr.Dataset()
        ds_data[row] = values
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
        dates = [str(date) for date in ds.date.values]
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


def _index_with_start(dates, start):
    """The index of the budget whose period contains the start, the first
    to end after it, or None"""
    if start is None:
        return None
    later = [index for index, date in enumerate(dates) if date > start]
    return later[0] if later else None
