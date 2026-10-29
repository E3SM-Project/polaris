(dev-e3sm-init-framework)=

# Framework

The `e3sm/init` component includes a small amount of shared framework code in
`polaris.e3sm.init.topo`. This framework defines supported source-topography
resolutions and helper functions used by `e3sm/init` tasks and by other
components that need the same resolution logic.

## Supported Resolutions

The supported cubed-sphere resolutions are collected in
`CUBED_SPHERE_RESOLUTIONS`:

- `3000`, the standard high-resolution source-topography product
- `120`, the lower-cost source-topography product for coarse workflows

The supported latitude-longitude resolutions are collected in
`LAT_LON_RESOLUTIONS`:

- `1.0`
- `0.25`
- `0.125`
- `0.0625`
- `0.03125`

## Resolution Naming

The helper `format_lat_lon_resolution_name()` converts a latitude-longitude
resolution in degrees into the directory naming convention used throughout
Polaris. It formats the resolution with
`LAT_LON_RESOLUTION_DECIMALS = 5` decimal places and appends `_degree`.

Examples:

- `1.0` becomes `1.00000_degree`
- `0.125` becomes `0.12500_degree`
- `0.03125` becomes `0.03125_degree`

## Cubed-Sphere Resolution Selection

The helper `get_cubed_sphere_resolution(low_res)` returns either
`STANDARD_CUBED_SPHERE_RESOLUTION` or
`LOW_RES_CUBED_SPHERE_RESOLUTION`.

The helper `uses_low_res_cubed_sphere(cell_width)` encapsulates the current
selection rule for MPAS base meshes. It returns `True` when `cell_width` is
at least `LOW_RES_BASE_MESH_CELL_WIDTH`, currently `120.0` km.

This separation keeps shared resolution logic in the component framework
rather than in `polaris.tasks.e3sm.init`, which allows mesh and ocean
workflows to reuse the same supported-resolution definitions.
(dev-e3sm-init-framework-staging)=

## Staging E3SM Input Files

`polaris.e3sm.init` also holds what any workflow needs to stage files in an
`inputdata`-style tree for E3SM.  The {ref}`dev-e3sm-init-component-inputs`
tasks are the first to use it.  None of these modules imports from
`polaris.tasks`.

- `inputdata` — the general names and paths.  Paths are keyed by E3SM's grid
  name for a component, such as `u02-oi30`, not by how a mesh was built.
  `get_creation_date()` and `set_creation_date()` take the config section that
  holds `creation_date`, and `get_nonempty_option()` reads an option, such as
  a name only a person can assign, that is blank until set.
- `partitions` — the core counts a graph is partitioned into
  (`get_core_list()`, ported from Compass), which of them are still to build,
  building them with `gpmetis` several at a time, and graphs of a subset of a
  mesh's cells for partitioning regions separately.
- `GraphPartitionStep` — partitions a graph into every core count.  It takes
  the config section to read its bounds and its number of partitions at once
  from, so a workflow with two meshes can give each its own.  By default it
  partitions a single linked `graph.info`; a subclass that builds its own
  graphs overrides `run()`.
- `AssembleStep` — the base for a step that builds the staged tree.  Its
  `run()` deletes `assembled_files/` and stages the workflow's README, and a
  subclass then calls `stage()` and `stage_partitions()` from its own `run()`.
  Staging waits until run time because the staged names depend on config
  options a person may change after setup.  The step also links in
  `sync_to_inputdata.sh`, which copies the tree into an inputdata directory
  and is run by hand.
