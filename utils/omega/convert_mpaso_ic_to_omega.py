#!/usr/bin/env python3

import argparse
from pathlib import Path

import gsw
import numpy as np
import xarray as xr
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
        '--zero-velocity-mpas-file',
        help=(
            'Output MPAS-O initial condition file with only velocity fields '
            'zeroed. If omitted, defaults to <input-file>.zero_velocity.nc.'
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
    return parser.parse_args()


def convert_to_omega(
    input_file, output_file, eos_type, zero_velocity_mpas_file
):
    with xr.open_dataset(input_file, decode_times=False) as ds_in:
        ds = ds_in.load()

    output_file = _append_eos_suffix(output_file, eos_type)

    if zero_velocity_mpas_file is None:
        input_path = Path(input_file)
        zero_velocity_mpas_file = (
            str(input_path.with_suffix('')) + '.zero_velocity.nc'
        )

    ds_mpas_zero = ds.copy(deep=True)
    mpas_velocity_fields = _zero_velocity_fields(ds_mpas_zero)
    ds_mpas_zero.to_netcdf(zero_velocity_mpas_file)
    print(f'Wrote {zero_velocity_mpas_file}')
    if mpas_velocity_fields:
        print(
            f'Zeroed MPAS velocity fields: {", ".join(mpas_velocity_fields)}'
        )
    else:
        print('No MPAS velocity fields found to zero')

    required_vars = ['layerThickness']
    missing = [name for name in required_vars if name not in ds.variables]
    if missing:
        raise ValueError(f'Missing required variables: {missing}')

    valid = ds['layerThickness'].values > 0.0
    if eos_type == 'teos10':
        spec_vol = _convert_teos10_tracers(ds, valid)
    elif eos_type == 'linear':
        spec_vol = _compute_linear_spec_vol(ds, valid)

    _add_pseudo_thickness(ds, valid, spec_vol)
    velocity_fields = _zero_velocity_fields(ds)
    ds = _map_mpaso_to_omega(ds)

    ds.to_netcdf(output_file)

    print(f'Wrote {output_file}')
    if eos_type == 'teos10':
        print('Converted temperature: potential -> conservative')
        print('Converted salinity: practical -> absolute')
    else:
        print(
            'Kept temperature and salinity unchanged '
            '(potential temperature and practical salinity)'
        )
    print('Added PseudoThickness')
    if velocity_fields:
        print(f'Zeroed velocity fields: {", ".join(velocity_fields)}')
    else:
        print('No velocity fields found to zero')


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


def main():
    args = parse_args()
    convert_to_omega(
        args.input_file,
        args.output_file,
        args.eos_type,
        args.zero_velocity_mpas_file,
    )


if __name__ == '__main__':
    main()
