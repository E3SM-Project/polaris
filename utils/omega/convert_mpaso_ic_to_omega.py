#!/usr/bin/env python3

import argparse
from pathlib import Path

import gsw
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from ruamel.yaml import YAML

from polaris.constants import get_constant


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'Convert MPAS-Ocean initial conditions to Omega variable names, '
            'convert TEOS-10 tracers (pt/SA -> CT/SP), zero velocity fields, '
            'and add PseudoThickness.'
        )
    )
    parser.add_argument(
        '--input-file',
        required=True,
        help='Input MPAS-Ocean initial condition file.',
    )
    parser.add_argument(
        '--output-file',
        required=True,
        help=(
            'Base output initial condition file with Omega names. The script '
            'appends .teos10eos.nc or .lineareos.nc based on --eos-type.'
        ),
    )
    parser.add_argument(
        '--eos-type',
        choices=['teos10', 'linear'],
        default='teos10',
        help=(
            'Equation of state mode: teos10 converts tracers '
            '(pt/PS -> CT/AS), linear leaves tracers unchanged '
            '(potential temperature and practical salinity).'
        ),
    )
    parser.add_argument(
        '--visualization',
        action='store_true',
        help=(
            'Generate temperature/salinity percent-difference slice '
            'figures and save next to the output NetCDF file.'
        ),
    )
    return parser.parse_args()


def convert_to_omega(input_file, output_file, eos_type, visualization=False):
    with xr.open_dataset(input_file, decode_times=False) as ds_in:
        ds_input = ds_in.load()

    output_file = _append_eos_suffix(output_file, eos_type)

    input_path = Path(input_file)
    zero_velocity_mpas_file = str(input_path.with_suffix('')) + '.mpas.nc'

    ds_mpas_zero = ds_input.copy(deep=True)
    mpas_velocity_fields = _zero_velocity_fields(ds_mpas_zero)
    _rescale_sphere_radius(ds_mpas_zero)
    _keep_selected_global_attrs(ds_mpas_zero)

    write_netcdf(ds_mpas_zero, zero_velocity_mpas_file)
    print(f'Wrote {zero_velocity_mpas_file}')
    print(
        'Rescaled MPAS earth radius, coordinates, and areas based on '
        'earth radius in pcd.yaml'
    )
    if mpas_velocity_fields:
        print(f'Zeroed velocity fields: {", ".join(mpas_velocity_fields)}')
    else:
        print('No velocity fields found to zero')
    print('Removed unnecessary global attributes')

    required_vars = ['layerThickness']
    missing = [
        name for name in required_vars if name not in ds_input.variables
    ]
    if missing:
        raise ValueError(f'Missing required variables: {missing}')

    # Keep the original input dataset untouched; all Omega transforms
    # happen on a separate working copy.
    ds_omega = ds_input.copy(deep=True)

    # Create valid mask with shape (Time, nCells, nVertLevels)
    layer_thickness_valid = ds_omega['layerThickness'].values > 0.0
    if layer_thickness_valid.ndim == 2:
        # Broadcast (nCells, nVertLevels) to (nTime, nCells, nVertLevels)
        valid = np.tile(
            layer_thickness_valid[np.newaxis, :, :],
            (ds_omega.sizes['Time'], 1, 1),
        )
    else:
        valid = layer_thickness_valid

    if eos_type == 'teos10':
        spec_vol = _convert_teos10_tracers(ds_omega, valid)
    elif eos_type == 'linear':
        spec_vol = _compute_linear_spec_vol(ds_omega, valid)

    _add_pseudo_thickness(ds_omega, valid, spec_vol)
    velocity_fields = _zero_velocity_fields(ds_omega)
    _rescale_sphere_radius(ds_omega)

    if visualization:
        _save_percent_difference_visualizations(
            ds_original=ds_mpas_zero,
            ds_omega=ds_omega,
            output_file=output_file,
        )

    ds_omega = _map_mpaso_to_omega(ds_omega)
    _keep_selected_global_attrs(ds_omega)

    write_netcdf(ds_omega, output_file)

    print(f'Wrote {output_file}')
    if eos_type == 'teos10':
        print(
            'Converted to Omega TEOS-10 temperature: potential -> conservative'
        )
        print('Converted to Omega TEOS-10 salinity: practical -> absolute')
    else:
        print(
            'Kept temperature and salinity unchanged '
            '(potential temperature and practical salinity)'
        )
    print('Added Omega variable PseudoThickness')
    print(
        'Rescaled Omega earth radius, coordinates, and areas based on '
        'earth radius in pcd.yaml'
    )
    if velocity_fields:
        print(f'Zeroed velocity fields: {", ".join(velocity_fields)}')
    else:
        print('No velocity fields found to zero')
    print(
        'Renamed variables to Omega names based on mpaso_to_omega.yaml mapping'
    )
    print('Removed unnecessary global attributes')
    if visualization:
        print('Saved temperature/salinity percent-difference visualizations')


