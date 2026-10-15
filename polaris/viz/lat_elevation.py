"""
Plots of a field against latitude and elevation.

The overturning streamfunction is the first of these, but regional
overturning, zonal means and meridional heat transport all live on the same
axes, so the plot is a primitive here rather than something the step that
makes it owns.
"""

import numpy as np
import xarray as xr
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from polaris.viz.helper import add_fitted_suptitle
from polaris.viz.spherical import setup_colormap
from polaris.viz.style import mplstyle_context

# The number of filled levels the color map is divided into.  Enough that the
# fill reads as continuous shading, which is what the color bar promises, and
# few enough that the contour lines drawn over it are still the thing the eye
# follows.
FILL_LEVELS = 51

# The most contour lines a plot carries before they stop being something the
# eye can follow and become a scribble.  Past this the interval is widened to
# a round multiple of the one that was asked for, so that a field whose range
# is much larger than expected still gets a readable plot rather than one that
# has to be tuned by hand before it can be looked at.
MAX_CONTOUR_LINES = 25


def plot_lat_elevation_field(
    da,
    lat,
    z,
    out_filename,
    config,
    colormap_section,
    contour_interval=None,
    max_abs=None,
    title=None,
    colorbar_label='',
    x_label='Latitude ($^{\\circ}$N)',
    y_label='Elevation (m)',
    figsize=(8.0, 5.0),
    dpi=None,
):
    """
    Plot a field against latitude and elevation as filled contours with
    contour lines over them

    The vertical axis is elevation in m, positive up, so the sea surface is at
    the top of the plot without the axis being inverted.  That is the sign
    convention the rest of the ocean analysis uses, and an inverted axis
    labelled with elevations would quietly contradict it.

    Parameters
    ----------
    da : xarray.DataArray
        The two-dimensional field to plot, with one dimension of length
        ``len(z)`` and one of length ``len(lat)``.  It is transposed as
        needed; when the two are the same length its dimensions are taken to
        be elevation and then latitude.

    lat : numpy.ndarray or xarray.DataArray
        The latitude of each column of ``da``, in degrees north.  These are
        the positions the field is defined at, not cell boundaries.

    z : numpy.ndarray or xarray.DataArray
        The elevation of each row of ``da``, in m and positive up

    out_filename : str
        The image file to write

    config : polaris.config.PolarisConfigParser
        The config options the color map is read from

    colormap_section : str
        The name of a section in the config options.  Options must include
        ``colormap_name``, ``norm_type`` and ``norm_args``, as for
        :py:func:`polaris.viz.setup_colormap`.

    contour_interval : float, optional
        The spacing of the contour lines drawn over the fill, in the units of
        ``da``.  Without it no contour lines are drawn.

    max_abs : float, optional
        The maximum absolute value of a color map centered on zero, which
        replaces the limits ``norm_args`` gives.  This is how a diverging
        field is plotted symmetrically about zero; a field with no natural
        center leaves it out and sets its limits in ``norm_args``.

    title : str, optional
        A title for the figure

    colorbar_label : str, optional
        The label on the color bar, usually the units of ``da``

    x_label : str, optional
        The label on the latitude axis

    y_label : str, optional
        The label on the elevation axis

    figsize : tuple of float, optional
        The size of the figure in inches

    dpi : int, optional
        Dots per inch for the saved image

    Returns
    -------
    contour_interval : float or None
        The interval the contour lines were actually drawn at, which is a
        round multiple of ``contour_interval`` when that one would have drawn
        more than :py:data:`MAX_CONTOUR_LINES` of them, or ``None`` if no
        lines were asked for
    """
    lat = np.asarray(lat, dtype=float)
    z = np.asarray(z, dtype=float)
    values = _oriented_values(da, lat=lat, z=z)

    colormap, norm, ticks = setup_colormap(config, colormap_section)
    if max_abs is not None:
        norm.vmin = -max_abs
        norm.vmax = max_abs
    if norm.vmin is None or norm.vmax is None:
        norm.autoscale_None(np.ma.masked_invalid(values))

    with mplstyle_context(dpi=dpi):
        figure = Figure(figsize=figsize, layout='constrained')
        axes = figure.subplots()
        # what is below the seafloor is not zero, so it is left unpainted
        # against a neutral ground rather than taking a color from the map
        axes.set_facecolor('0.85')

        levels = np.linspace(norm.vmin, norm.vmax, FILL_LEVELS)
        filled = axes.contourf(
            lat,
            z,
            values,
            levels=levels,
            cmap=colormap,
            norm=norm,
            extend=_extend(values, norm.vmin, norm.vmax),
        )
        # a contour plot saved to PDF or SVG shows the seams between its
        # polygons unless they are drawn over their own edges
        filled.set_edgecolor('face')

        drawn_interval = None
        if contour_interval is not None:
            lines, drawn_interval = _contour_levels(contour_interval, values)
            if len(lines) > 0:
                # negative contours come out dashed, which is what tells the
                # two circulation cells apart in black and white
                axes.contour(
                    lat, z, values, levels=lines, colors='k', linewidths=0.5
                )

        if ticks is None:
            # the fill is finely divided so that it reads as continuous
            # shading, and a color bar ticked at its own levels would be
            # labelled with whatever values those happened to land on
            ticks = MaxNLocator(nbins=9, steps=[1, 2, 2.5, 5, 10])
        figure.colorbar(filled, ax=axes, label=colorbar_label, ticks=ticks)

        axes.set_xlim(float(lat.min()), float(lat.max()))
        axes.set_ylim(float(z.min()), float(z.max()))
        axes.set_xticks(_latitude_ticks(lat))
        axes.set_xlabel(x_label)
        axes.set_ylabel(y_label)
        if title is not None:
            add_fitted_suptitle(figure, title)
        figure.savefig(out_filename)
    return drawn_interval


