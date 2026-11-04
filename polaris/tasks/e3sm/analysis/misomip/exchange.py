import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.analysis.product_step import ProductStep
from polaris.e3sm.analysis.calendar import month_start_days, xtime_to_days
from polaris.e3sm.analysis.runs import E3smRun
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    DAILY_EXCHANGE_FILENAME,
    SECONDS_PER_YEAR,
    TIME_SERIES_FILENAME,
)
from polaris.viz.time_series import Series, plot_time_series

#: MALI's stream of global statistics, written every time step
LANDICE_STATS_STREAM = 'globalStatsOutput'

#: The local names of the ocean's monthly series and daily exchange
OCEAN_SERIES_FILENAME = 'ocean_time_series.nc'
OCEAN_DAILY_FILENAME = 'ocean_daily_exchange.nc'

#: The scale from kg s-1 to Gt yr-1
GT_PER_YEAR = SECONDS_PER_YEAR * 1e-12

#: The coverage of a period by MALI's time steps below which its applied
#: melt is incomplete and the period is reported apart
MIN_COVERAGE = 0.999

#: The shifts, in coupling intervals, at which the daily series are also
#: compared, to confirm that MALI applies the ocean's melt over the same
#: interval
CHECKED_SHIFTS = [0, 1, 2]


class ModelExchange(ProductStep):
    """
    A step that compares the net mass flux out of the ice shelves that the
    ocean sends with the melt MALI applies, each from its own model's output

    MALI's step over each glc coupling interval applies the coupler's
    average of what the ocean sent over the same interval, so each of the
    ocean's periods is compared with the same period in MALI.

    Attributes
    ----------
    stats_filenames : list of str
        The local names of MALI's global statistics, in order

    has_daily : bool
        Whether the ocean's daily means are compared too

    interval : float
        The glc coupling interval (days)

    start : float or None
        The start of the run, in days since the start of year 1, if it was
        an initial start, or ``None``
    """

    def __init__(self, component, subdir, case, diagnostics):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        case : polaris.e3sm.analysis.case.E3smCase
            The case of the coupled run

        diagnostics : RunDiagnostics
            The diagnostics step of the case's run
        """
        super().__init__(
            component=component,
            name='model_exchange',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.add_input_file(
            filename=OCEAN_SERIES_FILENAME,
            work_dir_target=f'{diagnostics.path}/{TIME_SERIES_FILENAME}',
        )
        self.has_daily = bool(diagnostics.daily_mean_filenames)
        if self.has_daily:
            self.add_input_file(
                filename=OCEAN_DAILY_FILENAME,
                work_dir_target=f'{diagnostics.path}/'
                f'{DAILY_EXCHANGE_FILENAME}',
            )
        self.add_dependency(diagnostics)

        landice = E3smRun(case.case_dir, 'mali')
        self.stats_filenames = []
        for stream_file in landice.find_stream_files(LANDICE_STATS_STREAM):
            filename = os.path.join(
                'landice_stats', os.path.basename(stream_file.path)
            )
            self.add_input_file(filename=filename, target=stream_file.path)
            self.stats_filenames.append(filename)
        self.interval = get_coupling_interval(case, 'GLC')
        self.start = None
        if case.get_value('RUN_TYPE') == 'startup':
            self.start = (
                xtime_to_days(f'{case.get_value("RUN_STARTDATE")}_00:00:00')
                + float(case.get_value('START_TOD')) / 86400.0
            )
        self.add_output_file(filename='model_exchange.csv')

    def run(self):
        """
        Compare the fluxes
        """
        logger = self.logger
        steps = read_landice_steps(self.stats_filenames)
        periods = [('monthly', _ocean_months(OCEAN_SERIES_FILENAME))]
        if self.has_daily:
            ds_daily = xr.open_dataset(OCEAN_DAILY_FILENAME).rename(
                dayStart='periodStart', dayEnd='periodEnd'
            )
            if 'totalFluxSentToLandIce' in ds_daily:
                periods.append(('daily', ds_daily))
            else:
                logger.info(
                    "The ocean's daily means lack the fields for the flux "
                    'it sends, so only monthly fluxes are compared.'
                )
        rows = []
        for period, ds_ocean in periods:
            ds = compare_with_landice(
                ds_ocean, steps, self.interval, self.start
            )
            estimated = bool(
                ds_ocean.totalFluxSentToLandIce.attrs.get('estimated', 0)
            )
            self._plot(ds, period, estimated)
            rows.extend(_rows(ds, period))
            _log_largest(logger, ds, period, estimated)
            if period == 'daily':
                for shift in CHECKED_SHIFTS:
                    ds_shift = compare_with_landice(
                        ds_ocean,
                        steps,
                        self.interval,
                        self.start,
                        shift=shift,
                    )
                    rms = _rms(
                        ds_shift.relativeDifference.where(_kept(ds_shift))
                    )
                    logger.info(
                        f'Daily, with MALI {shift} coupling intervals '
                        f'later: RMS relative difference {rms:.3g}'
                    )
        with open('model_exchange.csv', 'w') as csv:
            csv.write(
                'period,start_day,ocean_sent,mali_applied,'
                'relative_difference,mali_coverage,initial_start\n'
            )
            for row in rows:
                csv.write(','.join(row) + '\n')

    def _plot(self, ds, period, estimated):
        """Plot the two fluxes and their relative difference"""
        years = ds.periodStart.values / 365.0
        sent_label = 'ocean, sent to MALI'
        if estimated:
            sent_label = f'{sent_label} (estimated)'
        lines = [
            Series(
                years,
                GT_PER_YEAR * ds.oceanSent.values,
                sent_label,
                marker='.',
            ),
            Series(
                years,
                GT_PER_YEAR * ds.landiceApplied.values,
                'MALI, applied',
                linestyle='--',
                marker='.',
            ),
        ]
        if 'oceanMelt' in ds:
            lines.append(
                Series(
                    years,
                    GT_PER_YEAR * ds.oceanMelt.values,
                    "ocean's melt",
                    linestyle=':',
                )
            )
        stem = f'melt_sent_and_applied_{period}'
        title = f'Melt the ocean sends and MALI applies, {period}'
        plot_time_series(
            lines,
            f'{stem}.png',
            ylabel='mass flux (Gt yr$^{-1}$)',
            xlabel='start of the period (years)',
            title=title,
            legend_outside=True,
        )
        write_netcdf(ds, f'{stem}.nc')
        self.add_product(
            plot=f'{stem}.png',
            data=f'{stem}.nc',
            group='conservation',
            gallery='model_exchange',
            title=title,
        )

        kept = _kept(ds)
        stem = f'melt_exchange_difference_{period}'
        title = (
            f'Relative difference of the melt MALI applies from what the '
            f'ocean sends, {period}'
        )
        plot_time_series(
            [
                Series(
                    years[kept.values],
                    ds.relativeDifference.values[kept.values],
                    'MALI applied less ocean sent, relative',
                    marker='.',
                )
            ],
            f'{stem}.png',
            ylabel='relative difference',
            xlabel='start of the period (years)',
            title=title,
        )
        write_netcdf(ds[['relativeDifference']], f'{stem}.nc')
        self.add_product(
            plot=f'{stem}.png',
            data=f'{stem}.nc',
            group='conservation',
            gallery='model_exchange',
            title=title,
        )


def get_coupling_interval(case, component):
    """
    Get a component's coupling interval in a case

    Parameters
    ----------
    case : polaris.e3sm.analysis.case.E3smCase
        The case

    component : str
        The component, such as ``GLC`` or ``OCN``

    Returns
    -------
    interval : float
        The coupling interval (days)
    """
    base = case.get_value('NCPL_BASE_PERIOD')
    if base != 'day':
        raise ValueError(
            f'The case couples per {base}, but only coupling per day is '
            f'supported.'
        )
    return 1.0 / float(case.get_value(f'{component}_NCPL'))


def read_landice_steps(filenames):
    """
    Read the melt MALI applied in each time step from its global statistics

    Parameters
    ----------
    filenames : list of str
        MALI's global statistics, written every time step, in order

    Returns
    -------
    steps : xarray.Dataset
        ``stepEnd`` and ``stepLength`` (days) and ``appliedMelt`` (kg s-1),
        the floating ice's basal melt MALI applied in each step, positive
        for melt, in order of the steps' ends, each step once
    """
    ends = []
    lengths = []
    melt = []
    for filename in filenames:
        with xr.open_dataset(filename, decode_times=False) as ds:
            ends.append(xtime_to_days(ds.xtime.values))
            lengths.append(ds.deltat.values / 86400.0)
            # MALI's sign is positive for accretion, in kg yr-1
            melt.append(
                -ds.totalFloatingBasalMassBal.values / SECONDS_PER_YEAR
            )
    end = np.concatenate(ends)
    # a restart writes the step it starts from again
    end, unique = np.unique(end, return_index=True)
    steps = xr.Dataset()
    steps['stepEnd'] = ('nSteps', end)
    steps['stepLength'] = ('nSteps', np.concatenate(lengths)[unique])
    steps['appliedMelt'] = ('nSteps', np.concatenate(melt)[unique])
    return steps


def compare_with_landice(ds_ocean, steps, interval, start, shift=0):
    """
    Compare the ocean's flux in each period with the melt MALI applies over
    the same period, or over it shifted later by whole coupling intervals

    Parameters
    ----------
    ds_ocean : xarray.Dataset
        ``periodStart`` and ``periodEnd`` (days since the start of year 1)
        and ``totalFluxSentToLandIce`` (kg s-1), and optionally
        ``totalMeltFlux``, along ``Time``

    steps : xarray.Dataset
        MALI's steps, from :py:func:`read_landice_steps`

    interval : float
        The glc coupling interval (days)

    start : float or None
        The start of the run, if an initial start, whose period is marked

    shift : int, optional
        The shift in coupling intervals, 0 for the period MALI applies the
        ocean's flux over

    Returns
    -------
    ds : xarray.Dataset
        The comparison along ``Time``
    """
    period_start = ds_ocean.periodStart.values
    period_end = ds_ocean.periodEnd.values
    offset = shift * interval
    applied, coverage = _mean_over_windows(
        steps, period_start + offset, period_end + offset
    )
    sent = ds_ocean.totalFluxSentToLandIce.values
    ds = xr.Dataset()
    ds['periodStart'] = ('Time', period_start)
    ds['periodEnd'] = ('Time', period_end)
    ds['oceanSent'] = ('Time', sent)
    if 'totalMeltFlux' in ds_ocean:
        ds['oceanMelt'] = ('Time', ds_ocean.totalMeltFlux.values)
    ds['landiceApplied'] = ('Time', applied)
    ds['landiceCoverage'] = ('Time', coverage)
    with np.errstate(divide='ignore', invalid='ignore'):
        ds['relativeDifference'] = (
            'Time',
            np.where(sent != 0.0, (applied - sent) / np.abs(sent), np.nan),
        )
    initial = np.zeros(len(period_start), dtype=bool)
    if start is not None:
        initial = np.logical_and(period_start <= start, start < period_end)
    ds['initialStart'] = ('Time', initial)
    attrs = dict(
        periodStart=('start of the period', 'days since 0001-01-01'),
        periodEnd=('end of the period', 'days since 0001-01-01'),
        oceanSent=(
            'net mass flux out of the ice shelves the ocean sends to MALI',
            'kg s-1',
        ),
        oceanMelt=("the ocean's total melt flux", 'kg s-1'),
        landiceApplied=(
            f'basal melt of floating ice MALI applies, {shift} coupling '
            f'intervals later',
            'kg s-1',
        ),
        landiceCoverage=(
            "fraction of the shifted period MALI's steps cover",
            '1',
        ),
        relativeDifference=(
            'MALI applied less ocean sent, relative to ocean sent',
            '1',
        ),
        initialStart=('whether the period contains the initial start', '1'),
    )
    for name, var in ds.data_vars.items():
        long_name, units = attrs[str(name)]
        var.attrs = dict(long_name=long_name, units=units)
    return ds


def _ocean_months(filename):
    """The ocean's monthly series, with the start and end of each month"""
    ds = xr.open_dataset(filename)
    if 'totalFluxSentToLandIce' not in ds:
        raise ValueError(
            f'{filename} has no totalFluxSentToLandIce, so the run is not '
            f'coupled to a land-ice model that receives melt.'
        )
    starts = []
    ends = []
    for years in ds.time.values:
        year = int(np.floor(years)) + 1
        month = int(round(12.0 * (years - (year - 1)) + 0.5))
        starts.append(month_start_days(year, month))
        ends.append(month_start_days(year, month + 1))
    ds_months = ds[['totalFluxSentToLandIce', 'totalMeltFlux']]
    ds_months['periodStart'] = ('Time', np.array(starts))
    ds_months['periodEnd'] = ('Time', np.array(ends))
    return ds_months


