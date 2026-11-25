"""
A movie of the ocean and MALI along the centerline of a MISOMIP run, one
frame a month: the ocean's monthly-mean temperature and salinity over the
whole domain, under MALI's ice at the end of the month where MALI ran, the
melt the ocean computes and MALI applies on the centerline, and MALI's
thickness change since the start
"""

from dataclasses import dataclass

import cmocean
import mosaic
import numpy as np
import xarray as xr
from matplotlib import animation
from matplotlib.collections import QuadMesh
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from mpas_tools.ocean.viz.transect import plot_transect

from polaris.constants import get_constant
from polaris.e3sm.analysis.calendar import days_to_date
from polaris.landice.diagnostics import (
    grounding_line_on_row,
    thickness_above_flotation,
)
from polaris.tasks.e3sm.analysis.misomip.colors import (
    get_signed_colors,
    get_signed_range,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import (
    SECONDS_PER_YEAR,
    get_centerline_transect,
    get_landice_row_from_mesh,
    isomip_mesh,
)
from polaris.tasks.e3sm.analysis.misomip.wet_dry import (
    WET_DRY_COLORS,
    WET_DRY_LABELS,
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

#: The share of a cell ice must cover for the thermal driving at its top
#: cell to be shown: mostly open cells at the ice's edges take the freezing
#: point of the surface from their small cell-mean ice pressure
MOSTLY_ICE_FRACTION = 0.5

#: The caption of the cells a thermal-driving map leaves out
MOSTLY_ICE_LABEL = (
    f'thermal driving only where ice covers at least '
    f'{MOSTLY_ICE_FRACTION:.0%} of the cell'
)

#: The title of the map of melt plus frazil, by where it comes from: what
#: MALI applies to its floating ice, or, where MALI does not evolve, what
#: the ocean sends to MALI
MELT_FRAZIL_TITLES = {
    'mali': 'melt + frazil, applied by MALI',
    'ocean': 'melt + frazil, sent by the ocean',
}

#: The spacing (km) of the ticks on the x axis
X_TICK_SPACING = 50.0

FIG_WIDTH = 10.0
LEGEND_SIZE = 10
PNG_DPI = 150
GIF_DPI = 80

MONTH_STARTS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


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
    colors=None,
):
    """
    Plot the movie of the ocean, and of MALI where it ran, along a line of
    constant y, and its last frame.  MALI's thickness change has a panel
    where its ice changes.

    Each month of the ocean is a frame, with MALI's latest record at or
    before the month's end, which is MALI's geometry over the month where
    it is static or prescribed.

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

    colors : SectionColors, optional
        The colors of temperature and salinity, from the data where not
        given
    """
    movie = _CenterlineMovie(
        ds_init, ds_centerline, y, title, ds_landice_mesh, densities, colors
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


@dataclass
class SectionColors:
    """
    The colors of the sections of temperature and salinity, the same in
    every run

    Attributes
    ----------
    temperature_range : tuple of float or None
        The range of temperature (degC), from the data if ``None``

    salinity_range : tuple of float or None
        The range of salinity (PSU), from the data if ``None`` and there is
        no norm

    salinity_norm : matplotlib.colors.Normalize or None
        The norm of salinity's colors in uneven bins, in place of its range

    salinity_ticks : list of float or None
        The ticks of salinity's color bar
    """

    temperature_range: tuple | None = None
    salinity_range: tuple | None = None
    salinity_norm: Normalize | None = None
    salinity_ticks: list | None = None


def pick_landice_records(days, record_days):
    """
    Pick MALI's record for each day: the latest at or before it, and the
    first written of records at the same time, as a restart writes the
    record it starts from again

    Parameters
    ----------
    days : list of float
        The days, such as the ends of the ocean's months, in days since
        0001-01-01

    record_days : numpy.ndarray
        The times of MALI's records, in days since 0001-01-01

    Returns
    -------
    records : dict of float to int
        The index of each day's record, leaving out the days before MALI's
        first record
    """
    first: dict = dict()
    for index, day in enumerate(np.round(record_days, 6)):
        first.setdefault(float(day), index)
    times = np.array(sorted(first))
    records = dict()
    for day in days:
        position = np.searchsorted(times, day + 1e-6, side='right') - 1
        if position >= 0:
            records[day] = first[float(times[position])]
    return records


class _CenterlineMovie:
    """The data and figure of the movie along the centerline"""

    def __init__(
        self, ds_init, ds_centerline, y, title, ds_landice, densities, colors
    ):
        self.colors = SectionColors() if colors is None else colors
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
            self.mali_index = pick_landice_records(
                list(month_end), ds_centerline.recordTime.values
            )
            frame_days = [day for day in month_end if day in self.mali_index]
        else:
            frame_days = list(month_end)
        self.frame_days = frame_days
        self._set_limits()

        panels = 4 if self.ice_changes else 3
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
        if self.ice_changes:
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
        """The melt + frazil MALI applies (m yr-1, water equivalent) over
        the month ending nearest the day, or None"""
        if self.applied_end is None:
            return None
        index = int(np.argmin(np.abs(self.applied_end - day)))
        melt = self.ds.appliedMelt.isel(nAppliedMonths=index).values
        return melt / self.water_density * SECONDS_PER_YEAR

    def _mali_row(self, name, day):
        """A field of MALI on the row at its record for a day"""
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
        melt_min = 0.0
        dh_max = 0.0
        for day in self.frame_days:
            layer_thickness = self._full('layerThickness', day)
            wet = self._wet(layer_thickness)[self.line_cells]
            temp = self._full('temperature', day).values[self.line_cells]
            salt = self._full('salinity', day).values[self.line_cells]
            temp_values.append(temp[wet])
            salt_values.append(salt[wet])
            ocean_melt = self._ocean_melt(day)
            melt_max = max(melt_max, float(np.nanmax(ocean_melt)))
            melt_min = min(melt_min, float(np.nanmin(ocean_melt)))
            if self.has_landice:
                applied = self._applied_melt(day)
                if applied is not None:
                    away = np.where(self.away_from_front, applied, 0.0)
                    melt_max = max(melt_max, float(np.nanmax(away)))
                    melt_min = min(melt_min, float(np.nanmin(away)))
                thick = self._mali_row('thickness', day)
                dh = np.where(
                    (thick > 0.0) & self.away_from_front,
                    thick - self.thick0_row,
                    0.0,
                )
                dh_max = max(dh_max, float(np.max(np.abs(dh))))
        colors = self.colors
        if colors.temperature_range is not None:
            self.temp_range = tuple(colors.temperature_range)
        else:
            # the full range of temperature, so the restoring region's warm
            # water, a small share of the cells, keeps its color
            temp_all = np.concatenate(temp_values)
            self.temp_range = (
                float(np.nanmin(temp_all)),
                float(np.nanmax(temp_all)),
            )
        if colors.salinity_norm is not None:
            norm = colors.salinity_norm
            self.salt_range = (norm.vmin, norm.vmax)
        elif colors.salinity_range is not None:
            self.salt_range = tuple(colors.salinity_range)
        else:
            self.salt_range = tuple(
                np.nanpercentile(np.concatenate(salt_values), [0.5, 99.5])
            )
        self.melt_max = max(melt_max, 0.1) * 1.1
        # freezing, if any, shows below zero
        self.melt_min = 1.1 * melt_min
        self.dh_max = max(dh_max, 0.1) * 1.1
        # MALI's thickness change is left out where its ice never changes,
        # as when MALI is static
        self.ice_changes = dh_max > 0.0

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
            mesh = next(
                child
                for child in ax.collections
                if isinstance(child, QuadMesh)
            )
            ticks = None
            if name == 'salinity' and self.colors.salinity_norm is not None:
                mesh.set_norm(self.colors.salinity_norm)
                ticks = self.colors.salinity_ticks
            if name not in self.colorbars:
                self.colorbars[name] = self.fig.colorbar(
                    mesh, ax=ax, label=label, extend='both', ticks=ticks
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
            label='melt, ocean, per cell area',
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
                    label='melt + frazil, applied by MALI',
                )
            ax.axvline(
                self._to_transect(gl_x),
                color='k',
                linestyle='--',
                linewidth=0.8,
            )
        ax.axhline(0.0, color='0.5', linewidth=0.6)
        ax.set_ylim(self.melt_min, self.melt_max)
        ax.set_ylabel('m yr$^{-1}$')
        ax.set_title(
            'melt rate, water equivalent, on the centerline, monthly mean '
            '(negative for freezing)'
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


class _MeltMovieLayout:
    """
    Where the melt movie's maps, colorbar and legend go: both maps the
    same size, one above the other, so their cells line up, with the
    colorbar and legend below them, outside the maps

    Each rectangle is (left, bottom, width, height), in fractions of the
    figure
    """

    # inches
    LEFT = 0.8
    RIGHT = 0.3
    TITLE = 0.45
    AXIS_LABELS = 0.65
    COLORBAR = 0.15
    COLORBAR_LABELS = 0.6
    LEGEND = 0.55
    BOTTOM = 0.1

    def __init__(self, aspect, has_wet_dry):
        """
        Lay the movie out

        Parameters
        ----------
        aspect : float
            The maps' height over their width
        has_wet_dry : bool
            Whether there is a map of wet and dry cells below the melt
        """
        width = FIG_WIDTH - self.LEFT - self.RIGHT
        map_height = width * aspect
        # from the top down
        tops = []
        top = 0.0
        for size in [
            self.TITLE,
            map_height,
            self.AXIS_LABELS,
            self.COLORBAR,
            self.COLORBAR_LABELS,
        ]:
            tops.append(top)
            top += size
        if has_wet_dry:
            for size in [self.TITLE, map_height, self.AXIS_LABELS]:
                tops.append(top)
                top += size
            legend_top = top
            top += self.LEGEND
        self.height = top + self.BOTTOM

        def rect(top, height, left=self.LEFT, rect_width=width):
            return (
                left / FIG_WIDTH,
                1.0 - (top + height) / self.height,
                rect_width / FIG_WIDTH,
                height / self.height,
            )

        self.melt_map = rect(tops[1], map_height)
        # the colorbar half as wide as the maps, centered below them
        self.colorbar = rect(
            tops[3], self.COLORBAR, self.LEFT + 0.25 * width, 0.5 * width
        )
        self.wet_dry_map = None
        self.legend_anchor = None
        if has_wet_dry:
            self.wet_dry_map = rect(tops[6], map_height)
            self.legend_anchor = (
                (self.LEFT + 0.5 * width) / FIG_WIDTH,
                1.0 - legend_top / self.height,
            )


class _WetDryPanel:
    """A map, below the melt's, of the cells the ocean treats as wet or
    dry, with MALI's grounding line on top"""

    def __init__(self, fig, layout, descriptor, wet_dry, title, xlim, ylim):
        self.wet_dry = wet_dry
        self.title = title
        self.ax = fig.add_axes(layout.wet_dry_map)
        n_cells = wet_dry.classes.shape[1]
        cmap = ListedColormap(WET_DRY_COLORS)
        cmap.set_bad('white')
        norm = BoundaryNorm(np.arange(len(WET_DRY_COLORS) + 1) - 0.5, cmap.N)
        self.collection = mosaic.polypcolor(
            self.ax,
            descriptor,
            np.full(n_cells, np.nan),
            cmap=cmap,
            norm=norm,
            edgecolor='face',
        )
        handles = [
            Patch(facecolor=color, label=label)
            for color, label in zip(
                WET_DRY_COLORS, WET_DRY_LABELS, strict=True
            )
        ]
        fig.legend(
            handles=handles,
            loc='upper center',
            bbox_to_anchor=layout.legend_anchor,
            ncols=2,
            fontsize='small',
            frameon=False,
        )
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        self.ax.set_aspect('equal')
        self.ax.set_xlabel('x (km)')
        self.ax.set_ylabel('y (km)')
        (self.gl_line,) = self.ax.plot([], [], 'k.', markersize=1.0)

    def update(self, day, gl_line):
        """Show the state holding on a day and the melt panel's grounding
        line"""
        index = self.wet_dry.state_at(day)
        if index is None:
            values = np.full(self.wet_dry.classes.shape[1], np.nan)
            first = days_to_date(self.wet_dry.start_days[0])
            label = f'no snapshot until {first}'
        else:
            values = self.wet_dry.classes[index].astype(float)
            label = self.wet_dry.labels[index]
        self.collection.set_array(values)
        self.gl_line.set_data(*gl_line.get_data())
        self.ax.set_title(f'{self.title}: wet or dry, {label}')
        return [self.collection, self.gl_line]


def _date_text(day):
    """
    'YYYY-MM-DD' for days since 0001-01-01 of the 365-day calendar, all
    numbers so an animation's title keeps its width from frame to frame
    """
    day = int(round(day))
    year, day_of_year = 1 + day // 365, day % 365
    month = max(m for m in range(12) if MONTH_STARTS[m] <= day_of_year)
    return (
        f'{year:04d}-{month + 1:02d}-'
        f'{day_of_year - MONTH_STARTS[month] + 1:02d}'
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
    Map the melt rate, the melt plus the frazil under the ice where MALI
    ran, MALI's thickness change where its ice changes, and the thermal
    driving at the top cell at a few times spread over the run.  Melt and
    thermal driving keep their sign: freezing is blue, and water below its
    freezing point has colors of its own.

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
    maps = dict(
        melt=[snaps.melt_map(day) for day in days],
        td=[snaps.thermal_driving(day) for day in days],
    )
    if snaps.has_landice:
        maps['dh'] = [snaps.thickness_change(day) for day in days]
    # MALI's thickness change is left out where its ice never changes, as
    # when MALI is static
    ice_changes = 'dh' in maps and any(
        np.any(np.nan_to_num(dh) != 0.0) for dh in maps['dh']
    )
    columns = ['melt']
    if snaps.melt_frazil_source is not None:
        columns.append('melt_frazil')
    if ice_changes:
        columns.append('dh')
    columns.append('td')
    if 'melt_frazil' in columns:
        maps['melt_frazil'] = [snaps.melt_frazil_map(day) for day in days]
    colors = dict()
    # melt and melt plus frazil share their colors, so they compare
    melt_kinds = [kind for kind in ['melt', 'melt_frazil'] if kind in maps]
    melt_arrays = [array for kind in melt_kinds for array in maps[kind]]
    melt_colors = get_signed_colors('melt', *get_signed_range(melt_arrays))
    for kind in melt_kinds:
        colors[kind] = melt_colors
    colors['td'] = get_signed_colors(
        'thermal_driving', *get_signed_range(maps['td'])
    )
    dh_max = 1e-3
    if ice_changes:
        dh_max = max(
            dh_max,
            float(
                np.nanpercentile(
                    np.abs(np.concatenate([dh.ravel() for dh in maps['dh']])),
                    99.5,
                )
            ),
        )
    nrow = len(days)
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(
            figsize=(
                FIG_WIDTH * max(len(columns), 3) / 3.0,
                1.15 * nrow + 2.0,
            ),
            constrained_layout=True,
        )
        axes = fig.subplots(
            nrow, len(columns), sharex=True, sharey=True, squeeze=False
        )
        collections = dict()
        for row, day in enumerate(days):
            for col, column in enumerate(columns):
                ax = axes[row, col]
                on_landice = column == 'dh' or (
                    column == 'melt_frazil'
                    and snaps.melt_frazil_source == 'mali'
                )
                descriptor = (
                    snaps.landice_descriptor
                    if on_landice
                    else snaps.ocean_descriptor
                )
                if column == 'dh':
                    style = dict(
                        cmap=cmocean.cm.balance_r, vmin=-dh_max, vmax=dh_max
                    )
                else:
                    cmap, norm, _ = colors[column]
                    style = dict(cmap=cmap, norm=norm)
                collections[column] = mosaic.polypcolor(
                    ax,
                    descriptor,
                    maps[column][row],
                    edgecolor='face',
                    **style,
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
        melt_label = 'm yr$^{-1}$, water equivalent\n(negative: freezing)'
        titles = dict(
            melt='melt rate (no frazil)',
            melt_frazil=MELT_FRAZIL_TITLES.get(snaps.melt_frazil_source or ''),
            dh='MALI thickness change',
            td='top-cell thermal driving',
        )
        labels = dict(
            melt=melt_label,
            melt_frazil=melt_label,
            dh='m since the start',
            td=r'$^\circ$C',
        )
        for col, column in enumerate(columns):
            axes[0, col].set_title(titles[column])
            axes[-1, col].set_xlabel('x (km)')
            ticks = None if column == 'dh' else colors[column][2]
            fig.colorbar(
                collections[column],
                ax=axes[:, col],
                label=labels[column],
                orientation='horizontal',
                shrink=0.9,
                ticks=ticks,
                extend='both' if column != 'dh' else 'neither',
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
    temperature_range=None,
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

    temperature_range : tuple of float, optional
        The range of temperature (degC), from the data by default
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
    if temperature_range is not None:
        t_min, t_max = temperature_range
    else:
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
        # the ice's cover in the initial condition: the melt is shown on
        # every cell under it, the thin film included, and the thermal
        # driving where it covers most of the cell
        self.ice_fraction = ds_init.landIceFraction.values
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
        # melt plus frazil is for runs with MALI: what MALI applies where
        # it wrote it, otherwise what the ocean computes under the ice
        self.melt_frazil_source = None
        if self.has_landice and 'appliedBasalMassBal' in ds:
            self.melt_frazil_source = 'mali'
        elif self.has_landice and 'meltFrazilDayFlux' in ds:
            self.melt_frazil_source = 'ocean'

    def _snapshot(self, day):
        return self.ds.isel(nSnapshots=self.ocean_index[day])

    def melt_map(self, day):
        """The melt rate (m yr-1, water equivalent) over the day ending at
        the snapshot, under the ice, the thin film included"""
        snapshot = self._snapshot(day)
        if 'meltDayFlux' not in snapshot:
            return np.full(self.n_cells, np.nan)
        melt = snapshot.meltDayFlux.values / self.water_density
        under_ice = self.ice_fraction > 0.0
        return np.where(under_ice, melt * SECONDS_PER_YEAR, np.nan)

    def melt_frazil_map(self, day):
        """The melt plus the frazil under the ice (m yr-1, water
        equivalent), positive out of the ice: on MALI's mesh, what MALI
        applies to its ice at the snapshot; otherwise on the ocean's, over
        the day ending at the snapshot under the ice, the thin film
        included"""
        if self.melt_frazil_source == 'mali':
            index = self.landice_index[day]
            applied = self.ds.appliedBasalMassBal.isel(
                nLandiceSnapshots=index
            ).values
            under_ice = self.landice_thickness(day) > 0.0
            flux = -applied
        else:
            snapshot = self._snapshot(day)
            under_ice = self.ice_fraction > 0.0
            flux = snapshot.meltFrazilDayFlux.values
        flux = flux / self.water_density * SECONDS_PER_YEAR
        return np.where(under_ice, flux, np.nan)

    def thermal_driving(self, day):
        """The thermal driving at the top cell where ice covers most of
        the cell"""
        snapshot = self._snapshot(day)
        mostly_ice = self.ice_fraction >= MOSTLY_ICE_FRACTION
        return np.where(mostly_ice, snapshot.thermalDriving.values, np.nan)

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


def plot_melt_movie(
    ds_init, ds_melt, title, gif_filename, max_frames=180, wet_dry=None
):
    """
    Animate the ocean's daily-mean melt rate under the ice, the thin film
    included, with MALI's grounding line where it ran, and, below it, the
    cells the ocean treats as wet or dry

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

    wet_dry : WetDryStates, optional
        Which cells are grounded, dry, in between or wet over time, for a
        panel below the melt, each state shown until the next
    """
    water_density = get_constant('pure_water_density_reference')
    n_cells = ds_init.sizes['nCells']
    ice_cells = ds_melt.iceCell.values
    melt = ds_melt.meltFlux.values / water_density * SECONDS_PER_YEAR
    day_end = ds_melt.dayEnd.values
    # the scale leaves out the first day, whose start-up melt can be far
    # larger
    later = melt[1:] if melt.shape[0] > 1 else melt
    cmap, norm, ticks = get_signed_colors('melt', *get_signed_range([later]))
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
    layout = _MeltMovieLayout(
        (ylim[1] - ylim[0]) / (xlim[1] - xlim[0]), wet_dry is not None
    )
    with mplstyle_context(dpi=PNG_DPI):
        fig = Figure(figsize=(FIG_WIDTH, layout.height))
        ax = fig.add_axes(layout.melt_map)
        collection = mosaic.polypcolor(
            ax,
            descriptor,
            melt_map(0),
            cmap=cmap,
            norm=norm,
            edgecolor='face',
        )
        fig.colorbar(
            collection,
            cax=fig.add_axes(layout.colorbar),
            label='m yr$^{-1}$, negative for freezing',
            ticks=ticks,
            extend='both',
            orientation='horizontal',
        )
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_aspect('equal')
        ax.set_xlabel('x (km)')
        ax.set_ylabel('y (km)')
        wet_dry_panel = None
        if wet_dry is not None:
            wet_dry_panel = _WetDryPanel(
                fig, layout, descriptor, wet_dry, title, xlim, ylim
            )
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
            artists = [collection, gl_line]
            if wet_dry_panel is not None:
                artists.extend(
                    wet_dry_panel.update(day_end[index] - 1.0, gl_line)
                )
            return artists

        anim = animation.FuncAnimation(fig, frame, frames=frames)
        anim.save(
            gif_filename,
            writer=SharedPaletteGifWriter(fps=4 if len(frames) <= 40 else 12),
            dpi=GIF_DPI,
        )