def _oriented_values(da, lat, z):
    """
    Get the values of ``da`` as an array with elevation down its rows and
    latitude across its columns, which is the shape contouring wants
    """
    if not isinstance(da, xr.DataArray):
        da = xr.DataArray(np.asarray(da))
    shape = (len(z), len(lat))
    if da.shape == shape:
        return da.values
    if da.shape == shape[::-1]:
        return da.values.transpose()
    raise ValueError(
        f'A field of shape {da.shape} with dimensions '
        f'{tuple(str(dim) for dim in da.dims)} is neither '
        f'{shape} nor {shape[::-1]}, so it cannot be plotted against '
        f'{len(lat)} latitudes and {len(z)} elevations.'
    )


def _extend(values, vmin, vmax):
    """
    Say which ends of the color map the data run past

    The arrows on a color bar are a claim that there is data beyond it, so
    they are drawn only where there is.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 'neither'
    below = bool(finite.min() < vmin)
    above = bool(finite.max() > vmax)
    if below and above:
        return 'both'
    if below:
        return 'min'
    if above:
        return 'max'
    return 'neither'


def _contour_levels(interval, values):
    """
    Get the values to draw contour lines at, and the interval they end up
    spaced by

    The levels follow the data rather than the color map, so that a color map
    deliberately clipped to bring out the weaker circulation still has contour
    lines through the saturated part of it, which is the only thing left there
    that says how strong it is.  Restricting them to the range of the data
    also keeps matplotlib from warning once per level about levels no contour
    passes through.

    Following the data is what makes the count unbounded, though: a field with
    a range much wider than the interval was chosen for turns the plot into a
    scribble.  So the interval is widened to a round multiple of itself --- 2,
    5, 10, 20 times and so on --- until the lines are few enough to follow.
    The caller is told which interval was used so it can say so.
    """
    if interval <= 0.0:
        raise ValueError(
            f'The contour interval must be positive, but it is {interval}.'
        )
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.array([]), interval

    low = float(finite.min())
    high = float(finite.max())
    for factor in _round_factors():
        spacing = interval * factor
        first = np.ceil(low / spacing)
        last = np.floor(high / spacing)
        if last < first:
            # the field does not reach a single multiple of this spacing, so
            # widening it further cannot help
            return np.array([]), spacing
        if int(last - first) + 1 <= MAX_CONTOUR_LINES:
            return np.arange(first, last + 1) * spacing, spacing
    return np.array([]), interval


def _round_factors():
    """
    The round multiples an interval may be widened by, in order

    1, 2, 5, 10, 20, 50 and so on, so that a widened interval is still a
    number a reader can do arithmetic with.
    """
    for power in range(12):
        for step in (1, 2, 5):
            yield step * 10**power


def _latitude_ticks(lat, spacing=30.0):
    """
    Get the latitude ticks, at a round spacing over the range the data cover

    A global plot then carries the ticks a reader expects at 60S, 30S, the
    equator and so on, and a plot of part of the globe is not left with the
    one or two of them that happen to fall inside it.
    """
    low = np.ceil(float(lat.min()) / spacing) * spacing
    high = np.floor(float(lat.max()) / spacing) * spacing
    if high < low:
        return np.array([float(lat.min()), float(lat.max())])
    return np.arange(low, high + 0.5 * spacing, spacing)
