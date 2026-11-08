(dev-ocean-add-reconstruction-weights)=

# add_reconstruction_weights

`utils/omega/add_reconstruction_weights.py` is a standalone script that
computes edge vector reconstruction weights and appends them to an existing
MPAS-Ocean or Omega mesh file.

The weights are computed using the least-squares method described in
[Peixoto and Barros (2014)](https://doi.org/10.1016/j.jcp.2014.04.043)
using a two-ring edge stencil (see Figure 5 of that paper).

The script auto-detects whether the input file uses MPAS-Ocean or Omega
naming conventions and writes output in the same convention.
`compute_reconstruction_weights()` internally selects only the small
mesh/grid variables needed for the calculation, so large state/tracer
fields are never loaded, making it safe to run on production meshes.

## Usage

```bash
./utils/omega/add_reconstruction_weights.py \
    -i <input_mesh.nc> \
    -o <output_mesh.nc>
```

| Flag | Description |
|------|-------------|
| `-i` / `--input_file`  | Input mesh file (MPAS-Ocean or Omega format) |
| `-o` / `--output_file` | Output file (copy of input with weights appended) |

For production-sized meshes (e.g. `6to18km`) the script should be run on a
compute node. Since the mesh connectivity information needed to compute the
weights fits into memory, the reconstruction weights are computed serially
using numpy/xarray, as recommended by
[Dask best practices](https://docs.dask.org/en/stable/array-best-practices.html#use-numpy).
