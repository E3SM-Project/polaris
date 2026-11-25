(users-mesh-unified-coastline)=

# Coastline tasks

The `mesh/spherical/unified/coastline` tasks build coastline masks and
signed-distance fields from the shared combined-topography products on
latitude-longitude grids. These tasks are intended for inspecting and caching
coastline products that later unified-mesh workflows (such as
{ref}`users-mesh-unified-river`) can reuse.

Current coastline products are derived only from the combined topography
fields produced by the `e3sm/init/topo/combine` workflow (see
{ref}`e3sm-init-topo-tasks`).

## Available tasks

Polaris provides one standalone coastline task for each supported
latitude-longitude target grid:

- `mesh/spherical/unified/coastline/0.03125_degree/task`
- `mesh/spherical/unified/coastline/0.06250_degree/task`
- `mesh/spherical/unified/coastline/0.12500_degree/task`
- `mesh/spherical/unified/coastline/0.25000_degree/task`

Current testing suggests `0.25000_degree` is still useful for lower-cost
inspection but is too coarse for scientifically valid coastline products.
Prefer `0.12500_degree`, `0.06250_degree`, or `0.03125_degree` when coastline
fidelity matters.

The tasks use a two-tier design described in the next section.

## Two-tier design: prepare and remap

The coastline is computed once at the finest supported resolution
(0.03125°) and then remapped to coarser resolutions. This ensures that the
highest-fidelity information—including narrow channels, fjords, and
connectivity decisions made by the flood fill—is preserved at all resolution
tiers.

Every task (at any resolution) includes a shared `coastline_final` step
that contains the highest-fidelity coastline available at the task's
resolution. Coarser-resolution tasks additionally include a `coastline_compute`
step for the underlying 0.03125° computation.

**Finest resolution (0.03125°):**

- `combine_topo_lat_lon_0.03125_degree` — the shared topography-combine step
  at 0.03125°;
- `coastline_final` — the shared compute step that builds convention-specific
  ocean masks and signed-distance fields at 0.03125°; and
- `viz_coastline` — writes diagnostic PNG images and a text summary.

**Coarser resolutions (0.06250°, 0.12500°, 0.25000°):**

- `combine_topo_lat_lon_0.03125_degree` — the same shared topography-combine
  step at 0.03125° (the finest combine step is always used by the compute step);
- `coastline_compute` — the same shared 0.03125° compute step;
- `coastline_final` — a remap step that maps the 0.03125° output to the target
  coarser grid; and
- `viz_coastline` — writes diagnostic PNG images and a text summary of the
  remapped coastline.

## Coastline conventions

Each run writes three convention-specific NetCDF files:

- `coastline_calving_front.nc`
- `coastline_grounding_line.nc`
- `coastline_bedrock_zero.nc`

These correspond to three ways of handling Antarctic floating and grounded
ice when defining the ocean mask:

- `calving_front`: cells below sea level are ocean only where `ice_mask`
  indicates they are ice free;
- `grounding_line`: cells below sea level are ocean where `grounded_mask`
  indicates they are not grounded ice; and
- `bedrock_zero`: all cells below sea level are candidate ocean.

## How the coastline is derived at 0.03125°

For each convention, Polaris builds the coastline fields in four stages at the
finest resolution:

1. It classifies each raster cell as candidate ocean or not candidate ocean
   using `base_elevation`, `ice_mask`, and `grounded_mask`.
2. It keeps only the connected ocean by labeling four-neighbor connected
   components on the latitude-longitude grid, merging components that meet
   across the antimeridian, and retaining only components that touch the
   northernmost latitude row.
3. It marks coastline transitions on east and north cell edges wherever the
   final ocean mask changes from ocean to land.
4. It computes signed distance to the nearest raster coastline sample from
   those edge transitions.

The flood-fill step removes disconnected inland basins. A cell can be
below sea level and still be classified as land if it belongs to a component
that never connects to the northern boundary of the grid through candidate
ocean cells.

The raster flood fill uses four-neighbor connectivity rather than diagonal
connectivity. North-south and east-west neighbors count as connected, but
cells that touch only at a corner do not. Longitudinal periodicity is handled
explicitly, so ocean that crosses the antimeridian remains connected.

The signed-distance calculation is also raster-based. Polaris places sample
points at the midpoints of coastline edges, converts both those samples and
all grid-cell centers from longitude/latitude to Cartesian coordinates on the
sphere, and builds a `scipy.spatial.cKDTree` from the coastline samples. The
nearest-neighbor search is performed in latitude chunks controlled by
`distance_chunk_size`, then the Cartesian chord distance is converted to a
spherical arc distance in meters. The result is positive in ocean cells and
negative in land cells.

