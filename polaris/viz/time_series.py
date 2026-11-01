import warnings
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

    marker : str, optional
        A marker at each value, which shows a series of a few values
    """

    time: np.ndarray
    values: np.ndarray
    label: str
    color: str | None = None
    linestyle: str = '-'
    linewidth: float | None = None
    marker: str | None = None


def plot_time_series(
    series,
    out_filename,
    ylabel,
    xlabel='time (years)',
    title=None,
    ensemble=None,
    ensemble_label='ensemble range',
    figsize=(8.0, 4.0),
    xlim=None,
    legend_outside=False,
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
        range between their minimum and maximum at each time.  For the
        range, the members are interpolated to the times of the longest,
        and each counts only within its own times.

    ensemble_label : str, optional
        The legend entry for the ensemble's range

    figsize : tuple of float, optional
        The figure's width and height in inches

    xlim : tuple of float, optional
        The limits of the x axis

    legend_outside : bool, optional
        Whether to place the legend to the right of the axes, so it hides no
        lines
    """
    with mplstyle_context():
        fig = Figure(figsize=figsize)
        ax = fig.add_subplot(111)
        if ensemble:
            time, lower, upper = _ensemble_range(ensemble)
            ax.fill_between(
                time, lower, upper, color='0.85', label=ensemble_label
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
            if line.marker is not None:
                kwargs['marker'] = line.marker
            ax.plot(line.time, line.values, **kwargs)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if title is not None:
            ax.set_title(title)
        if len(series) > 1 or ensemble:
            if legend_outside:
                ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5))
            else:
                ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        if xlim is not None:
            ax.set_xlim(xlim)
        fig.savefig(out_filename, bbox_inches='tight')


def _ensemble_range(ensemble):
    """
    The minimum and maximum of an ensemble at the times of its longest
    member, from the members that have a value at each time
    """
    longest = max(ensemble, key=lambda member: len(member.time))
    time = np.asarray(longest.time)
    members = []
    for member in ensemble:
        valid = np.isfinite(member.values)
        member_time = np.asarray(member.time)[valid]
        values = np.asarray(member.values)[valid]
        if len(values) == 0:
            continue
        members.append(
            np.interp(time, member_time, values, left=np.nan, right=np.nan)
        )
    members_array = np.array(members)
    # times where no member has a value are left blank
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        lower = np.nanmin(members_array, axis=0)
        upper = np.nanmax(members_array, axis=0)
    return time, lower, upper
