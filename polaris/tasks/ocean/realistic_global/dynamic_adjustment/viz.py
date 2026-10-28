"""
Plot the global-statistics time series of a dynamic-adjustment sequence.

The per-stage summary in ``dynamic_adjustment_stats.csv`` reduces each stage to
one row, which is enough to say whether a check passed but not enough to say
*why*.  A quantity that ends a stage where it started may have been flat
throughout or may have spiked and recovered, and those call for different
changes to the schedule.  This step plots the underlying series so that the
shape is visible.

The stages are drawn on one continuous axis with their boundaries marked and
their damping coefficients labelled, because the question being asked is almost
always how a quantity responded to the damping coming off.

A second figure asks how far the adjustment moved the ocean away from its
initial condition: volume-weighted histograms of the change in temperature
and salinity from the initial state to the end of the last stage.
"""

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.mpas.time import duration_to_seconds
from polaris.ocean.model.time import get_time_since_start
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    cfl_estimate_series,
    min_edge_length_of_mesh,
    open_stage_stats,
    stage_stats_path,
)

FIGURE_FILENAME = 'dynamic_adjustment_stats.png'
TRACER_CHANGE_FILENAME = 'dynamic_adjustment_tracer_change.png'

# What each model's temperature and salinity are, for the axis labels of the
# tracer-change figure: each model is plotted in its own convention.
_TRACER_LABELS = {
    'mpas-ocean': {
        'temperature': ('potential temperature', r'$^\circ$C'),
        'salinity': ('salinity', 'PSU'),
    },
    'omega': {
        'temperature': ('conservative temperature', r'$^\circ$C'),
        'salinity': ('absolute salinity', r'g kg$^{-1}$'),
    },
}

# Values this large in magnitude are fill values in an inactive layer, not
# tracer values.
_FILL_THRESHOLD = 1.0e20


@dataclass(frozen=True)
class Panel:
    """
    One panel of the figure.

    Attributes
    ----------
    title : str
        The panel title.

    ylabel : str
        The y-axis label.

    series : list
        ``(variable, label)`` pairs to draw, in MPAS-Ocean naming.  A label of
        ``''`` draws an unlabelled line and no legend.

    log : bool
        Whether the y axis is logarithmic.  Used where the quantity spans
        orders of magnitude, which kinetic energy does during a spin-up.

    anomaly : bool
        Whether to plot the change from the first sample rather than the value.
        A volume-weighted mean tracer moves by a tiny fraction of its own
        magnitude, so the change is invisible on an absolute axis.
    """

    title: str
    ylabel: str
    series: List[Tuple[str, str]] = field(default_factory=list)
    log: bool = False
    anomaly: bool = False


# The panels, in the order they are drawn.  Kinetic energy comes first: it is
# what the adjustment is judged on.  A panel whose series are all missing --
# Omega reports no CFL number or volume-weighted sums -- is dropped, and the
# grid closes up around it.
PANELS: Tuple[Panel, ...] = (
    Panel(
        'cell kinetic energy',
        r'm$^2$ s$^{-2}$',
        [('kineticEnergyCellMax', 'max'), ('kineticEnergyCellAvg', 'mean')],
        log=True,
    ),
    Panel(
        'domain-integrated kinetic energy',
        r'm$^5$ s$^{-2}$',
        [('kineticEnergyCellSum', '')],
        log=True,
    ),
    Panel(
        'maximum normal velocity',
        r'm s$^{-1}$',
        [('normalVelocityMax', '')],
    ),
    # Omega reports no CFL number, so for Omega the panel shows the
    # conservative estimate from its normal-velocity extrema instead, labelled
    # as the upper bound it is
    Panel(
        'CFL number',
        '',
        [
            ('CFLNumberGlobal', ''),
            ('CFLNumberEstimate', 'upper-bound estimate'),
        ],
    ),
    Panel(
        'temperature extremes',
        r'$^\circ$C',
        [('temperatureMax', 'max'), ('temperatureMin', 'min')],
    ),
    Panel(
        'mean temperature change',
        r'$^\circ$C',
        [('temperatureAvg', '')],
        anomaly=True,
    ),
    Panel(
        'salinity extremes',
        'PSU',
        [('salinityMax', 'max'), ('salinityMin', 'min')],
    ),
    Panel(
        'mean salinity change',
        'PSU',
        [('salinityAvg', '')],
        anomaly=True,
    ),
    Panel(
        'minimum layer thickness',
        'm',
        [('layerThicknessMin', '')],
    ),
)


