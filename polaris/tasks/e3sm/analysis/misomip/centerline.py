"""
A movie of the ocean and MALI along the centerline of a MISOMIP run, one
frame a month: the ocean's monthly-mean temperature and salinity over the
whole domain, under MALI's ice at the end of the month where MALI ran, the
melt the ocean computes and MALI applies on the centerline, and MALI's
thickness change since the start
"""

import cmocean
import mosaic
import numpy as np
import xarray as xr
from matplotlib import animation
from matplotlib.figure import Figure
from mpas_tools.ocean.viz.transect import plot_transect

from polaris.constants import get_constant
from polaris.landice.diagnostics import (
    grounding_line_on_row,
    thickness_above_flotation,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    SECONDS_PER_YEAR,
    get_centerline_transect,
    get_landice_row_from_mesh,
    isomip_mesh,
)
from polaris.viz.animation import SharedPaletteGifWriter
from polaris.viz.style import mplstyle_context

#: The elevations (m) the sections show
ZLIM = (-740.0, 200.0)

#: The distance (km) behind MALI's initial calving front within which its
#: melt and thickness change are left out
FRONT_MARGIN = 3.0

#: The mean layer thickness (m) below which a column holds only the thin
#: film, which the color ranges leave out
THIN_FILM_LAYER = 0.1

#: The distances (km) the snapshot maps extend upstream of the floating ice
#: and downstream of it
MAP_MARGIN_UPSTREAM = 75.0
MAP_MARGIN_DOWNSTREAM = 20.0

#: The spacing (km) of the ticks on the x axis
X_TICK_SPACING = 50.0

FIG_WIDTH = 10.0
LEGEND_SIZE = 10
PNG_DPI = 150
GIF_DPI = 80

MONTH_STARTS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
MONTH_NAMES = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
]


def plot_centerline_movie(
    ds_init,
    ds_centerline,
    y,
    title,
    gif_filename,
    png_filename,
    ds_landice_mesh=None,
    densities=None,
    fps=None,
):
    """
    Plot the movie of the ocean, and of MALI where it ran, along a line of
    constant y, and its last frame

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_centerline : xarray.Dataset
        The ocean on the transect's cells each month, and MALI on its row of
        cells each record and its applied melt each month where it ran, from
        the diagnostics

    y : float
        The line's y (m) in the protocol's coordinates

    title : str
        The start of each frame's title, such as the run's label

    gif_filename : str
        The movie

    png_filename : str
        The last frame

    ds_landice_mesh : xarray.Dataset, optional
        MALI's initial condition, with its mesh, bed and thickness, if MALI
        ran

    densities : tuple of float, optional
        MALI's ice and ocean densities (kg m-3), if MALI ran

    fps : int, optional
        The frames per second; by default 3 for a year of frames and 12 for
        more
    """
    movie = _CenterlineMovie(
        ds_init, ds_centerline, y, title, ds_landice_mesh, densities
    )
    frames = movie.frame_days
    if fps is None:
        fps = 3 if len(frames) <= 12 else 12
    with mplstyle_context(dpi=PNG_DPI):
        movie.draw(frames[-1])
        movie.fig.savefig(png_filename)
        writer = SharedPaletteGifWriter(fps=fps)
        anim = animation.FuncAnimation(
            movie.fig, movie.draw, frames=frames, repeat=False
        )
        anim.save(gif_filename, writer=writer, dpi=GIF_DPI)


