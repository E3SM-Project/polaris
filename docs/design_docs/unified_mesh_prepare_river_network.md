# Unified Mesh: River Network Preparation

date: 2026/04/19

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

## Summary

This design describes the shared `prepare_river_network` step and associated
tasks that can run the shared river steps on their own for the unified global
base-mesh workflow. The purpose of the step is to simplify a global river
dataset into products that can be consumed directly by `build_sizing_field`
without re-reading or reinterpreting the raw source data.

The shared river-network workflow is implemented in Polaris pull request
<https://github.com/E3SM-Project/polaris/pull/556>.

The preferred first source is HydroRIVERS or an equivalent global flowline
dataset. Unlike the standalone
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
workflow, the Polaris design makes the downstream interface explicit. In
particular, the workflow distinguishes between the authoritative simplified
river network, the target-grid products needed by `build_sizing_field`, and
the mesh-conditioned products needed by `create_base_mesh`, rather than
overloading a single raster with mixed semantics.

Because river-network simplification and river-driven meshing are the parts of
the workflow where Xylar's design intuition is currently weakest, the first
Polaris design should preserve the
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
river algorithms as closely as is practical.

The implementation aligns `prepare_river_network` with the shared target-grid
tier and coastline interpretation chosen for the workflow, so that river
outlets and coastal refinement can be made consistent.

Success means that Polaris gains a documented, reusable river-network
preprocessing workflow that preserves the major hydrographic controls relevant
for mesh generation and makes its outputs easy to inspect and easy for
downstream steps to consume.

## Workflow Context

The overall unified-mesh workflow is described in
[Unified Mesh: Global Base Mesh Workflow](unified_base_mesh.md).

The upstream unified-mesh workflow design is:

- [Unified Mesh: Coastline Preparation](unified_mesh_prepare_coastline.md)

The downstream unified-mesh workflow designs are:

- [Unified Mesh: Sizing-Field Construction](unified_mesh_build_sizing_field.md)
- [Unified Mesh: Base-Mesh Creation and Downstream Integration](unified_mesh_create_base_mesh.md)

## Requirements