class VizDynamicAdjustmentStep(Step):
    """
    A step that plots the global-statistics time series of a completed
    dynamic-adjustment sequence.

    It reads the same statistics files the ``summary`` step reduces, so the
    figure and the summary describe the same run.  Like that step, it opens
    them by path rather than declaring them as inputs, so a stage that wrote no
    statistics is skipped rather than failing the step -- a partial picture of
    a run that went wrong is more use than none.  Also like that step, it
    declares each stage's ``output.nc`` as an input, which is what makes a
    parallel run wait for the stages before plotting.

    The step belongs to the standalone ``dynamic_adjustment`` task.  If the
    stages are later reused as shared steps by a longer spin-up workflow, this
    should not come with them: it describes a completed adjustment, which is
    not what a workflow consuming the relaxed restart is asking about.

    Attributes
    ----------
    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.

    min_res : float or None
        The mesh minimum resolution in km, used for a per-kilometer Omega
        timestep in the CFL estimate.

    mesh_filename : str or None
        The local name of the horizontal mesh, if one was given.

    init_filename : str or None
        The local name of the initial state, if one was given.
    """

    def __init__(
        self,
        component,
        subdir,
        stages,
        min_res=None,
        mesh_target=None,
        init_target=None,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stages : list of ForwardStage
            The stages of the adjustment, in schedule order.  Their start times
            are what place the stages on a common axis, and their damping is
            what the stage labels report.

        min_res : float, optional
            The mesh minimum resolution in km, used for a per-kilometer Omega
            timestep in the CFL estimate.

        mesh_target : str, optional
            The horizontal mesh, relative to the base work directory.  Its
            cell areas weight the tracer-change histograms, and its smallest
            edge sets Omega's CFL estimate.  It is linked as ``mesh.nc``.

        init_target : str, optional
            The initial state the first stage starts from, relative to the base
            work directory.  The tracer changes are measured from it.  It is
            linked as ``init.nc``.
        """
        super().__init__(component=component, name='viz', subdir=subdir)
        self.stages = list(stages)
        self.min_res = min_res
        for stage in self.stages:
            self.add_input_file(
                filename=f'output_{stage.name}.nc',
                target=f'../{stage.name}/output.nc',
            )
        self.mesh_filename = None
        if mesh_target is not None:
            self.add_input_file(
                filename='mesh.nc', work_dir_target=mesh_target
            )
            self.mesh_filename = 'mesh.nc'
        self.init_filename = None
        if init_target is not None:
            self.add_input_file(
                filename='init.nc', work_dir_target=init_target
            )
            self.init_filename = 'init.nc'

    def run(self):
        """
        Read each stage's statistics and plot them as one series, then plot
        how far the adjustment moved temperature and salinity.
        """
        super().run()
        model = self.config.get('ocean', 'model')

        self._plot_stats(model)
        self._plot_tracer_change(model)

    def _plot_stats(self, model):
        """Plot the global-statistics series of every stage."""
        logger = self.logger
        stage_data = self._read_stages(model)
        if not stage_data:
            logger.info(
                'No global statistics were found for any stage; there is '
                'nothing to plot.'
            )
            return

        available = {variable for _, data in stage_data for variable in data}
        panels = [
            panel
            for panel in PANELS
            if any(variable in available for variable, _ in panel.series)
        ]
        if not panels:
            logger.info(
                'The statistics hold none of the plotted variables; there is '
                'nothing to plot.'
            )
            return

        _plot(panels, stage_data, self.stages, FIGURE_FILENAME)
        logger.info(f'Wrote {FIGURE_FILENAME}')

    def _plot_tracer_change(self, model):
        """
        Plot volume-weighted histograms of the change in temperature and
        salinity from the initial state to the end of the last stage.
        """
        logger = self.logger
        if self.init_filename is None or self.mesh_filename is None:
            logger.info(
                'No initial state or mesh was linked; skipping the '
                'tracer-change histograms.'
            )
            return
        if not self.stages:
            return
        final_filename = f'output_{self.stages[-1].name}.nc'
        changes = tracer_changes(
            self.component,
            self.config,
            init_filename=self.init_filename,
            final_filename=final_filename,
            mesh_filename=self.mesh_filename,
        )
        for name, change in changes.items():
            logger.info(
                f'{name} change from the initial state to the end of '
                f'{self.stages[-1].name!r}: volume-weighted mean '
                f'{change.mean:.3g}, RMS {change.rms:.3g}, 99% of the volume '
                f'within {change.p99:.3g}, largest {change.max_abs:.3g}'
            )
        plot_tracer_changes(
            changes,
            model,
            self.stages[-1].name,
            TRACER_CHANGE_FILENAME,
        )
        logger.info(f'Wrote {TRACER_CHANGE_FILENAME}')

    def _read_stages(self, model):
        """
        ``(stage, {variable: (days, values)})`` for each stage that wrote
        statistics, with the days measured from the start of the first stage so
        the stages share one axis.
        """
        min_edge_length = None
        if (
            model == 'omega'
            and self.mesh_filename is not None
            and self.min_res is not None
        ):
            min_edge_length = min_edge_length_of_mesh(
                self.component, self.config, self.mesh_filename
            )
        origin = self.stages[0].start_time if self.stages else None
        stage_data = []
        for stage in self.stages:
            path = stage_stats_path(stage, model)
            if not os.path.exists(path):
                self.logger.info(
                    f'Stage {stage.name!r} wrote no statistics; skipping it.'
                )
                continue
            ds = open_stage_stats(self.component, path, self.config)
            with ds:
                offset = _days_between(origin, stage.start_time)
                try:
                    days = get_time_since_start(ds, units='days')
                except ValueError:
                    # nothing to put the samples on an axis with; a partial
                    # figure is still worth more than no figure
                    self.logger.info(
                        f'Stage {stage.name!r} statistics carry no time '
                        f'variable; skipping it.'
                    )
                    continue
                days = np.asarray(days, dtype=float)
                # the file's own origin is whatever the model counted from,
                # which a restart may or may not reset, so anchor on the
                # schedule instead
                days = offset + (days - days[0])
                data = {
                    variable: (days, ds[variable].values.astype(float))
                    for panel in PANELS
                    for variable, _ in panel.series
                    if variable in ds
                }
                if min_edge_length is not None:
                    estimate = cfl_estimate_series(
                        ds, stage, self.min_res, min_edge_length
                    )
                    if estimate is not None:
                        data['CFLNumberEstimate'] = (days, estimate)
            stage_data.append((stage, data))
        return stage_data


@dataclass(frozen=True)
class TracerChange:
    """
    The change in one tracer over the adjustment: a volume-weighted histogram
    and the numbers that summarize it.

    Attributes
    ----------
    density : numpy.ndarray
        The volume-weighted probability density in each bin, per unit of the
        tracer.

    edges : numpy.ndarray
        The bin edges, symmetric about zero.

    mean : float
        The volume-weighted mean change.

    rms : float
        The volume-weighted root-mean-square change.

    p99 : float
        The magnitude of change that 99% of the ocean volume stays within.

    max_abs : float
        The largest magnitude of change anywhere.
    """

    density: np.ndarray
    edges: np.ndarray
    mean: float
    rms: float
    p99: float
    max_abs: float


def tracer_changes(
    component: Any,
    config: Any,
    init_filename: str,
    final_filename: str,
    mesh_filename: str,
    bin_count: int = 201,
) -> Dict[str, TracerChange]:
    """
    The change in temperature and salinity from an initial state to the last
    record of a stage's output, cell by cell and layer by layer, weighted by
    the initial volume of each cell.

    Each model's tracers are compared in that model's own convention.  Only
    active layers count: those with a positive initial thickness and finite,
    unfilled values at both ends.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component, which opens the files with MPAS-Ocean names.

    config : polaris.config.PolarisConfigParser
        The config, which says which model wrote the files.

    init_filename : str
        The initial state.

    final_filename : str
        The output of the last stage; its last record is the end state.

    mesh_filename : str
        The horizontal mesh, whose cell areas weight the histograms.

    bin_count : int, optional
        The number of histogram bins.

    Returns
    -------
    dict
        A :py:class:`TracerChange` for ``temperature`` and for ``salinity``.
    """
    with component.open_model_dataset(mesh_filename, config) as ds_mesh:
        area = np.asarray(ds_mesh['areaCell'].values, dtype=float)
    with component.open_model_dataset(init_filename, config) as ds_init:
        thickness = _record(ds_init['layerThickness'], 0)
    active = np.isfinite(thickness) & (thickness > 0.0)
    weights = area[:, np.newaxis] * np.where(active, thickness, 0.0)
    del thickness

    # one record per chunk, so that only the last record of what may be a
    # long output file is read, and nothing Omega's layer thickness would be
    # derived from is computed
    time_dim = _time_dim(final_filename)
    chunks = {} if time_dim is None else {time_dim: 1}

    changes = {}
    for name in ('temperature', 'salinity'):
        with component.open_model_dataset(init_filename, config) as ds_init:
            initial = _record(ds_init[name], 0)
        with component.open_model_dataset(
            final_filename, config, chunks=chunks
        ) as ds_final:
            final = _record(ds_final[name], -1)
        changes[name] = _tracer_change(
            initial, final, weights, active, bin_count
        )
        del initial, final
    return changes


def plot_tracer_changes(
    changes: Dict[str, TracerChange],
    model: str,
    last_stage_name: str,
    filename: str,
) -> None:
    """
    Plot the volume-weighted histograms of tracer change side by side.

    The density axis is logarithmic, because the question is how large the
    rare changes are as much as how small the typical one is.

    Parameters
    ----------
    changes : dict
        A :py:class:`TracerChange` for each tracer, as from
        :py:func:`tracer_changes`.

    model : str
        The ocean model, which says what the tracers are called.

    last_stage_name : str
        The stage whose end state the changes are measured to.

    filename : str
        The figure to write.
    """
    labels = _TRACER_LABELS.get(model, _TRACER_LABELS['mpas-ocean'])
    figure, axes = plt.subplots(
        1, len(changes), figsize=(6.0 * len(changes), 3.8), squeeze=False
    )
    for axis, (name, change) in zip(axes[0], changes.items(), strict=False):
        long_name, units = labels[name]
        axis.stairs(change.density, change.edges, linewidth=1.2)
        axis.set_yscale('log')
        axis.axvline(0.0, color='0.7', linewidth=0.8, linestyle='--')
        axis.set_title(long_name, fontsize=10)
        axis.set_xlabel(f'change ({units})', fontsize=9)
        axis.set_ylabel(f'volume-weighted PDF (per {units})', fontsize=9)
        axis.tick_params(labelsize=8)
        summary = (
            f'mean {change.mean:.2g}\n'
            f'RMS {change.rms:.2g}\n'
            f'99% of volume within $\\pm${change.p99:.2g}\n'
            f'largest {change.max_abs:.2g}'
        )
        axis.text(
            0.02,
            0.97,
            summary,
            transform=axis.transAxes,
            ha='left',
            va='top',
            fontsize=8,
            bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.8},
        )
    figure.suptitle(
        f'dynamic adjustment: change from the initial state to the end of '
        f'{last_stage_name}',
        fontsize=11,
    )
    figure.tight_layout()
    figure.savefig(filename, dpi=150)
    plt.close(figure)


def _record(data_array: Any, index: int) -> np.ndarray:
    """One time record of a field, or the field if it has no time."""
    if 'Time' in data_array.dims:
        data_array = data_array.isel(Time=index)
    return np.asarray(data_array.values, dtype=float)


def _time_dim(filename: str) -> Optional[str]:
    """The name a file gives its time dimension, before any renaming."""
    with xr.open_dataset(filename, decode_times=False) as ds:
        for name in ('Time', 'time'):
            if name in ds.dims:
                return name
    return None


def _tracer_change(
    initial: np.ndarray,
    final: np.ndarray,
    weights: np.ndarray,
    active: np.ndarray,
    bin_count: int,
) -> TracerChange:
    """The volume-weighted histogram and summary of one tracer's change."""
    valid = (
        active
        & np.isfinite(initial)
        & np.isfinite(final)
        & (np.abs(initial) < _FILL_THRESHOLD)
        & (np.abs(final) < _FILL_THRESHOLD)
    )
    change = (final - initial)[valid]
    weight = weights[valid]
    total = float(weight.sum())
    if change.size == 0 or total <= 0.0:
        raise ValueError(
            'No active cells hold the tracer at both ends of the adjustment.'
        )
    magnitude = np.abs(change)
    max_abs = float(magnitude.max())
    limit = max_abs if max_abs > 0.0 else 1.0
    density, edges = np.histogram(
        change,
        bins=np.linspace(-limit, limit, bin_count + 1),
        weights=weight,
        density=True,
    )
    return TracerChange(
        density=density,
        edges=edges,
        mean=float(np.sum(weight * change) / total),
        rms=float(np.sqrt(np.sum(weight * change**2) / total)),
        p99=_weighted_quantile(magnitude, weight, 0.99, limit),
        max_abs=max_abs,
    )


def _weighted_quantile(
    values: np.ndarray, weights: np.ndarray, quantile: float, limit: float
) -> float:
    """
    A weighted quantile of non-negative values, from a fine histogram rather
    than a sort, which would cost far more on a large mesh.  It is accurate to
    one ten-thousandth of ``limit``.
    """
    counts, edges = np.histogram(
        values, bins=10000, range=(0.0, limit), weights=weights
    )
    cumulative = np.cumsum(counts) / counts.sum()
    index = int(np.searchsorted(cumulative, quantile))
    return float(edges[min(index + 1, len(edges) - 1)])


def _days_between(origin: Optional[str], when: str) -> float:
    """Days from the chain origin to a stage's start time."""
    if origin is None:
        return 0.0
    time_format = '%Y-%m-%d_%H:%M:%S'
    start = datetime.datetime.strptime(origin, time_format)
    stop = datetime.datetime.strptime(when, time_format)
    return (stop - start).total_seconds() / 86400.0


def _plot(panels, stage_data, stages, filename) -> None:
    """Draw the panels and save the figure."""
    columns = 2 if len(panels) > 1 else 1
    rows = int(np.ceil(len(panels) / columns))
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(6.0 * columns, 2.6 * rows),
        squeeze=False,
        sharex=True,
    )
    flat_axes = [axis for row in axes for axis in row]

    boundaries = _stage_boundaries(stages)
    for axis, panel in zip(flat_axes, panels, strict=False):
        _draw_panel(axis, panel, stage_data, boundaries)
    for axis in flat_axes[len(panels) :]:
        axis.set_visible(False)

    for axis in axes[-1]:
        if axis.get_visible():
            axis.set_xlabel('days')

    _label_stages(flat_axes[0], stages)
    # only a strip for the suptitle: the stage labels are annotations on the
    # top-left axes, so tight_layout already counts them in its bounding box
    # and makes room for however many rows they were stacked onto
    top = 1.0 - 0.3 / figure.get_figheight()
    figure.tight_layout(rect=(0.0, 0.0, 1.0, top))
    figure.suptitle('dynamic adjustment: global statistics', y=0.995)
    figure.savefig(filename, dpi=150)
    plt.close(figure)


