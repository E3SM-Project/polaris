"""
The colors of fields whose sign matters, so a negative value never looks
like zero: melt (and melt plus frazil), whose refreezing is blue, and
thermal driving, whose water below its freezing point has a short colormap
of its own
"""

import cmocean
import numpy as np
from matplotlib.colors import FuncNorm, ListedColormap
from matplotlib.ticker import MaxNLocator

#: The share of a color bar below zero, at most
NEGATIVE_SHARE = 0.1

#: The colors in a signed colormap, so ``NEGATIVE_SHARE`` of them is a
#: whole number and zero falls on the first positive color
_COLORS = 1000

#: The share of a range's values beyond each end of its colors
_TAIL_PERCENT = 0.5


def get_signed_range(arrays):
    """
    Get the range of a signed field's colors from its values: from the
    0.5th to the 99.5th percentile, with zero always inside

    Parameters
    ----------
    arrays : list of numpy.ndarray
        The values, NaN where there are none

    Returns
    -------
    vmin, vmax : float
        The range
    """
    values = np.concatenate([np.ravel(array) for array in arrays])
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0, 1.0
    vmin = float(np.percentile(values, _TAIL_PERCENT))
    vmax = float(np.percentile(values, 100.0 - _TAIL_PERCENT))
    return min(vmin, 0.0), max(vmax, 0.0)


def get_signed_colors(kind, vmin, vmax):
    """
    Get the colormap and norm of a signed field, with zero
    ``NEGATIVE_SHARE`` of the way up the color bar

    The negative side reaches ``vmin`` or ``vmax`` over 9, whichever is
    further from zero, so the bar is linear unless the negative values
    reach further, which are then squeezed into the bar's bottom tenth.

    Parameters
    ----------
    kind : {'melt', 'thermal_driving'}
        The field: melt or melt plus frazil, red for melt and blue for
        refreezing on one diverging colormap; or thermal driving,
        ``cmo.thermal`` above zero and a short ramp of greens below

    vmin, vmax : float
        The range of the field

    Returns
    -------
    cmap : matplotlib.colors.Colormap
        The colormap

    norm : matplotlib.colors.FuncNorm
        The norm

    ticks : list of float
        The color bar's ticks: the bottom of the bar and even steps above
        zero, short of the top; zero is too near the bottom for a label of
        its own
    """
    vmax = vmax if vmax > 0.0 else 1.0
    linear = vmax * NEGATIVE_SHARE / (1.0 - NEGATIVE_SHARE)
    lowest = -_round_up(max(-vmin, linear))
    n_negative = int(round(NEGATIVE_SHARE * _COLORS))
    n_positive = _COLORS - n_negative
    if kind == 'melt':
        # the blues run on into the white at zero, so the map is continuous,
        # and the least freezing is still a shade off white
        negative = cmocean.cm.balance(
            np.linspace(0.0, 0.5, n_negative, endpoint=False)
        )
        positive = cmocean.cm.balance(np.linspace(0.5, 1.0, n_positive))
    elif kind == 'thermal_driving':
        # darkest at zero, beside the darkest blue of cmo.thermal, and
        # paler the further below freezing
        negative = cmocean.cm.algae(np.linspace(0.15, 0.95, n_negative))
        positive = cmocean.cm.thermal(np.linspace(0.0, 1.0, n_positive))
    else:
        raise ValueError(f'Unknown kind of signed field: {kind}')
    cmap = ListedColormap(np.concatenate([negative, positive]))
    stops = [lowest, 0.0, vmax]
    shares = [0.0, NEGATIVE_SHARE, 1.0]

    def forward(values):
        return np.interp(values, stops, shares)

    def inverse(values):
        return np.interp(values, shares, stops)

    norm = FuncNorm((forward, inverse), vmin=lowest, vmax=vmax)
    steps = MaxNLocator(nbins=5).tick_values(0.0, vmax)
    # a tick at the very top can sit under a long title
    ticks = [lowest] + [
        float(tick) for tick in steps if 0.0 < tick <= 0.95 * vmax
    ]
    return cmap, norm, ticks


def _round_up(value):
    """A positive value rounded up to 2 significant figures"""
    scale = 10.0 ** (np.floor(np.log10(value)) - 1.0)
    return float(np.ceil(value / scale - 1e-9) * scale)