class _CenterlineMovie:
    """The data and figure of the movie along the centerline"""

    def __init__(
        self, ds_init, ds_centerline, y, title, ds_landice, densities
    ):
        self.ds_init = ds_init
        self.ds = ds_centerline
        self.y = y
        self.title = title
        self.water_density = get_constant('pure_water_density_reference')
        self.n_cells = ds_init.sizes['nCells']
        self.cells = ds_centerline.transectCell.values

        x_cell = ds_init.xIsomipCell.values
        self.x_start = 1e-3 * float(x_cell.min())
        self.x_end = 1e-3 * float(x_cell.max())

        ds_first = get_centerline_transect(ds_init, ds_init.layerThickness, y)
        self.seg_cells = ds_first.horizCellIndices.values
        self.line_cells = np.unique(self.seg_cells)
        d_node = 1e-3 * ds_first.dNode.values
        self.seg_x = self.x_start + 0.5 * (d_node[:-1] + d_node[1:])

        levels = np.arange(ds_init.sizes['nVertLevels'])
        self.valid = np.logical_and(
            levels >= ds_init.minLevelCell.values[:, np.newaxis] - 1,
            levels <= ds_init.maxLevelCell.values[:, np.newaxis] - 1,
        )

        month_end = np.round(ds_centerline.monthEnd.values, 6)
        self.ocean_index = {day: index for index, day in enumerate(month_end)}
        self.has_landice = (
            ds_landice is not None and 'thickness' in ds_centerline
        )
        if self.has_landice:
            self._init_landice(ds_landice, densities)
            frame_days = [day for day in month_end if day in self.mali_index]
        else:
            frame_days = list(month_end)
        self.frame_days = frame_days
        self._set_limits()

        panels = 4 if self.has_landice else 3
        ratios = [3.0, 3.0, 1.4, 1.4][:panels]
        self.fig = Figure(
            figsize=(FIG_WIDTH, 2.7 * sum(ratios) / 2.0 + 1.0),
            constrained_layout=True,
        )
        grid = self.fig.add_gridspec(panels, 1, height_ratios=ratios)
        self.ax_temp = self.fig.add_subplot(grid[0])
        self.ax_salt = self.fig.add_subplot(grid[1], sharex=self.ax_temp)
        self.ax_melt = self.fig.add_subplot(grid[2], sharex=self.ax_temp)
        self.ax_dh = None
        if self.has_landice:
            self.ax_dh = self.fig.add_subplot(grid[3], sharex=self.ax_temp)
        self.colorbars: dict = dict()

    def _init_landice(self, ds_landice, densities):
        """MALI's row of cells, its initial state there and its records"""
        ds = self.ds
        row = ds.rowCell.values
        self.ice_density, self.ocean_density = densities
        self.x_row = 1e-3 * ds_landice.xCell.values[row]
        self.row_spacing = float(np.median(np.diff(self.x_row)))
        self.bed_row = ds_landice.bedTopography.values[row]
        self.thick0_row = ds_landice.thickness.values[row]
        front_x = float(self.x_row[self.thick0_row > 0.0].max())
        self.away_from_front = self.x_row < front_x - FRONT_MARGIN
        record_time = np.round(ds.recordTime.values, 6)
        # a restart writes the record it starts from again; take the first
        self.mali_index: dict = dict()
        for index, day in enumerate(record_time):
            self.mali_index.setdefault(day, index)
        self.applied_end = None
        if 'appliedMelt' in ds:
            self.applied_end = ds.appliedMonthEnd.values
        self.gl0 = self._grounding_line(self.thick0_row)

    def _full(self, name, day):
        """A field of the ocean in the month ending on a day, on every cell,
        NaN off the transect's cells"""
        values = self.ds[name].isel(Time=self.ocean_index[day]).values
        full = np.full((self.n_cells,) + values.shape[1:], np.nan)
        full[self.cells] = values
        dims = ('nCells', 'nVertLevels')[: full.ndim]
        return xr.DataArray(full, dims=dims)

    def _wet(self, layer_thickness):
        """Valid layers in columns whose mean layer is thicker than the thin
        film's"""
        thickness = np.where(self.valid, layer_thickness.values, np.nan)
        with np.errstate(invalid='ignore'):
            mean_layer = np.nanmean(thickness, axis=1)
            return np.logical_and(
                self.valid, (mean_layer > THIN_FILM_LAYER)[:, np.newaxis]
            )

    def _ocean_melt(self, day):
        """The ocean's melt rate (m yr-1, water equivalent) on the
        transect's segments"""
        flux = self._full('landIceFreshwaterFlux', day).values[self.seg_cells]
        return flux / self.water_density * SECONDS_PER_YEAR

    def _applied_melt(self, day):
        """MALI's applied melt rate (m yr-1, water equivalent) over the
        month ending nearest the day, or None"""
        if self.applied_end is None:
            return None
        index = int(np.argmin(np.abs(self.applied_end - day)))
        melt = self.ds.appliedMelt.isel(nAppliedMonths=index).values
        return melt / self.water_density * SECONDS_PER_YEAR

    def _mali_row(self, name, day):
        """A field of MALI on the row at the record of a day"""
        record = self.mali_index[day]
        return self.ds[name].isel(nLandiceRecords=record).values

    def _grounding_line(self, thick):
        """The downstream edge (km) of the last grounded cell on the row"""
        floating = (
            thick * self.ice_density / self.ocean_density < -self.bed_row
        )
        grounded = np.logical_and(thick > 0.0, ~floating)
        return float(self.x_row[grounded].max()) + 0.5 * self.row_spacing

    def _set_limits(self):
        """Color and axis limits over every frame, so the colors mean the
        same thing throughout"""
        temp_values = []
        salt_values = []
        melt_max = 0.0
        dh_max = 0.0
        for day in self.frame_days:
            layer_thickness = self._full('layerThickness', day)
            wet = self._wet(layer_thickness)[self.line_cells]
            temp = self._full('temperature', day).values[self.line_cells]
            salt = self._full('salinity', day).values[self.line_cells]
            temp_values.append(temp[wet])
            salt_values.append(salt[wet])
            melt_max = max(melt_max, float(np.nanmax(self._ocean_melt(day))))
            if self.has_landice:
                applied = self._applied_melt(day)
                if applied is not None:
                    away = np.where(self.away_from_front, applied, 0.0)
                    melt_max = max(melt_max, float(np.nanmax(away)))
                thick = self._mali_row('thickness', day)
                dh = np.where(
                    (thick > 0.0) & self.away_from_front,
                    thick - self.thick0_row,
                    0.0,
                )
                dh_max = max(dh_max, float(np.max(np.abs(dh))))
        # the full range of temperature, so the restoring region's warm
        # water, a small share of the cells, keeps its color
        temp_all = np.concatenate(temp_values)
        self.temp_range = (
            float(np.nanmin(temp_all)),
            float(np.nanmax(temp_all)),
        )
        self.salt_range = tuple(
            np.nanpercentile(np.concatenate(salt_values), [0.5, 99.5])
        )
        self.melt_max = max(melt_max, 0.1) * 1.1
        self.dh_max = max(dh_max, 0.1) * 1.1

    def _to_transect(self, x):
        """Protocol x (km) to the distance along the transect (km)"""
        return np.asarray(x) - self.x_start

    def _draw_ice(self, ax, thick, lower, gl_x):
        """Draw MALI's ice, the bed and the grounding line on a section"""
        upper = lower + thick
        has_ice = thick > 0.0
        xs = self._to_transect(self.x_row)
        ax.fill_between(
            xs,
            np.where(has_ice, lower, np.nan),
            np.where(has_ice, upper, np.nan),
            color='0.85',
            edgecolor='0.4',
            linewidth=0.6,
            label='MALI ice',
        )
        ax.plot(
            xs, self.bed_row, color='saddlebrown', linewidth=1.0, label='bed'
        )
        ax.axvline(
            self._to_transect(gl_x),
            color='k',
            linestyle='--',
            linewidth=0.8,
            label=f'MALI grounding line, {gl_x:.1f} km',
        )

    def draw(self, day):
        """Draw the frame of the month ending on a day"""
        layer_thickness = self._full('layerThickness', day)
        ds_transect = get_centerline_transect(
            self.ds_init, layer_thickness, self.y
        )
        gl_x = None
        if self.has_landice:
            thick = self._mali_row('thickness', day)
            lower = self._mali_row('lowerSurface', day)
            gl_x = self._grounding_line(thick)
        xlim = self._to_transect([self.x_start, self.x_end])
        for ax, name, value_range, cmap, label in [
            (
                self.ax_temp,
                'temperature',
                self.temp_range,
                'cmo.thermal',
                r'potential temperature ($^\circ$C)',
            ),
            (
                self.ax_salt,
                'salinity',
                self.salt_range,
                'cmo.haline',
                'salinity (PSU)',
            ),
        ]:
            ax.clear()
            # the film is drawn, though the color ranges leave it out
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=self._full(name, day),
                ax=ax,
                vmin=value_range[0],
                vmax=value_range[1],
                cmap=cmap,
                colorbar_label=None,
            )
            if name not in self.colorbars:
                self.colorbars[name] = self.fig.colorbar(
                    ax.collections[0], ax=ax, label=label, extend='both'
                )
            if gl_x is not None:
                self._draw_ice(ax, thick, lower, gl_x)
            ax.set_xlim(*xlim)
            ax.set_ylim(*ZLIM)
            ax.set_ylabel('z (m)')
            ax.set_xlabel('')
            ax.set_title(f'{label.split(" (")[0]}, monthly mean')
        if gl_x is not None:
            # the open ocean above sea level, at the top right, is empty
            self.ax_temp.legend(
                loc='upper right', ncol=3, fontsize=LEGEND_SIZE, framealpha=0.9
            )

        ax = self.ax_melt
        ax.clear()
        ax.step(
            self._to_transect(self.seg_x),
            self._ocean_melt(day),
            where='mid',
            color='tab:blue',
            linewidth=1.2,
            label='ocean, per cell area',
        )
        if self.has_landice:
            applied = self._applied_melt(day)
            if applied is not None:
                ax.plot(
                    self._to_transect(self.x_row),
                    np.where(
                        (self.thick0_row > 0.0) & self.away_from_front,
                        applied,
                        np.nan,
                    ),
                    color='tab:red',
                    linewidth=1.0,
                    label='MALI, applied',
                )
            ax.axvline(
                self._to_transect(gl_x),
                color='k',
                linestyle='--',
                linewidth=0.8,
            )
        ax.set_ylim(0.0, self.melt_max)
        ax.set_ylabel('m yr$^{-1}$')
        ax.set_title(
            'melt rate, water equivalent, on the centerline, monthly mean'
        )
        ax.legend(loc='upper right', fontsize=LEGEND_SIZE)

        axes = [self.ax_temp, self.ax_salt, self.ax_melt]
        if self.ax_dh is not None:
            ax = self.ax_dh
            ax.clear()
            dh = np.where(
                (thick > 0.0) & self.away_from_front,
                thick - self.thick0_row,
                np.nan,
            )
            ax.plot(
                self._to_transect(self.x_row), dh, color='k', linewidth=1.2
            )
            ax.axhline(0.0, color='0.6', linewidth=0.6)
            ax.axvline(
                self._to_transect(gl_x),
                color='k',
                linestyle='--',
                linewidth=0.8,
            )
            ax.axvline(
                self._to_transect(self.gl0),
                color='0.5',
                linestyle=':',
                linewidth=0.8,
                label=f'initial grounding line, {self.gl0:.1f} km',
            )
            ax.set_ylim(-self.dh_max, self.dh_max)
            ax.set_ylabel('m')
            ax.set_title('MALI thickness change since the start')
            ax.legend(loc='upper right', fontsize=LEGEND_SIZE)
            axes.append(ax)
        ticks = np.arange(
            X_TICK_SPACING * np.ceil(self.x_start / X_TICK_SPACING),
            self.x_end + 1.0,
            X_TICK_SPACING,
        )
        for ax in axes:
            ax.set_xticks(self._to_transect(ticks))
            ax.set_xticklabels([f'{x:g}' for x in ticks])
        for ax in axes[:-1]:
            ax.tick_params(labelbottom=False)
        axes[-1].set_xlabel('x (km)')
        self.fig.suptitle(
            f'{self.title} on y = {1e-3 * self.y:g} km: month ending '
            f'{_date_text(day)}'
        )


