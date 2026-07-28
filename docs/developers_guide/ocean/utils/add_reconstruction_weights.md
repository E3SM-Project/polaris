(dev-ocean-add-reconstruction-weights)=

# add_reconstruction_weights

`utils/omega/add_reconstruction_weights.py` is a standalone script that
computes edge vector reconstruction weights and appends them to an existing
MPAS-Ocean or Omega mesh file.

The weights are computed using the least-squares method described in
[Peixoto and Barros (2014)](https://doi.org/10.1016/j.jcp.2014.04.043)
using a two-ring edge stencil (see Figure 5 of that paper).

The script auto-detects whether the input file uses MPAS-Ocean or Omega
naming conventions and writes output in the same convention.  Only the
small mesh/grid variables are loaded; large state/tracer fields are
skipped, making it safe to run on production meshes.

## Usage

```bash
./utils/omega/add_reconstruction_weights.py \
    -i <input_mesh.nc> \
    -o <output_mesh.nc> \
    [-w <num_workers>] \
    [-c <chunk_size>]
```

| Flag | Description |
|------|-------------|
| `-i` / `--input_file`  | Input mesh file (MPAS-Ocean or Omega format) |
| `-o` / `--output_file` | Output file (copy of input with weights appended) |
| `-w` / `--num_workers` | Number of dask worker processes (enables parallel mode) |
| `-c` / `--chunk_size`  | Cells per dask chunk (default: 1000) |

Passing either `-w` or `-c` enables dask parallelism. If `-c` is given
without `-w`, the worker count is inferred from mache (requires running
on a recognised machine).

## Parallel performance

The script uses a local multiprocessing dask scheduler and can exploit
all cores on a single node. Based on timing tests on Chrysalis with the
EC30to60 mesh (~1.8 M cells, 32 workers):

| `num_workers` | `chunk_size` | wall time |
|:---:|---:|---:|
| 32 | 7000 | ~5m 57s |
| 32 | 3700 | ~4m 42s |
| 32 | 1850 | ~4m 16s |

**Fewer workers with more, smaller chunks per worker tends to be faster
than filling each worker with one large chunk.**  Start with a chunk size
that gives several chunks per worker and tune from there.
