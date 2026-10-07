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
section.  You must set `mesh_filename` and `mesh_name`.  `mask_group` defaults
to `Ocean Basins` and can be any of the aggregation group names listed in the
[geometric_features documentation](https://mpas-dev.github.io/geometric_features/main/aggregation.html),
such as `MOC Basins`.

Each task produces masks for a single `mask_group`.  To create masks for
several groups, set up the task in a separate work directory for each group.

The output filename is:

```text
<mesh_name>_<prefix><date>.nc
```

where `prefix` and `date` come from the selected mask group.  The task also
writes the GeoJSON feature collection used to create the masks.

The remaining options are not tuned for any particular mesh.  For a large
mesh, the main thing to change is `cpus_per_task`, if more cores are
available.

## config options

```cfg
# options for creating region or transect masks on an MPAS mesh
[feature_masks]

# Path to an existing standard MPAS mesh file for configurable use
mesh_filename = <<<missing>>>

# Mesh name used in output filenames and metadata
mesh_name = <<<missing>>>

# Any group name supported by geometric_features.get_aggregator_by_name()
mask_group = Ocean Basins

# Mask types. Use "default" for:
#   regions: cell vertex
#   transects: cell edge vertex
mask_types = default

# Whether transect output should include transectEdgeMaskSigns
add_edge_sign = False

# Number of MPAS locations processed per chunk
chunk_size = 1000

# Region polygon subdivision threshold in degrees
subdivision_threshold = 30.0

# Transect subdivision resolution in meters. None means no subdivision.
subdivision_resolution = None

# Whether mpas_tools should display progress bars
show_progress = False

# Python multiprocessing start method: fork, spawn, or forkserver
multiprocessing_method = forkserver

# number of cores to use if available
cpus_per_task = 128

# minimum number of cores, below which the step fails
min_cpus_per_task = 1
```

## Example

```bash
polaris setup -t mesh/spherical/feature_masks/configurable -w feature_masks
```

Edit
`feature_masks/mesh/spherical/feature_masks/configurable/feature_masks.cfg`
to point at the desired mesh and select the mask group, then run the task.
Missing required options are reported when the task runs, after the work-dir
config has been edited.
