import os

import cartopy.crs as ccrs
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.lines import Line2D
from shapely.geometry import LineString, MultiLineString, box, shape

from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.river.source import _read_geojson
from polaris.viz import use_mplstyle

CONUS_EXTENT = (-128.0, -65.0, 22.0, 52.0)

COAST_COLOR = '#222222'
LAND_COLOR = '#c8ced6'
OCEAN_COLOR = '#e7f0f7'
RIVER_COLOR = '#0a6ba8'
MATCHED_COLOR = '#c43c39'
UNMATCHED_COLOR = '#7a2cb8'
INLAND_SINK_COLOR = '#c97800'


class VizRiverStep(Step):
    """
    A step for visualizing river-network diagnostics.
    """

    def __init__(self, component, prepare_step, river_step, subdir):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        prepare_step : polaris.tasks.mesh.spherical.unified.river.source.
            PrepareRiverSourceStep
            The shared source-level river step

        river_step : polaris.tasks.mesh.spherical.unified.river.lat_lon.
            PrepareRiverLatLonStep
            The shared lat-lon river step to visualize

        subdir : str
            The subdirectory within the component's work directory
        """
        super().__init__(
            component=component,
            name='viz_river_network',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.prepare_step = prepare_step
        self.river_step = river_step
        self.output_filenames = [
            'river_network_overview.png',
            'debug_summary.txt',
        ]

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        convention = self.river_step.config.get(
            'unified_mesh', 'coastline_convention'
        )
        self.add_input_file(
            filename='simplified_river_network.geojson',
            work_dir_target=os.path.join(
                self.prepare_step.path, self.prepare_step.simplified_filename
            ),
        )
        self.add_input_file(
            filename='retained_outlets.geojson',
            work_dir_target=os.path.join(
                self.prepare_step.path, self.prepare_step.outlets_filename
            ),
        )
        self.add_input_file(
            filename='river_network.nc',
            work_dir_target=os.path.join(
                self.river_step.path, self.river_step.masks_filename
            ),
        )
        self.add_input_file(
            filename='river_outlets.geojson',
            work_dir_target=os.path.join(
                self.river_step.path, self.river_step.outlets_filename
            ),
        )
        self.add_input_file(
            filename='coastline.nc',
            work_dir_target=os.path.join(
                self.river_step.coastline_step.path,
                self.river_step.coastline_step.output_filenames[convention],
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

        simplified_fc = _read_geojson('simplified_river_network.geojson')
        retained_outlets_fc = _read_geojson('retained_outlets.geojson')
        snapped_outlets_fc = _read_geojson('river_outlets.geojson')

        with xr.open_dataset('river_network.nc') as ds_river:
            lon = ds_river.lon.values
            lat = ds_river.lat.values
            river_channel_mask = ds_river.river_channel_mask.values > 0
            river_outlet_mask = ds_river.river_outlet_mask.values > 0
            river_ocean_outlet_mask = (
                ds_river.river_ocean_outlet_mask.values > 0
            )
            river_inland_sink_mask = ds_river.river_inland_sink_mask.values > 0
            matched_ocean_outlets = int(
                ds_river.attrs['matched_ocean_outlets']
            )
            unmatched_ocean_outlets = int(
                ds_river.attrs['unmatched_ocean_outlets']
            )

        with xr.open_dataset('coastline.nc') as ds_coastline:
            ocean_mask = ds_coastline.ocean_mask.values > 0
            land_mask = _get_land_mask(ds_coastline)

        self._plot_network_overview(
            lon=lon,
            lat=lat,
            land_mask=land_mask,
            ocean_mask=ocean_mask,
            simplified_fc=simplified_fc,
            snapped_outlets_fc=snapped_outlets_fc,
            dpi=dpi,
            out_filename='river_network_overview.png',
        )

        _write_summary(
            filename='debug_summary.txt',
            simplified_fc=simplified_fc,
            retained_outlets_fc=retained_outlets_fc,
            snapped_outlets_fc=snapped_outlets_fc,
            river_channel_mask=river_channel_mask,
            river_outlet_mask=river_outlet_mask,
            river_ocean_outlet_mask=river_ocean_outlet_mask,
            river_inland_sink_mask=river_inland_sink_mask,
            matched_ocean_outlets=matched_ocean_outlets,
            unmatched_ocean_outlets=unmatched_ocean_outlets,
        )

    def _plot_network_overview(
        self,
        lon,
        lat,
        land_mask,
        ocean_mask,
        simplified_fc,
        snapped_outlets_fc,
        dpi,
        out_filename,
    ):
        """
        Plot the simplified river network and snapped outlet classes.
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
                color=RIVER_COLOR,
                lw=0.9,
            )
            _plot_snapped_points(
                ax=current_ax,
                feature_collection=snapped_outlets_fc,
                size=38,
            )
        _add_figure_legend(fig=fig, handles=_get_overview_legend_handles())
        ax.set_title('Simplified river network and snapped outlets')
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


