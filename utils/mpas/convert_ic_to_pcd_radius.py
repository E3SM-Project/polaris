#!/usr/bin/env python3
"""
Convert an MPAS-Ocean or MPAS-Seaice initial condition to the PCD's mean
Earth radius, drop the Coriolis parameter (which the models compute at
init) and write it with a new date stamp.
"""

import argparse
import os
import re
from datetime import datetime

import netCDF4
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.constants import get_constant
from polaris.constants.pcd import get_pcd_version
from polaris.mesh.radius import rescale_sphere_radius

CORIOLIS_VARIABLES = ['fCell', 'fEdge', 'fVertex']

# old file-name prefixes and their replacements in new initial conditions
PREFIX_RENAMES = {'cice': 'mpassi'}

# netCDF4 data models and the formats mpas_tools.io.write_netcdf() takes
FORMATS = {
    'NETCDF3_CLASSIC': 'NETCDF3_CLASSIC',
    'NETCDF3_64BIT_OFFSET': 'NETCDF3_64BIT',
    'NETCDF3_64BIT_DATA': 'NETCDF3_64BIT_DATA',
    'NETCDF4_CLASSIC': 'NETCDF4_CLASSIC',
    'NETCDF4': 'NETCDF4',
}

DATE_STAMP = re.compile(r'^(\d{6}|\d{8})$')


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Rescale an MPAS-Ocean or MPAS-Seaice initial condition to the '
            "PCD's mean Earth radius, drop fCell, fEdge and fVertex, and "
            'write it with a new YYYYMMDD date stamp.'
        )
    )
    parser.add_argument(
        '-i',
        '--input-file',
        required=True,
        help=(
            'The initial condition to convert, named like '
            '<prefix>.<YYMMDD or YYYYMMDD>.nc.'
        ),
    )
    parser.add_argument(
        '-o',
        '--output',
        default='.',
        help=(
            'The output file, or a directory in which to write a file named '
            'after the input with the new date stamp (and cice. renamed to '
            'mpassi.).  The default is the current directory.'
        ),
    )
    parser.add_argument(
        '--date',
        default=datetime.now().strftime('%Y%m%d'),
        help='The new date stamp as YYYYMMDD.  The default is today.',
    )
    args = parser.parse_args()

    if not re.fullmatch(r'\d{8}', args.date):
        parser.error(f'--date must be YYYYMMDD, not {args.date!r}')

    output_file = args.output
    if os.path.isdir(output_file):
        try:
            name = get_output_name(args.input_file, args.date)
        except ValueError as error:
            parser.error(str(error))
        output_file = os.path.join(output_file, name)

    convert_ic(args.input_file, output_file)


def get_output_name(input_file, date):
    """
    Get the name of the converted file: the input's name with its date stamp
    replaced by ``date`` and any old prefix renamed

    Parameters
    ----------
    input_file : str
        The initial condition being converted

    date : str
        The new date stamp as YYYYMMDD

    Returns
    -------
    name : str
        The file name (without a directory) for the converted file
    """
    name = os.path.basename(input_file)
    stem, ext = os.path.splitext(name)
    parts = stem.split('.')
    for index in range(len(parts) - 1, 0, -1):
        if DATE_STAMP.match(parts[index]):
            parts[index] = date
            break
    else:
        raise ValueError(
            f'No YYMMDD or YYYYMMDD date stamp found in {name}; give the '
            f'output file name with --output.'
        )
    parts[0] = PREFIX_RENAMES.get(parts[0], parts[0])
    return '.'.join(parts) + ext


def convert_ic(input_file, output_file):
    """
    Rescale an initial condition to the PCD's mean Earth radius, drop the
    Coriolis parameter and write the result in the input's netCDF format

    Parameters
    ----------
    input_file : str
        The initial condition to convert

    output_file : str
        The converted initial condition to write
    """
    if os.path.abspath(output_file) == os.path.abspath(input_file):
        raise ValueError(f'The output would overwrite {input_file}.')
    if os.path.exists(output_file):
        raise ValueError(f'{output_file} already exists.')

    with netCDF4.Dataset(input_file) as nc:
        file_format = FORMATS[nc.data_model]

    with xr.open_dataset(
        input_file, decode_times=False, decode_timedelta=False
    ) as ds_in:
        ds = ds_in.load()

    old_radius = float(ds.attrs.get('sphere_radius', 0.0))
    new_radius = float(get_constant('mean_radius'))
    rescaled = rescale_sphere_radius(ds, new_radius)

    dropped = [name for name in CORIOLIS_VARIABLES if name in ds]
    ds = ds.drop_vars(dropped)

    pcd_version = get_pcd_version()
    note = (
        f'{datetime.now().strftime("%a %b %d %H:%M:%S %Y")}: rescaled '
        f'sphere_radius from {old_radius!r} to the PCD {pcd_version} '
        f'mean_radius {new_radius!r}'
    )
    if dropped:
        note = f'{note}; removed {", ".join(dropped)}'
    if 'history' in ds.attrs:
        note = f'{note}\n{ds.attrs["history"]}'
    ds.attrs['history'] = note

    write_netcdf(ds, output_file, format=file_format, engine='netcdf4')

    print(f'Wrote {output_file} ({file_format})')
    print(
        f'Rescaled sphere_radius {old_radius!r} -> {new_radius!r} '
        f'(PCD {pcd_version}), a factor of {new_radius / old_radius!r}'
    )
    print(f'Rescaled: {", ".join(rescaled)}')
    if dropped:
        print(f'Removed: {", ".join(dropped)}')
    else:
        print('No Coriolis variables to remove')


if __name__ == '__main__':
    main()
