import os

import cartopy.crs as ccrs
import cmocean  # noqa: F401
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.step import Step
from polaris.viz import use_mplstyle


class VizSizingFieldStep(Step):
    """
    Visualize sizing-field diagnostics.
    """

    def __init__(self, component, sizing_step, subdir):
        super().__init__(
            component=component,
            name='viz_sizing_field',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.sizing_step = sizing_step
        self.output_filenames = [
            'sizing_field_overview.png',
            'active_control.png',
            'debug_summary.txt',
        ]

    def setup(self):
        """
        Link the sizing-field dataset and declare outputs.
        """
        self.add_input_file(
            filename='sizing_field.nc',
            work_dir_target=os.path.join(
                self.sizing_step.path, self.sizing_step.sizing_field_filename
            ),
        )
        for filename in self.output_filenames:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Create simple global diagnostic plots and a text summary.
        """
        use_mplstyle()
        dpi = self.config['viz_sizing_field'].getint('dpi')
        cmap = self.config['viz_sizing_field'].get('cell_width_cmap')

        with xr.open_dataset('sizing_field.nc') as ds:
            lon = ds.lon.values
            lat = ds.lat.values
            cell_width_fields = [
                ('cellWidth', 'Final cell width (km)'),
                ('ocean_background_cell_width', 'Ocean background (km)'),
                ('land_river_cell_width', 'Land/river composite (km)'),
            ]
            delta_field = ds.coastal_transition_delta.values

            fig = plt.figure(
                figsize=(15.0, 9.2), dpi=dpi, constrained_layout=True
            )
            grid = fig.add_gridspec(4, 2, height_ratios=[1.0, 1.0, 0.12, 0.14])
            axes = np.array(
                [
                    fig.add_subplot(grid[0, 0], projection=ccrs.PlateCarree()),
                    fig.add_subplot(grid[0, 1], projection=ccrs.PlateCarree()),
                    fig.add_subplot(grid[1, 0], projection=ccrs.PlateCarree()),
                    fig.add_subplot(grid[1, 1], projection=ccrs.PlateCarree()),
                ]
            )
            delta_cax = fig.add_subplot(grid[2, 1])
            shared_cax = fig.add_subplot(grid[3, :])
            norm, ticks = _get_cell_width_norm_and_ticks(
                fields=[
                    ds[var_name].values for var_name, _ in cell_width_fields
                ]
            )
            image = None
            for ax, (var_name, title) in zip(
                axes[:3], cell_width_fields, strict=True
            ):
                image = self._plot_scalar_field(
                    ax=ax,
                    lon=lon,
                    lat=lat,
                    field=ds[var_name].values,
                    title=title,
                    cmap=cmap,
                    norm=norm,
                    add_colorbar=False,
                )
            delta_norm, delta_ticks = _get_difference_norm_and_ticks(
                field=delta_field
            )
            delta_image = self._plot_scalar_field(
                ax=axes[3],
                lon=lon,
                lat=lat,
                field=delta_field,
                title='Coastal transition delta (km)',
                cmap='cmo.balance',
                norm=delta_norm,
                add_colorbar=False,
            )
            assert image is not None
            colorbar = fig.colorbar(
                image,
                cax=shared_cax,
                orientation='horizontal',
                label='Cell width (km)',
            )
            if ticks is not None:
                colorbar.set_ticks(np.asarray(ticks).tolist())
            delta_colorbar = fig.colorbar(
                delta_image,
                cax=delta_cax,
                orientation='horizontal',
                label='Final minus pre-coastline cell width (km)',
            )
            if delta_ticks is not None:
                delta_colorbar.set_ticks(delta_ticks)
            fig.savefig('sizing_field_overview.png', bbox_inches='tight')
            plt.close(fig)

            fig = plt.figure(figsize=(11.0, 5.0), dpi=dpi)
            ax = plt.axes(projection=ccrs.PlateCarree())
            control_cmap = mcolors.ListedColormap(
                ['#3b528b', '#5ec962', '#fdae61', '#d7191c']
            )
            control_norm = mcolors.BoundaryNorm(
                np.arange(-0.5, 4.5, 1.0), control_cmap.N
            )
            image = self._plot_scalar_field(
                ax=ax,
                lon=lon,
                lat=lat,
                field=ds.active_control.values,
                title='Active sizing control',
                cmap=control_cmap,
                norm=control_norm,
                add_colorbar=False,
            )
            colorbar = fig.colorbar(
                image, ax=ax, ticks=np.arange(4), shrink=0.75
            )
            colorbar.ax.set_yticklabels(
                ['background', 'coastline', 'river channel', 'river outlet']
            )
            fig.savefig('active_control.png', bbox_inches='tight')
            plt.close(fig)

            self._write_summary(ds)

    def _plot_scalar_field(
        self,
        ax,
        lon,
        lat,
        field,
        title,
        cmap,
        norm=None,
        vmin=None,
        vmax=None,
        add_colorbar=True,
    ):
        """
        Plot one scalar field on a simple global Plate Carree map.
        """
        ax.set_global()
        image = ax.imshow(
            field,
            origin='lower',
            extent=[lon.min(), lon.max(), lat.min(), lat.max()],
            transform=ccrs.PlateCarree(),
            cmap=cmap,
            norm=norm,
            vmin=vmin,
            vmax=vmax,
            interpolation='nearest',
        )
        ax.set_title(title)
        if add_colorbar:
            plt.colorbar(image, ax=ax, shrink=0.75)
        return image

    @staticmethod
    def _write_summary(ds):
        """
        Write a compact summary of the sizing-field dataset.
        """
        with open('debug_summary.txt', 'w') as summary:
            summary.write(f'mesh_name: {ds.attrs["mesh_name"]}\n')
            summary.write(
                'target_grid_resolution_degrees: '
                f'{ds.attrs["target_grid_resolution_degrees"]}\n'
            )
            summary.write(
                f'cellWidth_min_km: {float(np.min(ds.cellWidth.values)):.6f}\n'
            )
            summary.write(
                f'cellWidth_max_km: {float(np.max(ds.cellWidth.values)):.6f}\n'
            )
            background = ds.background_cell_width.values
            count = int(np.count_nonzero(ds.cellWidth.values != background))
            summary.write(
                f'cellWidth_differs_from_background_count: {count}\n'
            )
            for var_name in [
                'background_cell_width',
                'ocean_background_cell_width',
                'land_river_cell_width',
                'pre_coastline_cell_width',
                'coastline_cell_width',
                'coastal_transition_delta',
                'river_channel_cell_width',
                'river_outlet_cell_width',
            ]:
                values = ds[var_name].values
                summary.write(
                    f'{var_name}_min_km: {float(np.min(values)):.6f}\n'
                )
                summary.write(
                    f'{var_name}_max_km: {float(np.max(values)):.6f}\n'
                )
                if var_name not in [
                    'background_cell_width',
                    'ocean_background_cell_width',
                    'coastal_transition_delta',
                ]:
                    count = int(np.count_nonzero(values < background))
                    summary.write(
                        f'{var_name}_finer_than_background_count: {count}\n'
                    )
            for prefix in ['river_channel', 'river_outlet']:
                _write_attr_count_summary(
                    summary=summary, attrs=ds.attrs, prefix=prefix
                )
            for control_value, label in enumerate(
                ['background', 'coastline', 'river_channel', 'river_outlet']
            ):
                count = int(
                    np.count_nonzero(ds.active_control.values == control_value)
                )
                summary.write(f'{label}_count: {count}\n')


def _get_cell_width_norm_and_ticks(fields):
    """
    Get a shared linear norm and optional readable ticks for cell-width plots.
    """
    finite_values = np.concatenate(
        [field[np.isfinite(field)].ravel() for field in fields]
    )
    vmin = float(np.min(finite_values))
    vmax = float(np.max(finite_values))

    if np.isclose(vmin, vmax):
        padding = max(abs(vmin) * 0.01, 1.0)
        return mcolors.Normalize(vmin=vmin - padding, vmax=vmax + padding), [
            vmin
        ]

    unique_values = np.unique(finite_values)
    if unique_values.size <= 6:
        ticks = unique_values
    else:
        ticks = None
    return mcolors.Normalize(vmin=vmin, vmax=vmax), ticks


def _get_difference_norm_and_ticks(field):
    """
    Get a zero-centered norm and optional readable ticks for difference plots.
    """
    finite_values = field[np.isfinite(field)]
    max_abs = float(np.max(np.abs(finite_values)))
    if np.isclose(max_abs, 0.0):
        max_abs = 1.0
        ticks = [0.0]
    else:
        ticks = [-max_abs, 0.0, max_abs]

    return mcolors.TwoSlopeNorm(
        vmin=-max_abs, vcenter=0.0, vmax=max_abs
    ), ticks


def _write_attr_count_summary(summary, attrs, prefix):
    """
    Write optional sizing-candidate provenance counts.
    """
    for suffix in [
        'mask_count',
        'finer_than_background_count',
        'equal_to_background_count',
        'coarser_than_background_count',
    ]:
        attr_name = f'{prefix}_{suffix}'
        if attr_name in attrs:
            summary.write(f'{attr_name}: {attrs[attr_name]}\n')
