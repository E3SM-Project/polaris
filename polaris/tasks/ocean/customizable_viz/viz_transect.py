import cmocean  # noqa: F401
import xarray as xr
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect

from polaris.ocean.model import OceanIOStep


class VizTransect(OceanIOStep):
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
        section_name = 'customizable_viz_transect'
        self.variables = self.config.getlist(
            section_name, 'variables', dtype=str
        )
        self.time_stamp = self.config.get(section_name, 'time_stamp')

        for var_name in self.variables:
            self.add_output_file(f'{var_name}__transect_{self.time_stamp}.png')

    def run(self):
        ds = xr.open_dataset('input.nc')
        # ds_init = self.open_model_dataset('initial_state.nc')

        section = self.config['customizable_viz_transect']

        # time_stamp = self.time_stamp
        # tidx = np.argwhere(ds['xtime_startMonthly'].values == time_stamp)
        t_index = 0
        # ds = ds.isel(Time=t_index)

        x_start = section.getfloat('x_start')
        x_end = section.getfloat('x_end')
        y_start = section.getfloat('y_start')
        y_end = section.getfloat('y_end')
        vmin = section.getfloat('vmin')
        vmax = section.getfloat('vmax')
        x = xr.DataArray(data=[x_start, x_end])
        y = xr.DataArray(data=[y_start, y_end])
        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds,
            layer_thickness=ds.layerThickness.isel(Time=t_index),
            bottom_depth=ds.bottomDepth,
            min_level_cell=ds.minLevelCell - 1,
            max_level_cell=ds.maxLevelCell - 1,
            spherical=True,
        )

        for var_name in self.variables:
            mpas_field = ds[var_name].isel(Time=t_index)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=mpas_field,
                title=f'{var_name}',
                out_filename=f'{var_name}_transect_t{self.time_stamp}.png',
                interface_color='gray',
                vmin=vmin,
                vmax=vmax,
                cmap='cmo.thermal',
                # colorbar_label=r'$^\circ$C',
                colorbar_label=r'g/kg',
                color_start_and_end=True,
            )