def _draw_panel(axis: Any, panel: Panel, stage_data, boundaries) -> None:
    """Draw one panel, joining every stage into a single line per variable."""
    labelled = False
    for variable, label in panel.series:
        days: List[float] = []
        values: List[float] = []
        for _, data in stage_data:
            if variable not in data:
                continue
            stage_days, stage_values = data[variable]
            days.extend(stage_days.tolist())
            values.extend(stage_values.tolist())
        if not days:
            continue
        array = np.array(values, dtype=float)
        if panel.anomaly:
            array = array - array[0]
        axis.plot(days, array, label=label or None, linewidth=1.2)
        labelled = labelled or bool(label)

    for boundary in boundaries:
        axis.axvline(boundary, color='0.7', linewidth=0.8, linestyle='--')

    if panel.log:
        axis.set_yscale('log')
    axis.set_title(panel.title, fontsize=10)
    axis.set_ylabel(panel.ylabel, fontsize=9)
    axis.tick_params(labelsize=8)
    if labelled:
        axis.legend(fontsize=8, loc='best')


def _stage_boundaries(stages) -> List[float]:
    """The day of each stage start after the first, for the divider lines."""
    if not stages:
        return []
    origin = stages[0].start_time
    return [_days_between(origin, stage.start_time) for stage in stages[1:]]


