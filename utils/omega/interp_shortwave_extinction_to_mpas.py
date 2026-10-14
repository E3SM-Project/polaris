#!/usr/bin/env python3

import argparse
from pathlib import Path

import xarray as xr
from convert_mpaso_ic_to_omega import (
    SHORTWAVE_EXTINCTION_VARIABLES,
    _get_shortwave_extinction_files,
    _remap_shortwave_to_mpas,
)
from mpas_tools.io import write_netcdf


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'Interpolate shortwave extinction coefficients from a '
            'uniform lat/lon grid onto an MPAS mesh.'
        )
    )
    parser.add_argument(
        '--mesh',
        required=True,
        help='MPAS mesh file to interpolate onto.',
    )
    parser.add_argument(
        '--output-file',
        required=True,
        help='Output file with latCell, lonCell, and extinction fields.',
    )
    parser.add_argument(
        '--input-file',
        default=None,
        help=(
            'Optional source shortwave extinction file. If not supplied, '
            'the file is downloaded from the Polaris data repository.'
        ),
    )
    parser.add_argument(
        '--src-scrip-file',
        default=None,
        help=(
            'Optional source SCRIP file for shortwave extinction data. '
            'If not supplied, the file is downloaded from the Polaris '
            'data repository.'
        ),
    )
    parser.add_argument(
        '--scrip-file',
        default=None,
        help=(
            'Optional pre-computed MPAS destination SCRIP file. If not '
            'supplied, one is generated from --mesh with scrip_from_mpas.'
        ),
    )
    parser.add_argument(
        '--remap-method',
        choices=['conserve', 'bilinear'],
        default='bilinear',
        help='Horizontal remapping method.',
    )
    parser.add_argument(
        '--work-dir',
        default=None,
        help=(
            'Directory for intermediate SCRIP and remapped files '
            "(default: the output file's directory)."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output_file)
    work_dir = Path(args.work_dir) if args.work_dir else output_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    input_file = args.input_file
    src_scrip_file = args.src_scrip_file
    if input_file is None or src_scrip_file is None:
        dl_sw, dl_scrip = _get_shortwave_extinction_files()
        input_file = input_file or dl_sw
        src_scrip_file = src_scrip_file or dl_scrip

    ds_remap = _remap_shortwave_to_mpas(
        mpas_file=args.mesh,
        shortwave_file=input_file,
        shortwave_scrip_file=src_scrip_file,
        remap_method=args.remap_method,
        mpas_scrip_file=args.scrip_file,
        work_dir=work_dir,
    )

    with xr.open_dataset(args.mesh) as ds_mesh:
        ds_out = ds_mesh[['latCell', 'lonCell']].load()

    cell_dim = ds_out['latCell'].dims[0]
    for var in SHORTWAVE_EXTINCTION_VARIABLES:
        field = ds_remap[var].squeeze(drop=True)
        src_dim = field.dims[0]
        if src_dim != cell_dim:
            field = field.rename({src_dim: cell_dim})
        ds_out[var] = field

    write_netcdf(
        ds_out,
        args.output_file,
        format='NETCDF3_64BIT_DATA',
        engine='netcdf4',
    )
    print(f'Wrote {args.output_file}')


if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
