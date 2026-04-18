(e3sm-init-topo-tasks)=

# Topography Tasks

The `e3sm/init/topo` tasks create shared topography products and derived MPAS
inputs that are reused by mesh-generation and E3SM initial-condition
workflows.

Supported cubed-sphere products are:

- `ne3000`
- `ne120`

Supported latitude-longitude products are:

- `1.00000_degree`
- `0.25000_degree`
- `0.12500_degree`
- `0.06250_degree`
- `0.03125_degree`

Latitude-longitude product names follow the naming convention used by
`format_lat_lon_resolution_name()`, which formats the resolution with
5 decimal places and appends `_degree`. For example, `0.125` becomes
`0.12500_degree` and `0.03125` becomes `0.03125_degree`.

Standalone tasks are available to create each combined topography product:

- `e3sm/init/topo/combine_bedmap3_gebco2023/cubed_sphere/ne3000/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/cubed_sphere/ne120/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/1.00000_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.25000_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.12500_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.06250_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.03125_degree/task`

The remap and cull tasks reuse these shared products when generating inputs
for MPAS base meshes.

## Configuration Options

These tasks create shared config files in their work directories:

- `combine_topo.cfg` for combine tasks
- `remap_topo.cfg` for remap tasks
- `cull_topo.cfg` for cull tasks

### Combine Tasks

Combine tasks use the `[combine_topo]` section.

The following options are set automatically from the task path and normally
should not be changed by hand:

- `target_grid`
- `resolution_latlon`
- `resolution_cubedsphere`

Common user-tunable options are:

- `method`: Remapping method used when combining datasets.
- `renorm_thresh`: Threshold below which interpolated fields are not
	renormalized.
- `ntasks` and `min_tasks`: Target and minimum MPI task counts for remapping.
- `latmin` and `latmax`: Latitude range over which Antarctic and global
	topography are blended.
- `lat_tiles` and `lon_tiles`: Tile counts used to decompose global remapping.

Visualization tasks also use `viz_combine_topo_*` sections for colormap and
normalization settings.

### Remap Tasks

Remap tasks use the `[mask_topography]` and `[remap_topography]` sections.

Common user-tunable options are:

- `ocean_includes_grounded_ice`: Whether grounded Antarctic ice is treated as
	part of the ocean mask.
- `description`: Metadata description written to the remapped product.
- `ntasks` and `min_tasks`: Target and minimum MPI task counts for remapping.
- `renorm_threshold`: Minimum land or ocean area fraction required before
	renormalizing elevation variables.
- `expand_distance` and `expand_factor`: Smoothing controls for remapped
	topography.

For lower-resolution cubed-sphere source topography, Polaris automatically
applies lower `ntasks` and `min_tasks` defaults from `remap_low_res.cfg`.

Visualization steps also use `viz_remapped_topo_*` sections for plot styling.

### Cull Tasks

Cull tasks use the `[cull_mesh]` section.

Common user-tunable options are:

- `cpus_per_task` and `min_cpus_per_task`: Thread-count settings for culling.
- `include_critical_transects`: Whether critical land and ocean transects from
	`geometric_features` are enforced during masking.
- `sea_ice_latitude_threshold`: Latitude poleward of which ocean transects are
	widened to avoid land-locked sea-ice cells.
- `land_locked_cell_iterations`: Number of passes used to detect and remove
	land-locked ocean cells.
- `land_ice_max_latitude`: Southern latitude threshold used to classify
	critical land transects as land ice.
- `land_ice_min_fraction`: Minimum land-ice fraction used in south-pole flood
	filling for the land-ice mask.