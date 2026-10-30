import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np

from polaris.landice.mismip_plus.diagnostics import thickness_above_flotation
from polaris.landice.mismip_plus.geometry import (
    ICE_DENSITY,
    MALI_SECONDS_PER_YEAR,
)
from polaris.viz import mplstyle_context, plot_horiz_field

# the diagnostics in time-series plots, their scales and labels
TIME_SERIES = [
    ('xGL', 1e-3, 'grounding line on\ncenterline (km)'),
    ('iceVAF', 1e-12, 'volume above\nflotation (10$^3$ km$^3$)'),
    ('groundedArea', 1e-9, 'grounded area\n(10$^3$ km$^2$)'),
    ('iceVolume', 1e-12, 'ice volume\n(10$^3$ km$^3$)'),
]

# the scale from MALI's volumes in m^3 to masses in Gt
GT_PER_CUBIC_METER = 1e-12 * ICE_DENSITY

# MALI's global statistics of volume and area, plotted as changes from the
# start, their scales and labels
GLOBAL_STATS_VOLUME = [
    ('totalIceVolume', GT_PER_CUBIC_METER, 'volume change\n(Gt)'),
    ('volumeAboveFloatation', GT_PER_CUBIC_METER, 'VAF change\n(Gt)'),
    ('groundedIceVolume', GT_PER_CUBIC_METER, 'grounded volume change\n(Gt)'),
    ('floatingIceVolume', GT_PER_CUBIC_METER, 'floating volume change\n(Gt)'),
    ('groundedIceArea', 1e-6, 'grounded area change\n(km$^2$)'),
    ('floatingIceArea', 1e-6, 'floating area change\n(km$^2$)'),
    ('totalIceArea', 1e-6, 'total area change\n(km$^2$)'),
]

# MALI's global statistics of mass fluxes in kg a^-1, their scales and labels
GLOBAL_STATS_FLUX = [
    ('totalSfcMassBal', 1e-12, 'total SMB flux\n(Gt a$^{-1}$)'),
    ('totalBasalMassBal', 1e-12, 'total BMB flux\n(Gt a$^{-1}$)'),
    ('totalGroundedSfcMassBal', 1e-12, 'grounded SMB flux\n(Gt a$^{-1}$)'),
    ('totalGroundedBasalMassBal', 1e-12, 'grounded BMB flux\n(Gt a$^{-1}$)'),
    ('totalFloatingSfcMassBal', 1e-12, 'floating SMB flux\n(Gt a$^{-1}$)'),
    ('totalFloatingBasalMassBal', 1e-12, 'floating BMB flux\n(Gt a$^{-1}$)'),
    ('groundingLineFlux', 1e-12, 'GL flux\n(Gt a$^{-1}$)'),
    ('groundingLineMigrationFlux', 1e-12, 'GL migration flux\n(Gt a$^{-1}$)'),
    ('totalCalvingFlux', 1e-12, 'calving flux\n(Gt a$^{-1}$)'),
    ('totalFaceMeltingFlux', 1e-12, 'face-melt flux\n(Gt a$^{-1}$)'),
]


def plot_thickness_and_speed(ds, config, prefix, title):
    """
    Plot thickness and surface speed with the grounding line

    Parameters
    ----------
    ds : xarray.Dataset
        A MALI restart or output file with mesh variables, ``thickness``,
        ``bedTopography`` and ``uReconstructX`` and ``uReconstructY`` or
        ``surfaceSpeed``, at a single time

    config : polaris.config.PolarisConfigParser
        Config options with a ``mismip_plus_viz`` section

    prefix : str
        The prefix of the image files

    title : str
        The time to put in the titles
    """
    section = config['mismip_plus_viz']
    if 'surfaceSpeed' in ds:
        speed = MALI_SECONDS_PER_YEAR * ds.surfaceSpeed
    else:
        speed = MALI_SECONDS_PER_YEAR * np.sqrt(
            ds.uReconstructX.isel(nVertInterfaces=0) ** 2
            + ds.uReconstructY.isel(nVertInterfaces=0) ** 2
        )
    thickness = ds.thickness.where(ds.thickness > 0.0)

    for field, name, label, cmap, vmax in [
        (thickness, 'thickness', 'thickness (m)', 'thickness_cmap', None),
        (
            speed.where(ds.thickness > 0.0),
            'surface_speed',
            'surface speed (m a$^{-1}$)',
            'speed_cmap',
            section.getfloat('speed_max'),
        ),
    ]:
        with mplstyle_context():
            fig, ax = plt.subplots(figsize=(10.0, 2.2))
            plot_horiz_field(
                ds_mesh=ds,
                field=field,
                ax=ax,
                title=f'{label.split(" (")[0].capitalize()} {title}',
                cmap=section.get(cmap),
                vmin=0.0,
                vmax=vmax,
                cmap_title=label,
            )
            plot_grounding_line(ax, ds, colors='black', linewidths=0.8)
            fig.savefig(f'{prefix}{name}.png', bbox_inches='tight')
            plt.close(fig)


