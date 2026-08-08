#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from importlib import resources
from typing import Iterator, Literal

import xarray as xr
from ruamel.yaml import YAML

from polaris.mesh.reconstruct import compute_reconstruction_weights


class MeshConverter:
    def __init__(self):
        self.dim_map, self.var_map = self._load_mpaso_to_omega_map()

    def _load_mpaso_to_omega_map(self):
        text = (
            resources.files('polaris.ocean.model')
            .joinpath('mpaso_to_omega.yaml')
            .read_text()
        )
        nested = YAML(typ='rt').load(text)

        return nested['dimensions'], nested['variables']

    def omega_to_mpas(self, ds: xr.Dataset) -> xr.Dataset:
        # omega -> mpas
        rename = {v: k for k, v in self.dim_map.items() if v in ds.dims}
        rename.update({v: k for k, v in self.var_map.items() if v in ds})

        return ds.rename(rename)

    def mpas_to_omega(self, ds: xr.Dataset) -> xr.Dataset:
        # mpas -> omega
        rename = {k: v for k, v in self.dim_map.items() if k in ds.dims}
        rename.update({k: v for k, v in self.var_map.items() if k in ds})

        return ds.rename(rename)

    def detect_format(self, ds: xr.Dataset) -> Literal['mpaso', 'omega']:

        dims = ds.dims
        items = self.dim_map.items()

        is_omega = all(v in dims for k, v in items if k in dims or v in dims)
        is_mpas = all(k in dims for k, v in items if k in dims or v in dims)

        if is_omega and is_mpas:
            raise ValueError(
                'Invalid input: dataset contains both MPASO and Omega '
                'dimensions names.'
            )

        return 'omega' if is_omega else 'mpaso'


@contextmanager
def _timed(step: str) -> Iterator[None]:
    """Print how long the wrapped block of code took to run, labeled
    with ``step``.
    """
    t0 = time.perf_counter()
    yield
    print(f'{step}: {time.perf_counter() - t0:.2f}s')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Add edge vector reconstruction weights to a dataset.'
    )
    parser.add_argument(
        '-i',
        '--input_file',
        required=True,
        type=str,
        help='Path to the input dataset file.',
    )
    parser.add_argument(
        '-o',
        '--output_file',
        required=True,
        type=str,
        help='Path to the output dataset file.',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    converter = MeshConverter()

    ds = xr.open_dataset(args.input_file)
    input_format = converter.detect_format(ds)

    ds_mpas = ds if input_format == 'mpaso' else converter.omega_to_mpas(ds)

    # Done reading -- close the input file before copying it below.
    ds.close()

    # The output should contain the full input mesh plus the new
    # weight fields, not just the weights. For a production mesh (40+
    # GB) re-writing everything through xarray/netCDF would be far
    # slower than necessary, so instead we copy the input file
    # byte-for-byte and merge in the (small) computed weight fields
    # via NCO below, once they're ready.
    with _timed('copy input -> output'):
        shutil.copyfile(args.input_file, args.output_file)

    # don't need _timed context manager b/c func prints its own timing info
    weights_ds = compute_reconstruction_weights(ds_mpas)

    # Match the naming convention of the input file.
    if input_format == 'omega':
        weights_ds = converter.mpas_to_omega(weights_ds)

    # Write weight to tmp file, then use `ncks` to merge into input mesh
    with tempfile.NamedTemporaryFile(
        suffix='.nc', prefix='weights_', dir=os.getcwd()
    ) as tmp:
        with _timed('write weights (temporary file)'):
            weights_ds.to_netcdf(tmp.name, mode='w')

        with _timed('merge weights into output (ncks -A)'):
            subprocess.run(
                ['ncks', '-A', tmp.name, args.output_file], check=True
            )


if __name__ == '__main__':
    main()
