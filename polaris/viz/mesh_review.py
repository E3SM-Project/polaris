import os
from dataclasses import dataclass
from typing import Any, cast

import cartopy.crs as ccrs
import matplotlib.path as mpath
import matplotlib.pyplot as plt
import mosaic
import numpy as np
import xarray as xr
from cartopy.geodesic import Geodesic
from cartopy.mpl.geoaxes import GeoAxes
from matplotlib import colormaps, patheffects
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.figure import Figure
from ruamel.yaml import YAML

from polaris.viz.style import mplstyle_context

_OVERVIEW_TITLES = {
    'north': 'Northern high latitudes',
    'global': 'Mid and low latitudes',
    'south': 'Southern high latitudes',
}


@dataclass(frozen=True)
class Inset:
    """
    A circular, orthographic view of a region of a spherical mesh

    Attributes
    ----------
    index : int
        The number of the inset, used in its title and filenames

    name : str
        A human-readable name for the region

    centlat : float
        Latitude of the center of the view in degrees north

    centlon : float
        Longitude of the center of the view in degrees east

    horizon : float
        Great-circle radius of the view in degrees (at most 90)
    """

    index: int
    name: str
    centlat: float
    centlon: float
    horizon: float


def load_insets(filename: str | os.PathLike[str]) -> list[Inset]:
    """
    Read inset definitions from a YAML file

    The file holds a list of entries with ``name``, ``centlat``, ``centlon``
    and ``horizon``.  Each inset is numbered by its 1-based position in the
    list.

    Parameters
    ----------
    filename : str or os.PathLike
        The YAML file

    Returns
    -------
    insets : list of Inset
    """
    with open(filename) as f:
        entries = YAML(typ='safe').load(f)
    return [
        Inset(index=index, **entry)
        for index, entry in enumerate(entries, start=1)
    ]


def plot_inset(
    ds: xr.Dataset,
    field: xr.DataArray,
    inset: Inset,
    label: str,
    filename: str | None = None,
    wireframe_kwargs: dict[str, Any] | None = None,
    contourf_kwargs: dict[str, Any] | None = None,
    contour_kwargs: dict[str, Any] | None = None,
    dpi: int = 200,
) -> tuple[Figure, np.ndarray]:
    """
    Plot the mesh wireframe and a filled cell field side by side in an inset

    Parameters
    ----------
    ds : xarray.Dataset
        The MPAS mesh

    field : xarray.DataArray
        A field on cell centers

    inset : Inset
        The region to plot

    label : str
        The colorbar label

    filename : str, optional
        The image file to write, if any

    wireframe_kwargs : dict, optional
        Keyword arguments to ``mosaic.wireframe`` for the mesh

    contourf_kwargs : dict, optional
        Keyword arguments to ``mosaic.contourf`` for the filled field, such
        as ``levels`` and ``cmap``.  Unless a ``norm`` is given, the bands
        between ``levels`` get evenly spaced colors, however unevenly spaced
        the levels are.

    contour_kwargs : dict, optional
        Keyword arguments to ``mosaic.contour`` for lines of ``field`` drawn
        on both panels and shown in a legend.  If given, it must include
        ``levels``.  Unless ``colors`` or ``cmap`` is given, each line gets
        its own qualitative color.

    dpi : int, optional
        Dots per inch of the image written to ``filename``

    Returns
    -------
    fig : matplotlib.figure.Figure
        The figure, which the caller is responsible for closing

    axes : numpy.ndarray of cartopy.mpl.geoaxes.GeoAxes
        The wireframe and field panels
    """
    wireframe_kwargs = {
        'color': 'tab:blue',
        'linewidth': 0.5,
        'zorder': 0,
        **(wireframe_kwargs or {}),
    }

    contourf_kwargs = {
        'extend': 'both',
        'zorder': 0,
        **(contourf_kwargs or {}),
    }
    if 'levels' in contourf_kwargs and 'norm' not in contourf_kwargs:
        cmap = plt.get_cmap(contourf_kwargs.get('cmap'))
        contourf_kwargs['norm'] = BoundaryNorm(
            contourf_kwargs['levels'],
            cmap.N,
            extend=contourf_kwargs['extend'],
        )

    if contour_kwargs is not None:
        defaults: dict[str, Any] = {'linewidths': 1.0, 'zorder': 1}
        if 'cmap' not in contour_kwargs:
            # skip blue, the default wireframe color
            n = len(contour_kwargs['levels'])
            defaults['colors'] = colormaps['tab10'](np.arange(1, n + 1))
        contour_kwargs = defaults | contour_kwargs

    projection = ccrs.Orthographic(inset.centlon, inset.centlat)

    with mplstyle_context(dpi=dpi):
        fig, axes = plt.subplots(
            ncols=2,
            figsize=(12, 6),
            layout='constrained',
            subplot_kw={'projection': projection},
        )
        descriptor = mosaic.Descriptor(ds, projection=projection)

        _set_horizon(axes[0], inset.horizon)
        _set_horizon(axes[1], inset.horizon, labels=False)

        mosaic.wireframe(axes[0], descriptor, **wireframe_kwargs)
        filled = mosaic.contourf(axes[1], descriptor, field, **contourf_kwargs)
        cbar = fig.colorbar(
            filled,
            ax=axes[1],
            spacing='uniform',
            shrink=0.8,
            pad=0.04,
            drawedges=True,
            ticks=filled.levels,
        )
        cbar.set_ticklabels([f'{level:g}' for level in filled.levels])
        cbar.ax.tick_params(size=0, labelsize=8)
        cbar.set_label(label, fontsize=9)

        for ax in axes:
            if contour_kwargs is not None:
                lines = mosaic.contour(ax, descriptor, field, **contour_kwargs)
            mosaic.coastlines(ax, descriptor, color='k', lw=1.0, zorder=2)

        if contour_kwargs is not None:
            handles, _ = lines.legend_elements()
            fig.legend(
                handles,
                [f'{level:g}' for level in lines.levels],
                loc='lower center',
                ncol=len(handles),
                fontsize=9,
                frameon=False,
                handlelength=2.5,
                columnspacing=2.0,
            )

        fig.suptitle(f'{inset.index}: {inset.name}', fontsize=13)
        if filename is not None:
            fig.savefig(filename, bbox_inches='tight')

    return fig, axes


