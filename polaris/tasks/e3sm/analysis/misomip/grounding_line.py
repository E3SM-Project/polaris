"""
Plots of the ocean near the grounding line of a MISOMIP run: sections
along the centerline in depth and in height above the bed, the bottom
layer against time along the centerline, and a plan view
"""

import cmocean
import mosaic
import numpy as np
import xarray as xr
from matplotlib.collections import QuadMesh
from matplotlib.colors import BoundaryNorm, LogNorm
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.e3sm.analysis.calendar import (
    DAYS_IN_MONTH,
    MODEL_YEAR_LABEL,
    days_to_model_year,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    get_centerline_transect,
    isomip_mesh,
)
from polaris.viz.style import mplstyle_context

#: The edges of the temperature bins (degC): fine near freezing in the
#: cavity, coarser up to the warm water and the thin film
TEMPERATURE_BOUNDS = [
    -2.3, -2.2, -2.1, -2.05, -2.0, -1.95, -1.9, -1.85, -1.8, -1.7, -1.6,
    -1.5, -1.2, -0.9, -0.6, -0.3, 0.0, 0.5, 1.0,
]  # fmt: skip

#: The edges of the salinity bins (PSU): coarse for the thin film's fresh
#: water, fine for the cavity
SALINITY_BOUNDS = [
    0.0, 5.0, 10.0, 20.0, 30.0, 33.0, 33.5, 33.8, 34.0, 34.1, 34.2, 34.3,
    34.4, 34.5, 34.6, 34.7, 34.8,
]  # fmt: skip

#: The width (km) of the zoomed sections, which start this far (km) before
#: the grounding line
ZOOM_WIDTH = 30.0
ZOOM_BEFORE = 9.0

#: The range (km) around the grounding line of the plot of the bottom layer
#: against time and of the plan view
HOVMOLLER_RANGE = (-15.0, 75.0)
PLAN_RANGE = (-25.0, 105.0)

#: The smallest height above the bed (m) the log axis shows
MIN_HEIGHT = 0.02

FIG_WIDTH = 10.0
PNG_DPI = 150


def ocean_grounding_line(ds_init, y):
    """
    The x (km) where the ocean's floating ice starts along a line of
    constant y, for runs without MALI

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    y : float
        The line's y (m) in the protocol's coordinates

    Returns
    -------
    x : float
        The upstream edge (km) of the first floating cell on the line
    """
    ds_transect = get_centerline_transect(ds_init, ds_init.layerThickness, y)
    cells = ds_transect.horizCellIndices.values
    floating = ds_init.landIceFloatingFraction.values[cells] > 0.0
    d_node = 1e-3 * ds_transect.dNode.values
    x_start = 1e-3 * float(ds_init.xIsomipCell.min())
    return x_start + float(d_node[:-1][floating].min())