def _plot_lines(ax, feature_collection, color, lw):
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
                alpha=0.95,
                transform=ccrs.PlateCarree(),
                zorder=2,
            )


def _plot_snapped_points(ax, feature_collection, size):
    """
    Plot snapped outlet points with colors by outlet type and match status.
    """
    for feature in feature_collection['features']:
        props = feature['properties']
        geom = shape(feature['geometry'])
        color, marker = _get_outlet_style(
            outlet_type=props['outlet_type'],
            matched=props['matched_to_ocean'],
        )
        ax.scatter(
            [float(geom.x)],
            [float(geom.y)],
            color=color,
            marker=marker,
            s=size,
            edgecolors='white',
            linewidths=0.4,
            transform=ccrs.PlateCarree(),
            zorder=5,
        )


def _get_outlet_style(outlet_type, matched):
    """
    Get marker styling for a snapped outlet.
    """
    if outlet_type == 'inland_sink':
        return INLAND_SINK_COLOR, '^'
    if matched:
        return MATCHED_COLOR, 'o'
    return UNMATCHED_COLOR, 's'


def _get_overview_legend_handles():
    """
    Build legend handles for the overview figure.
    """
    return [
        Line2D(
            [0],
            [0],
            color=RIVER_COLOR,
            linewidth=1.4,
            label='Simplified river network',
        ),
        Line2D(
            [0],
            [0],
            marker='o',
            linestyle='None',
            color=MATCHED_COLOR,
            markerfacecolor=MATCHED_COLOR,
            markersize=8,
            label='Matched ocean outlet',
        ),
        Line2D(
            [0],
            [0],
            marker='s',
            linestyle='None',
            color=UNMATCHED_COLOR,
            markerfacecolor=UNMATCHED_COLOR,
            markersize=8,
            label='Unmatched ocean outlet',
        ),
        Line2D(
            [0],
            [0],
            marker='^',
            linestyle='None',
            color=INLAND_SINK_COLOR,
            markerfacecolor=INLAND_SINK_COLOR,
            markersize=8,
            label='Inland sink outlet',
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
    retained_outlets_fc,
    snapped_outlets_fc,
    river_channel_mask,
    river_outlet_mask,
    river_ocean_outlet_mask,
    river_inland_sink_mask,
    matched_ocean_outlets,
    unmatched_ocean_outlets,
):
    """
    Write a compact text summary of river-network diagnostics.
    """
    drainage_areas = [
        feature['properties']['drainage_area']
        for feature in simplified_fc['features']
    ]
    snapping_distances = [
        feature['properties']['snapping_distance_m']
        for feature in snapped_outlets_fc['features']
    ]
    with open(filename, 'w', encoding='utf-8') as summary:
        summary.write('River Network Diagnostics\n')
        summary.write('=========================\n\n')
        summary.write(
            f'Simplified segments: {len(simplified_fc["features"])}\n'
        )
        summary.write(
            f'Retained outlets: {len(retained_outlets_fc["features"])}\n'
        )
        summary.write(
            f'Rasterized channel cells: {int(np.sum(river_channel_mask))}\n'
        )
        summary.write(
            f'Rasterized outlet cells: {int(np.sum(river_outlet_mask))}\n'
        )
        summary.write(
            'Rasterized ocean-outlet cells: '
            f'{int(np.sum(river_ocean_outlet_mask))}\n'
        )
        summary.write(
            'Rasterized inland-sink cells: '
            f'{int(np.sum(river_inland_sink_mask))}\n'
        )
        summary.write(f'Matched ocean outlets: {matched_ocean_outlets}\n')
        summary.write(f'Unmatched ocean outlets: {unmatched_ocean_outlets}\n')
        if len(drainage_areas) > 0:
            summary.write(
                'Drainage area range (km^2): '
                f'{min(drainage_areas) / 1.0e6:.1f} to '
                f'{max(drainage_areas) / 1.0e6:.1f}\n'
            )
        if len(snapping_distances) > 0:
            summary.write(
                'Snapping distance range (km): '
                f'{min(snapping_distances) / 1.0e3:.1f} to '
                f'{max(snapping_distances) / 1.0e3:.1f}\n'
            )