def _to_degrees(angle):
    finite = np.isfinite(angle)
    if not np.any(finite):
        return angle
    max_abs = np.nanmax(np.abs(angle[finite]))
    if max_abs <= 2.0 * get_constant('pi') + 1.0e-12:
        return angle * get_constant('radian')
    return angle


def _append_eos_suffix(output_file, eos_type):
    eos_suffix = '.teos10eos.nc' if eos_type == 'teos10' else '.lineareos.nc'

    if output_file.endswith('.teos10eos.nc') or output_file.endswith(
        '.lineareos.nc'
    ):
        return output_file

    if output_file.endswith('.nc'):
        return f'{output_file[:-3]}{eos_suffix}'

    return f'{output_file}{eos_suffix}'


def _convert_teos10_tracers(ds, valid):
    required_vars = [
        'temperature',
        'salinity',
        'latCell',
        'lonCell',
        'layerThickness',
    ]
    missing = [name for name in required_vars if name not in ds.variables]
    if missing:
        raise ValueError(f'Missing required variables: {missing}')

    temperature = ds['temperature']
    salinity = ds['salinity']

    lat = _to_degrees(ds['latCell'].values)
    lon = _to_degrees(ds['lonCell'].values)

    conservative_temperature = np.full(temperature.shape, np.nan)
    absolute_salinity = np.full(salinity.shape, np.nan)
    spec_vol = np.full(ds['layerThickness'].shape, np.nan)

    g = get_constant('standard_acceleration_of_gravity')
    Pa_per_dbar = 1.0e4  # 1 dbar = 10000 Pa

    for time_index in range(ds.sizes['Time']):
        # Pressure at the top interface of the current layer (dbar),
        # accumulated downward via hydrostatic integration.
        # Start with surface pressure from atmospheric and sea ice
        # contributions if available, otherwise zero.
        p_interface = np.zeros(ds.sizes['nCells'])
        if 'atmosphericPressure' in ds:
            p_interface = p_interface + (
                ds['atmosphericPressure'].isel(Time=time_index).values
                / Pa_per_dbar
            )
        if 'seaIcePressure' in ds:
            p_interface = p_interface + (
                ds['seaIcePressure'].isel(Time=time_index).values / Pa_per_dbar
            )
        rho_prev = np.full(ds.sizes['nCells'], np.nan)

        for depth_index in range(ds.sizes['nVertLevels']):
            # Extract the current layer's potential temperature,
            # practical salinity, and thickness
            potential_temperature = temperature.isel(
                Time=time_index, nVertLevels=depth_index
            ).values
            practical_salinity = salinity.isel(
                Time=time_index, nVertLevels=depth_index
            ).values
            dz = (
                ds['layerThickness']
                .isel(Time=time_index, nVertLevels=depth_index)
                .values
            )

            # Create a mask for valid data points where all required inputs
            # are finite
            base_mask = (
                np.isfinite(potential_temperature)
                & np.isfinite(practical_salinity)
                & np.isfinite(dz)
                & np.isfinite(lat)
                & np.isfinite(lon)
                & valid[time_index, :, depth_index]
            )

            # Initialize output slices with NaNs
            conservative_slice = np.full(potential_temperature.shape, np.nan)
            absolute_slice = np.full(practical_salinity.shape, np.nan)
            spec_vol_slice = np.full(practical_salinity.shape, np.nan)

            # First-pass mid-layer pressure using previous layer's density
            # For the top layer, use the interface pressure directly since
            # we have no layer above to integrate through
            if depth_index == 0:
                p_mid_est = p_interface
            else:
                p_mid_est = p_interface + 0.5 * rho_prev * g * dz / Pa_per_dbar

            # Compute SA and CT to update the mid-layer pressure
            sa_tmp = np.full(practical_salinity.shape, np.nan)
            mask_tmp = base_mask & np.isfinite(p_mid_est)
            sa_tmp[mask_tmp] = gsw.SA_from_SP(
                practical_salinity[mask_tmp],
                p_mid_est[mask_tmp],
                lon[mask_tmp],
                lat[mask_tmp],
            )
            conservative_tmp = np.full(potential_temperature.shape, np.nan)
            mask_ct_tmp = mask_tmp & np.isfinite(sa_tmp)
            conservative_tmp[mask_ct_tmp] = gsw.CT_from_pt(
                sa_tmp[mask_ct_tmp],
                potential_temperature[mask_ct_tmp],
            )

            # Compute in-situ density using the estimated mid-layer pressure
            rho = np.full(practical_salinity.shape, np.nan)
            mask_rho = mask_ct_tmp & np.isfinite(conservative_tmp)
            rho[mask_rho] = gsw.rho(
                sa_tmp[mask_rho],
                conservative_tmp[mask_rho],
                p_mid_est[mask_rho],
            )

            # Updated mid-layer pressure from hydrostatic integration
            pressure_dbar = np.full(practical_salinity.shape, np.nan)
            pressure_dbar[mask_rho] = (
                p_interface[mask_rho]
                + 0.5 * rho[mask_rho] * g * dz[mask_rho] / Pa_per_dbar
            )

            # Final mask for valid points where we can compute absolute
            # salinity and specific volume
            mask = base_mask & np.isfinite(pressure_dbar)

            # Compute final SA, CT, and specific volume for valid points using
            # the updated mid-layer pressure.
            absolute_slice[mask] = gsw.SA_from_SP(
                practical_salinity[mask],
                pressure_dbar[mask],
                lon[mask],
                lat[mask],
            )
            conservative_slice[mask] = gsw.CT_from_pt(
                absolute_slice[mask],
                potential_temperature[mask],
            )
            spec_vol_slice[mask] = gsw.specvol(
                absolute_slice[mask],
                conservative_slice[mask],
                pressure_dbar[mask],
            )

            # Store the converted tracers and specific volume back into the
            # output arrays
            conservative_temperature[time_index, :, depth_index] = (
                conservative_slice
            )
            absolute_salinity[time_index, :, depth_index] = absolute_slice
            spec_vol[time_index, :, depth_index] = spec_vol_slice

            # Advance interface pressure to the bottom of this layer
            # and carry rho forward as the first-pass for the next layer
            p_interface = np.where(
                mask_rho,
                p_interface + rho * g * dz / Pa_per_dbar,
                p_interface,
            )
            rho_prev = np.where(mask_rho, rho, rho_prev)

    ds['temperature'] = xr.DataArray(
        conservative_temperature,
        dims=temperature.dims,
        attrs=temperature.attrs,
    )
    ds['salinity'] = xr.DataArray(
        absolute_salinity,
        dims=salinity.dims,
        attrs=salinity.attrs,
    )

    ds.temperature.attrs['standard_name'] = (
        'sea_water_conservative_temperature'
    )
    ds.temperature.attrs['long_name'] = 'Conservative temperature'
    ds.salinity.attrs['standard_name'] = 'sea_water_absolute_salinity'
    ds.salinity.attrs['long_name'] = 'Absolute salinity'

    return spec_vol