def plot_grounding_line(ax, ds, **kwargs):
    """
    Plot the grounding line, the zero contour of the thickness above flotation

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to plot on

    ds : xarray.Dataset
        A dataset with ``xCell``, ``yCell``, ``thickness`` and
        ``bedTopography`` at a single time

    kwargs : dict
        Keyword arguments to ``tricontour()``
    """
    haf = thickness_above_flotation(ds.thickness, ds.bedTopography)
    haf = haf.where(ds.thickness > 0.0, -1.0)
    return ax.tricontour(
        ds.xCell.values, ds.yCell.values, haf.values, levels=[0.0], **kwargs
    )


def plot_time_series(series, filename, title, references=None):
    """
    Plot the MISMIP+ diagnostics against time

    Parameters
    ----------
    series : list of tuple
        Each entry is a label and a dataset of diagnostics with a ``Time``
        coordinate in years

    filename : str
        The image file to write

    title : str
        The title of the figure

    references : list of tuple, optional
        Each entry is a label, a dataset of diagnostics with a ``time``
        variable and an ``entry`` dimension, and keyword arguments for the
        lines of every entry
    """
    with mplstyle_context():
        _plot_time_series(series, filename, title, references)


def _plot_time_series(series, filename, title, references):
    fig, axes = plt.subplots(
        len(TIME_SERIES), 1, figsize=(7.0, 9.0), sharex=True
    )
    for ax, (var, scale, label) in zip(axes, TIME_SERIES, strict=True):
        if references is not None:
            for ref_label, ds_ref, kwargs in references:
                for index in range(ds_ref.sizes['entry']):
                    ds_entry = ds_ref.isel(entry=index)
                    ax.plot(
                        ds_entry.time.values,
                        scale * ds_entry[var].values,
                        label=ref_label if index == 0 else None,
                        **kwargs,
                    )
        for series_label, ds in series:
            ax.plot(
                ds.Time.values,
                scale * ds[var].values,
                label=series_label,
                linewidth=2.0,
            )
        ax.set_ylabel(label)
        ax.ticklabel_format(axis='y', useOffset=False)
        ax.grid(True)
    # the references may run longer than the series
    t_min = min(float(ds.Time.min()) for _, ds in series)
    t_max = max(float(ds.Time.max()) for _, ds in series)
    axes[-1].set_xlim(t_min, t_max)
    axes[-1].set_xlabel('time (a)')
    # below the panels, since the entries fill each of them
    axes[-1].legend(
        loc='upper center',
        bbox_to_anchor=(0.5, -0.35),
        ncol=2,
        fontsize='small',
    )
    axes[0].set_title(title)
    fig.savefig(filename, bbox_inches='tight')
    plt.close(fig)


def plot_global_stats(series, prefix, title):
    """
    Plot MALI's global statistics against time: the changes in volume and
    area since the start in ``<prefix>global_stats_volume.png`` and the mass
    fluxes in ``<prefix>global_stats_flux.png``

    Parameters
    ----------
    series : list of tuple
        Each entry is a label and a dataset of MALI's global statistics with
        a ``Time`` coordinate in years.  Changes are from the first time of
        the first dataset.

    prefix : str
        The prefix of the image files

    title : str
        The title of the figures
    """
    with mplstyle_context():
        for stats, suffix, change in [
            (GLOBAL_STATS_VOLUME, 'volume', True),
            (GLOBAL_STATS_FLUX, 'flux', False),
        ]:
            _plot_global_stats(
                series,
                stats,
                filename=f'{prefix}global_stats_{suffix}.png',
                title=title,
                change=change,
            )


def _plot_global_stats(series, stats, filename, title, change):
    nrows = (len(stats) + 1) // 2
    fig, axes = plt.subplots(
        nrows, 2, figsize=(10.0, 2.8 * nrows), sharex=True
    )
    axes = axes.ravel()
    _, ds_start = series[0]
    for ax, (var, scale, label) in zip(axes, stats, strict=False):
        start = float(ds_start[var].isel(Time=0)) if change else 0.0
        for series_label, ds in series:
            ax.plot(
                ds.Time.values,
                scale * (ds[var].values - start),
                label=series_label,
            )
        ax.set_ylabel(label)
        ax.grid(True)
    # the volume figure has a panel to spare
    for ax in axes[len(stats) :]:
        ax.axis('off')
    # label the time axis of the lowest panel in each column
    for column in range(2):
        ax = axes[column : len(stats) : 2][-1]
        ax.tick_params(labelbottom=True)
        ax.set_xlabel('time (a)')
    if len(series) > 1:
        axes[0].legend(fontsize='small')
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(filename, bbox_inches='tight')
    plt.close(fig)
