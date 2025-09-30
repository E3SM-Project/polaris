import cmocean  # noqa: F401
import numpy as np

from polaris.ocean.model import OceanIOStep
from polaris.viz import (
    get_viz_defaults,
    plot_global_mpas_field,
)


class VizHorizField(OceanIOStep):
    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)

    def runtime_setup(self):
        section = self.config['customizable_viz']
        self.mesh_file = section.get('mesh_file')
        self.input_file = section.get('input_file')

    def run(self):  # noqa:C901
        section_name = 'customizable_viz_horiz_field'
        section = self.config[section_name]

        # Determine the projection from the config file
        projection_name = section.get('projection')
        central_longitude = section.getfloat('central_longitude')

        # Descriptor is none for the first variable and assigned thereafter
        descriptor = None

        ds_mesh = self.open_model_dataset(
            self.mesh_file, decode_timedelta=False
        )
        min_latitude = section.getfloat('min_latitude')
        max_latitude = section.getfloat('max_latitude')
        min_longitude = section.getfloat('min_longitude')
        max_longitude = section.getfloat('max_longitude')
        lat_cell = ds_mesh['latCell'] * 180.0 / np.pi
        lon_cell = ds_mesh['lonCell'] * 180.0 / np.pi
        if min_longitude < lon_cell.min():
            min_longitude += 360.0
            max_longitude += 360.0
        cell_indices = np.where(
            (lat_cell >= min_latitude)
            & (lat_cell <= max_latitude)
            & (lon_cell >= min_longitude)
            & (lon_cell <= max_longitude)
        )
        if len(cell_indices[0]) == 0:
            raise ValueError(
                'No cells found within the specified lat/lon bounds. '
                'Please adjust the min/max latitude/longitude values.'
            )
        ds_mesh = ds_mesh.isel(nCells=cell_indices[0])
        # z_index = 0
        z_target = section.getfloat('z_target')
        z_bottom = ds_mesh['restingThickness'].cumsum(dim='nVertLevels')
        dz = z_bottom.mean(dim='nCells') - z_target
        z_index = np.argmin(np.abs(dz.values))
        if dz[z_index] > 0 and z_index > 0:
            z_index -= 1
        z_mean = z_bottom.mean(dim='nCells')[z_index].values
        print(
            f'Using z_index {z_index} for z_target {z_target} '
            f'with mean depth {z_mean} '
        )

        ds = self.open_model_dataset(self.input_file, decode_timedelta=False)
        if 'timeSeriesStatsMonthly' in self.input_file:
            prefix = 'timeMonthly_avg_'
            time_variable = 'xtime_startMonthly'
            has_time_variable = True
        elif 'xtime' in ds.keys():
            prefix = ''
            time_variable = 'xtime'
            has_time_variable = True
        elif 'Time' in ds.keys():
            prefix = 'timeMonthly_avg_'
            time_variable = 'Time'
            has_time_variable = True
        else:
            has_time_variable = False
        if has_time_variable:
            t_index = 0
            start_time = ds[time_variable].values[t_index]
            # if 'Time' not in ds.keys():
            start_time = start_time.decode()
            time_stamp = start_time.split('_')[0]
            # else:
            #    time_stamp = start_time.strftime('%Y-%m-%d')

            # TODO consider supporting setting a time_stamp value in the config
            # file to enable extraction from streams whose output frequency is
            # different from the file frequency
            # tidx = np.argwhere(ds['xtime'].values == time_stamp)
            ds = ds.isel(Time=t_index)
        ds = ds.isel(nCells=cell_indices[0])
        if ds.sizes['nCells'] != ds_mesh.sizes['nCells']:
            raise ValueError(
                f'Number of cells in the mesh {ds_mesh.sizes["nCells"]} '
                f'and input {ds.sizes["nCells"]} do not match. '
            )
        print(f'Using dataset with nCells={ds_mesh.sizes["nCells"]}')
        viz_dict = get_viz_defaults()
        variables = self.config.getlist(section_name, 'variables', dtype=str)

        for var_name in variables:
            if 'accumulated' in var_name:
                full_var_name = var_name
            else:
                full_var_name = f'{prefix}{var_name}'
            if full_var_name not in ds.keys():
                if f'{prefix}activeTracers_{var_name}' in ds.keys():
                    full_var_name = f'{prefix}activeTracers_{var_name}'
                else:
                    print(
                        f'Skipping {full_var_name}, '
                        f'not found in {self.input_file}'
                    )
                    continue
            print(f'Plotting {full_var_name}')
            filename_suffix = ''
            mpas_field = ds[full_var_name]
            if 'nVertLevels' in mpas_field.sizes:
                mpas_field = mpas_field.isel(nVertLevels=z_index)
                if z_index != 0:
                    filename_suffix = f'_z{z_index}'

            if self.config.has_option(section_name, 'colormap_name'):
                cmap = self.config.get(section_name, 'colormap_name')
            else:
                if var_name in viz_dict.keys():
                    cmap = viz_dict[var_name]['colormap']
                else:
                    cmap = viz_dict['default']['colormap']
                self.config.set(section_name, 'colormap_name', value=cmap)

            if self.config.has_option(
                section_name, 'vmin'
            ) and self.config.has_option(section_name, 'vmax'):
                vmin = section.getfloat('vmin')
                vmax = section.getfloat('vmax')
            else:
                if (
                    cmap == 'cmo.balance'
                    or 'vertVelocityTop' in var_name
                    or 'Tendency' in var_name
                    or 'Flux' in var_name
                ):
                    vmax = max(abs(vmax), abs(vmin))
                    vmin = -vmax
                else:
                    vmin = np.percentile(mpas_field.values, 5)
                    vmax = np.percentile(mpas_field.values, 95)
            if var_name in viz_dict.keys():
                units = viz_dict[var_name]['units']
            else:
                units = viz_dict['default']['units']

            self.config.set(
                section_name,
                'norm_args',
                value='{"vmin": ' + str(vmin) + ', "vmax": ' + str(vmax) + '}',
            )

            descriptor = plot_global_mpas_field(
                mesh_filename=self.mesh_file,
                da=mpas_field,
                out_filename=f'{var_name}_horiz_{time_stamp}{filename_suffix}.png',
                config=self.config,
                colormap_section='customizable_viz_horiz_field',
                descriptor=descriptor,
                colorbar_label=f'{var_name} {units}',
                plot_land=True,
                projection_name=projection_name,
                central_longitude=central_longitude,
                min_latitude=min_latitude,
                max_latitude=max_latitude,
                min_longitude=min_longitude,
                max_longitude=max_longitude,
            )