def _add_pseudo_thickness(ds, valid, spec_vol):
    rho_sw = get_constant('seawater_density_reference')
    pseudo_thickness = ds['layerThickness'].values / (rho_sw * spec_vol)
    pseudo_thickness = np.where(valid, pseudo_thickness, 0.0)
    ds['PseudoThickness'] = xr.DataArray(
        data=pseudo_thickness,
        dims=ds['layerThickness'].dims,
        attrs={
            'long_name': 'pseudo-layer thickness',
            'units': 'm',
            'description': 'PseudoThickness = layerThickness / '
            '(RhoSw * SpecVol)',
        },
    )


def _compute_linear_spec_vol(ds, valid):
    required_vars = ['temperature', 'salinity']
    missing = [name for name in required_vars if name not in ds.variables]
    if missing:
        raise ValueError(
            f'Missing required variables for linear EOS: {missing}'
        )

    # Match Omega LinearEos defaults in Eos.h:
    # SpecVol = 1 / (RhoT0S0 + DRhodT*T + DRhodS*S)
    drhodt = -0.2
    drhods = 0.8
    rho_t0s0 = 1.000e3

    density = (
        rho_t0s0
        + drhodt * ds['temperature'].values
        + drhods * ds['salinity'].values
    )
    spec_vol = np.full(ds['layerThickness'].shape, np.nan)

    mask = valid & np.isfinite(density) & (density > 0.0)
    spec_vol[mask] = 1.0 / density[mask]

    return spec_vol


