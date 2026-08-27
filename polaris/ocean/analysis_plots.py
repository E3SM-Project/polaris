"""
Plots shared by the steps that analyze a completed simulation.

The steps that make these plots read their data in very different ways --
one from a forward step in its own task, another from a run that finished
months ago -- so the plotting is kept here, free of any dependence on
:py:class:`polaris.Step`, and each step passes in arrays it has already
selected.
"""

import matplotlib.pyplot as plt
import numpy as np

from polaris.viz import mplstyle_context

# the label each statistic is given in the legend and in the netCDF file
# beside the plot, using the Polaris-standard spelling of the statistic
STAT_LABELS = {
    'min': 'Min',
    'max': 'Max',
    'mean': 'Avg',
    'std': 'SD',
}

# the line style each statistic is drawn with; the standard deviation is a
# shaded envelope around the mean rather than a line
_STAT_STYLES = [('min', ':k'), ('max', '--k'), ('mean', '-k')]


def plot_global_stats(
    time, stats, field_name, out_filename, x_label='Days', title=None
):
    """
    Plot a time series of the global statistics of one field

    Two panels share a time axis: the statistics themselves, with a
    standard-deviation envelope around the mean, and the change in each
    statistic since the beginning of the time series, which is where drift
    shows up.

    Parameters
    ----------
    time : numpy.ndarray
        The time axis of the series

    stats : dict of str to numpy.ndarray
        The statistics to plot, keyed by ``'min'``, ``'max'``, ``'mean'`` and
        ``'std'``.  Any subset may be given and a statistic that is absent is
        omitted from the plot.  The envelope is drawn only when both
        ``'mean'`` and ``'std'`` are present.

    field_name : str
        The name of the field, used to label the vertical axes

    out_filename : str
        The image file to write

    x_label : str, optional
        The label for the time axis

    title : str, optional
        A title for the figure
    """
    with mplstyle_context():
        fig, axes = plt.subplots(
            nrows=2, ncols=1, sharex=True, sharey=False, figsize=(5, 8)
        )

        for stat, style in _STAT_STYLES:
            if stat not in stats:
                continue
            values = np.asarray(stats[stat])
            label = STAT_LABELS[stat]
            axes[0].plot(time, values, style, label=label)
            axes[1].plot(time, values - values[0], style, label=label)

        if 'mean' in stats and 'std' in stats:
            mean = np.asarray(stats['mean'])
            std = np.asarray(stats['std'])
            axes[0].fill_between(
                time,
                mean + std,
                mean - std,
                color='k',
                alpha=0.5,
                label=STAT_LABELS['std'],
            )

        axes[0].legend()
        axes[1].legend()
        axes[0].set_xlabel(x_label)
        axes[1].set_xlabel(x_label)
        axes[0].set_ylabel(field_name)
        axes[1].set_ylabel(f'{field_name} - {field_name} at t=0')
        axes[0].set_xlim([min(time), max(time)])
        if title is not None:
            fig.suptitle(title)
        fig.savefig(out_filename, bbox_inches='tight')
        plt.close(fig)
