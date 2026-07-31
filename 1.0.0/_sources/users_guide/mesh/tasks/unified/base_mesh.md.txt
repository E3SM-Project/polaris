(users-mesh-unified-base-mesh)=

# Unified base-mesh tasks

The `mesh/spherical/unified/<mesh_name>/base_mesh` tasks generate the final
MPAS base mesh for each named unified mesh. The mesh is created by JIGSAW
using the sizing field (see {ref}`users-mesh-unified-sizing-field`) as a
cell-width target and the clipped river network (see
{ref}`users-mesh-unified-river`) as geometric constraints, so that mesh edges
align with retained river centerlines.

The resulting base mesh covers the full sphere at variable resolution
controlled by the mesh configuration.

## Available tasks

Polaris registers one base-mesh task for each named unified mesh:

- `mesh/spherical/unified/<mesh_name>/base_mesh/task`

Supported `mesh_name` values are:

- `u.oi240.lr240`
- `u.oi30.lr10`
- `u.oi6to18.lr6to10`
- `u.oi.so12to30.lr10`

The task work directory contains symlinks to all upstream coastline, river,
and sizing-field shared steps, plus:

- `base_mesh`, the step that runs JIGSAW and produces the MPAS mesh file
  `base_mesh.nc`; and
- `base_mesh_viz`, a diagnostic step that writes cell-width and resolution
  overview plots.

## Outputs

The `base_mesh` step produces:

- `base_mesh.nc`: the global MPAS base mesh;
- `graph.info`: the mesh graph file needed for mesh decomposition; and
- `cell_width.nc`: the lat-lon cell-width map passed to JIGSAW for
  diagnostic purposes.

The `base_mesh_viz` step produces:

- a global resolution map on the MPAS mesh;
- a `dcEdge` map on the MPAS mesh;
- a sizing-field map on the lat-lon source grid; and
- a river-alignment figure showing the retained river geometry overlaid on
  the mesh resolution.

A plain-text `debug_summary.txt` records key scalar diagnostics such as cell
count and min/max resolution.

## Configuration

Base-mesh configuration spans two config sections.

The `[spherical_mesh]` section (shared with the JIGSAW-based spherical mesh
infrastructure) controls JIGSAW tuning. Key options:

- `min_cell_width` and `max_cell_width`: representative cell-width bounds
  derived automatically from the sizing-field settings. These are informational
  and do not override the full variable-resolution sizing field.
- Other JIGSAW tuning options inherited from
  `polaris.mesh.spherical.QuasiUniformSphericalMeshStep`.

The `[river_network]` section controls how the clipped river network is
pre-processed before being passed to JIGSAW as geometric constraints. The key
option is:

- `base_mesh_simplify_tolerance_km`: used both to simplify individual river
  polylines (see {ref}`users-mesh-unified-river`) and as the snap tolerance
  for merging nearby constraint vertices from different river features.
  Vertices closer than this distance are merged into a single cluster at their
  centroid, preventing JIGSAW from creating thin-sliver triangles that would
  produce degenerate MPAS cell polygons.  The default is 2 km; mesh-specific
  configs may override it (e.g. 3 km for `u.oi6to18.lr6to10`).

Refinement options are controlled through the `[sizing_field]` section (see
{ref}`users-mesh-unified-sizing-field`).

## Running a task

```bash
polaris setup -t \
    mesh/spherical/unified/u.oi30.lr10/base_mesh/task \
    -w base_mesh_30km
```

This will also run all upstream shared steps (topography combine, coastline,
river, and sizing field) unless they are already cached or have been run
previously in a shared work directory.