def _date_text(day):
    """'Year N, Mon D' for days since 0001-01-01 of the 365-day calendar"""
    day = int(round(day))
    year, day_of_year = 1 + day // 365, day % 365
    month = max(m for m in range(12) if MONTH_STARTS[m] <= day_of_year)
    return (
        f'Year {year}, {MONTH_NAMES[month]} '
        f'{day_of_year - MONTH_STARTS[month] + 1}'
    )


def pick_snapshot_days(days, count=5):
    """
    Pick the days of the snapshots: every one for up to ``count``, and
    otherwise ``count`` spread over the run, the first and last included

    Parameters
    ----------
    days : list of float
        The days with snapshots, in order

    count : int, optional
        The most snapshots

    Returns
    -------
    picked : list of float
        The days picked, in order
    """
    days = sorted(days)
    if len(days) <= count:
        return days
    span = days[-1] - days[0]
    picked = set()
    for target in days[0] + np.linspace(0.0, span, count):
        nearest = int(np.argmin(np.abs(np.array(days) - target)))
        picked.add(days[nearest])
    return sorted(picked)


def plot_snapshots(
    ds_init,
    ds_snapshots,
    title,
    png_filename,
    ds_landice_mesh=None,
    densities=None,
):
    """
    Map the melt rate, MALI's thickness change where it ran, and the
    thermal driving at the top cell at a few times spread over the run

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_snapshots : xarray.Dataset
        The snapshots from the diagnostics

    title : str
        The figure's title

    png_filename : str
        The figure

    ds_landice_mesh : xarray.Dataset, optional
        MALI's initial condition, with its mesh, bed and thickness, if MALI
        ran

    densities : tuple of float, optional
        MALI's ice and ocean densities (kg m-3), if MALI ran
    """
    snaps = _Snapshots(ds_init, ds_snapshots, ds_landice_mesh, densities)
    days = snaps.days
    columns = ['melt', 'dh', 'td'] if snaps.has_landice else ['melt', 'td']
    melt_maps = [snaps.melt_map(day) for day in days]
    melt_max = float(
        np.nanpercentile(
            np.concatenate([melt.ravel() for melt in melt_maps]), 99.5
        )
    )
    td_maps = [snaps.thermal_driving(day) for day in days]
    td_max = float(
        np.nanpercentile(np.concatenate([td.ravel() for td in td_maps]), 99.5)
    )
    dh_maps = []
    dh_max = 1e-3
    if snaps.has_landice:
        dh_maps = [snaps.thickness_change(day) for day in days]
        dh_max = max(
            dh_max,
            float(
                np.nanpercentile(
                    np.abs(np.concatenate([dh.ravel() for dh in dh_maps])),
                    99.5,
                )
            ),
        )
    nrow = len(days)
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(
            figsize=(FIG_WIDTH, 1.15 * nrow + 2.0), constrained_layout=True
        )
        axes = fig.subplots(
            nrow, len(columns), sharex=True, sharey=True, squeeze=False
        )
        collections = dict()
        for row, day in enumerate(days):
            for col, column in enumerate(columns):
                ax = axes[row, col]
                if column == 'melt':
                    collections[column] = mosaic.polypcolor(
                        ax,
                        snaps.ocean_descriptor,
                        melt_maps[row],
                        cmap=cmocean.cm.amp,
                        vmin=0.0,
                        vmax=melt_max,
                        edgecolor='face',
                    )
                elif column == 'dh':
                    collections[column] = mosaic.polypcolor(
                        ax,
                        snaps.landice_descriptor,
                        dh_maps[row],
                        cmap=cmocean.cm.balance_r,
                        vmin=-dh_max,
                        vmax=dh_max,
                        edgecolor='face',
                    )
                else:
                    collections[column] = mosaic.polypcolor(
                        ax,
                        snaps.ocean_descriptor,
                        td_maps[row],
                        cmap=cmocean.cm.thermal,
                        vmin=0.0,
                        vmax=td_max,
                        edgecolor='face',
                    )
                if snaps.has_landice:
                    snaps.draw_grounding_line(ax, day)
                ax.set_xlim(*snaps.map_xlim)
                ax.set_ylim(snaps.y_min, snaps.y_max)
                ax.set_aspect('equal')
            axes[row, 0].set_ylabel('y (km)')
            axes[row, 0].text(
                0.02,
                0.95,
                _date_text(day),
                transform=axes[row, 0].transAxes,
                va='top',
                ha='left',
                fontsize=LEGEND_SIZE,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.8),
            )
        titles = dict(
            melt='melt rate',
            dh='MALI thickness change',
            td='top-cell thermal driving',
        )
        labels = dict(
            melt='melt rate, water equivalent (m yr$^{-1}$)',
            dh='m since the start',
            td=r'$^\circ$C',
        )
        for col, column in enumerate(columns):
            axes[0, col].set_title(titles[column])
            axes[-1, col].set_xlabel('x (km)')
            fig.colorbar(
                collections[column],
                ax=axes[:, col],
                label=labels[column],
                orientation='horizontal',
                shrink=0.9,
            )
        fig.suptitle(title)
        fig.savefig(png_filename)


