"""
Per-stage diagnostics for a dynamic-adjustment sequence.

Each stage of the adjustment is summarized by one row of scalars, so that the
whole sequence can be read as a table rather than by opening every stage's
output in a viewer.  This is what says whether the damping ramp and the stage
durations were chosen well: kinetic energy should be falling and flattening,
the volume-weighted mean tracers should not be moving at all, and nothing
should be approaching a blow-up.

The numbers come from each stage's global-statistics file wherever possible,
because the model has already reduced them over the whole domain at the output
cadence -- so a transient excursion in the middle of a stage is visible, which
it is not in an end-of-stage field.  Anything the configured model does not
report is computed from ``output.nc`` instead, but only where the two give the
same quantity: a maximum is a maximum however it is computed, whereas a
volume-weighted mean is not the same as an unweighted one, so volume-weighted
metrics are left blank rather than quietly replaced.

The extremes cover what a stage *did*, not what it was handed: the sample
written before the first time step is skipped.  For the first stage that sample
is the initial condition, and for every later one it is the previous stage's
final state, already covered by that stage's own check.  The tracer extremes
skip a further startup window at the beginning of the sequence, over which the
initial condition's artifacts are still mixing away; the CFL number and the
velocity and thickness extremes do not, because the opening hours are where a
time step that is too long shows itself.  The viz step plots the full series,
so the skipped values are still visible where they matter.

MPAS-Ocean and Omega do not report the same statistics.  Omega's
``GlobalStats`` covers temperature, salinity, layer thickness and normal
velocity; it has no kinetic energy, no CFL number and no volume-weighted sums.
A blank column therefore means "this model does not report it", not "something
went wrong".
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from polaris.mpas.time import duration_to_seconds
from polaris.ocean.model.time import get_days_since_start
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage

# The global-statistics filename each model writes, as configured by
# ``forward.yaml``.  Omega treats its ``Filename`` as a prefix and appends the
# reduction period, with no ``.nc`` extension.
STATS_FILENAMES = {
    'mpas-ocean': 'global_stats.nc',
    'omega': 'global_stats_1DayTimeStats',
}


@dataclass(frozen=True)
class Metric:
    """
    One column of the per-stage summary.

    Attributes
    ----------
    name : str
        The column name.

    stats_var : str
        The variable to read from the global-statistics file, in MPAS-Ocean
        naming.  Omega's names are mapped to these by ``open_model_dataset``.

    reduction : str
        How to reduce the statistic's time series over the stage: ``'max'`` and
        ``'min'`` give the extreme reached at any point during the stage, which
        is what catches an excursion that recovers before the stage ends;
        ``'last'`` gives the end-of-stage value, which is what a settling trend
        is measured on.

    units : str
        The units of the metric, for the log table and the file header.

    output_var : str or None
        The ``output.nc`` field to fall back to when the statistic is not
        reported by the configured model, or ``None`` when there is no
        equivalent that means the same thing.

    startup_window : bool
        Whether the metric skips the sequence's startup window as well as the
        stage's first sample.  Set for the tracer extremes, which the WOA23
        source artifacts distort until the model has mixed them away, and not
        for the CFL number or the velocity and thickness extremes, where the
        opening hours are exactly what wants watching.
    """

    name: str
    stats_var: str
    reduction: str
    units: str
    output_var: Optional[str] = None
    startup_window: bool = False


# The columns of the summary, in the order they are written.  Kinetic energy
# comes first because it is the metric the adjustment is judged on.
METRICS: Tuple[Metric, ...] = (
    Metric(
        'kinetic_energy_max',
        'kineticEnergyCellMax',
        'last',
        'm^2/s^2',
        output_var='kineticEnergyCell',
    ),
    Metric(
        'kinetic_energy_max_in_stage',
        'kineticEnergyCellMax',
        'max',
        'm^2/s^2',
    ),
    Metric('kinetic_energy_mean', 'kineticEnergyCellAvg', 'last', 'm^2/s^2'),
    Metric('kinetic_energy_total', 'kineticEnergyCellSum', 'last', 'm^5/s^2'),
    Metric('ocean_volume', 'volumeCellGlobal', 'last', 'm^3'),
    Metric('cfl_max_in_stage', 'CFLNumberGlobal', 'max', '1'),
    Metric(
        'temperature_max_in_stage',
        'temperatureMax',
        'max',
        'degC',
        output_var='temperature',
        startup_window=True,
    ),
    Metric(
        'temperature_min_in_stage',
        'temperatureMin',
        'min',
        'degC',
        output_var='temperature',
        startup_window=True,
    ),
    Metric('temperature_mean', 'temperatureAvg', 'last', 'degC'),
    Metric(
        'salinity_max_in_stage',
        'salinityMax',
        'max',
        'PSU',
        output_var='salinity',
        startup_window=True,
    ),
    Metric(
        'salinity_min_in_stage',
        'salinityMin',
        'min',
        'PSU',
        output_var='salinity',
        startup_window=True,
    ),
    Metric('salinity_mean', 'salinityAvg', 'last', 'PSU'),
    Metric(
        'layer_thickness_min_in_stage',
        'layerThicknessMin',
        'min',
        'm',
        output_var='layerThickness',
    ),
    Metric(
        'normal_velocity_max_in_stage',
        'normalVelocityMax',
        'max',
        'm/s',
        output_var='normalVelocity',
    ),
)

# Mean-change columns, computed from the change in a volume-weighted mean
# across the stage rather than read directly.  These are a conservation check,
# not a settling one: these runs are forced by wind alone, with no surface
# fluxes, so the volume-weighted mean tracers are conserved exactly and the
# expected value of every one of these columns is zero.  A value that is not
# machine noise means the model lost or gained tracer, which says nothing about
# whether the fast waves have been damped out.
MEAN_CHANGES: Tuple[Tuple[str, str], ...] = (
    ('mean_temperature_change_per_day', 'temperatureAvg'),
    ('mean_salinity_change_per_day', 'salinityAvg'),
)

# The units of each mean-change column, keyed by column name.
MEAN_CHANGE_UNITS = {
    'mean_temperature_change_per_day': 'degC/day',
    'mean_salinity_change_per_day': 'PSU/day',
}


def column_names() -> List[str]:
    """
    The summary columns, in order, after the stage name.

    Returns
    -------
    list of str
        The metric and mean-change column names.
    """
    return [metric.name for metric in METRICS] + [
        name for name, _ in MEAN_CHANGES
    ]


def column_units() -> Dict[str, str]:
    """
    The units of each summary column.

    Returns
    -------
    dict
        A map from column name to units.
    """
    units = {metric.name: metric.units for metric in METRICS}
    units.update(MEAN_CHANGE_UNITS)
    return units


def collect_stage_diagnostics(
    component: Any,
    config: Any,
    stage: ForwardStage,
    stats_filename: Optional[str],
    output_filename: str,
    logger: Any,
    exclude_days: float = 0.0,
) -> Dict[str, Optional[float]]:
    """
    Summarize one stage as a row of scalars.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component, used to open datasets with Omega's variable names
        mapped to the MPAS-Ocean ones these metrics are written in.

    config : polaris.config.PolarisConfigParser
        The step's config.

    stage : polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage
        The stage being summarized; its ``run_duration`` turns a change across
        the stage into a per-day rate.

    stats_filename : str or None
        The stage's global-statistics file, or ``None`` when it is not
        available, in which case every metric falls back to ``output.nc``.

    output_filename : str
        The stage's ``output.nc``.

    logger : logging.Logger
        A logger for reporting which source each metric came from.

    exclude_days : float
        How much of this stage, in days, lies inside the sequence's startup
        window, as returned by
        :py:func:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule.excluded_days_in_stage`.
        Only the tracer extremes honor it.

    Returns
    -------
    dict
        A map from column name to value, with ``None`` where the configured
        model does not report the metric.
    """
    row: Dict[str, Optional[float]] = {}

    ds_stats = None
    if stats_filename is not None and os.path.exists(stats_filename):
        ds_stats = component.open_model_dataset(stats_filename, config)

    first_index = None
    first_after_window = None
    if ds_stats is not None:
        first_index = first_judged_index(ds_stats)
        first_after_window = first_judged_index(ds_stats, exclude_days)

    try:
        from_stats = []
        from_output = []
        missing = []
        for metric in METRICS:
            value = None
            if ds_stats is not None and metric.stats_var in ds_stats:
                if metric.startup_window:
                    start = first_after_window
                else:
                    start = first_index
                value = _reduce(
                    ds_stats[metric.stats_var], metric.reduction, start
                )
                from_stats.append(metric.name)
            elif metric.output_var is not None:
                value = _from_output(
                    component, config, output_filename, metric
                )
                if value is not None:
                    from_output.append(metric.name)
            if value is None:
                missing.append(metric.name)
            row[metric.name] = value

        for name, stats_var in MEAN_CHANGES:
            row[name] = _mean_change(ds_stats, stats_var, stage)
            if row[name] is None:
                missing.append(name)

        _log_sources(logger, stage.name, from_stats, from_output, missing)
    finally:
        if ds_stats is not None:
            ds_stats.close()

    return row


def _reduce(
    data_array: Any, reduction: str, first_index: Optional[int]
) -> Optional[float]:
    """
    Reduce a statistic's time series over the samples the stage is judged on.

    ``first_index`` is where those samples begin, as returned by
    :py:func:`first_judged_index`, and ``None`` when the stage left none.  An
    end-of-stage (``'last'``) value is taken from the final sample regardless:
    it is the state the stage handed on, which exists however few samples were
    written.
    """
    if reduction == 'last':
        return float(data_array.isel(Time=-1))
    if first_index is None:
        return None
    evolved = data_array.isel(Time=slice(first_index, None))
    if reduction == 'max':
        return float(evolved.max())
    if reduction == 'min':
        return float(evolved.min())
    raise ValueError(f'Unknown reduction {reduction!r}.')


# Samples are matched to the startup window with a tolerance of about a tenth
# of a millisecond, so that a window landing on a sample time excludes that
# sample rather than depending on how the model rounded the time it wrote.
_DAY_TOLERANCE = 1.0e-9


def first_judged_index(ds: Any, exclude_days: float = 0.0) -> Optional[int]:
    """
    The index of the first sample of a stage that is judged.

    The stage's first sample is never judged: it is written before any time
    step, so for the first stage it is the initial condition and for every
    later one it is the previous stage's final state, which that stage's own
    check already covered.  Nothing therefore goes unexamined.

    ``exclude_days`` extends that to every sample within a window measured from
    the start of the stage, which is how the sequence's startup window reaches
    the stages it covers.

    Parameters
    ----------
    ds : xarray.Dataset
        The stage's global statistics.

    exclude_days : float
        The length of the window, in days into this stage.  Zero leaves only
        the first sample excluded.

    Returns
    -------
    int or None
        The index, or ``None`` when the stage wrote nothing outside the
        exclusions.
    """
    n_time = ds.sizes.get('Time', 0)
    index = 1
    if exclude_days > 0.0:
        try:
            days = np.asarray(get_days_since_start(ds), dtype=float)
            elapsed = days - days[0]
        except (ValueError, IndexError):
            elapsed = None
        if elapsed is not None:
            beyond = int(
                np.searchsorted(
                    elapsed, exclude_days + _DAY_TOLERANCE, side='right'
                )
            )
            index = max(index, beyond)
    return None if index >= n_time else index


def _from_output(
    component: Any, config: Any, output_filename: str, metric: Metric
) -> Optional[float]:
    """
    Compute a metric from ``output.nc`` when the statistic is not reported.

    Only maxima and minima are computed this way: they mean the same thing
    however they are obtained.  An end-of-stage (``'last'``) metric is taken
    from the final output time.
    """
    with component.open_model_dataset(output_filename, config) as ds:
        if metric.output_var not in ds:
            return None
        field = ds[metric.output_var]
        if metric.reduction == 'min':
            return float(field.min())
        if metric.reduction == 'max':
            return float(field.max())
        # 'last': the extreme at the final output time, which is the state
        # the next stage is handed
        return float(field.isel(Time=-1).max())


def _mean_change(
    ds_stats: Any, stats_var: str, stage: ForwardStage
) -> Optional[float]:
    """
    The change in a volume-weighted mean across the stage, per day.

    ``None`` when the statistic is not reported or the stage wrote only one
    time, in which case there is no change to measure.
    """
    if ds_stats is None or stats_var not in ds_stats:
        return None
    series = ds_stats[stats_var]
    if series.sizes.get('Time', 0) < 2:
        return None
    days = duration_to_seconds(stage.run_duration) / 86400.0
    if days <= 0.0:
        return None
    change = float(series.isel(Time=-1)) - float(series.isel(Time=0))
    return change / days


def _log_sources(
    logger: Any,
    stage_name: str,
    from_stats: List[str],
    from_output: List[str],
    missing: List[str],
) -> None:
    """Say where each metric came from, so a blank column is explicable."""
    logger.info(f'Stage {stage_name!r} diagnostics:')
    logger.info(f'  from global statistics: {len(from_stats)} metric(s)')
    if from_output:
        logger.info(f'  computed from output.nc: {", ".join(from_output)}')
    if missing:
        logger.info(
            f'  not reported by this model: {", ".join(sorted(missing))}'
        )


def write_summary(
    filename: str,
    stage_names: List[str],
    rows: List[Dict[str, Optional[float]]],
) -> None:
    """
    Write the per-stage summary as CSV, one row per stage.

    Parameters
    ----------
    filename : str
        The file to write.

    stage_names : list of str
        The stage names, in schedule order.

    rows : list of dict
        One row per stage, as returned by :py:func:`collect_stage_diagnostics`.
    """
    names = column_names()
    units = column_units()
    header = ['stage'] + [f'{name} [{units[name]}]' for name in names]
    lines = [','.join(header)]
    for stage_name, row in zip(stage_names, rows, strict=False):
        values = [
            '' if row.get(name) is None else repr(float(row[name]))  # type: ignore[arg-type]
            for name in names
        ]
        lines.append(','.join([stage_name] + values))
    with open(filename, 'w') as summary_file:
        summary_file.write('\n'.join(lines) + '\n')


def log_summary(
    logger: Any,
    stage_names: List[str],
    rows: List[Dict[str, Optional[float]]],
) -> None:
    """
    Log the summary as a table, so the trend is visible without opening a file.

    Only the columns that at least one stage reported are shown, so an Omega
    run does not print a wall of blanks.

    Parameters
    ----------
    logger : logging.Logger
        The logger to write to.

    stage_names : list of str
        The stage names, in schedule order.

    rows : list of dict
        One row per stage.
    """
    names = [
        name
        for name in column_names()
        if any(row.get(name) is not None for row in rows)
    ]
    if not names:
        logger.info('No dynamic-adjustment diagnostics were available.')
        return

    stage_width = max([len('stage')] + [len(name) for name in stage_names])
    widths = {name: max(len(name), 12) for name in names}
    header = 'stage'.ljust(stage_width) + ''.join(
        '  ' + name.rjust(widths[name]) for name in names
    )
    logger.info('Dynamic-adjustment diagnostics:')
    logger.info(f'  {header}')
    for stage_name, row in zip(stage_names, rows, strict=False):
        cells = []
        for name in names:
            value = row.get(name)
            text = '' if value is None else f'{value:.6g}'
            cells.append('  ' + text.rjust(widths[name]))
        logger.info(f'  {stage_name.ljust(stage_width)}{"".join(cells)}')


def stats_filename_for_model(model: str) -> Optional[str]:
    """
    The global-statistics filename the given model writes, or ``None`` when the
    model is not one this workflow knows about.

    Parameters
    ----------
    model : str
        The configured ocean model.

    Returns
    -------
    str or None
        The filename, without a directory.
    """
    return STATS_FILENAMES.get(model)


def stage_stats_path(stage_name: str, model: str) -> Optional[str]:
    """
    Where a stage's global-statistics file sits, relative to a sibling step's
    work directory.

    Parameters
    ----------
    stage_name : str
        The stage's name, which is also its work-directory name.

    model : str
        The configured ocean model.

    Returns
    -------
    str or None
        The path, or ``None`` when the model has no known statistics file.
    """
    filename = stats_filename_for_model(model)
    return None if filename is None else f'../{stage_name}/{filename}'


def extreme_and_day(
    ds: Any, variable: str, reduction: str, exclude_days: float = 0.0
) -> Tuple[Optional[float], Optional[float]]:
    """
    The extreme of a statistic over the part of a stage that is judged, and the
    day it occurred.

    Which samples those are is decided by :py:func:`first_judged_index`.  The
    day is measured from the start of the stage, so it does not depend on how
    the model counts across a restart.

    Parameters
    ----------
    ds : xarray.Dataset
        The stage's global statistics.

    variable : str
        The statistic to reduce, in MPAS-Ocean naming.

    reduction : {'max', 'min'}
        Which extreme to take.

    exclude_days : float
        How much of this stage lies inside the sequence's startup window, in
        days.  Passed for the tracer extremes and left at zero for the CFL
        number.

    Returns
    -------
    tuple
        The extreme and the day it occurred, or ``(None, None)`` when the
        statistic is not in the dataset or the stage left nothing to judge.
    """
    if variable not in ds:
        return None, None
    first_index = first_judged_index(ds, exclude_days)
    if first_index is None:
        return None, None
    series = ds[variable].isel(Time=slice(first_index, None))
    # np.arg* rather than the DataArray methods, whose no-argument behaviour
    # is changing to return a dict of per-dimension indices
    values = np.asarray(series.values)
    index = int(np.argmax(values) if reduction == 'max' else np.argmin(values))
    value = float(series.isel(Time=index))
    # the excluded samples were dropped, so shift back onto the full series
    index += first_index
    try:
        days = np.asarray(get_days_since_start(ds), dtype=float)
        when = float(days[index] - days[0])
    except (ValueError, IndexError):
        when = None
    return value, when
