(dev-mesh-unified-river)=

# River-Network Steps and Tasks

This section of the Developer's guide covers the code for the unified-mesh
river workflow. The {ref}`users-mesh-unified-river` section describes the
user-facing behavior, configuration options, algorithms, and output products.

The `polaris.tasks.mesh.spherical.unified.river` package separates the river
workflow into source-level simplification, target-grid rasterization, optional
diagnostics, and downstream base-mesh conditioning. The package makes available
functions that return a dict of shared steps and thin task wrappers so the same
implementation can be reused by standalone inspection tasks and by downstream
unified-mesh tasks.

## Available tasks

The helper
{py:func}`polaris.tasks.mesh.spherical.unified.river.add_river_tasks`
registers one standalone task for each mesh name in
`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`:

- {py:class}`polaris.tasks.mesh.spherical.unified.river.UnifiedRiverNetworkTask` at
  `mesh/spherical/unified/<mesh_name>/river/task`.

{py:func}`polaris.tasks.mesh.add_tasks.add_mesh_tasks` wires these tasks into
the `mesh` component after the generic base-mesh tasks (see
{ref}`dev-mesh-base-mesh-task`) and the shared coastline tasks (see
{ref}`dev-mesh-unified-coastline`).

## Task structure and shared steps

`UnifiedRiverNetworkTask` layers shared dependencies in a fixed order:

1. It requests the shared lat-lon topography step (see
   {ref}`dev-e3sm-init-topo-combine-tasks`) from
   {py:func}`polaris.tasks.e3sm.init.topo.combine.steps.get_lat_lon_topo_steps`
   and exposes it as `combine_topo`.
2. It requests the shared coastline steps (see {ref}`dev-mesh-unified-coastline`)
   from
   {py:func}`polaris.tasks.mesh.spherical.unified.coastline.get_unified_mesh_coastline_steps`
   and exposes them as `coastline_compute` and the optional
   `viz_coastline_compute`.
3. It requests the full set of shared river steps from
   {py:func}`polaris.tasks.mesh.spherical.unified.river.get_unified_mesh_river_steps`
   and exposes {py:class}`polaris.tasks.mesh.spherical.unified.river.SimplifyRiverNetworkStep`
   as `river_simplify`,
   {py:class}`polaris.tasks.mesh.spherical.unified.river.RasterizeRiverLatLonStep`
   as `river_rasterize`,
   {py:class}`polaris.tasks.mesh.spherical.unified.river.VizRiverStep` as
   `viz_river_network`, and
   {py:class}`polaris.tasks.mesh.spherical.unified.river.ClipRiverNetworkStep`
   as `river_clip`.

This ordering keeps the river implementation dependent only on the explicit
products it consumes: simplified HydroRIVERS geometry and the selected
coastline dataset.

The shared-step factory in `steps.py` is the main extension point for other
task families:

- {py:func}`polaris.tasks.mesh.spherical.unified.river.get_unified_mesh_river_steps`
  builds or reuses the full chain of shared river steps —
  {py:class}`polaris.tasks.mesh.spherical.unified.river.SimplifyRiverNetworkStep`,
  {py:class}`polaris.tasks.mesh.spherical.unified.river.RasterizeRiverLatLonStep`,
  optional {py:class}`polaris.tasks.mesh.spherical.unified.river.VizRiverStep`,
  and {py:class}`polaris.tasks.mesh.spherical.unified.river.ClipRiverNetworkStep`
  — returning them as a dict keyed by step name along with the lat-lon mesh
  config.

## Implementation map

### `simplify.py`

`SimplifyRiverNetworkStep.setup()` registers the HydroRIVERS archive as an input
file through `add_input_file()` using the public URL from `river_network.cfg`.
`SimplifyRiverNetworkStep.run()` unpacks the archive, converts the shapefile to
GeoJSON, simplifies the source network, and writes:

- `source_river_network.geojson`
- `simplified_river_network.geojson`
- `retained_outlets.geojson`

The public helper
{py:func}`polaris.tasks.mesh.spherical.unified.river.simplify_river_network_feature_collection`
contains the source-level retention logic. It builds canonical segments,
validates downstream topology, filters outlet candidates, and traverses
retained basins while preserving main stems and significant tributaries.