def plot_centerline_sections(
    ds_init,
    ds_snapshots,
    y,
    title,
    png_filename,
    ds_landice_mesh=None,
    densities=None,
):
    """
    Plot the temperature along a line of constant y, under MALI's ice where
    it ran, at a few times spread over the run

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_snapshots : xarray.Dataset
        The snapshots from the diagnostics

    y : float
        The line's y (m) in the protocol's coordinates

    title : str
        The figure's title

    png_filename : str
        The figure

    ds_landice_mesh : xarray.Dataset, optional
        MALI's initial condition, with its mesh, bed and thickness, if MALI
        ran

    densities : tuple of float, optional
        MALI's ice and ocean densities (kg m-3), if MALI ran
    """
    snaps = _Snapshots(ds_init, ds_snapshots, ds_landice_mesh, densities)
    days = snaps.days
    transects = []
    temps = []
    for day in days:
        thickness, temperature = snaps.section_fields(day)
        transects.append(get_centerline_transect(ds_init, thickness, y))
        temps.append(temperature)
    line_cells = np.unique(
        np.concatenate([ds.horizCellIndices.values for ds in transects])
    )
    values = np.concatenate(
        [temp.values[line_cells].ravel() for temp in temps]
    )
    t_min = float(np.nanmin(values))
    t_max = float(np.nanmax(values))
    if snaps.has_landice:
        row = get_landice_row_from_mesh(snaps.ds_landice, y)
        x_row = 1e-3 * snaps.ds_landice.xCell.values[row]
        bed_row = snaps.ds_landice.bedTopography.values[row]
    nrow = len(days)
    ticks = np.arange(
        X_TICK_SPACING * np.ceil(snaps.x_start / X_TICK_SPACING),
        snaps.x_end + 1.0,
        X_TICK_SPACING,
    )
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(
            figsize=(FIG_WIDTH, 2.2 * nrow + 1.2), constrained_layout=True
        )
        axes = fig.subplots(nrow, 1, sharex=True, squeeze=False)
        for index, day in enumerate(days):
            ax = axes[index, 0]
            plot_transect(
                ds_transect=transects[index],
                mpas_field=temps[index],
                ax=ax,
                vmin=t_min,
                vmax=t_max,
                cmap='cmo.thermal',
                colorbar_label=None,
            )
            if snaps.has_landice:
                thick = snaps.landice_thickness(day)[row]
                flotation = -snaps.ice_density / snaps.ocean_density * thick
                lower = np.maximum(bed_row, flotation)
                upper = lower + thick
                has_ice = thick > 0.0
                xs = x_row - snaps.x_start
                ax.fill_between(
                    xs,
                    np.where(has_ice, lower, np.nan),
                    np.where(has_ice, upper, np.nan),
                    color='0.85',
                    edgecolor='0.4',
                    linewidth=0.6,
                    label='MALI ice',
                )
                ax.plot(
                    xs,
                    bed_row,
                    color='saddlebrown',
                    linewidth=1.0,
                    label='bed',
                )
                gl = 1e-3 * snaps.grounding_line_on_row(day, y)
                ax.axvline(
                    gl - snaps.x_start,
                    color='k',
                    linestyle='--',
                    linewidth=0.8,
                    label=f'MALI grounding line, {gl:.3f} km',
                )
                # the open ocean above sea level, at the top right, is empty
                ax.legend(
                    loc='upper right',
                    ncol=3,
                    fontsize=LEGEND_SIZE,
                    framealpha=0.9,
                )
            ax.set_xlim(0.0, snaps.x_end - snaps.x_start)
            ax.set_ylim(*ZLIM)
            ax.set_ylabel('z (m)')
            ax.set_xlabel('')
            ax.text(
                0.01,
                0.04,
                _date_text(day),
                transform=ax.transAxes,
                va='bottom',
                ha='left',
                fontsize=LEGEND_SIZE,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.8),
            )
            ax.set_xticks(ticks - snaps.x_start)
            ax.set_xticklabels([f'{x:g}' for x in ticks])
        axes[0, 0].set_title(title)
        axes[-1, 0].set_xlabel('x (km)')
        fig.colorbar(
            axes[0, 0].collections[0],
            ax=axes[:, 0],
            label=r'potential temperature ($^\circ$C)',
            shrink=0.6,
        )
        fig.savefig(png_filename)


