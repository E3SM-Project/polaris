import os

import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.ocean.model import OceanIOStep as OceanIOStep
from polaris.viz import (
    determine_time_variable,
    get_viz_defaults,
)


class VizTransect(OceanIOStep):
    """
    A step for visualizing MPAS vertical transects
    """

    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)

    def runtime_setup(self):
        section = self.config['customizable_viz']
        self.mesh_file = section.get('mesh_file')
        self.input_file = section.get('input_file')
        self.transect_file = section.get('transect_file')
        section_name = 'customizable_viz_transect'
        self.variables = self.config.getlist(
            section_name, 'variables', dtype=str
        )
        if not self.variables:
            raise ValueError(
                f'No variables specified in the {section_name} section of '
                'the config file.'
            )

    def run(self):
        section_name = 'customizable_viz_transect'
        section = self.config[section_name]
        layer_interface_color = section.get('layer_interface_color')
        x_start = section.getfloat('x_start')
        x_end = section.getfloat('x_end')
        y_start = section.getfloat('y_start')
        y_end = section.getfloat('y_end')

        x = xr.DataArray(data=[x_start, x_end])
        y = xr.DataArray(data=[y_start, y_end])

        ds_mesh = self.open_model_dataset(self.mesh_file)
        ds = self.open_model_dataset(self.input_file, decode_timedelta=False)
        # TODO support time selection from config file
        if 'Time' in ds.dims:
            t_index = 0
            ds = ds.isel(Time=t_index)
        prefix, time_variable = determine_time_variable(ds)
        if time_variable is not None:
            start_time = ds[time_variable].values
            if isinstance(start_time, np.ndarray):
                start_time = (
                    start_time.item()
                    if start_time.size == 1
                    else start_time[0]
                )
            if isinstance(start_time, (bytes, bytearray, np.bytes_)):
                start_time = start_time.decode()
            else:
                start_time = str(start_time)
            time_stamp = f'_{start_time.split("_")[0]}'
        else:
            time_stamp = ''

        if os.path.exists(self.transect_file):
            ds_transect = xr.open_dataset(self.transect_file)
            self.logger.info(f'loading transect from {self.transect_file}')
        else:
            ds_transect = compute_transect(
                x=x,
                y=y,
                ds_horiz_mesh=ds_mesh,
                layer_thickness=ds[f'{prefix}layerThickness'],
                bottom_depth=ds_mesh.bottomDepth,
                min_level_cell=ds_mesh.minLevelCell - 1,
                max_level_cell=ds_mesh.maxLevelCell - 1,
                spherical=True,
            )
            self.logger.info('saving transect to {self.transect_file}')
            write_netcdf(ds_transect, self.transect_file)

        cell_indices = ds_transect.cellIndices
        ds_data = ds.isel(nCells=cell_indices)

        viz_dict = get_viz_defaults()
        if self.config.has_option(section_name, 'colormap_range_percent'):
            colormap_range_percent = self.config.getfloat(
                section_name, 'colormap_range_percent'
            )
        else:
            colormap_range_percent = 0.0

        for var_name in self.variables:
            if 'accumulated' in var_name:
                full_var_name = var_name
            else:
                full_var_name = f'{prefix}{var_name}'
            if full_var_name not in ds.keys():
                if f'{prefix}activeTracers_{var_name}' in ds.keys():
                    full_var_name = f'{prefix}activeTracers_{var_name}'
                elif var_name == 'columnThickness':
                    ds[full_var_name] = ds.bottomDepth + ds.ssh
                else:
                    print(
                        f'Skipping {full_var_name}, '
                        f'not found in {self.input_file}'
                    )
                    continue
            print(f'Plotting {full_var_name}')
            mpas_field = ds[f'{full_var_name}']
            data = ds_data[f'{full_var_name}']
            if var_name in viz_dict.keys():
                cmap = viz_dict[var_name]['colormap']
                units = viz_dict[var_name]['units']
            else:
                cmap = viz_dict['default']['colormap']
                units = viz_dict['default']['units']

            if colormap_range_percent > 0.0:
                mask = data.values == data.values
                vmin = np.percentile(data.values[mask], colormap_range_percent)
                vmax = np.percentile(
                    data.values[mask], 100.0 - colormap_range_percent
                )
            else:
                if 'nVertLevelsP1' in ds.sizes:
                    plot_data = data.isel(
                        nVertLevelsP1=ds_transect.levelIndices
                    )
                else:
                    plot_data = data.isel(nVertLevels=ds_transect.levelIndices)
                valid = ds_transect.validCells
                plot_data = plot_data.where(valid)
                vmin = plot_data.min().values
                vmax = plot_data.max().values

            if self.config.has_option(
                section_name, 'vmin'
            ) and self.config.has_option(section_name, 'vmax'):
                vmin = section.getfloat('vmin')
                vmax = section.getfloat('vmax')
            elif (
                cmap == 'cmo.balance'
                or 'vertVelocityTop' in var_name
                or 'Tendency' in var_name
                or 'Flux' in var_name
            ):
                vmax = max(abs(vmin), abs(vmax))
                vmin = -vmax

            norm_args = f'"vmin": {vmin}, "vmax": {vmax}'
            self.config.set(
                section_name,
                'norm_args',
                value='{' + norm_args + '}',
            )

            plot_transect(
                ds_transect=ds_transect,
                mpas_field=mpas_field,
                title=f'{var_name}',
                out_filename=f'{var_name}_transect{time_stamp}.png',
                interface_color=layer_interface_color,
                vmin=vmin,
                vmax=vmax,
                cmap=cmap,
                colorbar_label=units,
                color_start_and_end=True,
            )
