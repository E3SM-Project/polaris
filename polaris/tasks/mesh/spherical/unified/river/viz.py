import os

import cartopy.crs as ccrs
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D
from shapely.geometry import LineString, MultiLineString, box, shape

from polaris.mesh.spherical.unified.river.geojson import read_geojson
from polaris.step import Step
from polaris.viz import use_mplstyle

CONUS_EXTENT = (-128.0, -65.0, 22.0, 52.0)

COAST_COLOR = '#222222'
LAND_COLOR = '#c8ced6'
OCEAN_COLOR = '#e7f0f7'
SIMPLIFIED_COLOR = '#0a6ba8'
CLIPPED_COLOR = '#c43c39'
CHANNEL_COLOR = '#0f766e'


class VizRiverStep(Step):
    """
    A step for visualizing river-network diagnostics.
    """

    def __init__(
        self, component, simplify_step, rasterize_step, clip_step, subdir
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        simplify_step : polaris.tasks.mesh.spherical.unified.river.simplify.SimplifyRiverNetworkStep
            The shared source-level river step

        rasterize_step : polaris.tasks.mesh.spherical.unified.river.rasterize.RasterizeRiverLatLonStep
            The shared lat-lon river step to visualize

        clip_step : polaris.tasks.mesh.spherical.unified.river.clip.ClipRiverNetworkStep
            The shared clipped river-network step

        subdir : str
            The subdirectory within the component's work directory
        """  # noqa: E501
        super().__init__(
            component=component,
            name='viz_river_network',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.simplify_step = simplify_step
        self.rasterize_step = rasterize_step
        self.clip_step = clip_step
        self.output_filenames = [
            'river_network_overlay.png',
            'rasterized_river_network.png',
            'debug_summary.txt',
        ]

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        convention = self.rasterize_step.config.get(
            'spherical_mesh', 'antarctic_boundary_convention'
        )
        self.add_input_file(
            filename='simplified_river_network.geojson',
            work_dir_target=os.path.join(
                self.simplify_step.path, self.simplify_step.simplified_filename
            ),
        )
        self.add_input_file(
            filename='clipped_river_network.geojson',
            work_dir_target=os.path.join(
                self.clip_step.path, self.clip_step.clipped_filename
            ),
        )
        self.add_input_file(
            filename='river_network.nc',
            work_dir_target=os.path.join(
                self.rasterize_step.path, self.rasterize_step.masks_filename
            ),
        )
        self.add_input_file(
            filename='coastline.nc',
            work_dir_target=os.path.join(
                self.rasterize_step.coastline_step.path,
                self.rasterize_step.coastline_step.output_filenames[
                    convention
                ],
            ),
        )
        for filename in self.output_filenames:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step.
        """
        use_mplstyle()

        dpi = self.config['viz_river_network'].getint('dpi')

        simplified_fc = read_geojson('simplified_river_network.geojson')
        clipped_fc = read_geojson('clipped_river_network.geojson')

        with xr.open_dataset('river_network.nc') as ds_river:
            lon = ds_river.lon.values
            lat = ds_river.lat.values
            river_channel_mask = ds_river.river_channel_mask.values > 0

        with xr.open_dataset('coastline.nc') as ds_coastline:
            ocean_mask = ds_coastline.ocean_mask.values > 0
            land_mask = _get_land_mask(ds_coastline)

        self._plot_network_overlay(
            lon=lon,
            lat=lat,
            land_mask=land_mask,
            ocean_mask=ocean_mask,
            simplified_fc=simplified_fc,
            clipped_fc=clipped_fc,
            dpi=dpi,
            out_filename='river_network_overlay.png',
        )
        self._plot_rasterized_network(
            lon=lon,
            lat=lat,
            river_channel_mask=river_channel_mask,
            dpi=dpi,
            out_filename='rasterized_river_network.png',
        )

        _write_summary(
            filename='debug_summary.txt',
            simplified_fc=simplified_fc,
            clipped_fc=clipped_fc,
            river_channel_mask=river_channel_mask,
        )

    def _plot_network_overlay(
        self,
        lon,
        lat,
        land_mask,
        ocean_mask,
        simplified_fc,
        clipped_fc,
        dpi,
        out_filename,
    ):
        """
        Plot simplified and clipped river networks together.
        """
        fig, ax, inset_ax = _setup_axes_with_inset(dpi=dpi)
        for current_ax in (ax, inset_ax):
            _plot_context(
                ax=current_ax,
                lon=lon,
                lat=lat,
                land_mask=land_mask,
                ocean_mask=ocean_mask,
            )
            _plot_lines(
                ax=current_ax,
                feature_collection=simplified_fc,
                color=SIMPLIFIED_COLOR,
                lw=0.9,
                alpha=0.7,
                zorder=2,
            )
            _plot_lines(
                ax=current_ax,
                feature_collection=clipped_fc,
                color=CLIPPED_COLOR,
                lw=0.9,
                alpha=0.95,
                zorder=3,
            )
        _add_figure_legend(fig=fig, handles=_get_overlay_legend_handles())
        ax.set_title('Simplified and clipped river networks')
        fig.savefig(out_filename, bbox_inches='tight')
        plt.close(fig)

    def _plot_rasterized_network(
        self,
        lon,
        lat,
        river_channel_mask,
        dpi,
        out_filename,
    ):
        """
        Plot the rasterized river-channel mask.
        """
        fig = plt.figure(figsize=(11.0, 5.0), dpi=dpi)
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_global()
        channel = np.where(river_channel_mask, 1.0, np.nan)
        ax.imshow(
            channel,
            origin='lower',
            extent=_get_extent(lon=lon, lat=lat),
            transform=ccrs.PlateCarree(),
            cmap=mcolors.ListedColormap([CHANNEL_COLOR]),
            interpolation='nearest',
        )
        ax.coastlines(linewidth=0.45, color=COAST_COLOR)
        ax.set_title('Rasterized river-channel mask')
        fig.savefig(out_filename, bbox_inches='tight')
        plt.close(fig)


def _setup_axes_with_inset(dpi):
    """
    Create a global Robinson plot with a CONUS inset.
    """
    fig = plt.figure(figsize=(16.0, 9.0), dpi=dpi)
    ax = fig.add_axes([0.03, 0.12, 0.68, 0.78], projection=ccrs.Robinson())
    ax.set_global()
    ax.coastlines(linewidth=0.45, color=COAST_COLOR)

    inset_ax = fig.add_axes(
        [0.73, 0.17, 0.24, 0.28], projection=ccrs.PlateCarree()
    )
    inset_ax.set_extent(CONUS_EXTENT, crs=ccrs.PlateCarree())
    inset_ax.coastlines(linewidth=0.45, color=COAST_COLOR)
    inset_ax.set_title('CONUS inset', fontsize=11, pad=4.0)

    _plot_inset_outline(ax=ax, extent=CONUS_EXTENT)
    return fig, ax, inset_ax


def _plot_context(ax, lon, lat, land_mask, ocean_mask):
    """
    Plot muted land and ocean context layers.
    """
    _plot_ocean_mask(ax=ax, lon=lon, lat=lat, ocean_mask=ocean_mask)
    _plot_land_mask(ax=ax, lon=lon, lat=lat, land_mask=land_mask)


def _plot_inset_outline(ax, extent):
    """
    Highlight the inset region on the global map.
    """
    ax.add_geometries(
        [box(extent[0], extent[2], extent[1], extent[3])],
        crs=ccrs.PlateCarree(),
        facecolor='none',
        edgecolor='#4a5568',
        linewidth=1.0,
        linestyle='--',
        zorder=6,
    )


def _plot_land_mask(ax, lon, lat, land_mask):
    """
    Plot the land mask as a muted background.
    """
    if land_mask is None:
        return
    background = np.where(land_mask, 1.0, np.nan)
    ax.imshow(
        background,
        origin='lower',
        extent=_get_extent(lon=lon, lat=lat),
        transform=ccrs.PlateCarree(),
        cmap=mcolors.ListedColormap([LAND_COLOR]),
        interpolation='nearest',
        alpha=0.8,
        zorder=0,
    )


def _get_land_mask(ds_coastline):
    """
    Derive the land mask from ocean_mask.
    """
    return ds_coastline.ocean_mask.values <= 0


def _plot_ocean_mask(ax, lon, lat, ocean_mask):
    """
    Plot the ocean mask as a muted context layer.
    """
    ocean = np.where(ocean_mask, 1.0, np.nan)
    ax.imshow(
        ocean,
        origin='lower',
        extent=_get_extent(lon=lon, lat=lat),
        transform=ccrs.PlateCarree(),
        cmap=mcolors.ListedColormap([OCEAN_COLOR]),
        interpolation='nearest',
        alpha=0.85,
        zorder=-1,
    )


def _plot_lines(ax, feature_collection, color, lw, alpha, zorder):
    """
    Plot river lines from a GeoJSON feature collection.
    """
    for feature in feature_collection['features']:
        geom = shape(feature['geometry'])
        if isinstance(geom, LineString):
            line_geometries = [geom]
        elif isinstance(geom, MultiLineString):
            line_geometries = list(geom.geoms)
        else:
            continue
        for line in line_geometries:
            coords = np.asarray(line.coords)
            ax.plot(
                coords[:, 0],
                coords[:, 1],
                color=color,
                linewidth=lw,
                alpha=alpha,
                transform=ccrs.PlateCarree(),
                zorder=zorder,
            )


def _get_overlay_legend_handles():
    """
    Build legend handles for the overlay figure.
    """
    return [
        Line2D(
            [0],
            [0],
            color=SIMPLIFIED_COLOR,
            linewidth=1.4,
            label='Simplified river network',
        ),
        Line2D(
            [0],
            [0],
            color=CLIPPED_COLOR,
            linewidth=1.4,
            label='Clipped river network',
        ),
    ]


def _add_figure_legend(fig, handles):
    """
    Add a shared legend below the main map.
    """
    fig.legend(
        handles=handles,
        loc='lower center',
        bbox_to_anchor=(0.5, 0.02),
        ncol=2,
        frameon=True,
    )


def _get_extent(lon, lat):
    """
    Get an image extent from regular lat-lon cell centers.
    """
    lon_edges = _compute_edges(lon)
    lat_edges = _compute_edges(lat)
    return [lon_edges[0], lon_edges[-1], lat_edges[0], lat_edges[-1]]


def _compute_edges(values):
    """
    Compute cell edges from regular cell-center coordinates.
    """
    values = np.asarray(values)
    if values.size == 1:
        delta = 1.0
        return np.array([values[0] - 0.5 * delta, values[0] + 0.5 * delta])
    midpoints = 0.5 * (values[:-1] + values[1:])
    first = values[0] - 0.5 * (values[1] - values[0])
    last = values[-1] + 0.5 * (values[-1] - values[-2])
    return np.concatenate(([first], midpoints, [last]))


def _write_summary(
    filename,
    simplified_fc,
    clipped_fc,
    river_channel_mask,
):
    """
    Write a compact text summary of river-network diagnostics.
    """
    simplified_segments = len(simplified_fc['features'])
    clipped_segments = len(clipped_fc['features'])
    drainage_areas = [
        feature['properties']['drainage_area']
        for feature in simplified_fc['features']
    ]
    with open(filename, 'w', encoding='utf-8') as summary:
        summary.write('River Network Diagnostics\n')
        summary.write('=========================\n\n')
        summary.write(f'Simplified segments: {simplified_segments}\n')
        summary.write(f'Clipped segments: {clipped_segments}\n')
        summary.write(
            'Segments removed by clipping: '
            f'{simplified_segments - clipped_segments}\n'
        )
        summary.write(
            f'Rasterized channel cells: {int(np.sum(river_channel_mask))}\n'
        )
        if len(drainage_areas) > 0:
            summary.write(
                'Drainage area range (km^2): '
                f'{min(drainage_areas) / 1.0e6:.1f} to '
                f'{max(drainage_areas) / 1.0e6:.1f}\n'
            )