### Requirement: Downstream-Ready River Network Products

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_river_network` shall provide source-level, target-grid, and
mesh-conditioned river products that can be consumed directly by
`build_sizing_field` and `create_base_mesh`.

The shared products shall retain the major river-network information needed for
mesh refinement and direct cell-center placement, including channel locations
and outlet locations.

The downstream sizing-field and base-mesh steps shall not need to rerun
HydroRIVERS filtering, network reconstruction, outlet discovery, or
coastline-aware river clipping and simplification.

### Requirement: Hydrologically Meaningful Simplification

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation shall preserve the dominant global river outlets,
main stems, and major tributaries needed to inform mesh resolution.

The design shall support filtering by drainage area and by proximity so the
retained network reflects the target mesh scale rather than the full source
dataset density.

The simplification shall preserve connectivity and confluence structure rather
than reducing the product to disconnected local segments.

Where practical, the first Polaris design shall preserve the existing
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
river-network algorithms rather than redesigning them.

### Requirement: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

River outlets that drain to the ocean shall be made consistent with the
coastline interpretation selected in `prepare_coastline`.

Endorheic basins and other inland sinks shall remain explicit rather than
being folded into the ocean-outlet logic.

The workflow shall not assume that raw river-source outlet locations are
already perfectly consistent with the preferred coastline source.

### Requirement: Standalone River-Network Task

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Polaris shall provide a standalone task per named unified mesh that runs the
full shared river-network workflow for that mesh, including HydroRIVERS
simplification, coastline-consistent rasterization, and coastline-aware
clipping, together with the shared upstream steps it depends on (for example
`e3sm/init/topo/combine` and `prepare_coastline`).

The standalone task shall make it practical to inspect retained basins,
outlets, target-grid river masks, and outlet-snapping diagnostics without
running the full unified mesh workflow.

The same shared steps and configuration shall be reusable from the full unified
workflow when settings match.

### Requirement: Reproducible Source Data Access

Date last modified: 2026/04/19

Contributors:

- Xylar Asay-Davis
- Codex

All source datasets needed by `prepare_river_network` shall be obtained either
from documented public sources or, if that is not feasible, from the Polaris
database.

The preferred implementation shall download raw source data from public
sources and perform any needed preprocessing within Polaris rather than
requiring users to provide local input-file paths.

Adding preprocessed artifacts to the Polaris database should be treated as a
fallback for cases where the source data are not publicly distributable or the
required preprocessing cannot be reproduced robustly within Polaris.

## Algorithm Design

### Algorithm Design: Downstream-Ready River Network Products

Date last modified: 2026/05/08

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current implementation separates source-level hydrographic products from
target-grid products rather than trying to make one step serve both roles.
This aligns with the design intent that downstream consumers should not need to
reinterpret HydroRIVERS or infer outlet semantics from one overloaded raster.

At the source level, the workflow writes:

- `source_river_network.geojson`, containing the converted HydroRIVERS source;
- `simplified_river_network.geojson`, containing retained segments with
  `hyriv_id`, `main_riv`, `ord_stra`, `drainage_area`, `next_down`,
  `endorheic`, `outlet_type`, and `outlet_hyriv_id`; and
- `retained_outlets.geojson`, containing the retained outlet points and their
  basic classification.

At the target-grid level, the workflow writes:

- `river_network.nc`, with `river_channel_mask`, `river_outlet_mask`,
  `river_ocean_outlet_mask`, and `river_inland_sink_mask`; and
- `river_outlets.geojson`, containing the snapped outlet points together with
  source coordinates, snapped coordinates, snapped grid indices, snapping
  distance, and `matched_to_ocean`.

This is intentionally clearer than the standalone workflow's mixed raster
semantics. The present implementation does not yet add stream-order rasters or
basin IDs, but it does establish a clean product split that the
`build_sizing_field` implementation now consumes directly.

For base-mesh consumers, the workflow also writes a mesh-conditioned product
set:

- `clipped_river_network.geojson`, containing river segments clipped inland of
  the coastline and simplified for direct JIGSAW geometry use;
- `clipped_outlets.geojson`, containing only outlets that remain relevant after
  that conditioning; and
- `clipped_river_network.nc`, containing masks regenerated from the clipped
  network for diagnostics.

These products are where the river workflow becomes aware of the selected
unified mesh and its direct cell-placement needs. `build_sizing_field` uses the
target-grid masks, while `create_base_mesh` consumes the conditioned vector
geometry.

Generating the clipped products requires evaluating the coastline's
`signed_distance` field at each river coordinate.  Rather than calling
`interp_bilin()` once per segment or outlet feature, the implementation batches
all coordinates from all segments into a single array, performs one vectorised
bilinear-interpolation call over the entire network, and then splits the
resulting distance values back to the corresponding per-segment slices.  The
same batching is applied to outlet coordinates in `clip_outlet_feature_collection`.
This makes the coastline-distance interpolation cost proportional to the total
number of river vertices rather than to the number of segments, which can be
significant for globally dense simplified networks.

### Algorithm Design: Hydrologically Meaningful Simplification

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The current Polaris implementation is a focused reimplementation built around
HydroRIVERS attributes such as `HYRIV_ID`, `MAIN_RIV`, `ORD_STRA`,
`UPLAND_SKM`, `NEXT_DOWN`, and `ENDORHEIC`. Its staged logic is:

1. Filter source flowlines by a minimum drainage-area threshold tied to the
   intended river-refinement scale.
2. Merge multiple source features with the same `hyriv_id` into one canonical
   segment when needed.
3. Validate that the retained `NEXT_DOWN` graph is acyclic before attempting
   basin traversal.
4. Identify candidate outlets from segments with `next_down == 0`, then retain
   large, well-separated outlets based on geodesic distance while preserving
   distinct inland sinks.
5. Traverse upstream iteratively from each retained outlet, keeping the
   largest upstream segment at each confluence as the main stem.
6. Retain additional tributaries when either their drainage area exceeds a
   configurable fraction of the main stem or their minimum distance from the
   already retained basin skeleton exceeds the outlet-distance tolerance.

The key point is that simplification should be basin-aware and topology-aware.
The Polaris design should preserve connectivity and confluences, not just apply
independent Douglas-Peucker style simplification to each source feature.

### Algorithm Design: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/05/08

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The simplified network is finalized in two phases: source-level retention and
target-grid reconciliation. The source-level step identifies retained outlet
points, and the lat-lon step then reconciles those points against the shared
coastline product.

For ocean-draining basins, the current implementation identifies the nearest
ocean cell in `coastline.nc` using a KD tree built once over all ocean cells
before the outlet loop begins.  Each ocean cell's lat/lon is converted to a
unit-sphere Cartesian coordinate (the 3-D point on the surface of the unit
sphere), so that the nearest neighbour in 3-D Euclidean space equals the nearest
neighbour by great-circle distance.  A single `query()` call on the pre-built
tree returns the closest ocean cell in O(log n) time rather than requiring a
linear scan over the full grid.  The haversine distance to that cell is then
computed, and the outlet is marked as matched only if the distance is within the
configured `outlet_match_tolerance`. If no ocean cell is close enough, the outlet
is still snapped to the nearest grid cell but is recorded as
`matched_to_ocean = false` with the snapping distance preserved for diagnostics.

Endorheic basins bypass ocean matching and are snapped to the nearest land cell
derived from the coastline `ocean_mask`, using a KD tree built once over all land
cells with the same unit-sphere Cartesian approach.  They retain the explicit
`inland_sink` classification in both the vector outlet metadata and the target-
grid masks.

If an ocean-draining outlet cannot be matched within tolerance, the workflow
flags that basin through per-feature metadata and through the dataset attribute
`unmatched_ocean_outlets`.

Once outlet reconciliation is complete, the simplified river network can be
rasterized onto the shared target grid. Rasterization should produce separate
channel and outlet masks rather than a single overloaded integer raster.

### Algorithm Design: Standalone River-Network Task

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current standalone task design uses one thin wrapper per named unified
mesh, `UnifiedRiverNetworkTask`, rather than separate source-level and
lat-lon tasks. Each task wraps the full shared river-network step chain for
its mesh — coastline steps, simplification, rasterization, clipping, and
visualization — so all products can be inspected together without running the
full unified mesh workflow.

Organizing by mesh name rather than by resolution keeps the task structure
consistent with the sizing-field and base-mesh task families and avoids
creating standalone tasks for resolutions that are not tied to a specific
mesh configuration.

## Implementation

### Implementation: Downstream-Ready River Network Products

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The file naming and class layout are now concrete. The river implementation is
organized under `polaris/tasks/mesh/spherical/unified/river/` as:

- `simplify.py` (`SimplifyRiverNetworkStep`) for HydroRIVERS download,
  unpacking, shapefile conversion, and source-level simplification;
- `rasterize.py` (`RasterizeRiverLatLonStep`) for target-grid rasterization
  and outlet reconciliation;
- `clip.py` (`ClipRiverNetworkStep`) for coastline-aware clipping and
  conditioning of retained river geometry for final mesh generation;
- `viz.py` (`VizRiverStep`) for diagnostic plotting and text summaries;
- `steps.py` for shared-step setup helpers (`get_unified_mesh_river_steps()`);
- `task.py` and `tasks.py` for standalone task wrappers; and
- the configuration sections are loaded from the unified mesh config.

This implementation prioritizes a clean output contract over carrying forward
the standalone workflow's mixed raster conventions.

The simplification step obtains HydroRIVERS through `add_input_file()` using
the public archive URL in the river network config section, with the Polaris
database still available as a fallback cache location. The rasterization step
then consumes the shared coastline dataset for the selected convention. The
`ClipRiverNetworkStep` consumes the simplified network together with the
selected coastline product and writes the clipped river geometry consumed by
the unified base-mesh step.

The coastline-aware clipping in `condition_base_mesh_river_segments()` and
`clip_outlet_feature_collection()` uses a single batched call to `interp_bilin()`
rather than one call per segment or outlet.  All vertex coordinates are stacked
into one array, `_interpolate_signed_distance()` is called once, and the
resulting signed-distance values are split back to per-segment slices with
`np.split()`.  This keeps bilinear-interpolation overhead proportional to the
total vertex count rather than to the number of segments.

### Implementation: Hydrologically Meaningful Simplification

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current simplification logic lives in
`simplify_river_network_feature_collection()` in
`polaris/tasks/mesh/spherical/unified/river/simplify.py`. It uses small focused
helpers for canonicalizing segments, validating downstream topology, filtering
outlets, and traversing retained basin structure.

The implementation favors a compact Polaris-native reimplementation over a
direct migration of
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
helper layers. No clear defect emerged from the current unit tests, but this
remains an area where additional comparison against real HydroRIVERS output
would strengthen confidence.

### Implementation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/05/08

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current implementation keeps coastline matching and inland-sink treatment
explicit in both NetCDF and GeoJSON outputs. `river_network.nc` separates
channel cells, all outlet cells, ocean outlets, and inland sinks, and
`river_outlets.geojson` records both source and snapped positions together with
match status and snapping distance.

The nearest-ocean-cell and nearest-land-cell lookups are implemented in
`_build_cell_kdtree()` and the `_match_ocean_outlet()` / `_match_land_point()`
helpers in `rasterize.py`.  `_build_cell_kdtree()` uses `scipy.spatial.cKDTree`
on unit-sphere Cartesian coordinates derived from the grid cell lat/lon values.
Both trees are built once before iterating over outlet features, so the total
lookup cost is O(n_outlets · log n_cells) rather than O(n_outlets · n_cells).

### Implementation: Standalone River-Network Task

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current implementation adds one lightweight task wrapper per named unified
mesh in `polaris/tasks/mesh/spherical/unified/river/task.py` and avoids any
separate task-specific river-processing code path. `UnifiedRiverNetworkTask`
wraps the full shared step chain for its mesh — coastline steps, simplification
(`SimplifyRiverNetworkStep`), rasterization (`RasterizeRiverLatLonStep`),
clipping (`ClipRiverNetworkStep`), and visualization — so all products can be
inspected together. Task registration is handled by `add_river_tasks()` in
`tasks.py`, which iterates over `UNIFIED_MESH_NAMES` and registers one task per
mesh.

## Testing

### Testing and Validation: Downstream-Ready River Network Products

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` verify the
target-grid product contract. Specifically:

