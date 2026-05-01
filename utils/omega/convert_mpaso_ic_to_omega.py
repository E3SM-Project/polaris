#!/usr/bin/env python3

import argparse
from pathlib import Path

import gsw
import numpy as np
import xarray as xr
from ruamel.yaml import YAML

from polaris.constants import get_constant
from polaris.ocean.vertical import compute_zint_zmid_from_layer_thickness


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
        z_mid = _get_z_mid(ds)
        spec_vol = _convert_teos10_tracers(ds, valid, z_mid)
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
    if max_abs <= 2.0 * np.pi + 1.0e-12:
        return np.rad2deg(angle)
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


def _get_z_mid(ds):
    if 'zMid' in ds.keys():
        return ds['zMid']
    else:
        required_vars = ['layerThickness', 'bottomDepth']
        missing = [name for name in required_vars if name not in ds.variables]
        if missing:
            raise ValueError(
                f'Missing required variables for depth computation: {missing}'
            )

        layer_thickness = ds['layerThickness']
        bottom_depth = ds['bottomDepth']

        n_cells = ds.sizes['nCells']
        n_vert_levels = ds.sizes['nVertLevels']

        if 'minLevelCell' not in ds.variables:
            min_level_cell = xr.DataArray(
                np.zeros(n_cells, dtype=int),
                dims=['nCells'],
                name='minLevelCell',
            )
        else:
            min_level_cell = ds['minLevelCell']

        if 'maxLevelCell' not in ds.variables:
            max_level_cell = xr.DataArray(
                np.full(n_cells, n_vert_levels - 1, dtype=int),
                dims=['nCells'],
                name='maxLevelCell',
            )
        else:
            max_level_cell = ds['maxLevelCell']

        _, z_mid = compute_zint_zmid_from_layer_thickness(
            layer_thickness,
            bottom_depth,
            min_level_cell,
            max_level_cell,
        )

        return z_mid.values


def _convert_teos10_tracers(ds, valid, z_mid):
    required_vars = [
        'temperature',
        'salinity',
        'latCell',
        'lonCell',
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

    for time_index in range(ds.sizes['Time']):
        for depth_index in range(ds.sizes['nVertLevels']):
            potential_temperature = temperature.isel(
                Time=time_index, nVertLevels=depth_index
            ).values
            practical_salinity = salinity.isel(
                Time=time_index, nVertLevels=depth_index
            ).values
            z = z_mid[time_index, :, depth_index]
            pressure_dbar = gsw.p_from_z(z, lat)

            mask = (
                np.isfinite(potential_temperature)
                & np.isfinite(practical_salinity)
                & np.isfinite(pressure_dbar)
                & np.isfinite(lat)
                & np.isfinite(lon)
                & valid[time_index, :, depth_index]
            )

            conservative_slice = np.full(potential_temperature.shape, np.nan)
            absolute_slice = np.full(practical_salinity.shape, np.nan)
            spec_vol_slice = np.full(practical_salinity.shape, np.nan)

            conservative_slice[mask] = gsw.CT_from_pt(
                practical_salinity[mask],
                potential_temperature[mask],
            )
            absolute_slice[mask] = gsw.SA_from_SP(
                practical_salinity[mask],
                pressure_dbar[mask],
                lon[mask],
                lat[mask],
            )
            spec_vol_slice[mask] = gsw.specvol(
                absolute_slice[mask],
                conservative_slice[mask],
                pressure_dbar[mask],
            )

            conservative_temperature[time_index, :, depth_index] = (
                conservative_slice
            )
            absolute_salinity[time_index, :, depth_index] = absolute_slice
            spec_vol[time_index, :, depth_index] = spec_vol_slice

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
