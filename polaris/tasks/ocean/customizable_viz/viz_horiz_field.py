import cmocean  # noqa: F401
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.viz import plot_global_mpas_field


class VizHorizField(OceanIOStep):
    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)

    def setup(self):
        section = self.config['customizable_viz']
        # mesh_file = section.get('mesh_file')
        input_file = section.get('input_file')
        self.add_input_file(
            filename='input.nc',
            target=input_file,
        )
        # self.add_input_file(
        #    filename='mesh.nc',
        #    target=mesh_file,
        # )
        section_name = 'customizable_viz_horiz_field'
        self.variables = self.config.getlist(
            section_name, 'variables', dtype=str
        )
        self.time_stamp = self.config.get(section_name, 'time_stamp')

        for var_name in self.variables:
            self.add_output_file(f'{var_name}_horiz_{self.time_stamp}.png')

    def run(self):
        ds = xr.open_dataset('input.nc')
        # ds_init = self.open_model_dataset('initial_state.nc')

        # section = self.config['customizable_viz_horiz_field']

        time_stamp = self.time_stamp
        ##tidx = np.argwhere(ds['xtime_startMonthly'].values == time_stamp)
        t_index = 0
        ds = ds.isel(Time=t_index)
        z_index = 0
        # z_index = np.argmin(np.abs(ds['zMid'].values - z_target))

        for var_name in self.variables:
            var = ds[var_name]
            if 'nVertLevels' in var.sizes:
                var = var.isel(nVertLevels=z_index)
            plot_global_mpas_field(
                # mesh_filename='mesh.nc',
                mesh_filename='input.nc',
                da=var,
                out_filename=f'{var_name}_horiz_{time_stamp}.png',
                config=self.config,
                colormap_section='customizable_viz_horiz_field',
                title=f'{var_name} at {time_stamp}',
                plot_land=True,
                central_longitude=180.0,
            )
