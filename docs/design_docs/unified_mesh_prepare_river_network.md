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
tier and coastline interpretation chosen for the workflow, while deferring
river-outlet reconciliation until after an MPAS base mesh exists.

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

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_river_network` shall provide source-level, target-grid, and
mesh-conditioned river products that can be consumed directly by
`build_sizing_field` and `create_base_mesh`.

The shared products shall retain the major river-network information needed for
mesh refinement and direct cell-center placement, including channel locations
and basin-root provenance.

The downstream sizing-field and base-mesh steps shall not need to rerun
HydroRIVERS filtering, network reconstruction, or coastline-aware river clipping
and simplification.

### Requirement: Hydrologically Meaningful Simplification

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation shall preserve the dominant global river main stems and
major tributaries needed to inform mesh resolution. Terminal river segments
shall be retained as basin roots for traversal and grouping, not as
coastline-reconciled outlet products.

The design shall support filtering by drainage area and by proximity so the
retained network reflects the target mesh scale rather than the full source
dataset density.

The simplification shall preserve connectivity and confluence structure rather
than reducing the product to disconnected local segments.

Where practical, the first Polaris design shall preserve the existing
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
river-network algorithms rather than redesigning them.

### Requirement: Deferred Outlet Reconciliation

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex

The pre-base-mesh river workflow shall not snap river outlets to the coastline,
write separate outlet products, or refine the sizing field based on outlet mask
cells.

The workflow shall preserve enough basin-root provenance, through
`outlet_hyriv_id`, `outlet_drainage_area`, and `river_network_rank`, for
downstream workflows to identify, select, and optionally write per-catchment
products without rerunning HydroRIVERS simplification. Outlet/coastline
reconciliation shall still occur after the MPAS base mesh exists.

### Requirement: Standalone River-Network Task

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Polaris shall provide a standalone task per named unified mesh that runs the
full shared river-network workflow for that mesh, including HydroRIVERS
simplification, channel rasterization, and coastline-aware
clipping, together with the shared upstream steps it depends on (for example
`e3sm/init/topo/combine` and `prepare_coastline`).

The standalone task shall make it practical to inspect retained basins,
target-grid river-channel masks, and clipped river geometry without running the
full unified mesh workflow.

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

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current implementation separates source-level hydrographic products from
target-grid products rather than trying to make one step serve both roles.
This aligns with the design intent that downstream consumers should not need to
reinterpret HydroRIVERS or infer outlet semantics from one overloaded raster.

At the source level, the workflow writes:

- `simplified_river_network.geojson`, containing retained segments with
  `hyriv_id`, `main_riv`, `ord_stra`, `drainage_area`, `next_down`,
  `endorheic`, `outlet_hyriv_id`, `outlet_drainage_area`, and
  `river_network_rank`; networks are ordered largest-first by terminal-root
  drainage area, and the rank field makes the N largest networks directly
  selectable without relying on feature order alone. The `outlet_hyriv_id`
  field is retained as basin-root provenance for future catchment grouping,
  not as a coastline-reconciled outlet product.

At the target-grid level, the workflow writes:

- `river_network.nc`, with `river_channel_mask`.

This is intentionally clearer than the standalone workflow's mixed raster
semantics. The present implementation does not yet add stream-order rasters or
basin IDs, but it does establish a clean product split that the
`build_sizing_field` implementation now consumes directly.

For base-mesh consumers, the workflow also writes a mesh-conditioned product
set:

- `clipped_river_network.geojson`, containing river segments clipped inland of
  the coastline and simplified for direct JIGSAW geometry use, with networks
  ordered largest-first by terminal-root drainage area; and
- `clipped_river_network.nc`, containing masks regenerated from the clipped
  network for diagnostics.

These products are where the river workflow becomes aware of the selected
unified mesh and its direct cell-placement needs. `build_sizing_field` uses the
target-grid masks, while `create_base_mesh` consumes the conditioned vector
geometry.

Generating the clipped products requires evaluating the coastline's
`signed_distance` field at each river coordinate.  Rather than calling
`interp_bilin()` once per segment, the implementation batches all coordinates
from all segments into a single array, performs one vectorised
bilinear-interpolation call over the entire network, and then splits the
resulting distance values back to the corresponding per-segment slices.  This
makes the coastline-distance interpolation cost proportional to the total number
of river vertices rather than to the number of segments, which can be
significant for globally dense simplified networks.

### Algorithm Design: Hydrologically Meaningful Simplification

Date last modified: 2026/05/15

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
4. Identify terminal basin roots from segments with `next_down == 0`.
5. Traverse upstream iteratively from each terminal root, keeping the
   largest upstream segment at each confluence as the main stem.
6. Retain additional tributaries when either their drainage area exceeds a
   configurable fraction of the main stem or their minimum distance from the
   already retained basin skeleton exceeds the branch-distance tolerance.

The key point is that simplification should be basin-aware and topology-aware.
The Polaris design should preserve connectivity and confluences, not just apply
independent Douglas-Peucker style simplification to each source feature.

### Algorithm Design: Deferred Outlet Reconciliation

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Outlet and coastline reconciliation is intentionally deferred until after an
MPAS base mesh exists. Before that point, snapping HydroRIVERS terminal points
to coastline cells and refining outlet mask cells adds complexity without a
clear benefit because the base-mesh workflow clips near-coast river geometry
and the sizing-field workflow blends land resolution toward ocean resolution
near the coastline.

The pre-base-mesh river workflow therefore keeps terminal-root provenance on
retained river segments through `outlet_hyriv_id`, `outlet_drainage_area`, and
`river_network_rank`. Rasterization produces the channel mask needed by the
sizing field, and clipped vector products provide the river geometry needed by
JIGSAW. Downstream workflows that need outlet locations or catchment-specific
files can group segments by `outlet_hyriv_id`, select the largest basins by
`river_network_rank`, and perform outlet/coastline reconciliation later.

### Algorithm Design: Standalone River-Network Task

Date last modified: 2026/05/15

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
  unpacking and source-level simplification;
- `rasterize.py` (`RasterizeRiverLatLonStep`) for target-grid rasterization
  of retained river channels;
- `clip.py` (`ClipRiverNetworkStep`) for coastline-aware clipping and
  conditioning of retained river geometry for final mesh generation;
- `viz.py` (`VizRiverStep`) for diagnostic plotting and text summaries;
- `steps.py` for shared-step setup helpers (`get_unified_mesh_river_steps()`);
- `task.py` and `tasks.py` for standalone task wrappers; and
- the configuration sections are loaded from the unified mesh config.

This implementation prioritizes a clean output contract over carrying forward
the standalone workflow's mixed raster conventions or writing default
per-catchment GeoJSON files. A single ranked GeoJSON keeps the authoritative
simplified network in one file while still allowing scripts to reproduce the
standalone workflow's "largest N basins" exports by filtering on
`river_network_rank`.

The simplification step obtains HydroRIVERS through `add_input_file()` using
the public archive URL in the river network config section, with the Polaris
database still available as a fallback cache location. The rasterization step
then consumes the shared coastline grid for the selected convention and writes a
channel-only mask. The `ClipRiverNetworkStep` consumes the simplified network
together with the selected coastline product and writes the clipped river
geometry consumed by the unified base-mesh step.

The coastline-aware clipping in `condition_base_mesh_river_segments()` and
the channel-only raster products use a single batched call to `interp_bilin()`
rather than one call per segment. All vertex coordinates are stacked into one
array, `_interpolate_signed_distance()` is called once, and the resulting
signed-distance values are split back to per-segment slices with `np.split()`.
This keeps bilinear-interpolation overhead proportional to the total vertex
count rather than to the number of segments.

### Implementation: Hydrologically Meaningful Simplification

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current simplification logic lives in
`simplify_river_network_feature_collection()` in
`polaris/tasks/mesh/spherical/unified/river/simplify.py`. It uses small focused
helpers for canonicalizing segments, validating downstream topology, filtering
by drainage area, and traversing retained basin structure from all terminal
roots.

After basin traversal, the implementation annotates each retained segment with
`outlet_drainage_area` and `river_network_rank`. The rank is 1-based, with
rank 1 assigned to the retained terminal basin with the largest outlet drainage
area. These properties are preserved by the canonical `RiverSegment` read/write
helpers and are carried through coastline conditioning so downstream products do
not silently drop the network-selection metadata.

The implementation favors a compact Polaris-native reimplementation over a
direct migration of
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
helper layers. No clear defect emerged from the current unit tests, but this
remains an area where additional comparison against real HydroRIVERS output
would strengthen confidence.

### Implementation: Deferred Outlet Reconciliation

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

The current implementation removes coastline matching and inland-sink treatment
from the pre-base-mesh river products. `river_network.nc` contains
`river_channel_mask` only, and the simplified/clipped GeoJSON products keep
basin-root provenance and network-selection metadata but no coastline-snapped
outlet products. Outlet snapping and catchment-specific outlet products are
deferred to downstream workflows that operate after the MPAS base mesh exists.

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

- `test_build_river_network_dataset_contract_and_channel_mask` verifies
  that `build_river_network_dataset()` writes the expected channel-only mask
  variable (`river_channel_mask`) without outlet-matching attributes.
- `test_mesh_river_step_factories_use_mesh_subdirs` verifies that
  `get_unified_mesh_river_steps()` creates `SimplifyRiverNetworkStep`,
  `RasterizeRiverLatLonStep`, and `ClipRiverNetworkStep` with the expected
  mesh-specific subdirectories.
- `test_mesh_river_step_factories_reuse_shared_configs` verifies step and
  config identity across multiple calls to `get_unified_mesh_river_steps()`.

The coastline-aware conditioning tests in the same file verify
`condition_base_mesh_river_segments()`. The `test_base_mesh.py` tests then
verify that `UnifiedBaseMeshStep` converts the prepared
`clipped_river_network.geojson` product into JIGSAW line constraints rather
than raw river geometry.

`build_sizing_field` unit tests consume the target-grid river masks. There is
still not a task-level integration test showing the full river workflow feeding
either the sizing-field task or the final base-mesh task on real data.

### Testing and Validation: Hydrologically Meaningful Simplification

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` validate
simplification behavior on synthetic networks:

