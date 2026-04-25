# Unified Mesh: River Network Preparation

date: 2026/04/19

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design describes the shared `prepare_river_network` step and associated
tasks that can run the shared river steps on their own for the unified global
base-mesh workflow. The purpose of the step is to simplify a global river
dataset into products that can be consumed directly by `build_sizing_field`
without re-reading or reinterpreting the raw source data.

The implementation is being added on the `add-prepare-river-network` branch in
Polaris pull request <https://github.com/E3SM-Project/polaris/pull/556>.

The preferred first source is HydroRIVERS or an equivalent global flowline
dataset. Unlike the standalone
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
workflow, the Polaris design makes the downstream interface explicit. In
particular, the workflow distinguishes between the authoritative simplified
river network and the target-grid products needed by `build_sizing_field`,
rather than overloading a single raster with mixed semantics.

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

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_river_network` shall provide source-level and target-grid products
that can be consumed directly by `build_sizing_field`.

The shared products shall retain the major river-network information needed for
mesh refinement, including channel locations and outlet locations.

The downstream sizing-field step shall not need to rerun HydroRIVERS
filtering, network reconstruction, or outlet discovery.

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

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide a standalone task for the shared source-level river
preprocessing and a standalone lat-lon task that runs the shared river
rasterization together with the shared steps it depends on (for example
`e3sm/init/topo/combine` and `prepare_coastline`).

These standalone tasks shall make it practical to inspect retained basins,
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

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

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
`add-build-sizing-field` implementation now consumes directly.

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

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The simplified network is finalized in two phases: source-level retention and
target-grid reconciliation. The source-level step identifies retained outlet
points, and the lat-lon step then reconciles those points against the shared
coastline product.

For ocean-draining basins, the current implementation searches for the nearest
ocean cell in `coastline.nc`, computes the haversine distance to that cell, and
marks the outlet as matched only if the distance is within the configured
`outlet_match_tolerance`. If no ocean cell is close enough, the outlet is still
snapped to the nearest grid cell but is recorded as `matched_to_ocean = false`
with the snapping distance preserved for diagnostics.

Endorheic basins bypass ocean matching and are snapped to the nearest land cell
derived from the coastline `ocean_mask`. They retain the explicit
`inland_sink` classification in both the vector outlet metadata and the target-
grid masks.

If an ocean-draining outlet cannot be matched within tolerance, the workflow
flags that basin through per-feature metadata and through the dataset attribute
`unmatched_ocean_outlets`.

Once outlet reconciliation is complete, the simplified river network can be
rasterized onto the shared target grid. Rasterization should produce separate
channel and outlet masks rather than a single overloaded integer raster.

### Algorithm Design: Standalone River-Network Task

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The current standalone task design uses two thin wrappers rather than one
monolithic task.

`PrepareRiverNetworkTask` wraps only the shared source-level step and is the
right place to inspect HydroRIVERS conversion and source-grid-independent
simplification choices. `LatLonRiverNetworkTask` adds the shared lat-lon topo
combine step, the shared coastline step, the shared lat-lon river step, and an
optional visualization step so outlet matching and rasterization can be
inspected on a concrete target grid.

This split keeps each task close to one layer of the interface while still
reusing the same shared steps that the `build_sizing_field` task consumes.

## Implementation

### Implementation: Downstream-Ready River Network Products

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The file naming and class layout are now concrete. The river implementation is
organized under `polaris/tasks/mesh/spherical/unified/river/` as:

- `source.py` for HydroRIVERS download, unpacking, shapefile conversion, and
  source-level simplification;
- `lat_lon.py` for target-grid rasterization and outlet reconciliation;
- `viz.py` for diagnostic plotting and text summaries;
- `steps.py` for shared-step factories;
- `task.py` for standalone task wrappers; and
- `river_network.cfg` for the shared configuration sections.

This implementation prioritizes a clean output contract over carrying forward
the standalone workflow's mixed raster conventions.

The first Polaris implementation should also avoid making the default workflow
depend on a user-supplied local source-file path. Instead, it should identify
the required public datasets and either download them directly or, only if
necessary, consume them from the Polaris database.

The source step obtains HydroRIVERS through `add_input_file()` using the public
archive URL in `[prepare_river_network]`, with the Polaris database still
available as a fallback cache location. The lat-lon step then consumes the
shared coastline dataset selected by `[prepare_river_lat_lon]`.

### Implementation: Hydrologically Meaningful Simplification

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The current simplification logic lives in
`simplify_river_network_feature_collection()` in
`polaris/tasks/mesh/spherical/unified/river/source.py`. It uses small focused
helpers for canonicalizing segments, validating downstream topology, filtering
outlets, and traversing retained basin structure.

The implementation favors a compact Polaris-native reimplementation over a
direct migration of
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
helper layers. No clear defect emerged from the current unit tests, but this
remains an area where additional comparison against real HydroRIVERS output
would strengthen confidence.

### Implementation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation keeps coastline matching and inland-sink treatment
explicit in both NetCDF and GeoJSON outputs. `river_network.nc` separates
channel cells, all outlet cells, ocean outlets, and inland sinks, and
`river_outlets.geojson` records both source and snapped positions together with
match status and snapping distance.

### Implementation: Standalone River-Network Task

Date last modified: 2026/04/22

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation adds two lightweight task wrappers in
`polaris/tasks/mesh/spherical/unified/river/task.py` and avoids any separate
task-specific river-processing code path. `PrepareRiverNetworkTask` exposes the
shared source step, while `LatLonRiverNetworkTask` exposes the target-grid
workflow and diagnostics for each supported resolution.

## Testing

### Testing and Validation: Downstream-Ready River Network Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The implementation now has unit tests for the source-level and target-grid
product contracts in `tests/mesh/spherical/unified/test_river.py`. These tests
verify that the expected masks and snapped-outlet metadata are written, that
ocean-outlet and inland-sink cases remain distinct, and that named unified-mesh
configs provide the required river options.

`build_sizing_field` now exists and its unit tests consume the target-grid
river masks. There is still not a task-level integration test showing the full
river task output consumed by the sizing-field task output on real data.

### Testing and Validation: Hydrologically Meaningful Simplification

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Current unit tests validate whether major outlets, main stems, and major
tributaries are retained for representative synthetic networks, including deep
main stems and branching cases. They also verify that invalid cyclic
`NEXT_DOWN` graphs are rejected, that duplicate source features can be
converted from HydroRIVERS shapefile data, and that the HydroRIVERS archive
unpack path behaves as expected for a lightweight archive.

What is still missing is validation against real HydroRIVERS subsets to ensure
the present heuristics retain scientifically appropriate networks across
different hydrographic settings.

### Testing and Validation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Current unit tests verify matched and unmatched ocean-outlet behavior, inland-
sink snapping to land cells, derivation of the land mask from `ocean_mask`,
and physical channel-buffering behavior. The visualization step also writes
`river_network_overview.png` and `debug_summary.txt`, which makes outlet
matching diagnostics straightforward to inspect in task runs.

### Testing and Validation: Standalone River-Network Task

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone tasks are now the primary implementation path for inspecting
river simplification and target-grid diagnostics. Unit tests verify that the
source and lat-lon task factories register the expected named-mesh tasks, use
mesh-specific subdirectories, and reuse shared configs and steps.

Standalone smoke tests for each of the 3 supported unified meshes have been
run on Frontier, showing the expected rasterized river networks at each
resolution.  Specific parameter choices still need to be fine-tuned.