- `test_build_river_network_dataset_contract_and_snapped_outlets` verifies
  that `build_river_network_dataset()` writes the expected mask variables
  (`river_channel_mask`, `river_outlet_mask`, `river_ocean_outlet_mask`,
  `river_inland_sink_mask`), matched-outlet attributes
  (`matched_ocean_outlets`, `unmatched_ocean_outlets`), and snapped-outlet
  GeoJSON with `snapped_lon`, `snapped_lat`, and `matched_to_ocean`.
- `test_mesh_river_step_factories_use_mesh_subdirs` verifies that
  `get_unified_mesh_river_steps()` creates `SimplifyRiverNetworkStep`,
  `RasterizeRiverLatLonStep`, and `ClipRiverNetworkStep` with the expected
  mesh-specific subdirectories.
- `test_mesh_river_step_factories_reuse_shared_configs` verifies step and
  config identity across multiple calls to `get_unified_mesh_river_steps()`.

The coastline-aware conditioning tests in the same file verify
`condition_base_mesh_river_segments()` and `clip_outlet_feature_collection()`.
The `test_base_mesh.py` tests then verify that `UnifiedBaseMeshStep` converts
the prepared `clipped_river_network.geojson` product into JIGSAW line
constraints rather than raw river geometry.

`build_sizing_field` unit tests consume the target-grid river masks. There is
still not a task-level integration test showing the full river workflow feeding
either the sizing-field task or the final base-mesh task on real data.