Because the distance is measured to raster coastline samples rather than to an
exact vector shoreline, the answer is tied to the chosen latitude-longitude
resolution. Finer grids produce a more detailed coastline and a more accurate
approximation to the continuous shoreline.

## How the coastline is remapped to coarser resolutions

For each convention, the `coastline_final` (remap) step reads the 0.03125°
`ocean_mask` and `signed_distance` fields and produces the corresponding
fields at the coarser grid in two steps:

1. **Ocean mask.** The 0.03125° `ocean_mask` (treated as a float) is
   block-averaged onto the coarser grid by averaging each N×N block of fine
   cells (N = 2, 4, or 8 for 0.0625°, 0.125°, and 0.25°, respectively),
   yielding an ocean fraction in [0, 1]. That fraction is then thresholded
   at `mask_threshold` (default 0.5) to give the coarser binary `ocean_mask`.
   Because the 0.03125° mask already reflects the flood fill and critical
   transects, the coarser mask inherits that connectivity without repeating
   those steps.

2. **Signed distance.** The absolute value of the 0.03125° `signed_distance`
   is bilinearly remapped to the coarser grid. The sign is then restored from
   the remapped `ocean_mask`: positive in ocean cells, negative in land cells.
   This preserves the fidelity of the 0.03125° coastline geometry for distance
   magnitudes while keeping the sign self-consistent with the coarser mask.

The all-ocean-is-connected guarantee from the 0.03125° flood fill is inherited
by the coarser grids. A narrow channel that is ocean at 0.03125° may fall
below `mask_threshold` after block averaging if fewer than half of the
contributing fine cells are ocean; this is expected behavior at resolutions
that cannot represent the channel.

## Output fields

For each convention, the coastline file contains:

- `ocean_mask`
- `signed_distance`

These fields have the following interpretation:

- `ocean_mask`: candidate ocean cells that remain after the flood fill (at
  0.03125°) or after remapping and thresholding (at coarser resolutions);
- `signed_distance`: signed nearest-coastline distance in meters, negative
  over land and positive over ocean.

The 0.03125° output files also record provenance attributes such as
`coastline_edge_definition` and `flood_fill_seed_strategy`. The coarser
output files record `source_resolution_degrees` and `source_coastline_step`
so the remapping origin is traceable.

## Configuration

All coastline tasks share a single config file named `coastline.cfg`. The main
options are:

- `[coastline].include_critical_transects`: whether to apply the
  shared `geometric_features` critical land blockages and critical passages
  before flood filling at 0.03125°. Coarser resolutions inherit these
  decisions via remapping. The default is `True`.
- `[coastline].mask_threshold`: threshold for two purposes:
  converting remapped `ice_mask` and `grounded_mask` fields to binary masks
  (at 0.03125°), and converting remapped ocean fraction to a binary
  `ocean_mask` (at coarser resolutions). The default is `0.5`.
- `[coastline].sea_level_elevation`: elevation threshold for
  identifying below-sea-level cells. The default is `0.0` m.
- `[coastline].distance_chunk_size`: number of latitude rows
  processed at a time when computing signed distance at 0.03125°. This
  changes memory use and query batching, not the definition of the distance.
  The default is `64`.
- `[viz_coastline].antarctic_max_latitude`: northern extent of
  Antarctic stereographic plots. The default is `-45.0` degrees.
- `[viz_coastline].dpi`: output resolution for diagnostic plots. The
  default is `200`.
- `[viz_coastline].signed_distance_limit`: symmetric colorbar limit
  for signed-distance plots. The default is `500000.0` m.

## Diagnostics

The visualization step writes global and Antarctic binary plots of the final
`ocean_mask` for each convention, along with matching signed-distance plots.

When critical transects are enabled, the flood fill at 0.03125° honors the
same shared critical land blockages and critical passages from
`geometric_features` that are used in E3SM topography culling. This changes
connectivity in the final `ocean_mask` and derived `signed_distance` fields at
all resolution tiers without changing the output schema.

The file `debug_summary.txt` records convention-specific counts such as the
number of ocean and land cells, along with the minimum and maximum signed
distance.

## Running a task

You can set up one of the coastline tasks with standard polaris commands, for
example:

```bash
polaris setup -t mesh/spherical/unified/coastline/0.12500_degree/task \
    -w coastline_0125
```

After setup, the work directory for the 0.03125° task contains symlinks to the
shared `combine_topo_lat_lon_0.03125_degree`, `coastline_final`, and
`viz_coastline` steps, along with the shared `coastline.cfg` file. The
coarser-resolution work directories additionally contain a `coastline_compute`
symlink pointing to the shared 0.03125° compute step.
