import os

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from numpy.typing import NDArray
from pyremap.descriptor.utility import interp_extrap_corner

from polaris.mesh.spherical.critical_transects import (
    load_default_critical_transects,
)
from polaris.step import Step
from polaris.tasks.mesh.spherical.unified.coastline.prepare import (
    CONVENTIONS,
)
from polaris.viz import use_mplstyle


class VizCoastlineStep(Step):
    """
    A step for visualizing coastline diagnostics.
    """

    def __init__(self, component, coastline_step, subdir):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        coastline_step : polaris.tasks.mesh.spherical.unified.coastline.
            PrepareCoastlineStep
            The coastline step to visualize

        subdir : str
            The subdirectory within the component's work directory
        """
        super().__init__(
            component=component,
            name='viz_coastline',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.coastline_step = coastline_step

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        for convention in CONVENTIONS:
            filename = self.coastline_step.output_filenames[convention]
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(
                    self.coastline_step.path, filename
                ),
            )

    def run(self):
        """
        Run this step.
        """
        use_mplstyle()

        viz_section = self.config['viz_coastline']
        prepare_section = self.config['coastline']
        dpi = viz_section.getint('dpi')
        antarctic_max_latitude = viz_section.getfloat('antarctic_max_latitude')
        signed_distance_limit = viz_section.getfloat('signed_distance_limit')
        plot_info = _get_plot_info_from_file(
            self.coastline_step.output_filenames[CONVENTIONS[0]]
        )
        line_overlays = None
        if prepare_section.getboolean('include_critical_transects'):
            try:
                line_overlays = _get_critical_transect_overlays()
            except Exception:  # pragma: no cover - diagnostic fallback
                self.logger.warning(
                    'Could not load critical transects for coastline '
                    'overlays.',
                    exc_info=True,
                )

        with open('debug_summary.txt', 'w') as summary:
            for convention in CONVENTIONS:
                filename = self.coastline_step.output_filenames[convention]
                with xr.open_dataset(filename) as ds_coastline:
                    ocean_mask = ds_coastline.ocean_mask.values > 0
                    signed_distance = ds_coastline.signed_distance.values

                self._plot_binary_field(
                    plot_info=plot_info,
                    field=ocean_mask,
                    title=f'{convention} ocean mask',
                    out_prefix=f'{convention}_ocean_mask',
                    dpi=dpi,
                    antarctic_max_latitude=antarctic_max_latitude,
                    line_overlays=line_overlays,
                )
                self._plot_signed_distance(
                    plot_info=plot_info,
                    signed_distance=signed_distance,
                    title=f'{convention} signed distance',
                    out_prefix=f'{convention}_signed_distance',
                    distance_limit=signed_distance_limit,
                    dpi=dpi,
                    antarctic_max_latitude=antarctic_max_latitude,
                )
                self._write_convention_summary(
                    summary=summary,
                    convention=convention,
                    ocean_mask=ocean_mask,
                    signed_distance=signed_distance,
                )

    def _plot_binary_field(
        self,
        plot_info,
        field,
        title,
        out_prefix,
        dpi,
        antarctic_max_latitude,
        line_overlays=None,
    ):
        """
        Plot a binary diagnostic field for both global and Antarctic views.
        """
        field = np.asarray(field, dtype=float)
        self._plot_scalar_field(
            plot_info=plot_info,
            field=field,
            title=title,
            out_filename=f'{out_prefix}_global.png',
            dpi=dpi,
            antarctic_max_latitude=antarctic_max_latitude,
            projection='global',
            cmap='Greys',
            vmin=0.0,
            vmax=1.0,
            line_overlays=line_overlays,
        )
        self._plot_scalar_field(
            plot_info=plot_info,
            field=field,
            title=title,
            out_filename=f'{out_prefix}_antarctic.png',
            dpi=dpi,
            antarctic_max_latitude=antarctic_max_latitude,
            projection='antarctic',
            cmap='Greys',
            vmin=0.0,
            vmax=1.0,
            line_overlays=line_overlays,
        )

    def _plot_signed_distance(
        self,
        plot_info,
        signed_distance,
        title,
        out_prefix,
        distance_limit,
        dpi,
        antarctic_max_latitude,
    ):
        """
        Plot signed distance for both global and Antarctic views.
        """
        field = 1.0e-3 * signed_distance
        limit_km = 1.0e-3 * distance_limit
        norm = TwoSlopeNorm(vmin=-limit_km, vcenter=0.0, vmax=limit_km)

        self._plot_scalar_field(
            plot_info=plot_info,
            field=field,
            title=f'{title} (km)',
            out_filename=f'{out_prefix}_global.png',
            dpi=dpi,
            antarctic_max_latitude=antarctic_max_latitude,
            projection='global',
            cmap='RdBu_r',
            norm=norm,
        )
        self._plot_scalar_field(
            plot_info=plot_info,
            field=field,
            title=f'{title} (km)',
            out_filename=f'{out_prefix}_antarctic.png',
            dpi=dpi,
            antarctic_max_latitude=antarctic_max_latitude,
            projection='antarctic',
            cmap='RdBu_r',
            norm=norm,
        )

    def _plot_scalar_field(
        self,
        plot_info,
        field,
        title,
        out_filename,
        dpi,
        antarctic_max_latitude,
        projection,
        cmap,
        vmin=None,
        vmax=None,
        norm=None,
        line_overlays=None,
    ):
        """
        Plot a scalar field with pcolormesh.
        """
        ref_projection = ccrs.PlateCarree()
        ax_projection = _get_projection(projection)
        figsize = (20, 8) if projection == 'global' else (12, 12)

        ordered_field = field[:, plot_info['center_order']]

        fig = plt.figure(figsize=figsize, dpi=dpi)
        ax = plt.axes(projection=ax_projection)
        _configure_axes(
            ax=ax,
            projection=projection,
            antarctic_max_latitude=antarctic_max_latitude,
        )
        mesh = ax.pcolormesh(
            plot_info['lon_corner'],
            plot_info['lat_corner'],
            ordered_field,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            norm=norm,
            transform=ref_projection,
        )
        if line_overlays is not None:
            _plot_line_overlays(
                ax=ax,
                projection=projection,
                line_overlays=line_overlays,
            )
        fig.colorbar(mesh, ax=ax, shrink=0.7)
        ax.set_title(title)
        fig.savefig(out_filename, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

    @staticmethod
    def _write_convention_summary(
        summary,
        convention,
        ocean_mask,
        signed_distance,
    ):
        """
        Write convention-specific ocean-mask counts to the summary file.
        """
        total_cells = ocean_mask.size
        summary.write(f'[{convention}]\n')
        summary.write(f'total_cells: {total_cells}\n')
        summary.write(f'connected_ocean_cells: {int(ocean_mask.sum())}\n')
        summary.write(f'land_cells: {int(total_cells - ocean_mask.sum())}\n')
        summary.write(
            f'min_signed_distance_m: {float(np.nanmin(signed_distance))}\n'
        )
        summary.write(
            f'max_signed_distance_m: {float(np.nanmax(signed_distance))}\n'
        )
        summary.write('\n')


def _get_plot_info(lon, lat):
    """
    Get longitude and latitude arrays for plotting.
    """
    plot_lon = np.where(lon > 180.0, lon - 360.0, lon)
    center_order = np.argsort(plot_lon)
    plot_lon = plot_lon[center_order]
    lon_corner = interp_extrap_corner(plot_lon)
    lat_corner = interp_extrap_corner(lat)

    return dict(
        center_order=center_order,
        lon=plot_lon,
        lon_corner=lon_corner,
        lat=lat,
        lat_corner=lat_corner,
    )


def _get_plot_info_from_file(filename):
    """
    Read grid coordinates from a coastline file and build plot metadata.
    """
    with xr.open_dataset(filename) as ds_coastline:
        return _get_plot_info(
            lon=ds_coastline.lon.values,
            lat=ds_coastline.lat.values,
        )


def _get_projection(projection):
    """
    Get the requested Cartopy projection.
    """
    if projection == 'global':
        return ccrs.PlateCarree()
    if projection == 'antarctic':
        return ccrs.SouthPolarStereo()
    raise ValueError(f'Unexpected projection: {projection}')


def _get_critical_transect_overlays():
    """
    Build line overlays for critical passages and land blockages.
    """
    critical_transects = load_default_critical_transects()
    return [
        dict(
            label='Critical passages',
            color='tab:blue',
            segments=_get_feature_segments(critical_transects.passages),
        ),
        dict(
            label='Critical blockages',
            color='tab:red',
            segments=_get_feature_segments(critical_transects.land_blockages),
        ),
    ]


def _configure_axes(ax, projection, antarctic_max_latitude):
    """
    Configure common map settings for coastline diagnostics.
    """
    ref_projection = ccrs.PlateCarree()
    if projection == 'global':
        ax.set_global()
    elif projection == 'antarctic':
        ax.set_extent(
            [-180.0, 180.0, -90.0, antarctic_max_latitude],
            crs=ref_projection,
        )
    else:
        raise ValueError(f'Unexpected projection: {projection}')

    ax.gridlines(color='0.8', linestyle=':', linewidth=0.5)


def _plot_line_overlays(ax, projection, line_overlays):
    """
    Plot optional line overlays and add a legend when present.
    """
    ref_projection = ccrs.PlateCarree()
    line_width = 1.0 if projection == 'antarctic' else 1.3
    legend_handles = []

    for overlay in line_overlays:
        segments = overlay['segments']
        if len(segments) == 0:
            continue

        for lon, lat in segments:
            ax.plot(
                lon,
                lat,
                color=overlay['color'],
                linewidth=line_width,
                transform=ref_projection,
                zorder=3,
            )

        legend_handles.append(
            Line2D(
                [0.0],
                [0.0],
                color=overlay['color'],
                linewidth=2.0,
                label=overlay['label'],
            )
        )

    if legend_handles:
        location = 'lower left' if projection == 'global' else 'upper left'
        ax.legend(
            handles=legend_handles,
            loc=location,
            framealpha=0.9,
        )


def _get_feature_segments(feature_collection):
    """
    Convert feature-collection line geometries into plot-ready segments.
    """
    segments: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
    if feature_collection is None:
        return segments

    if isinstance(feature_collection, dict):
        features = feature_collection.get('features', [])
    else:
        features = getattr(feature_collection, 'features', [])

    for feature in features:
        geometry = feature.get('geometry')
        if geometry is None:
            continue

        geometry_type = geometry.get('type')
        if geometry_type == 'LineString':
            parts = [geometry['coordinates']]
        elif geometry_type == 'MultiLineString':
            parts = geometry['coordinates']
        else:
            raise ValueError(
                f'Unsupported critical transect geometry type: {geometry_type}'
            )

        for coordinates in parts:
            coordinates = np.asarray(coordinates, dtype=np.float64)
            lon = np.where(
                coordinates[:, 0] > 180.0,
                coordinates[:, 0] - 360.0,
                coordinates[:, 0],
            )
            lat = coordinates[:, 1]
            if lon.size > 1:
                segments.append((lon, lat))

    return segments
