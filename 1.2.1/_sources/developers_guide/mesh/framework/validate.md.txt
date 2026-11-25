(dev-mesh-validate)=

# Baseline Validation Variables

When a step is run with a baseline, polaris compares the variables named in
`validate_vars` for each output file against the same variables in the
baseline's copy of that file (see {ref}`dev-validation`).  For MPAS mesh files
that list is long, and it has to be the same everywhere or two steps that
write the same kind of file would be validated to different standards.
`polaris.mesh.validate` keeps the shared lists in one dependency-light module
so that framework steps and component steps can both import them without
pulling in anything else.

There are two lists:

- {py:data}`polaris.mesh.validate.MPAS_MESH_VALIDATE_VARS` -- the coordinate,
  area, index and connectivity variables of an MPAS mesh file; and
- {py:data}`polaris.mesh.validate.CELL_WIDTH_VALIDATE_VARS` -- just
  `cellWidth`, for the lon/lat cell-width file that drives JIGSAW.

Use them when adding the output file:

```python
from polaris.mesh.validate import MPAS_MESH_VALIDATE_VARS


self.add_output_file(
    filename='culled_mesh.nc',
    validate_vars=MPAS_MESH_VALIDATE_VARS,
)
```

`MPAS_MESH_VALIDATE_VARS` deliberately contains only variables that a base
mesh and a culled mesh both have, so the same list works for either without a
step having to trim it.  A step that writes extra fields should validate them
by extending the list locally rather than adding them here, unless every MPAS
mesh file in polaris will have them.  {ref}`dev-mesh-reconstruct` is the
pattern to follow: the reconstruction weights get their own list from
{py:func}`polaris.mesh.reconstruct.get_reconstruction_validate_vars()`,
because only some meshes carry them.
