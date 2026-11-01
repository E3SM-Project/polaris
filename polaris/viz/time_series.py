from typing import NamedTuple

import numpy as np
from matplotlib.figure import Figure

from polaris.viz.style import mplstyle_context


class Series(NamedTuple):
    """
    One line of a time-series plot

    Attributes
    ----------
    time : numpy.ndarray
        The times

    values : numpy.ndarray
        The values at those times

    label : str
        The label in the legend

    color : str, optional
        The line's color, from the style's cycle by default

    linestyle : str, optional
        The line's style

    linewidth : float, optional
        The line's width, from the style by default
    """

    time: np.ndarray
    values: np.ndarray
    label: str
    color: str | None = None
    linestyle: str = '-'
    linewidth: float | None = None


def plot_time_series(
    series,
    out_filename,
    ylabel,
    xlabel='time (years)',
    title=None,
    ensemble=None,
    ensemble_label='ensemble range',
    figsize=(8.0, 4.0),
):
    """
    Plot time series as lines, optionally over an ensemble's range

    Parameters
    ----------
    series : list of polaris.viz.time_series.Series
        The lines, in the order they are drawn and listed in the legend

    out_filename : str
        The image file to write

    ylabel : str
        The label of the y axis, with units

    xlabel : str, optional
        The label of the x axis

    title : str, optional
        The title

    ensemble : list of polaris.viz.time_series.Series, optional
        Members of an ensemble, drawn as thin grey lines over the shaded
        range between their minimum and maximum at each time.  The members
        are interpolated to the times of the first member for the range.

    ensemble_label : str, optional
        The legend entry for the ensemble's range

    figsize : tuple of float, optional
        The figure's width and height in inches
    """
    with mplstyle_context():
        fig = Figure(figsize=figsize)
        ax = fig.add_subplot(111)
        if ensemble:
            time = np.asarray(ensemble[0].time)
            members = np.array(
                [
                    np.interp(time, member.time, member.values)
                    for member in ensemble
                ]
            )
            ax.fill_between(
                time,
                np.nanmin(members, axis=0),
                np.nanmax(members, axis=0),
                color='0.85',
                label=ensemble_label,
            )
            for member in ensemble:
                ax.plot(
                    member.time,
                    member.values,
                    color=member.color or '0.6',
                    linestyle=member.linestyle,
                    linewidth=member.linewidth or 0.5,
                )
        for line in series:
            kwargs = dict(
                label=line.label,
                linestyle=line.linestyle,
            )
            if line.color is not None:
                kwargs['color'] = line.color
            if line.linewidth is not None:
                kwargs['linewidth'] = line.linewidth
            ax.plot(line.time, line.values, **kwargs)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if title is not None:
            ax.set_title(title)
        if len(series) > 1 or ensemble:
            ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        fig.savefig(out_filename, bbox_inches='tight')