### Testing and Validation: Hydrologically Meaningful Simplification

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` validate
simplification behavior on synthetic networks:

- `test_simplify_river_network_filters_outlets_and_minor_tributaries` verifies
  that major outlets and tributaries exceeding the area ratio are retained while
  nearby headwaters within the distance tolerance are filtered.
- `test_simplify_river_network_handles_deep_main_stem` confirms correctness for
  a 1500-segment chain without Python recursion limits.
- `test_simplify_river_network_rejects_next_down_cycles` verifies that cyclic
  `NEXT_DOWN` graphs are rejected with a clear error.
- `test_simplify_river_network_preserves_branch_traversal_order` verifies that
  multi-branch confluence structure is retained correctly.
- `test_convert_hydrorivers_shapefile_to_geojson` verifies shapefile conversion.
- `test_unpack_hydrorivers_archive` verifies archive unpacking.
- `test_drainage_area_threshold_auto_derived_from_config` and
  `test_outlet_distance_tolerance_auto_derived_from_config` verify that
  simplification thresholds are derived correctly from mesh configs.

What is still missing is validation against real HydroRIVERS subsets to ensure
the present heuristics retain scientifically appropriate networks across
different hydrographic settings.

### Testing and Validation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` cover outlet
matching and inland-sink treatment:

