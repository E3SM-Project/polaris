(dev-ocean-convert-ic-to-pcd-radius)=

# convert_ic_to_pcd_radius

`utils/mpas/convert_ic_to_pcd_radius.py` converts an existing MPAS-Ocean or
MPAS-Seaice initial condition on a spherical mesh to the Physical Constants
Dictionary (PCD) mean Earth radius, so that the mesh matches the radius the
models use. It:

1. rescales the horizontal coordinates, lengths and areas, and the
   `sphere_radius` attribute, from the file's `sphere_radius` to the PCD
   `mean_radius` with {py:func}`polaris.mesh.radius.rescale_sphere_radius`;
2. removes `fCell`, `fEdge` and `fVertex`, which the models compute at init
   on spherical meshes;
3. leaves every other field and global attribute unchanged, and records the
   old radius and the PCD version in the `history` attribute;
4. writes the result in the input's netCDF format.

Unless `--output` names a file, the output goes in the given directory (by
default the current one) and is named after the input with its 6- or
8-digit date stamp replaced by an 8-digit `YYYYMMDD` one (today's unless
`--date` is given). A `cice.` prefix becomes `mpassi.`.

```bash
./utils/mpas/convert_ic_to_pcd_radius.py \
    -i /path/to/inputdata/ocn/mpas-o/oQU240wLI/ocean.QU.240wLI.230220.nc \
    -o /path/to/output/
```

writes `/path/to/output/ocean.QU.240wLI.<YYYYMMDD>.nc`.

To use a converted file in E3SM, update the date in the component's
`buildnml` (`ic_date` for MPAS-Ocean, `grid_date` for MPAS-Seaice) and, for
renamed sea-ice files, `grid_prefix`.
