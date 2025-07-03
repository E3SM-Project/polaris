import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.viz import plot_global_mpas_field


class Viz(OceanIOStep):
    def __init__(self, component, name='viz', subdir=None):
        super().__init__(component=component, name=name, subdir=subdir)
        section = self.config.section('customizable_viz')
        mesh_file = section.get('mesh_file')
        input_file = section.get('input_file')
        self.add_input_file(
            filename='input.nc',
            target=input_file,
        )
        self.add_input_file(
            filename='mesh.nc',
            target=mesh_file,
        )
        section = self.config.section('customizable_viz_horiz_field')
        self.variables = section.getlist('variables')
        self.time_stamp = section.get('time_stamp')

        for var_name in self.variables:
            self.add_output_file(f'{var_name}_{self.time_stamp}.png')

    def run(self):
        # section = self.config.section('customizable_viz_horiz_field')

        ds = xr.open_dataset('input.nc')
        # ds_init = self.open_model_dataset('initial_state.nc')

        time_stamp = self.time_stamp
        tidx = np.argwhere(ds['xtime_startMonthly'].values == time_stamp)
        ds = ds.isel(Time=tidx)

        for var_name in self.variables:
            var = ds[var_name]
            if 'nVertLevels' in var.sizes:
                var = var.isel(nVertLevels=0)

            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=var,
                out_filename=f'{var_name}_{time_stamp}.png',
                config=self.config,
                colormap_section='customizable_viz',
                title=f'{var_name} at {time_stamp}',
                plot_land=True,
                central_longitude=180.0,
            )