def _rescale_sphere_radius(ds):
    if 'sphere_radius' not in ds.attrs:
        raise ValueError(
            'Global attribute sphere_radius is required to rescale xCell'
        )

    sphere_radius = float(ds.attrs['sphere_radius'])
    if sphere_radius <= 0.0:
        raise ValueError(f'Invalid sphere_radius: {sphere_radius}')

    mean_radius = get_constant('mean_radius')

    # Rescale coordinates and areas based on the ratio of mean_radius
    # in pcd.yaml versus sphere_radius in input file
    ds['xCell'] = mean_radius * ds['xCell'] / sphere_radius
    ds['yCell'] = mean_radius * ds['yCell'] / sphere_radius
    ds['zCell'] = mean_radius * ds['zCell'] / sphere_radius

    ds['xEdge'] = mean_radius * ds['xEdge'] / sphere_radius
    ds['yEdge'] = mean_radius * ds['yEdge'] / sphere_radius
    ds['zEdge'] = mean_radius * ds['zEdge'] / sphere_radius

    ds['xVertex'] = mean_radius * ds['xVertex'] / sphere_radius
    ds['yVertex'] = mean_radius * ds['yVertex'] / sphere_radius
    ds['zVertex'] = mean_radius * ds['zVertex'] / sphere_radius

    ds['dcEdge'] = mean_radius * ds['dcEdge'] / sphere_radius
    ds['dvEdge'] = mean_radius * ds['dvEdge'] / sphere_radius

    ds['areaCell'] = (
        mean_radius
        * mean_radius
        * ds['areaCell']
        / (sphere_radius * sphere_radius)
    )
    ds['areaTriangle'] = (
        mean_radius
        * mean_radius
        * ds['areaTriangle']
        / (sphere_radius * sphere_radius)
    )
    ds['kiteAreasOnVertex'] = (
        mean_radius
        * mean_radius
        * ds['kiteAreasOnVertex']
        / (sphere_radius * sphere_radius)
    )

    # Update sphere_radius global attribute to be consistent with mean_radius
    # in pcd.yaml
    ds.attrs['sphere_radius'] = mean_radius