class _Snapshots:
    """The ocean, and MALI where it ran, at the snapshots picked"""

    def __init__(self, ds_init, ds, ds_landice, densities):
        self.ds_init = ds_init
        self.ds = ds
        self.n_cells = ds_init.sizes['nCells']
        self.water_density = get_constant('pure_water_density_reference')
        x_cell = 1e-3 * ds_init.xIsomipCell.values
        y_cell = 1e-3 * ds_init.yIsomipCell.values
        self.x_start = float(x_cell.min())
        self.x_end = float(x_cell.max())
        self.y_min = float(y_cell.min())
        self.y_max = float(y_cell.max())
        # the maps show the floating ice, from upstream of its grounding
        # line to just past its front
        floating = ds_init.landIceFloatingFraction.values > 0.0
        self.map_xlim = (
            float(x_cell[floating].min()) - MAP_MARGIN_UPSTREAM,
            float(x_cell[floating].max()) + MAP_MARGIN_DOWNSTREAM,
        )
        ocean_mesh = isomip_mesh(ds_init)
        for name in ['xCell', 'yCell', 'xVertex', 'yVertex']:
            ocean_mesh[name] = 1e-3 * ocean_mesh[name]
        self.ocean_descriptor = mosaic.Descriptor(ocean_mesh)
        ocean_days = np.round(ds.snapshotTime.values, 6)
        self.has_landice = (
            ds_landice is not None and 'landiceSnapshotTime' in ds
        )
        if self.has_landice:
            self.ds_landice = ds_landice
            self.ice_density, self.ocean_density = densities
            landice_mesh = ds_landice.copy()
            for name in ['xCell', 'yCell', 'xVertex', 'yVertex']:
                landice_mesh[name] = 1e-3 * landice_mesh[name]
            landice_mesh.attrs.update(on_a_sphere='NO', is_periodic='NO')
            self.landice_descriptor = mosaic.Descriptor(landice_mesh)
            landice_days = np.round(ds.landiceSnapshotTime.values, 6)
            self.landice_index = {
                day: index for index, day in enumerate(landice_days)
            }
            days = [day for day in ocean_days if day in self.landice_index]
        else:
            days = list(ocean_days)
        self.ocean_index = {day: index for index, day in enumerate(ocean_days)}
        self.days = pick_snapshot_days(days)

    def _snapshot(self, day):
        return self.ds.isel(nSnapshots=self.ocean_index[day])

    def melt_map(self, day):
        """The melt rate (m yr-1, water equivalent) over the day ending at
        the snapshot, where the ice floats"""
        snapshot = self._snapshot(day)
        if 'meltDayFlux' not in snapshot:
            return np.full(self.n_cells, np.nan)
        melt = snapshot.meltDayFlux.values / self.water_density
        floating = snapshot.landIceFloatingFraction.values > 0.0
        return np.where(floating, melt * SECONDS_PER_YEAR, np.nan)

    def thermal_driving(self, day):
        """The thermal driving at the top cell where the ice floats"""
        snapshot = self._snapshot(day)
        floating = snapshot.landIceFloatingFraction.values > 0.0
        return np.where(floating, snapshot.thermalDriving.values, np.nan)

    def section_fields(self, day):
        """The layer thickness and the temperature, where the column is more
        than the thin film, on every cell, NaN off the transect's cells"""
        snapshot = self._snapshot(day)
        cells = self.ds.transectCell.values
        thickness = np.full(
            (self.n_cells, self.ds.sizes['nVertLevels']), np.nan
        )
        temperature = np.full_like(thickness, np.nan)
        thickness[cells] = snapshot.layerThicknessSection.values
        temperature[cells] = snapshot.temperatureSection.values
        levels = np.arange(self.ds.sizes['nVertLevels'])
        valid = np.logical_and(
            levels >= self.ds_init.minLevelCell.values[:, np.newaxis] - 1,
            levels <= self.ds_init.maxLevelCell.values[:, np.newaxis] - 1,
        )
        with np.errstate(invalid='ignore'):
            mean_layer = np.nanmean(np.where(valid, thickness, np.nan), axis=1)
        wet = np.logical_and(
            valid, (mean_layer > THIN_FILM_LAYER)[:, np.newaxis]
        )
        dims = ('nCells', 'nVertLevels')
        return (
            xr.DataArray(thickness, dims=dims),
            xr.DataArray(np.where(wet, temperature, np.nan), dims=dims),
        )

    def landice_thickness(self, day):
        """MALI's thickness at the snapshot"""
        index = self.landice_index[day]
        return self.ds.thickness.isel(nLandiceSnapshots=index).values

    def _haf(self, day):
        thickness = xr.DataArray(self.landice_thickness(day), dims='nCells')
        return thickness_above_flotation(
            thickness,
            self.ds_landice.bedTopography,
            self.ice_density,
            self.ocean_density,
        )

    def thickness_change(self, day):
        """MALI's thickness change since the start, away from its initial
        calving front"""
        thick = self.landice_thickness(day)
        thick0 = self.ds_landice.thickness.values
        x_mali = 1e-3 * self.ds_landice.xCell.values
        front_x = float(x_mali[thick0 > 0.0].max())
        away = x_mali < front_x - FRONT_MARGIN
        return np.where((thick > 0.0) & away, thick - thick0, np.nan)

    def draw_grounding_line(self, ax, day):
        """The grounding line and the calving front at the snapshot, and
        the initial grounding line"""
        x_mali = 1e-3 * self.ds_landice.xCell.values
        y_mali = 1e-3 * self.ds_landice.yCell.values
        thick = self.landice_thickness(day)
        haf = np.where(thick > 0.0, self._haf(day).values, -1.0)
        ax.tricontour(
            x_mali, y_mali, haf, levels=[0.0], colors='k', linewidths=1.0
        )
        thick0 = self.ds_landice.thickness.values
        haf0 = np.where(
            thick0 > 0.0,
            thickness_above_flotation(
                self.ds_landice.thickness,
                self.ds_landice.bedTopography,
                self.ice_density,
                self.ocean_density,
            ).values,
            -1.0,
        )
        ax.tricontour(
            x_mali,
            y_mali,
            haf0,
            levels=[0.0],
            colors='0.5',
            linewidths=0.8,
            linestyles='--',
        )
        ax.tricontour(
            x_mali,
            y_mali,
            thick,
            levels=[1.0],
            colors='k',
            linewidths=0.6,
            linestyles=':',
        )

    def grounding_line_on_row(self, day, y):
        """The grounding line (m) on a line of constant y at the snapshot"""
        return float(
            grounding_line_on_row(
                self._haf(day).expand_dims('Time'), self.ds_landice, y=y
            ).values[0]
        )


