"""
A movie of the ocean and MALI along the centerline of a MISOMIP run, one
frame a month: the ocean's monthly-mean temperature and salinity over the
whole domain, under MALI's ice at the end of the month where MALI ran, the
melt the ocean computes and MALI applies on the centerline, and MALI's
thickness change since the start
"""

import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from matplotlib import animation
from matplotlib.figure import Figure
from mpas_tools.ocean.viz.transect import plot_transect

from polaris.constants import get_constant
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    SECONDS_PER_YEAR,
    get_centerline_transect,
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