# The stage labels are drawn rotated, so a label's horizontal footprint is one
# line height and its vertical one is its length.  These are rough point sizes
# at LABEL_FONTSIZE; a label is measured as slightly wider than the digits it
# usually holds, so that a letter-heavy one like 'sim undamped' still fits.
LABEL_FONTSIZE = 7
_LINE_HEIGHT_PT = 1.3 * LABEL_FONTSIZE + 2.0
_CHARACTER_WIDTH_PT = 0.62 * LABEL_FONTSIZE
# Labels are stacked in points from the top of the axes, so their spacing does
# not depend on how tall tight_layout ends up making the panel.  Only the
# horizontal test needs a width, and an axes about 5.4 in wide is what a
# 6.0 in cell leaves; getting this wrong costs a row of headroom, not a
# collision.
_AXES_WIDTH_PT = 5.4 * 72.0
# enough to clear the panel's own title, which sits just above the axes
_TITLE_CLEARANCE_PT = 20.0


def _label_stages(axis: Any, stages) -> int:
    """
    Name each stage above the first panel, with its damping.

    The damping is what the labels are for: the usual question of one of these
    figures is how a quantity responded to the damping coming off.

    Labels read upwards, because a stage can be a small fraction of the axis:
    ``u-oi6to18-lr12p5`` opens with two 6-hour stages on a 30-day axis, and
    horizontal labels there overprinted into an unreadable smear.  Rotating
    cuts a label's width to one line height, and where even that does not fit
    -- those two stages are 0.25 days apart, narrower than any legible label
    -- the label climbs a row rather than overlap its neighbour.  Schedules
    whose stages are all comfortably wide stay on one row.

    Returns the number of rows the labels were stacked onto, which is 1 for
    every schedule but the crowded ones.
    """
    if not stages:
        return 0
    origin = stages[0].start_time
    labels = []
    for stage in stages:
        start = _days_between(origin, stage.start_time)
        middle = start + duration_to_seconds(stage.run_duration) / 172800.0
        damping = (
            'undamped' if stage.damping is None else f'{stage.damping:.0e}'
        )
        labels.append((middle, f'{_short_stage_name(stage.name)} {damping}'))

    span = _days_between(origin, stages[-1].start_time) + (
        duration_to_seconds(stages[-1].run_duration) / 86400.0
    )
    # a label's half-width in days, from one line height in points
    half_width = 0.0
    if span > 0.0:
        half_width = 0.5 * _LINE_HEIGHT_PT * span / _AXES_WIDTH_PT

    # each label goes on the lowest row where it clears the last one placed
    # there, so a crowded run of short stages climbs and the rest stay put
    rows: List[int] = []
    row_free_from: List[float] = []
    for middle, _ in labels:
        row = 0
        while (
            row < len(row_free_from)
            and middle - half_width < (row_free_from[row])
        ):
            row += 1
        if row == len(row_free_from):
            row_free_from.append(0.0)
        row_free_from[row] = middle + half_width
        rows.append(row)

    # a row has to start above the tallest label on the row below it, so a
    # single long label -- 'sim undamped' -- does not push every row up
    heights = [0.0] * len(row_free_from)
    for (_, text), row in zip(labels, rows, strict=False):
        height = len(text) * _CHARACTER_WIDTH_PT
        heights[row] = max(heights[row], height)
    offsets = [_TITLE_CLEARANCE_PT]
    for row in range(1, len(heights)):
        offsets.append(offsets[row - 1] + heights[row - 1] + 4.0)

    for (middle, text), row in zip(labels, rows, strict=False):
        axis.annotate(
            text,
            xy=(middle, 1.0),
            xycoords=('data', 'axes fraction'),
            xytext=(0.0, offsets[row]),
            textcoords='offset points',
            ha='center',
            va='bottom',
            rotation=90,
            fontsize=LABEL_FONTSIZE,
            color='0.35',
        )
    return len(heights)


def _short_stage_name(name: str) -> str:
    """
    A stage name short enough to sit above a stage's span without colliding
    with its neighbours.  The schedules name their damped stages
    ``damped_adjustment_<n>``, which is far longer than the label has room for
    once the damping value is appended.
    """
    prefix = 'damped_adjustment_'
    if name.startswith(prefix):
        return f'd{name[len(prefix) :]}'
    if name == 'simulation':
        return 'sim'
    return name
