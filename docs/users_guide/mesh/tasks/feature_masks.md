(users-mesh-feature-masks)=

# Feature Masks

The `mesh/spherical/feature_masks/configurable` task creates standard MPAS mask
files on an existing MPAS mesh.  The masks are based on a named `mask_group`
supported by `geometric_features.get_aggregator_by_name()`.

Both polygon region groups and transect groups are supported.  Polaris inspects
the feature collection and calls the appropriate `mpas_tools.mesh.mask`
function:

- region groups produce variables such as `regionCellMasks`,
  `regionVertexMasks`, and `regionNames`;
- transect groups produce variables such as `transectCellMasks`,
  `transectEdgeMasks`, `transectVertexMasks`, and `transectNames`.

The mesh-component task expects a standard MPAS mesh file.  Omega-format mesh
input is handled by the ocean component's feature-mask task because Omega I/O
translation is ocean-specific; see {ref}`users-ocean-feature-masks`.
The ocean task derives from the same mesh mask-generation behavior and only
changes how native ocean mesh files are opened.

## Configuration

The configurable task uses `feature_masks.cfg` and the `[feature_masks]`
section.
The required options are:

- `mesh_filename`: path to the standard MPAS mesh file;
- `mesh_name`: name used in output filenames and metadata;
- `mask_group`: one of the supported aggregation group names.

The output filename is:

```text
<mesh_name>_<prefix><date>.nc
```

where `prefix` and `date` come from the selected mask group.  The task also
writes the GeoJSON feature collection used to create the masks.

Common optional settings include:

- `mask_types`: use `default`, or a space-separated list from `cell`, `edge`,
  and `vertex`;
- `add_edge_sign`: add `transectEdgeMaskSigns` for transect edge masks;
- `cpus_per_task` and `min_cpus_per_task`: multiprocessing resources;
- `chunk_size`, `subdivision_threshold`, and `subdivision_resolution`:
  controls passed to `mpas_tools`.

## Example

```bash
polaris setup -t mesh/spherical/feature_masks/configurable -w feature_masks
```

Edit
`feature_masks/mesh/spherical/feature_masks/configurable/feature_masks.cfg`
to point at the desired mesh and select the mask group, then run the task.
Missing required options are reported when the task runs, after the work-dir
config has been edited.