def _mean_over_windows(steps, window_start, window_end):
    """MALI's mean applied melt over each window, assuming a constant rate
    within each step, and the fraction of the window its steps cover"""
    end = steps.stepEnd.values
    begin = end - steps.stepLength.values
    melt = steps.appliedMelt.values
    means = np.full(len(window_start), np.nan)
    coverage = np.zeros(len(window_start))
    for index, (low, high) in enumerate(
        zip(window_start, window_end, strict=True)
    ):
        overlap = np.clip(
            np.minimum(end, high) - np.maximum(begin, low), 0.0, None
        )
        covered = overlap.sum()
        coverage[index] = covered / (high - low)
        if covered > 0.0:
            means[index] = np.sum(melt * overlap) / covered
    return means, coverage


def _kept(ds):
    """The periods compared: complete in MALI and without the initial
    start"""
    return np.logical_and(
        ds.landiceCoverage >= MIN_COVERAGE, np.logical_not(ds.initialStart)
    )


def _rms(values):
    """The root mean square, ignoring NaNs"""
    return float(np.sqrt(np.nanmean(np.square(values))))


def _rows(ds, period):
    """The rows of the CSV file for one kind of period"""
    rows = []
    for index in range(ds.sizes['Time']):
        rows.append(
            [
                period,
                f'{float(ds.periodStart[index]):.6f}',
                f'{float(ds.oceanSent[index]):.8g}',
                f'{float(ds.landiceApplied[index]):.8g}',
                f'{float(ds.relativeDifference[index]):.3g}',
                f'{float(ds.landiceCoverage[index]):.6f}',
                str(bool(ds.initialStart[index])),
            ]
        )
    return rows


def _log_largest(logger, ds, period, estimated):
    """Log the largest relative difference of the periods compared, and
    the periods reported apart"""
    kept = _kept(ds)
    note = ' (the flux sent is estimated)' if estimated else ''
    if bool(kept.any()):
        largest = float(np.nanmax(np.abs(ds.relativeDifference.where(kept))))
        logger.info(
            f'The largest {period} relative difference of the melt MALI '
            f'applies from what the ocean sends is {largest:.3g}{note}.'
        )
    else:
        logger.info(f'No {period} period is complete in MALI yet.')
    for index in np.nonzero(np.logical_not(kept.values))[0]:
        reason = (
            'contains the initial start'
            if bool(ds.initialStart[index])
            else 'is not covered by MALI'
        )
        logger.info(
            f'The {period} period starting at day '
            f'{float(ds.periodStart[index]):.2f} {reason} and is reported '
            f'apart.'
        )