- `test_build_river_network_dataset_contract_and_snapped_outlets` verifies
  matched ocean-outlet snapping and inland-sink classification.
- `test_build_river_network_dataset_marks_distant_ocean_outlet_unmatched`
  verifies that an outlet beyond the tolerance is flagged `matched_to_ocean =
  false` and counted in `unmatched_ocean_outlets`.
- `test_build_river_network_dataset_derives_land_mask_from_ocean_mask` verifies
  that inland sinks are snapped to land cells derived from `ocean_mask`.
- `test_build_river_network_dataset_applies_physical_channel_buffer` verifies
  the physical buffer applied to rasterized channel cells.
- `test_condition_base_mesh_river_segments_clips_then_simplifies` and
  `test_condition_base_mesh_river_segments_drops_short_fragments` verify the
  coastline clipping applied before base-mesh conditioning.
- `test_clip_outlet_feature_collection_removes_ocean_outlets` verifies that
  ocean outlets within the clip zone are removed.

The visualization step writes `river_network_overview.png` and
`debug_summary.txt`, making outlet-matching diagnostics straightforward to
inspect in task runs.

### Testing and Validation: Standalone River-Network Task

Date last modified: 2026/05/11

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` verify the
standalone task structure:

- `test_add_river_tasks_registers_mesh_tasks` verifies that `add_river_tasks()`
  registers one `UnifiedRiverNetworkTask` per name in `UNIFIED_MESH_NAMES`,
  that each task subdirectory is `spherical/unified/<mesh_name>/river/task`,
  and that each task name is `river_network_<mesh_name>_task`.
- `test_mesh_river_step_factories_use_mesh_subdirs` verifies mesh-specific
  subdirectories for the simplify, rasterize, and clip steps.
- `test_mesh_river_step_factories_reuse_shared_configs` verifies that step
  and config instances are shared across multiple `get_unified_mesh_river_steps()`
  calls for the same mesh.

Standalone smoke tests for each of the supported unified meshes have been run
on Frontier, showing the expected rasterized river networks at each resolution.
Specific parameter choices still need to be fine-tuned.

Full end-to-end execution of the river workflow feeding the sizing-field and
base-mesh tasks on real data is planned but not yet performed.