def plot_inset_overviews(
    ds: xr.Dataset,
    insets: list[Inset],
    output_dir: str,
    polar_lat: float = 60.0,
    dpi: int = 200,
) -> list[str]:
    """
    Plot maps that outline and number each inset

    Insets centered poleward of ``polar_lat`` are shown on orthographic views
    of the poles that are just large enough to hold them.  The rest are shown
    on a global map.

    Parameters
    ----------
    ds : xarray.Dataset
        The MPAS mesh

    insets : list of Inset
        The insets to locate

    output_dir : str
        The directory for the images, ``overview_north.png``,
        ``overview_global.png`` and ``overview_south.png``.  A map with no
        insets is not written.

    polar_lat : float, optional
        Latitude (degrees) poleward of which insets go on the polar maps

    dpi : int, optional
        Dots per inch of the images

    Returns
    -------
    filenames : list of str
        The images that were written
    """
    groups = {
        'north': [i for i in insets if i.centlat >= polar_lat],
        'global': [i for i in insets if abs(i.centlat) < polar_lat],
        'south': [i for i in insets if i.centlat <= -polar_lat],
    }

    filenames = []
    for region, group in groups.items():
        if not group:
            continue

        with mplstyle_context(dpi=dpi):
            if region == 'global':
                projection, figsize = ccrs.EqualEarth(), (14, 7)
            else:
                pole = 90.0 if region == 'north' else -90.0
                projection, figsize = ccrs.Orthographic(0.0, pole), (9, 9)
            fig, ax = plt.subplots(
                figsize=figsize,
                layout='constrained',
                subplot_kw={'projection': projection},
            )
            ax = cast(GeoAxes, ax)

            if region == 'global':
                ax.set_global()
                ax.gridlines(
                    linestyle=':', linewidth=0.6, color='0.75', zorder=8
                )
            else:
                reach = max(90.0 - abs(i.centlat) + i.horizon for i in group)
                _set_horizon(ax, min(reach + 2.0, 90.0))

            descriptor = mosaic.Descriptor(ds, projection=projection)
            mosaic.polypcolor(
                ax,
                descriptor,
                xr.ones_like(ds.latCell),
                cmap=ListedColormap(['0.85']),
                zorder=0,
            )
            mosaic.coastlines(ax, descriptor, color='k', lw=0.6, zorder=1)

            for inset in group:
                boundary = Geodesic(radius=1.0, flattening=0.0).circle(
                    inset.centlon,
                    inset.centlat,
                    np.radians(inset.horizon),
                    n_samples=361,
                    endpoint=True,
                )
                ax.plot(
                    *np.asarray(boundary).T,
                    color='navy',
                    linewidth=0.8,
                    transform=ccrs.Geodetic(),
                    zorder=9,
                )
                ax.text(
                    inset.centlon,
                    inset.centlat,
                    str(inset.index),
                    ha='center',
                    va='center',
                    fontsize=8,
                    fontweight='bold',
                    color='navy',
                    transform=ccrs.PlateCarree(),
                    clip_on=True,
                    path_effects=[
                        patheffects.withStroke(linewidth=2, foreground='w')
                    ],
                    zorder=10,
                )

            ax.set_title(
                f'{_OVERVIEW_TITLES[region]}: regional inset locations'
            )
            filename = os.path.join(output_dir, f'overview_{region}.png')
            fig.savefig(filename, bbox_inches='tight')
            plt.close(fig)
        filenames.append(filename)

    return filenames


def _set_horizon(ax: GeoAxes, horizon: float, labels: bool = True) -> None:
    """
    Clip an orthographic map to a circle around its center and add gridlines
    """
    # the orthographic projection of a great-circle radius
    r = ax.projection.globe.semimajor_axis * np.sin(np.radians(horizon))
    theta = np.linspace(0.0, 2.0 * np.pi, 360)
    ax.set_boundary(
        mpath.Path(r * np.column_stack([np.cos(theta), np.sin(theta)]))
    )
    ax.set_xlim(-1.01 * r, 1.01 * r)
    ax.set_ylim(-1.01 * r, 1.01 * r)

    label_style = {'size': 7, 'color': '0.55'}
    ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=['left', 'bottom'] if labels else False,
        rotate_labels=True,
        xlabel_style=label_style,
        ylabel_style=label_style,
        linestyle=':',
        linewidth=0.6,
        color='0.75',
        zorder=8,
    )
