#!/usr/bin/env python3
"""
Convert an MPAS-Ocean or MPAS-Seaice initial condition to the PCD's mean
Earth radius, drop the Coriolis parameter (which the models compute at
init) and write it with a new date stamp.
"""

import argparse
import os
import re
import subprocess
from datetime import datetime

import netCDF4
import numpy as np
import xarray as xr
from mpas_tools.io import update_history

from polaris.constants import get_constant
from polaris.constants.pcd import get_pcd_version
from polaris.mesh.radius import rescale_sphere_radius

CORIOLIS_VARIABLES = ['fCell', 'fEdge', 'fVertex']

# old file-name prefixes and their replacements in new initial conditions
PREFIX_RENAMES = {'cice': 'mpassi'}

# ncks flags that convert a NETCDF4 file to each netCDF4 data model
NCKS_FORMAT_FLAGS = {
    'NETCDF3_CLASSIC': '-3',
    'NETCDF3_64BIT_OFFSET': '-6',
    'NETCDF3_64BIT_DATA': '-5',
    'NETCDF4_CLASSIC': '-7',
}

DATE_STAMP = re.compile(r'^(\d{6}|\d{8})$')

# the relative tolerance for the mesh's coordinates to lie on one sphere and
# for sphere_radius to match it
RADIUS_RTOL = 1e-10


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
        file_format = nc.data_model

    # keep variables and their attributes as they are in the file: no
    # masking (which would rewrite missing_value with the type of
    # _FillValue), no time decoding, and no coordinates (which xarray would
    # add as a coordinates attribute to every variable that shares their
    # dimensions)
    with xr.open_dataset(
        input_file,
        mask_and_scale=False,
        decode_times=False,
        decode_timedelta=False,
        decode_coords=False,
    ) as ds_in:
        ds = ds_in.load()
    unlimited_dims = ds.encoding.get('unlimited_dims', set())

    # some files have a sphere_radius that differs from the radius of their
    # coordinates, so rescale from the radius of the coordinates
    attr_radius = float(ds.attrs.get('sphere_radius', 0.0))
    old_radius = get_coordinate_radius(ds)
    corrected = abs(old_radius - attr_radius) > RADIUS_RTOL * old_radius
    if corrected:
        ds.attrs['sphere_radius'] = old_radius
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
    if corrected:
        note = (
            f'{note} (the radius of the coordinates; sphere_radius was '
            f'{attr_radius!r})'
        )
    if dropped:
        note = f'{note}; removed {", ".join(dropped)}'
    if 'history' in ds.attrs:
        note = f'{note}\n{ds.attrs["history"]}'
    ds.attrs['history'] = note

    update_history(ds)
    _write_like_input(ds, output_file, file_format, unlimited_dims)

    print(f'Wrote {output_file} ({file_format})')
    if corrected:
        print(
            f'sphere_radius was {attr_radius!r}, but the coordinates are at '
            f'{old_radius!r}; rescaled from the coordinates'
        )
    print(
        f'Rescaled sphere_radius {old_radius!r} -> {new_radius!r} '
        f'(PCD {pcd_version}), a factor of {new_radius / old_radius!r}'
    )
    print(f'Rescaled: {", ".join(rescaled)}')
    if dropped:
        print(f'Removed: {", ".join(dropped)}')
    else:
        print('No Coriolis variables to remove')


def get_coordinate_radius(ds):
    """
    Get the radius of the sphere that a mesh's cell, edge and vertex
    coordinates lie on

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset on a spherical MPAS mesh

    Returns
    -------
    radius : float
        The mean distance of the cell centers from the origin

    Raises
    ------
    ValueError
        If the coordinates do not all lie on one sphere
    """
    distances = []
    for loc in ['Cell', 'Edge', 'Vertex']:
        x, y, z = (ds[f'{coord}{loc}'].values for coord in 'xyz')
        distances.append(np.sqrt(x**2 + y**2 + z**2))
    radius = float(np.mean(distances[0]))
    spread = max(float(np.max(np.abs(dist - radius))) for dist in distances)
    if spread > RADIUS_RTOL * radius:
        raise ValueError(
            f'The mesh coordinates are not on one sphere: they differ from '
            f'a radius of {radius!r} by up to {spread!r}.'
        )
    return radius


def _write_like_input(ds, output_file, file_format, unlimited_dims):
    """
    Write a dataset with each variable's attributes and type from the input
    file, in the input's format.  xarray is slow to write
    NETCDF3_64BIT_DATA, the usual format of E3SM initial conditions, so any
    format other than NETCDF4 is written as NETCDF4 and converted with ncks.
    """
    for var in ds.variables.values():
        # the input's fill values are attributes; add none where it had none
        if '_FillValue' not in var.attrs:
            var.encoding['_FillValue'] = None

    # xarray drops dimensions no variable uses, and some files have an
    # unlimited Time dimension with no variables on it
    unused_dims = [dim for dim in unlimited_dims if dim not in ds.dims]
    kwargs = dict(
        format='NETCDF4',
        engine='netcdf4',
        unlimited_dims=[dim for dim in unlimited_dims if dim in ds.dims],
    )
    if file_format == 'NETCDF4':
        ds.to_netcdf(output_file, **kwargs)
        _add_unlimited_dims(output_file, unused_dims)
        return

    directory, name = os.path.split(os.path.abspath(output_file))
    tmp_file = os.path.join(directory, f'_tmp_{name}')
    try:
        ds.to_netcdf(tmp_file, **kwargs)
        _add_unlimited_dims(tmp_file, unused_dims)
        subprocess.run(
            [
                'ncks',
                '-O',
                '-h',
                NCKS_FORMAT_FLAGS[file_format],
                tmp_file,
                output_file,
            ],
            check=True,
        )
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def _add_unlimited_dims(filename, dims):
    """
    Add unlimited dimensions that no variable uses to a NETCDF4 file
    """
    if not dims:
        return
    with netCDF4.Dataset(filename, 'a') as nc:
        for dim in dims:
            nc.createDimension(dim, None)


if __name__ == '__main__':
    main()