def plot_gl_zoom(ds_init, ds_mean, gl, y, title, png_filename):
    """
    Plot temperature and salinity near the grounding line along a line of
    constant y, in depth and in height above the bed, and the water column
    and floating fraction along it

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_mean : xarray.Dataset
        The time means from the diagnostics

    gl : tuple of float
        The grounding line (km) at the start and the end

    y : float
        The line's y (m) in the protocol's coordinates

    title : str
        The figure's title

    png_filename : str
        The figure
    """
    xmin = float(np.floor(min(gl)) - ZOOM_BEFORE)
    xmax = xmin + ZOOM_WIDTH
    ds_mesh = isomip_mesh(ds_init)
    thickness = ds_mean.layerThickness
    ds_depth = compute_transect(
        x=xr.DataArray([1e3 * xmin, 1e3 * xmax], dims=('nPoints',)),
        y=xr.DataArray([y, y], dims=('nPoints',)),
        ds_horiz_mesh=ds_mesh,
        layer_thickness=thickness,
        bottom_depth=ds_init.bottomDepth,
        min_level_cell=ds_init.minLevelCell - 1,
        max_level_cell=ds_init.maxLevelCell - 1,
        spherical=False,
    )
    ds_height = _height_above_bed(ds_depth)
    to_km = FuncFormatter(lambda value, _: f'{value + xmin:g}')
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(figsize=(FIG_WIDTH + 1.0, 9.5), constrained_layout=True)
        mosaic_axes = fig.subplot_mosaic(
            [['a', 'b'], ['c', 'd'], ['e', 'e']],
            gridspec_kw={'height_ratios': [3, 3, 1.2]},
        )
        panels = [
            ('a', ds_depth, 'temperature', 'depth'),
            ('b', ds_depth, 'salinity', 'depth'),
            ('c', ds_height, 'temperature', 'height above the bed'),
            ('d', ds_height, 'salinity', 'height above the bed'),
        ]
        for key, ds_transect, name, kind in panels:
            ax = mosaic_axes[key]
            is_temp = name == 'temperature'
            cmap = cmocean.cm.thermal if is_temp else cmocean.cm.haline
            bounds = TEMPERATURE_BOUNDS if is_temp else SALINITY_BOUNDS
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=ds_mean[name],
                ax=ax,
                cmap=cmap,
                colorbar_label=None,
                interface_color='0.75',
                linewidth=0.15,
                outline_color='black',
            )
            mesh = [c for c in ax.collections if isinstance(c, QuadMesh)][0]
            mesh.set_norm(BoundaryNorm(bounds, cmap.N, extend='both'))
            fig.colorbar(
                mesh,
                ax=ax,
                label=r'$^\circ$C' if is_temp else 'PSU',
                extend='both',
            )
            if kind == 'depth':
                top = float(ds_depth.zSeafloor.max())
                ax.set_ylim(float(ds_depth.zSeafloor.min()) - 2.0, top + 80.0)
                ax.set_ylabel('z (m)')
            else:
                ax.set_yscale('log')
                ax.set_ylim(0.03, 300.0)
                ax.set_ylabel('height above the bed (m)')
            _mark_grounding_lines(ax, gl, xmin)
            ax.set_xlim(0.0, xmax - xmin)
            ax.xaxis.set_major_formatter(to_km)
            ax.set_xlabel('')
            label = 'Potential temperature' if is_temp else 'Salinity'
            ax.set_title(f'{label}, {kind}')

        # the water column and floating fraction of the cells on the line
        cells = ds_depth.horizCellIndices.values
        d_node = 1e-3 * ds_depth.dNode.values
        x_seg = 0.5 * (d_node[:-1] + d_node[1:])
        ax = mosaic_axes['e']
        column = np.nansum(thickness.values[cells], axis=1)
        ax.semilogy(x_seg, column, 'k.-', linewidth=0.8, zorder=5)
        ax.set_ylabel('water column (m)')
        ax.set_ylim(0.5, 400.0)
        ax_right = ax.twinx()
        ax_right.plot(
            x_seg,
            ds_mean.landIceFloatingFraction.values[cells],
            'C0.-',
            linewidth=0.8,
        )
        ax_right.set_ylabel("ocean's floating fraction", color='C0')
        ax_right.set_ylim(-0.05, 1.05)
        _mark_grounding_lines(ax, gl, xmin)
        ax.set_xlim(0.0, xmax - xmin)
        ax.xaxis.set_major_formatter(to_km)
        ax.set_xlabel('x (km)')
        fig.suptitle(
            f'{title}: y = {1e-3 * y:g} km\nlayer interfaces grey; grounding '
            f'line dashed at the start, solid at the end'
        )
        fig.savefig(png_filename)


def plot_bottom_hovmoller(ds_init, ds_centerline, gl, title, png_filename):
    """
    Plot the bottom layer's temperature and salinity and the water column
    along the centerline against x and the model year, near the grounding
    line

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_centerline : xarray.Dataset
        The ocean on the transect's cells each month, from the diagnostics

    gl : tuple of float
        The grounding line (km) at the start and the end

    title : str
        The figure's title

    png_filename : str
        The figure
    """
    transect_cells = ds_centerline.transectCell.values
    x_cell = 1e-3 * ds_init.xIsomipCell.values[transect_cells]
    y_cell = 1e-3 * ds_init.yIsomipCell.values[transect_cells]
    # the cells of the transect nearest its line, in order of x
    y_row = y_cell[np.argmin(np.abs(y_cell - np.median(y_cell)))]
    g0 = min(gl)
    on_row = (
        (np.abs(y_cell - y_row) < 0.1)
        & (x_cell > g0 + HOVMOLLER_RANGE[0])
        & (x_cell < g0 + HOVMOLLER_RANGE[1])
    )
    row = np.flatnonzero(on_row)
    row = row[np.argsort(x_cell[row])]
    bottom = ds_init.maxLevelCell.values[transect_cells[row]] - 1
    thickness = ds_centerline.layerThickness.values[:, row, :]
    columns = np.arange(len(row))
    fields = [
        ds_centerline.temperature.values[:, row, :][:, columns, bottom],
        ds_centerline.salinity.values[:, row, :][:, columns, bottom],
        np.nansum(thickness, axis=2),
    ]
    month_end = ds_centerline.monthEnd.values
    edges_days = np.concatenate([[_month_start(month_end[0])], month_end])
    time_edges = days_to_model_year(edges_days)
    x_row = x_cell[row]
    x_edges = np.concatenate(
        [[x_row[0] - 1.0], 0.5 * (x_row[:-1] + x_row[1:]), [x_row[-1] + 1.0]]
    )
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(figsize=(FIG_WIDTH + 2.0, 4.5), constrained_layout=True)
        axes = fig.subplots(1, 3, sharey=True)
        for ax, field, cmap, norm, label in [
            (
                axes[0],
                fields[0],
                cmocean.cm.thermal,
                BoundaryNorm(TEMPERATURE_BOUNDS, 256, extend='both'),
                r'bottom-layer potential temperature ($^\circ$C)',
            ),
            (
                axes[1],
                fields[1],
                cmocean.cm.haline,
                BoundaryNorm(SALINITY_BOUNDS, 256, extend='both'),
                'bottom-layer salinity (PSU)',
            ),
            (
                axes[2],
                fields[2],
                cmocean.cm.deep,
                LogNorm(1.0, 300.0),
                'water column (m)',
            ),
        ]:
            mesh = ax.pcolormesh(
                x_edges, time_edges, field, cmap=cmap, norm=norm
            )
            fig.colorbar(
                mesh,
                ax=ax,
                label=label,
                extend='both',
                orientation='horizontal',
            )
            ax.set_xlabel('x (km)')
        axes[0].set_ylabel(MODEL_YEAR_LABEL)
        fig.suptitle(
            f'{title}: monthly means along y = {y_row:.1f} km near the '
            f'grounding line'
        )
        fig.savefig(png_filename)


