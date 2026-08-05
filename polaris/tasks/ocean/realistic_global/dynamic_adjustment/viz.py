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
"""

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from polaris import Step
from polaris.mpas.time import duration_to_seconds
from polaris.ocean.model.time import get_days_since_start
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    stage_stats_path,
)

FIGURE_FILENAME = 'dynamic_adjustment_stats.png'


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
        magnitude, so the drift is invisible on an absolute axis.
    """

    title: str
    ylabel: str
    series: List[Tuple[str, str]] = field(default_factory=list)
    log: bool = False
    anomaly: bool = False


# The panels, in the order they are drawn.  Kinetic energy comes first: it is
# what the adjustment is judged on.  A panel whose series are all missing --
# Omega reports no kinetic energy, CFL number or volume-weighted sums -- is
# dropped, and the grid closes up around it.
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
    Panel('CFL number', '', [('CFLNumberGlobal', '')]),
    Panel(
        'temperature extremes',
        r'$^\circ$C',
        [('temperatureMax', 'max'), ('temperatureMin', 'min')],
    ),
    Panel(
        'mean temperature drift',
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
        'mean salinity drift',
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

    It reads the same statistics files the ``validate`` step reduces, so the
    figure and the summary describe the same run.  Like that step, it opens
    them by path rather than declaring them as inputs, so a stage that wrote no
    statistics is skipped rather than failing the step -- a partial picture of
    a run that went wrong is more use than none.

    The step belongs to the standalone ``dynamic_adjustment`` task.  If the
    stages are later reused as shared steps by a longer spin-up workflow, this
    should not come with them: it describes a completed adjustment, which is
    not what a workflow consuming the relaxed restart is asking about.

    Attributes
    ----------
    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.
    """

    def __init__(self, component, subdir, stages):
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
        """
        super().__init__(component=component, name='viz', subdir=subdir)
        self.stages = list(stages)

    def run(self):
        """
        Read each stage's statistics and plot them as one series.
        """
        super().run()
        logger = self.logger
        model = self.config.get('ocean', 'model')

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

    def _read_stages(self, model):
        """
        ``(stage, {variable: (days, values)})`` for each stage that wrote
        statistics, with the days measured from the start of the first stage so
        the stages share one axis.
        """
        origin = self.stages[0].start_time if self.stages else None
        stage_data = []
        for stage in self.stages:
            path = stage_stats_path(stage.name, model)
            if path is None or not os.path.exists(path):
                self.logger.info(
                    f'Stage {stage.name!r} wrote no statistics; skipping it.'
                )
                continue
            ds = self.component.open_model_dataset(path, self.config)
            with ds:
                offset = _days_between(origin, stage.start_time)
                try:
                    days = get_days_since_start(ds)
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
            stage_data.append((stage, data))
        return stage_data


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
    # leave room above the top row for the stage labels and the suptitle
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    figure.suptitle('dynamic adjustment: global statistics', y=0.995)
    figure.savefig(filename, dpi=150)
    plt.close(figure)


def _draw_panel(axis: Any, panel: Panel, stage_data, boundaries) -> None:
    """Draw one panel, joining every stage into a single line per variable."""
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

    for boundary in boundaries:
        axis.axvline(boundary, color='0.7', linewidth=0.8, linestyle='--')

    if panel.log:
        axis.set_yscale('log')
    axis.set_title(panel.title, fontsize=10)
    axis.set_ylabel(panel.ylabel, fontsize=9)
    axis.tick_params(labelsize=8)
    if any(label for _, label in panel.series):
        axis.legend(fontsize=8, loc='best')


def _stage_boundaries(stages) -> List[float]:
    """The day of each stage start after the first, for the divider lines."""
    if not stages:
        return []
    origin = stages[0].start_time
    return [_days_between(origin, stage.start_time) for stage in stages[1:]]


def _label_stages(axis: Any, stages) -> None:
    """
    Name each stage above the first panel, with its damping.

    The damping is what the labels are for: the usual question of one of these
    figures is how a quantity responded to the damping coming off.
    """
    if not stages:
        return
    origin = stages[0].start_time
    for stage in stages:
        start = _days_between(origin, stage.start_time)
        middle = start + duration_to_seconds(stage.run_duration) / 172800.0
        damping = (
            'undamped' if stage.damping is None else f'{stage.damping:.0e}'
        )
        axis.annotate(
            f'{_short_stage_name(stage.name)}\n{damping}',
            # above the panel's own title, which sits just over the axes
            xy=(middle, 1.16),
            xycoords=('data', 'axes fraction'),
            ha='center',
            va='bottom',
            fontsize=7,
            color='0.35',
        )


def _short_stage_name(name: str) -> str:
    """
    A stage name short enough to sit above a stage's span without colliding
    with its neighbours.  The schedules name their damped stages
    ``damped_adjustment_<n>``, which is far wider than a stage is on the axis.
    """
    prefix = 'damped_adjustment_'
    if name.startswith(prefix):
        return f'damped {name[len(prefix) :]}'
    return name
