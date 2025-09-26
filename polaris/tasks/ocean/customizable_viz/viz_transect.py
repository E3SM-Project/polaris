import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.ocean.model import OceanIOStep as OceanIOStep
from polaris.viz import get_viz_defaults


class VizTransect(OceanIOStep):
    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)

    def runtime_setup(self):
        section = self.config['customizable_viz']
        self.mesh_file = section.get('mesh_file')
        self.input_file = section.get('input_file')

    def run(self):
        section_name = 'customizable_viz_transect'
        variables = self.config.getlist(section_name, 'variables', dtype=str)
        section = self.config[section_name]
        # time_stamp = section.get('time_stamp')
        layer_interface_color = section.get('layer_interface_color')
        x_start = section.getfloat('x_start')
        x_end = section.getfloat('x_end')
        y_start = section.getfloat('y_start')
        y_end = section.getfloat('y_end')

        x = xr.DataArray(data=[x_start, x_end])
        y = xr.DataArray(data=[y_start, y_end])

        ds_mesh = self.open_model_dataset(self.mesh_file)
        ds = self.open_model_dataset(self.input_file, decode_timedelta=False)
        # tidx = np.argwhere(ds['xtime_startMonthly'].values == time_stamp)
        t_index = 0
        if 'xtime_startMonthly' in ds.keys():
            start_time = ds['xtime_startMonthly'].values[t_index].decode()
            time_stamp = start_time.split('_')[0]

        ds = ds.isel(Time=t_index)
        # Transect is constructed for nVertLevels quantities
        if 'nVertLevelsP1' in ds.sizes:
            ds = ds.isel(nVertLevelsP1=slice(0, -1))
        if 'timeSeriesStatsMonthly' in self.input_file:
            prefix = 'timeMonthly_avg_'
        else:
            prefix = ''
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

        viz_dict = get_viz_defaults()
        for var_name in variables:
            mpas_field = ds[f'{prefix}{var_name}']
            if self.config.has_option(section_name, 'vmin'):
                vmin = section.getfloat('vmin')
            else:
                vmin = np.percentile(mpas_field.values, 5)
            if self.config.has_option(section_name, 'vmax'):
                vmax = section.getfloat('vmax')
            else:
                vmax = np.percentile(mpas_field.values, 95)
            if vmax > 0.0 and vmin < 0.0:
                vmax = max(abs(vmax), abs(vmin))
                vmin = -vmax
            if var_name in viz_dict.keys():
                cmap = viz_dict[var_name]['colormap']
                units = viz_dict[var_name]['units']
            else:
                cmap = viz_dict['default']['colormap']
                units = viz_dict['default']['units']
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=mpas_field,
                title=f'{var_name}',
                out_filename=f'{var_name}_transect_{time_stamp}.png',
                interface_color=layer_interface_color,
                vmin=vmin,
                vmax=vmax,
                cmap=cmap,
                colorbar_label=units,
                color_start_and_end=True,
            )
