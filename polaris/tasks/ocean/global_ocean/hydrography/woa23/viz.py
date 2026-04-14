import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pyproj
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_lat_lon_field, use_mplstyle
from polaris.viz.spherical import setup_colormap


class Woa23VizStep(Step):
    """
    A step for visualizing extrapolated WOA23 hydrography.
    """

    def __init__(self, component, subdir, extrapolate_step, combine_topo_step):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extrapolate_step : polaris.Step
            The step that extrapolates WOA23 hydrography.

        combine_topo_step : polaris.Step
            The cached ``e3sm/init`` step that produces combined topography on
            the WOA23 grid.
        """
        super().__init__(
            component=component,
            name='viz',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.extrapolate_step = extrapolate_step
        self.combine_topo_step = combine_topo_step

    def setup(self):
        """
        Set up input and output files for the step.
        """
        super().setup()
        self.add_input_file(
            filename='woa.nc',
            work_dir_target=(
                f'{self.extrapolate_step.path}/'
                f'{self.extrapolate_step.output_filename}'
            ),
        )
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=(
                f'{self.combine_topo_step.path}/'
                f'{self.combine_topo_step.combined_filename}'
            ),
        )

        self.outputs = []
        for depth in self.config.getlist(
            'woa23', 'horizontal_plot_depths', dtype=float
        ):
            depth_tag = self._depth_tag(depth)
            self.add_output_file(filename=f'ct_an_depth_{depth_tag}.png')
            self.add_output_file(
                filename=f'ct_an_depth_{depth_tag}_filled.png'
            )
            self.add_output_file(filename=f'sa_an_depth_{depth_tag}.png')
            self.add_output_file(
                filename=f'sa_an_depth_{depth_tag}_filled.png'
            )

        self.add_output_file(filename='filchner_section.png')
        self.add_output_file(filename='filchner_section_filled.png')
        self.add_output_file(filename='ross_section.png')
        self.add_output_file(filename='ross_section_filled.png')

    def run(self):
        """
        Plot horizontal fields at selected depths and two Antarctic transects.
        """
        use_mplstyle()

        with xr.open_dataset('woa.nc', decode_times=False) as ds_woa:
            ds_woa = ds_woa.load()
        with xr.open_dataset('topography.nc') as ds_topo:
            ds_topo = ds_topo.load()

        self._plot_horizontal_maps(ds_woa=ds_woa, ds_topo=ds_topo)
        self._plot_configured_transects(ds_woa=ds_woa, ds_topo=ds_topo)

    def _plot_horizontal_maps(self, ds_woa, ds_topo):
        logger = self.logger
        fields = [
            (
                'ct_an',
                'Conservative temperature',
                r'Conservative temperature ($^{\circ}$C)',
                'woa23_viz_temperature',
            ),
            (
                'sa_an',
                'Absolute salinity',
                r'Absolute salinity (g kg$^{-1}$)',
                'woa23_viz_salinity',
            ),
        ]

        requested_depths = self.config.getlist(
            'woa23', 'horizontal_plot_depths', dtype=float
        )
        depth_values = ds_woa.depth.values

        for requested_depth in requested_depths:
            depth_index = int(
                np.abs(depth_values - requested_depth).argmin().item()
            )
            actual_depth = float(depth_values[depth_index])
            depth_tag = self._depth_tag(requested_depth)
            water_mask = self._get_level_water_mask(
                ds_topo=ds_topo, depth=actual_depth
            )

            logger.info(
                f'Plotting horizontal maps for requested depth '
                f'{requested_depth:g} m using WOA level {actual_depth:g} m'
            )
            for (
                field_name,
                field_title,
                colorbar_label,
                cmap_section,
            ) in fields:
                data = ds_woa[field_name].isel(depth=depth_index).values
                ocean_title = self._horizontal_title(
                    field_title=field_title,
                    requested_depth=requested_depth,
                    actual_depth=actual_depth,
                    filled=False,
                )
                plot_global_lat_lon_field(
                    lon=ds_woa.lon.values,
                    lat=ds_woa.lat.values,
                    data_array=np.where(water_mask, data, np.nan),
                    out_filename=f'{field_name}_depth_{depth_tag}.png',
                    config=self.config,
                    colormap_section=cmap_section,
                    title=ocean_title,
                    colorbar_label=colorbar_label,
                )

                filled_title = self._horizontal_title(
                    field_title=field_title,
                    requested_depth=requested_depth,
                    actual_depth=actual_depth,
                    filled=True,
                )
                plot_global_lat_lon_field(
                    lon=ds_woa.lon.values,
                    lat=ds_woa.lat.values,
                    data_array=data,
                    out_filename=f'{field_name}_depth_{depth_tag}_filled.png',
                    config=self.config,
                    colormap_section=cmap_section,
                    title=filled_title,
                    colorbar_label=colorbar_label,
                )

    def _plot_configured_transects(self, ds_woa, ds_topo):
        transects = [
            (
                'Filchner Trough',
                'filchner',
                'filchner_section.png',
                'filchner_section_filled.png',
            ),
            (
                'Ross Ice Shelf cavity',
                'ross',
                'ross_section.png',
                'ross_section_filled.png',
            ),
        ]

        max_depth = self.config.getfloat('woa23', 'section_max_depth')
        for transect_name, prefix, out_filename, filled_filename in transects:
            start_lon = self.config.getfloat('woa23', f'{prefix}_start_lon')
            start_lat = self.config.getfloat('woa23', f'{prefix}_start_lat')
            end_lon = self.config.getfloat('woa23', f'{prefix}_end_lon')
            end_lat = self.config.getfloat('woa23', f'{prefix}_end_lat')
            self.logger.info(f'Plotting {transect_name} section')
            self._plot_transect(
                ds_woa=ds_woa,
                ds_topo=ds_topo,
                title=transect_name,
                start_lon=start_lon,
                start_lat=start_lat,
                end_lon=end_lon,
                end_lat=end_lat,
                out_filename=out_filename,
                max_depth=max_depth,
                filled=False,
            )
            self._plot_transect(
                ds_woa=ds_woa,
                ds_topo=ds_topo,
                title=transect_name,
                start_lon=start_lon,
                start_lat=start_lat,
                end_lon=end_lon,
                end_lat=end_lat,
                out_filename=filled_filename,
                max_depth=max_depth,
                filled=True,
            )

    def _plot_transect(
        self,
        ds_woa,
        ds_topo,
        title,
        start_lon,
        start_lat,
        end_lon,
        end_lat,
        out_filename,
        max_depth,
        filled,
    ):
        distance, lon, lat = self._build_transect(
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=end_lon,
            end_lat=end_lat,
        )
        ds_woa = self._add_periodic_lon(ds_woa)
        ds_topo = self._add_periodic_lon(ds_topo)
        coords = {
            'lat': xr.DataArray(lat, dims=('nPoints',)),
            'lon': xr.DataArray(lon, dims=('nPoints',)),
        }

        ds_section = ds_woa[['ct_an', 'sa_an']].interp(**coords)
        ds_topo_section = ds_topo[['base_elevation', 'ice_draft']].interp(
            **coords
        )
        ds_topo_section['ocean_mask'] = (
            ds_topo[['ocean_mask']]
            .interp(
                method='nearest',
                **coords,
            )
            .ocean_mask
        )

        top_depth = np.maximum(-ds_topo_section.ice_draft.values, 0.0)
        bottom_depth = np.maximum(-ds_topo_section.base_elevation.values, 0.0)
        ocean_mask = ds_topo_section.ocean_mask.values > 0.5
        valid_column = np.logical_and(ocean_mask, bottom_depth > top_depth)

        depth = ds_woa.depth.values
        depth_bounds = self._depth_bounds(ds_woa.depth_bnds.values)
        distance_bounds = self._distance_bounds(distance)
        water_mask = (
            (depth[:, np.newaxis] >= top_depth[np.newaxis, :])
            & (depth[:, np.newaxis] <= bottom_depth[np.newaxis, :])
            & valid_column[np.newaxis, :]
        )

        fields = [
            (
                'ct_an',
                'Conservative temperature',
                r'Conservative temperature ($^{\circ}$C)',
                'woa23_viz_section_temperature',
            ),
            (
                'sa_an',
                'Absolute salinity',
                r'Absolute salinity (g kg$^{-1}$)',
                'woa23_viz_section_salinity',
            ),
        ]

        fig, axes = plt.subplots(
            2,
            1,
            figsize=(12, 8),
            sharex=True,
            constrained_layout=True,
        )

        max_depth = min(max_depth, float(depth_bounds[-1]))
        top_depth_plot = np.minimum(top_depth, max_depth)
        bottom_depth_plot = np.minimum(bottom_depth, max_depth)
        for ax, (field_name, field_title, colorbar_label, cmap_section) in zip(
            axes, fields, strict=True
        ):
            plot_data = ds_section[field_name].values
            if not filled:
                plot_data = np.where(water_mask, plot_data, np.nan)
            colormap, norm, ticks = setup_colormap(self.config, cmap_section)
            image = ax.pcolormesh(
                distance_bounds,
                depth_bounds,
                plot_data,
                cmap=colormap,
                norm=norm,
                shading='auto',
            )

            if not filled:
                # Grounded ice and land are shown as a light gray
                # background, floating ice by the cavity roof and the bed
                # by dark gray fill.
                ax.fill_between(
                    distance,
                    0.0,
                    max_depth,
                    where=np.logical_not(valid_column),
                    color='0.88',
                    linewidth=0.0,
                )
                ax.fill_between(
                    distance,
                    0.0,
                    top_depth_plot,
                    where=top_depth > 0.0,
                    color='lightsteelblue',
                    linewidth=0.0,
                )
                ax.fill_between(
                    distance,
                    bottom_depth_plot,
                    max_depth,
                    where=valid_column,
                    color='dimgray',
                    linewidth=0.0,
                )
                ax.plot(distance, top_depth_plot, color='k', linewidth=1.0)
                ax.plot(distance, bottom_depth_plot, color='k', linewidth=1.0)
            ax.set_ylabel('Depth (m)')
            ax.set_title(field_title)
            ax.set_ylim(max_depth, 0.0)
            colorbar = fig.colorbar(image, ax=ax, pad=0.01)
            colorbar.set_label(colorbar_label)
            if ticks is not None:
                colorbar.set_ticks(ticks)
                colorbar.set_ticklabels([f'{tick}' for tick in ticks])

        axes[-1].set_xlabel('Distance along transect (km)')
        fig.suptitle(
            f'{self._transect_title(title=title, filled=filled)}: '
            f'({start_lon:.2f}, {start_lat:.2f}) to '
            f'({end_lon:.2f}, {end_lat:.2f})'
        )
        fig.savefig(out_filename, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

    @staticmethod
    def _depth_tag(depth):
        depth_str = f'{depth:07.2f}'
        depth_str = depth_str.replace('.', 'p').replace('-', 'm')
        return f'{depth_str}m'

    @staticmethod
    def _horizontal_title(field_title, requested_depth, actual_depth, filled):
        if np.isclose(requested_depth, actual_depth):
            title = f'{field_title} at {actual_depth:g} m'
        else:
            title = (
                f'{field_title} near {requested_depth:g} m '
                f'(WOA level {actual_depth:g} m)'
            )

        if filled:
            return f'{title} (filled field)'
        return f'{title} (ocean only)'

    @staticmethod
    def _transect_title(title, filled):
        if filled:
            return f'{title} (filled field)'
        return f'{title} (ocean only)'

    @staticmethod
    def _get_level_water_mask(ds_topo, depth):
        top_depth = np.maximum(-ds_topo.ice_draft.values, 0.0)
        bottom_depth = np.maximum(-ds_topo.base_elevation.values, 0.0)
        ocean_mask = ds_topo.ocean_mask.values > 0.5
        return (top_depth <= depth) & (bottom_depth >= depth) & ocean_mask

    @staticmethod
    def _build_transect(start_lon, start_lat, end_lon, end_lat):
        geod = pyproj.Geod(ellps='WGS84')
        _, _, total_distance = geod.inv(start_lon, start_lat, end_lon, end_lat)
        total_distance_km = total_distance * 1.0e-3
        npoints = int(np.clip(total_distance_km / 10.0, 200, 1000))
        if npoints < 2:
            npoints = 2

        if npoints > 2:
            intermediate = geod.npts(
                start_lon,
                start_lat,
                end_lon,
                end_lat,
                npoints - 2,
            )
            lon = np.array(
                [start_lon] + [point[0] for point in intermediate] + [end_lon]
            )
            lat = np.array(
                [start_lat] + [point[1] for point in intermediate] + [end_lat]
            )
        else:
            lon = np.array([start_lon, end_lon])
            lat = np.array([start_lat, end_lat])

        _, _, segment_distance = geod.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
        distance = np.zeros(npoints)
        distance[1:] = np.cumsum(segment_distance) * 1.0e-3
        return distance, lon, lat

    @staticmethod
    def _add_periodic_lon(ds):
        lon = ds.lon
        lon_sections = [lon - 360.0, lon, lon + 360.0]
        lon_periodic = xr.concat(lon_sections, dim='lon')

        periodic = []
        for offset in [-360.0, 0.0, 360.0]:
            shifted = ds.assign_coords(lon=ds.lon + offset)
            periodic.append(shifted)

        ds_periodic = xr.concat(periodic, dim='lon', data_vars='all')
        ds_periodic = ds_periodic.assign_coords(lon=lon_periodic)
        return ds_periodic.sortby('lon')

    @staticmethod
    def _depth_bounds(depth_bounds):
        lower = depth_bounds[:, 0]
        upper = depth_bounds[:, 1]
        return np.concatenate(([lower[0]], upper))

    @staticmethod
    def _distance_bounds(distance):
        if distance.size == 1:
            return np.array([0.0, distance[0]])

        bounds = np.zeros(distance.size + 1)
        bounds[1:-1] = 0.5 * (distance[:-1] + distance[1:])
        bounds[0] = 0.0
        bounds[-1] = distance[-1]
        return bounds
