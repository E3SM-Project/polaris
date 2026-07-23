#!/usr/bin/env python3

import argparse
import contextlib
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from importlib import resources
from typing import Iterator, Literal

import dask
import xarray as xr
from mache import MachineInfo
from mache.discover import discover_machine
from mache.parallel import get_parallel_system
from ruamel.yaml import YAML

from polaris.mesh.reconstruct import compute_reconstruction_weights

DEFAULT_CHUNK_SIZE = 1_000

# Dimensions found only on large, multi-level/time-resolved/tracer
# fields (e.g. layerThickness(nCells, nVertLevels)) that are never
# needed to compute reconstruction weights. Filtering on these (rather
# than enumerating every small mesh variable) keeps everything the
# algorithm needs while skipping a production mesh's bulk. Names use
# the MPAS-Ocean convention, since filtering always runs after
# converting to that convention.
_LARGE_STATE_DIMS = frozenset(
    {'Time', 'nVertLevels', 'nVertLevelsP1', 'nTracers'}
)


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
                'Invlaid input: dataset contains both MPASO and Omega '
                'dimensions names.'
            )

        return 'omega' if is_omega else 'mpaso'


def _select_grid_vars(ds: xr.Dataset) -> list[str]:
    """Names of the mesh/grid variables, i.e. every variable except
    those with a large state/time/tracer dimension (see
    ``_LARGE_STATE_DIMS``). ``ds`` is expected to already be in
    MPAS-Ocean naming convention.
    """
    return [
        name
        for name, da in ds.data_vars.items()
        if not (set(da.dims) & _LARGE_STATE_DIMS)
    ]


def _default_num_workers() -> int:
    """Default dask worker count from mache's parallel system info.

    Using mache rather than reading SLURM environment variables
    ourselves keeps this in sync with each machine's known core count
    and correctly falls back to a login-node core count outside of a
    job allocation.
    """
    machine = discover_machine(quiet=True)
    if machine is None:
        raise ValueError(
            'Unable to discover the current machine from its host '
            'name; mache does not support this machine. Pass '
            '--num_workers explicitly instead.'
        )
    machine_info = MachineInfo(machine=machine, quiet=True)
    system = get_parallel_system(machine_info.config)
    return system.cores


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
    parser.add_argument(
        '-w',
        '--num_workers',
        required=False,
        type=int,
        default=None,
        help='Number of local dask worker processes to use. Providing '
        'this (with or without --chunk_size) enables dask, attaching '
        'to the resources available on the local node. If omitted, but '
        '--chunk_size is provided, this is taken from mache instead '
        '(requires running on a machine mache recognizes).',
    )
    parser.add_argument(
        '-c',
        '--chunk_size',
        required=False,
        type=int,
        default=None,
        help='Number of cells per dask chunk. Providing this (with or '
        f'without --num_workers) enables dask. Defaults to '
        f'{DEFAULT_CHUNK_SIZE} if dask is enabled via --num_workers '
        'but --chunk_size is not given.',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    use_dask = args.num_workers is not None or args.chunk_size is not None

    converter = MeshConverter()

    ds = xr.open_dataset(args.input_file)
    input_format = converter.detect_format(ds)

    ds_mpas = ds if input_format == 'mpaso' else converter.omega_to_mpas(ds)

    # Only the small grid variables feed the reconstruction calculation.
    # Restricting to those *before* loading/chunking anything means a
    # production mesh's large state/tracer fields are never read.
    mesh_ds = ds_mpas[_select_grid_vars(ds_mpas)]

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

    if use_dask:
        chunk_size = args.chunk_size or DEFAULT_CHUNK_SIZE
        num_workers = args.num_workers or _default_num_workers()
        dask_config: dict[str, str | int] = {
            'scheduler': 'processes',
            'multiprocessing.context': 'spawn',
        }
        if num_workers is not None:
            dask_config['num_workers'] = num_workers

        print(
            f'dask config: scheduler={dask_config["scheduler"]!r}, '
            f'num_workers={dask_config.get("num_workers", "(dask default)")}, '
            f'multiprocessing.context='
            f'{dask_config["multiprocessing.context"]!r}, '
            f'chunk_size={chunk_size}'
        )

        dask_ctx = dask.config.set(**dask_config)

        with _timed('dask setup + load/chunk'):
            # Read meshg variable subset into memory before chunking.
            mesh_ds = mesh_ds.load()
            mesh_ds = mesh_ds.chunk({'nCells': chunk_size})
    else:
        dask_ctx = contextlib.nullcontext()

    with _timed('compute_reconstruction_weights total'):
        with dask_ctx:
            weights_ds = compute_reconstruction_weights(mesh_ds)

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