The tributary-selection logic compares each non-primary tributary's drainage
area against the **basin outlet's** drainage area (not the primary upstream
tributary's area), matching the reference point used by the standalone
implementation. Strahler stream-order-1 headwater tributaries skip the
drainage-area check entirely and proceed directly to the distance-based
fallback, consistent with the standalone's more aggressive headwater pruning.

The internal `RiverSegment` dataclass is the canonical representation used by
the simplification helpers. It is intentionally not exported as part of the
public API.

### `rasterize.py`

`RasterizeRiverLatLonStep.setup()` links the simplified source products and the
selected coastline NetCDF file. `RasterizeRiverLatLonStep.run()` reads those
inputs, calls
{py:func}`polaris.tasks.mesh.spherical.unified.river.build_river_network_dataset`,
and writes:

- `river_network.nc`
- `river_outlets.geojson`

`build_river_network_dataset()` is the public target-grid helper. It rasterizes
river channels, snaps ocean outlets against coastline ocean cells, snaps inland
sinks to land cells, and writes a clean mask split between channels, all
outlets, ocean outlets, and inland sinks.

### `clip.py`

`ClipRiverNetworkStep` is produced through `get_unified_mesh_river_steps()`
and is included in `UnifiedRiverNetworkTask` as well as downstream unified
base-mesh consumers.

Its `run()` method reads the simplified river network and coastline products,
then conditions the retained geometry for direct base-mesh use by:

- clipping segments inland of the selected coastline by the configured clip
  distance;
- simplifying clipped geometry and removing degenerate or too-short pieces;
- dropping outlets that do not remain inland after clipping; and
- regenerating a diagnostic lat-lon mask product from the conditioned river
  geometry.

This step writes `clipped_river_network.geojson`, `clipped_outlets.geojson`,
and `clipped_river_network.nc`.

### `viz.py`

`VizRiverStep` is a pure diagnostic consumer of the shared source, coastline,
and lat-lon river products. It writes `river_network_overview.png` and
`debug_summary.txt`, and keeps visualization logic out of the numerical steps.

## Configuration plumbing

All shared river steps use mesh-specific configs built through
`polaris.mesh.spherical.unified.get_unified_mesh_config()`. That loader
combines:

- the generic `unified_mesh.cfg` defaults;
- the shared `river_network.cfg` file; and
- the selected named-mesh config file.

`SimplifyRiverNetworkStep` consumes `[river_network]` options and, when
`drainage_area_threshold` or `outlet_distance_tolerance` is set to the sentinel
value `-1`, reads `land_background_km` and `river_channel_km` from
`[sizing_field]` to derive the threshold values automatically.

`RasterizeRiverLatLonStep` consumes `[river_rasterize]` options and also reads the
selected `unified_mesh` settings such as `mesh_name`, `resolution_latlon`,
and `coastline_convention`.

`ClipRiverNetworkStep` consumes `[river_network]` and `unified_mesh`
settings, and currently reads the Antarctic coastline convention from the
`[spherical_mesh]` section when selecting the coastline product for clipping.

`VizRiverStep` consumes `[viz_river_network].dpi`.

## Extension points

Common extension paths for future development are:

- adding a new named unified mesh by creating a new config file under
  `polaris.mesh.spherical.unified`; task registration discovers mesh names
  from those config files automatically;
- extending source-level metadata or retention rules in
  `simplify_river_network_feature_collection()` and the associated GeoJSON
  property builders;
- extending the target-grid output contract in
  `build_river_network_dataset()` and the visualization step; and
- adjusting downstream coastline-aware conditioning in
  `ClipRiverNetworkStep` without creating a separate river-processing
  code path for base meshes.

The public API in this package is intentionally narrow: task wrappers,
shared-step factories, step classes, and the two reusable dataset-building
helpers. Most geometry and graph utilities remain private so they can evolve
without breaking downstream callers.

## Test coverage

Unit tests in `tests/mesh/spherical/unified/test_river.py` currently cover:

- source-level outlet filtering, deep main-stem traversal, tributary
  retention, and cycle detection;
- HydroRIVERS archive unpacking and shapefile-to-GeoJSON conversion helpers;
- target-grid raster and snapped-outlet contracts;
- coastline-aware base-mesh conditioning helpers and shared-step factories;
- and task registration for all named unified meshes.

There is not yet a full task-level integration test that runs the end-to-end
river workflow on real HydroRIVERS data inside the documentation build or unit
test suite.