def plot_gl_plan_view(ds_init, ds_mean, gl, title, png_filename):
    """
    Map the water column, the bottom layer's salinity and its temperature
    near the grounding line

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_mean : xarray.Dataset
        The time means from the diagnostics

    gl : tuple of float
        The grounding line (km) at the start and the end

    title : str
        The figure's title

    png_filename : str
        The figure
    """
    ds_mesh = isomip_mesh(ds_init)
    descriptor = mosaic.Descriptor(ds_mesh)
    column = ds_mean.layerThickness.sum(dim='nVertLevels')
    floating = ds_mean.landIceFloatingFraction.values
    x_cell = ds_mesh.xCell.values
    y_cell = ds_mesh.yCell.values
    g0 = min(gl)
    to_km = FuncFormatter(lambda value, _: f'{value / 1e3:g}')
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(figsize=(FIG_WIDTH * 0.8, 9.0), constrained_layout=True)
        axes = fig.subplots(3, 1, sharex=True)
        for ax, field, cmap, norm, label in [
            (
                axes[0],
                column,
                cmocean.cm.deep,
                LogNorm(1.0, 300.0),
                ('water column', 'm'),
            ),
            (
                axes[1],
                ds_mean.salinityBottom,
                cmocean.cm.haline,
                BoundaryNorm(SALINITY_BOUNDS, 256, extend='both'),
                ('bottom-layer salinity', 'PSU'),
            ),
            (
                axes[2],
                ds_mean.temperatureBottom,
                cmocean.cm.thermal,
                BoundaryNorm(TEMPERATURE_BOUNDS, 256, extend='both'),
                ('bottom-layer potential temperature', r'$^\circ$C'),
            ),
        ]:
            name, units = label
            collection = mosaic.polypcolor(
                ax, descriptor, field, cmap=cmap, norm=norm, edgecolor='face'
            )
            ax.tricontour(
                x_cell,
                y_cell,
                floating,
                levels=[0.5],
                colors='w',
                linewidths=0.8,
            )
            fig.colorbar(collection, ax=ax, label=units, extend='both')
            ax.set_title(name)
            ax.set_aspect('equal')
            ax.set_ylabel('y (km)')
            ax.xaxis.set_major_formatter(to_km)
            ax.yaxis.set_major_formatter(to_km)
            ax.set_xlim(1e3 * (g0 + PLAN_RANGE[0]), 1e3 * (g0 + PLAN_RANGE[1]))
            ax.set_ylim(float(y_cell.min()), float(y_cell.max()))
        axes[-1].set_xlabel('x (km)')
        fig.suptitle(f"{title}\nwhite: the ocean's floating fraction is 0.5")
        fig.savefig(png_filename)


def _height_above_bed(ds_transect):
    """The transect with its elevations as heights above the bed"""
    ds = ds_transect.copy()
    seafloor = ds_transect.zSeafloor
    ds['zTransectNode'] = (ds_transect.zTransectNode - seafloor).clip(
        min=MIN_HEIGHT
    )
    for distance, elevation in [
        ('dInterfaceSegment', 'zInterfaceSegment'),
        ('dCellBoundary', 'zCellBoundary'),
    ]:
        bed = np.interp(
            ds_transect[distance].values,
            ds_transect.dNode.values,
            seafloor.values,
        )
        ds[elevation] = (
            ds_transect[elevation]
            - xr.DataArray(bed, dims=ds_transect[distance].dims)
        ).clip(min=MIN_HEIGHT)
    ds['ssh'] = ds_transect.ssh - seafloor
    ds['zSeafloor'] = xr.zeros_like(seafloor) + MIN_HEIGHT
    return ds


def _mark_grounding_lines(ax, gl, xmin):
    """Mark the grounding line at the start, dashed, and the end, solid"""
    for x, linestyle in zip(gl, ['--', '-'], strict=True):
        ax.axvline(x - xmin, color='k', linewidth=0.9, linestyle=linestyle)


def _month_start(month_end):
    """The start (days since 0001-01-01) of the month ending at a day"""
    day_of_year = int(round(month_end)) % 365
    starts = np.cumsum([0] + DAYS_IN_MONTH)
    index = int(np.flatnonzero(starts == day_of_year)[0])
    return month_end - DAYS_IN_MONTH[index - 1]