def plot_melt_movie(ds_init, ds_melt, title, gif_filename, max_frames=180):
    """
    Animate the ocean's daily-mean melt rate under the ice, the thin film
    included, with MALI's grounding line where it ran

    Parameters
    ----------
    ds_init : xarray.Dataset
        The ocean's initial condition and mesh

    ds_melt : xarray.Dataset
        The daily melt on the cells under the ice and MALI's grounding-line
        points, from the diagnostics

    title : str
        The start of each frame's title, such as the run's label

    gif_filename : str
        The movie

    max_frames : int, optional
        The most frames, spread evenly over the days, the last included
    """
    water_density = get_constant('pure_water_density_reference')
    n_cells = ds_init.sizes['nCells']
    ice_cells = ds_melt.iceCell.values
    melt = ds_melt.meltFlux.values / water_density * SECONDS_PER_YEAR
    day_end = ds_melt.dayEnd.values
    # the scale leaves out the first day, whose start-up melt can be far
    # larger
    later = melt[1:] if melt.shape[0] > 1 else melt
    melt_max = float(np.nanpercentile(later, 99.5))
    has_gl = 'glStateTime' in ds_melt
    if has_gl:
        gl_time = ds_melt.glStateTime.values
    stride = max(1, int(np.ceil(len(day_end) / max_frames)))
    frames = list(range(0, len(day_end), stride))
    if frames[-1] != len(day_end) - 1:
        frames.append(len(day_end) - 1)
    floating = ds_init.landIceFloatingFraction.values > 0.0
    x_cell = 1e-3 * ds_init.xIsomipCell.values
    y_cell = 1e-3 * ds_init.yIsomipCell.values
    ocean_mesh = isomip_mesh(ds_init)
    for name in ['xCell', 'yCell', 'xVertex', 'yVertex']:
        ocean_mesh[name] = 1e-3 * ocean_mesh[name]
    descriptor = mosaic.Descriptor(ocean_mesh)

    def melt_map(index):
        # every cell under the ice, the thin film included, so the melt
        # follows a grounding line that moves away from where it started
        full = np.full(n_cells, np.nan)
        full[ice_cells] = melt[index]
        return full

    xlim = (
        float(x_cell[floating].min()) - MAP_MARGIN_UPSTREAM,
        float(x_cell[floating].max()) + MAP_MARGIN_DOWNSTREAM,
    )
    ylim = (float(y_cell.min()), float(y_cell.max()))
    # the figure has the map's aspect, so the map fills its width
    map_width = 0.92 * FIG_WIDTH
    height = map_width * (ylim[1] - ylim[0]) / (xlim[1] - xlim[0]) + 2.0
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(figsize=(FIG_WIDTH, height), constrained_layout=True)
        ax = fig.add_subplot(111)
        collection = mosaic.polypcolor(
            ax,
            descriptor,
            melt_map(0),
            cmap=cmocean.cm.amp,
            vmin=0.0,
            vmax=melt_max,
            edgecolor='face',
        )
        fig.colorbar(
            collection,
            ax=ax,
            label='m yr$^{-1}$',
            orientation='horizontal',
            shrink=0.5,
            pad=0.25,
        )
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect('equal')
        ax.set_xlabel('x (km)')
        ax.set_ylabel('y (km)')
        # lay the figure out once, with the longest title, and keep that
        # layout, so the map and colorbar do not move from frame to frame
        ax.set_title(
            f'{title}: daily-mean melt rate, water equivalent, Year 10000, '
            f'Mmm 30'
        )
        fig.canvas.draw()
        fig.set_layout_engine('none')
        (gl_line,) = ax.plot([], [], 'k.', markersize=1.0)

        def frame(index):
            collection.set_array(melt_map(index))
            if has_gl:
                # MALI's last state at or before the end of the day
                state = int(
                    np.searchsorted(gl_time, day_end[index] + 1e-6) - 1
                )
                state = max(state, 0)
                gl_line.set_data(
                    1e-3 * ds_melt.xGroundingLinePoints.values[state],
                    1e-3 * ds_melt.yGroundingLinePoints.values[state],
                )
            ax.set_title(
                f'{title}: daily-mean melt rate, water equivalent, '
                f'{_date_text(day_end[index] - 1.0)}'
            )
            return [collection, gl_line]

        anim = animation.FuncAnimation(fig, frame, frames=frames)
        anim.save(
            gif_filename,
            writer=SharedPaletteGifWriter(fps=4 if len(frames) <= 40 else 12),
            dpi=GIF_DPI,
        )