def _keep_selected_global_attrs(ds):
    keep_attrs = {
        'on_a_sphere',
        'sphere_radius',
        'is_periodic',
        'x_period',
        'y_period',
        'mesh_spec',
        'Conventions',
        'file_id',
    }
    ds.attrs = {
        name: value for name, value in ds.attrs.items() if name in keep_attrs
    }


def _zero_velocity_fields(ds):
    velocity_fields = []
    for var_name, data_array in ds.data_vars.items():
        is_numeric = np.issubdtype(data_array.dtype, np.number)
        if is_numeric and 'velocity' in var_name.lower():
            ds[var_name] = xr.zeros_like(data_array)
            velocity_fields.append(var_name)
    return velocity_fields


def _map_mpaso_to_omega(ds):
    yaml_path = (
        Path(__file__).resolve().parents[2]
        / 'polaris'
        / 'ocean'
        / 'model'
        / 'mpaso_to_omega.yaml'
    )
    mapping_text = yaml_path.read_text()
    yaml = YAML(typ='rt')
    mapping = yaml.load(mapping_text)

    dim_map = mapping['dimensions']
    var_map = mapping['variables']

    rename = {
        name: target for name, target in dim_map.items() if name in ds.dims
    }
    rename_vars = {
        name: target for name, target in var_map.items() if name in ds
    }
    rename.update(rename_vars)

    return ds.rename(rename)


