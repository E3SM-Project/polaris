import os

import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.viz import (
    determine_time_variable,
    get_viz_defaults,
    plot_global_mpas_field,
)


class VizHorizField(OceanIOStep):
    """
    A step for visualizing MPAS horizontal fields

    Attributes
    ----------
    mesh_file : str
        Absolute path to the mesh file

    input_file : str
        Absolute path to the data file with fields to visualize

    transect_file : str
        Absolute path to a transect file produced by
        polaris.tasks.ocean.customizable_viz.viz_transect.VizTransect

    variables : list of str
        Names of variables to visualize
    """

    def __init__(self, component, name, indir):
        super().__init__(component=component, name=name, indir=indir)
        self.mesh_file = ''
        self.input_file = ''
        self.transect_file = ''
        self.variables = []

    def runtime_setup(self):
        section = self.config['customizable_viz']
        self.mesh_file = section.get('mesh_file')
        self.input_file = section.get('input_file')
        self.transect_file = section.get('transect_file')

        section_name = 'customizable_viz_horiz_field'
        self.variables = self.config.getlist(
            section_name, 'variables', dtype=str
        )
        if not self.variables:
            raise ValueError(
                f'No variables specified in the {section_name} section of '
                'the config file.'
            )

    def run(self):  # noqa:C901
        if not os.path.exists(self.mesh_file):
            raise ValueError(f'Mesh file {self.mesh_file} is not found')
        if not os.path.exists(self.input_file):
            raise ValueError(f'Input file {self.input_file} is not found')

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
        lat_cell = np.rad2deg(ds_mesh['latCell'])
        lon_cell = np.rad2deg(ds_mesh['lonCell'])
        if min_longitude < 0.0 and lon_cell.min().values > 0.0:
            max_longitude_copy = max_longitude
            max_longitude = 360.0 - min_longitude
            min_longitude = max_longitude_copy
        cell_indices = np.where(
            (lat_cell >= min_latitude)
            & (lat_cell <= max_latitude)
            & (lon_cell >= min_longitude)
            & (lon_cell <= max_longitude)
        )
        if len(cell_indices[0]) == 0:
            raise ValueError(
                f'No cells of {ds_mesh.sizes["nCells"]} cells found within the'
                ' specified lat/lon bounds. Please adjust the min/max '
                'latitude/longitude values to be within the bounds of the '
                f'dataset: latitude '
                f'{lat_cell.min().values},{lat_cell.max().values} \n'
                f'longitude {lon_cell.min().values},{lon_cell.max().values}'
            )
        print(
            f'Using {len(cell_indices[0])} cells of '
            f'{ds_mesh.sizes["nCells"]} cells in the mesh'
        )
        ds_mesh = ds_mesh.isel(nCells=cell_indices[0])
        if 'nVertLevels' in ds_mesh.dims:
            z_target = section.getfloat('z_target')
            if 'restingThickness' in ds_mesh.keys():
                h_rest = ds_mesh.restingThickness
                z_bottom = h_rest.cumsum(dim='nVertLevels')
                dz = z_bottom.mean(dim='nCells') - z_target
                z_index = np.argmin(np.abs(dz.values))
                if dz[z_index] > 0 and z_index > 0:
                    z_index -= 1
                z_mean = z_bottom.mean(dim='nCells')[z_index].values
                print(
                    f'Using z_index {z_index} for z_target {z_target} '
                    f'with mean depth {z_mean} '
                )
            else:
                z_index = 0

        ds = self.open_model_dataset(self.input_file, decode_timedelta=False)

        if 'Time' in ds.sizes:
            t_index = 0
            # TODO support different time selection from config file
            ds = ds.isel(Time=t_index)

        prefix, time_variable = determine_time_variable(ds)
        # Default to empty stamp; only set if we have a usable scalar time
        time_stamp = ''
        if time_variable is not None:
            start_time = ds[time_variable].values

            # If it's a NumPy array, handle scalar vs. multi-value arrays
            if isinstance(start_time, np.ndarray):
                if start_time.size == 1:
                    # extract the scalar value
                    start_time = start_time.item()
                else:
                    # multiple times -> no single timestamp to use
                    start_time = None

            if start_time is not None:
                # decode bytes if necessary, otherwise convert to string
                if isinstance(start_time, (bytes, bytearray, np.bytes_)):
                    start_time = start_time.decode()
                else:
                    start_time = str(start_time)
                time_stamp = f'_{start_time.split("_")[0]}'

        if 'nCells' in ds.dims:
            ds = ds.isel(nCells=cell_indices[0])
            if ds.sizes['nCells'] != ds_mesh.sizes['nCells']:
                raise ValueError(
                    f'Number of cells in the mesh {ds_mesh.sizes["nCells"]} '
                    f'and input {ds.sizes["nCells"]} do not match. '
                )
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

            if colormap_range_percent > 0.0:
                vmin = np.percentile(mpas_field.values, colormap_range_percent)
                vmax = np.percentile(
                    mpas_field.values, 100.0 - colormap_range_percent
                )
            else:
                vmin = mpas_field.min().values
                vmax = mpas_field.max().values

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

            self.config.set(
                section_name,
                'norm_args',
                value='{"vmin": ' + str(vmin) + ', "vmax": ' + str(vmax) + '}',
            )

            if var_name in viz_dict.keys():
                units = viz_dict[var_name]['units']
            else:
                units = viz_dict['default']['units']

            if os.path.exists(self.transect_file):
                ds_transect = xr.open_dataset(self.transect_file)
            else:
                ds_transect = None
            # Only apply regional bounds for cell-centered fields
            if 'nEdges' in mpas_field.dims or 'nVertices' in mpas_field.dims:
                descriptor = plot_global_mpas_field(
                    mesh_filename=self.mesh_file,
                    da=mpas_field,
                    out_filename=f'{var_name}_horiz{time_stamp}{filename_suffix}.png',
                    config=self.config,
                    colormap_section='customizable_viz_horiz_field',
                    descriptor=descriptor,
                    colorbar_label=f'{var_name} [{units}]',
                    plot_land=True,
                    projection_name=projection_name,
                    ds_transect=ds_transect,
                    central_longitude=central_longitude,
                )
            elif 'nCells' in mpas_field.dims and 'nVertices' in ds_mesh.dims:
                descriptor = plot_global_mpas_field(
                    mesh_filename=self.mesh_file,
                    da=mpas_field,
                    out_filename=f'{var_name}_horiz{time_stamp}{filename_suffix}.png',
                    config=self.config,
                    colormap_section='customizable_viz_horiz_field',
                    descriptor=descriptor,
                    colorbar_label=f'{var_name} [{units}]',
                    plot_land=True,
                    projection_name=projection_name,
                    central_longitude=central_longitude,
                    cell_indices=cell_indices[0],
                    ds_transect=ds_transect,
                )
            else:
                raise ValueError(
                    f'{var_name} does not have expected '
                    'dimensions of nCells, nEdges, or nVertices'
                )