- `test_simplify_river_network_traverses_all_terminal_segments` verifies that
  all retained terminal segments are traversed and that `outlet_hyriv_id`,
  `outlet_drainage_area`, and `river_network_rank` are preserved as
  basin-root provenance and network-selection metadata.
- `test_simplify_river_network_handles_deep_main_stem` confirms correctness for
  a 1500-segment chain without Python recursion limits.
- `test_simplify_river_network_rejects_next_down_cycles` verifies that cyclic
  `NEXT_DOWN` graphs are rejected with a clear error.
- `test_simplify_river_network_preserves_branch_traversal_order` verifies that
  multi-branch confluence structure is retained correctly.
- `test_convert_hydrorivers_shapefile_to_geojson` verifies shapefile conversion.
- `test_unpack_hydrorivers_archive` verifies archive unpacking.
- `test_drainage_area_threshold_auto_derived_from_config` and
  `test_branch_distance_tolerance_auto_derived_from_config` verify that
  simplification thresholds are derived correctly from mesh configs.

What is still missing is validation against real HydroRIVERS subsets to ensure
the present heuristics retain scientifically appropriate networks across
different hydrographic settings.

### Testing and Validation: Deferred Outlet Reconciliation

Date last modified: 2026/05/15

Contributors:

- Xylar Asay-Davis
- Codex
- Claude

Unit tests in `tests/mesh/spherical/unified/test_river.py` cover the
channel-only pre-base-mesh products:

- `test_build_river_network_dataset_contract_and_channel_mask` verifies the
  channel-only raster contract.
- `test_build_river_network_dataset_applies_physical_channel_buffer` verifies
  the physical buffer applied to rasterized channel cells.
- `test_condition_base_mesh_river_segments_clips_then_simplifies` and
  `test_condition_base_mesh_river_segments_drops_short_fragments` verify the
  coastline clipping applied before base-mesh conditioning.

The visualization step writes `river_network_overlay.png`,
`rasterized_river_network.png`, and `debug_summary.txt`, making the simplified,
clipped, and rasterized channel products straightforward to inspect in task
runs.

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