def _select_visualization_levels(ds_original, count=5):
    n_levels = ds_original.sizes['nVertLevels']
    if n_levels <= 1:
        return np.array([0], dtype=int), np.array([0.0])

    raw = np.array(
        [
            0,
            max(1, n_levels // 4),
            max(1, n_levels // 2),
            max(1, (3 * n_levels) // 4),
            n_levels - 1,
        ],
        dtype=int,
    )
    levels = np.unique(np.clip(raw, 0, n_levels - 1))
    if levels.size < count:
        levels = np.unique(
            np.round(np.linspace(0, n_levels - 1, count)).astype(int)
        )

    layer_thickness = ds_original['layerThickness'].isel(Time=0).values
    valid = layer_thickness > 0.0
    z_interface = np.zeros(
        (ds_original.sizes['nCells'], ds_original.sizes['nVertLevels'] + 1)
    )
    z_interface[:, 1:] = np.cumsum(layer_thickness, axis=1)
    z_mid = 0.5 * (z_interface[:, :-1] + z_interface[:, 1:])
    ref_z = np.nanmedian(np.where(valid, z_mid, np.nan), axis=0)

    return levels, ref_z[levels]


def _save_percent_difference_visualizations(
    ds_original, ds_omega, output_file
):
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import cmocean
        import matplotlib.colors as mcolors
        import matplotlib.pyplot as plt
        import mosaic
    except ImportError as exc:
        raise ImportError(
            'Visualization requires cartopy, cmocean, matplotlib, and mosaic.'
        ) from exc

    transform = ccrs.Geodetic()

    ds_mesh = ds_original.copy(deep=False)
    ds_mesh.attrs['is_periodic'] = 'NO'
    salinity_projection = ccrs.PlateCarree(central_longitude=0.0)
    temperature_projection = ccrs.PlateCarree(central_longitude=180.0)
    salinity_descriptor = mosaic.Descriptor(
        ds_mesh,
        projection=salinity_projection,
        transform=transform,
        use_latlon=True,
    )
    temperature_descriptor = mosaic.Descriptor(
        ds_mesh,
        projection=temperature_projection,
        transform=transform,
        use_latlon=True,
    )

    levels, depths = _select_visualization_levels(ds_original, count=5)
    valid_original = ds_original['layerThickness'].isel(Time=0).values > 0.0
    valid_omega = ds_omega['layerThickness'].isel(Time=0).values > 0.0
    output_path = Path(output_file)

    def _plot_variable(var_name, label):
        diff_slices = []
        for level in levels:
            original = (
                ds_original[var_name].isel(Time=0, nVertLevels=level).values
            )
            omega = ds_omega[var_name].isel(Time=0, nVertLevels=level).values
            valid = (
                valid_original[:, level]
                & valid_omega[:, level]
                & np.isfinite(original)
                & np.isfinite(omega)
                & (np.abs(omega) > 1.0e-12)
            )
            diff_field = np.full(original.shape, np.nan)
            if var_name == 'temperature':
                diff_field[valid] = original[valid] - omega[valid]
            else:
                diff_field[valid] = (
                    100.0 * (omega[valid] - original[valid]) / omega[valid]
                )
            diff_slices.append(diff_field)

        all_values = np.concatenate(
            [values[np.isfinite(values)] for values in diff_slices]
        )
        max_abs = (
            float(np.nanpercentile(np.abs(all_values), 99))
            if all_values.size > 0
            else 1.0
        )
        if max_abs <= 0.0:
            max_abs = 1.0

        if var_name == 'temperature':
            projection = temperature_projection
            descriptor = temperature_descriptor
        else:
            projection = salinity_projection
            descriptor = salinity_descriptor

        fig, axes = plt.subplots(
            len(levels),
            1,
            figsize=(10, 4.5 * len(levels)),
            subplot_kw=dict(projection=projection),
            constrained_layout=True,
        )
        if len(levels) == 1:
            axes = [axes]

        if var_name == 'temperature':
            fig.suptitle(
                f'{label} absolute difference: MPAS-Ocean - Omega',
                fontsize=12,
                y=1.01,
            )
        else:
            fig.suptitle(
                f'{label} percent difference: 100*(Omega - MPAS-Ocean)/Omega',
                fontsize=12,
                y=1.01,
            )

        for ax, level, depth, diff_field in zip(
            axes, levels, depths, diff_slices, strict=True
        ):
            da = xr.DataArray(diff_field, dims=['nCells'])
            if var_name == 'salinity':
                norm = mcolors.Normalize(vmin=0.47, vmax=0.496)
                pc = mosaic.polypcolor(
                    ax,
                    descriptor,
                    da,
                    cmap='jet',  # cmocean.cm.thermal,
                    norm=norm,
                    antialiased=False,
                    zorder=2,
                )
            else:
                norm = mcolors.TwoSlopeNorm(vmin=-0.2, vcenter=0.0, vmax=0.15)
                pc = mosaic.polypcolor(
                    ax,
                    descriptor,
                    da,
                    cmap=cmocean.cm.balance,
                    norm=norm,
                    antialiased=False,
                    zorder=2,
                )

            ax.add_feature(cfeature.LAND, facecolor='lightgray', zorder=3)
            ax.add_feature(cfeature.COASTLINE, linewidth=0.4, zorder=4)
            ax.add_feature(
                cfeature.BORDERS, linewidth=0.2, linestyle=':', zorder=4
            )
            ax.gridlines(
                color='gray',
                linestyle=':',
                linewidth=0.4,
                draw_labels=False,
                zorder=5,
            )
            ax.set_global()
            ax.set_title(
                f'Level {int(level)} | ~{float(depth):.0f} m', fontsize=9
            )

            plt.colorbar(
                pc,
                ax=ax,
                orientation='vertical',
                label='%' if var_name == 'salinity' else '\u00b0C',
                shrink=0.7,
                pad=0.02,
            )

        suffix = (
            'absolute_difference'
            if var_name == 'temperature'
            else 'percent_difference'
        )
        figure_path = output_path.with_name(
            f'{output_path.stem}_{var_name}_{suffix}.png'
        )
        fig.savefig(figure_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f'Wrote {figure_path}')

    _plot_variable('temperature', 'Temperature')
    _plot_variable('salinity', 'Salinity')


def main():
    args = parse_args()
    convert_to_omega(
        args.input_file,
        args.output_file,
        args.eos_type,
        args.visualization,
    )


if __name__ == '__main__':
    main()
