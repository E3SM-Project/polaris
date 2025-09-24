import cmocean  # noqa: F401
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.customizable_viz.viz import (
    get_viz_defaults,
)
from polaris.viz import plot_polar_mpas_field


class VizHorizField(OceanIOStep):
    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)

    # def setup(self):
    #    section = self.config['customizable_viz']
    #    # mesh_file = section.get('mesh_file')
    #    input_file = section.get('input_file')
    #    self.add_input_file(
    #        filename='input.nc',
    #        target=input_file,
    #    )
    #    # self.add_input_file(
    #    #    filename='mesh.nc',
    #    #    target=mesh_file,
    #    # )
    #    section_name = 'customizable_viz_horiz_field'
    #    self.variables = self.config.getlist(
    #        section_name, 'variables', dtype=str
    #    )
    #    self.time_stamp = self.config.get(section_name, 'time_stamp')

    #    for var_name in self.variables:
    #        self.add_output_file(f'{var_name}_horiz_{self.time_stamp}.png')

    def runtime_setup(self):
        section = self.config['customizable_viz']
        self.mesh_file = section.get('mesh_file')
        self.input_file = section.get('input_file')

    def run(self):
        section_name = 'customizable_viz_horiz_field'
        section = self.config[section_name]

        # Determine the projection from the config file
        # projection_name = section.get('projection')
        central_longitude = section.getfloat('central_longitude')
        # projection = get_projection(projection_name,
        #                            central_longitude=central_longitude)

        # These settings are determined by the MPAS-Ocean mesh
        # transform = cartopy.crs.Geodetic()
        # use_latlon = True

        # Descriptor is none for the first variable and assigned thereafter
        descriptor = None
        # ds_mesh = self.open_model_dataset(self.mesh_file)
        # Shouldn't be necessary because mesh should have attr is_spherical
        # ds_mesh.attrs['is_periodic'] = 'NO'
        # descriptor = mosaic.Descriptor(
        #    ds_mesh,
        #    projection=projection,
        #    transform=transform,
        #    use_latlon=use_latlon,
        # )
        ds = self.open_model_dataset(self.input_file, decode_timedelta=False)
        if 'timeSeriesStatsMonthly' in self.input_file:
            prefix = 'timeMonthly_avg_'
            time_variable = 'xtime_startMonthly'
        else:
            print('did not find timeSeriesStatsMonthly in input_file name')
            prefix = ''
            time_variable = 'xtime'

        t_index = 0
        start_time = ds[time_variable].values[t_index].decode()
        time_stamp = start_time.split('_')[0]

        # TODO consider supporting setting a time_stamp value in the config
        # file to enable extraction from streams whose output frequency is
        # different from the file frequency
        # tidx = np.argwhere(ds['xtime'].values == time_stamp)
        ds = ds.isel(Time=t_index)
        z_index = 0
        # z_index = np.argmin(np.abs(ds['zMid'].values - z_target))

        viz_dict = get_viz_defaults()
        variables = self.config.getlist(section_name, 'variables', dtype=str)
        min_latitude = section.getfloat('min_latitude')
        max_latitude = section.getfloat('max_latitude')
        min_longitude = section.getfloat('min_longitude')
        max_longitude = section.getfloat('max_longitude')

        for var_name in variables:
            full_var_name = f'{prefix}{var_name}'
            if full_var_name not in ds.keys():
                print(
                    f'Skipping {full_var_name}, not found in {self.input_file}'
                )
                continue

            mpas_field = ds[full_var_name]
            if 'nVertLevels' in mpas_field.sizes:
                mpas_field = mpas_field.isel(nVertLevels=z_index)

            if self.config.has_option(section_name, 'vmin'):
                vmin = section.getfloat('vmin')
            else:
                vmin = np.percentile(mpas_field.values, 5)
            if self.config.has_option(section_name, 'vmax'):
                vmax = section.getfloat('vmax')
            else:
                vmax = np.percentile(mpas_field.values, 95)
            if vmin < 0.0:
                vmax = max(abs(vmax), abs(vmin))
                vmin = -vmax

            if var_name in viz_dict.keys():
                cmap = viz_dict[var_name]['colormap']
                units = viz_dict[var_name]['units']
            else:
                cmap = viz_dict['default']['colormap']
                units = viz_dict['default']['units']
            self.config.set(section_name, 'colormap_name', value=cmap)
            self.config.set(
                section_name,
                'norm_args',
                value='{"vmin": ' + str(vmin) + ', "vmax": ' + str(vmax) + '}',
            )

            # descriptor = plot_global_mpas_field(
            descriptor = plot_polar_mpas_field(
                mesh_filename=self.mesh_file,
                da=mpas_field,
                out_filename=f'{var_name}_horiz_{time_stamp}.png',
                config=self.config,
                colormap_section='customizable_viz_horiz_field',
                descriptor=descriptor,
                colorbar_label=f'{var_name} {units}',
                plot_land=True,
                central_longitude=central_longitude,
                min_latitude=min_latitude,
                max_latitude=max_latitude,
                min_longitude=min_longitude,
                max_longitude=max_longitude,
            )
