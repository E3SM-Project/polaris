# Sizing-Field Construction for Unified Base Mesh Workflow

date: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design proposes a shared `build_sizing_field` step and an associated task
that can run that shared step on its own for the unified global base-mesh
workflow. The purpose of the step is to combine baseline mesh-resolution
choices with coastline and river controls into a single global lon/lat sizing
field that can be passed directly to the final spherical JIGSAW mesh step.

The design assumes that `prepare_coastline` and `prepare_river_network` have
already converted raw source datasets into shared products with explicit
interfaces. `build_sizing_field` should consume those products directly rather
than mixing raw-data interpretation, feature preprocessing, and mesh-sizing
logic in one place.

This document intentionally emphasizes requirements and algorithm design more
than implementation or testing. A key design choice is that feature refinement
should be expressed as clearly as practical in the sizing field itself. For
coastline refinement, this points strongly toward explicit raster candidate
fields. For rivers, the first Polaris design should use the combination of
raster products and direct use of river geometry to guide mesh cell placement
to preserve the meshing behavior in the standalone reference implementation in
`mpas_land_mesh`.

Success means that Polaris gains a documented, reusable sizing-field workflow
whose inputs from earlier steps are clear, whose outputs are directly usable by
the final mesh step, and whose diagnostics make it easy to see why a given
region is refined.

## Requirements

### Requirement: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` shall produce a global sizing field on a regular lon/lat
grid that can be consumed directly by the final spherical mesh-generation
step.

The sizing field shall encode the raster part of the requested spatial
variation in target mesh resolution and shall interoperate cleanly with any
retained feature geometry that the final mesh step uses directly.

### Requirement: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` shall consume the outputs of `prepare_coastline` and
`prepare_river_network` through explicit interfaces.

The sizing-field step shall not need to re-read raw coastline, raw topography,
or raw HydroRIVERS source datasets in the standard workflow.

### Requirement: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow shall support a baseline resolution pattern together with local
refinement controls for coastline and river features.

The first design shall support separate control of at least:

- background ocean resolution;
- background land resolution;
- coastline refinement and transition zones; and
- river-channel and river-outlet refinement.

The design shall allow additional feature classes such as watershed
boundaries, lakes, or dams to be added later without redesigning the full
sizing-field logic.

### Requirement: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The sizing field shall be defined on the same supported target-grid tier used
by the upstream shared preprocessing steps.

The first design shall work with a small discrete set of supported target-grid
resolutions rather than assuming arbitrary default resolutions.

### Requirement: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide a task that runs the shared `build_sizing_field` step
and the shared steps it depends on (e.g. `prepare_coastline` and
`prepare_river_network`).

The standalone task shall make it practical to inspect candidate refinement
fields and the final sizing field without running the full unified mesh
workflow.

The same shared step and configuration shall be reusable from the full unified
workflow when settings match.

## Algorithm Design

### Algorithm Design: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The sizing field should be built on a regular lon/lat grid using the shared
target-grid tier selected for the workflow. The resulting field should be in
the same basic form already expected by Polaris spherical mesh generation:
`cellWidth(lat, lon)` or an equivalent gridded `h(x)` product.

The output should therefore be a directly inspectable and cacheable artifact
rather than an implicit side effect of JIGSAW geometry handling. This makes
the final `unified_base_mesh` step simpler because it only needs to consume the
finished sizing field and convert it into a JIGSAW mesh and then an MPAS mesh.

### Algorithm Design: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The intended input contract should be explicit:

- from `prepare_coastline`: a land/ocean mask on the selected target grid and
  a signed coastal-distance field, together with any needed coastline-edge
  diagnostics; and
- from `prepare_river_network`: a simplified vector river network suitable for
  downstream geometry use, plus target-grid river-channel and river-outlet
  masks, together with outlet metadata.

With this contract, `build_sizing_field` can focus on mesh-resolution logic
rather than source-data interpretation.

The first design should avoid making `prepare_river_network` responsible for
the full river-refinement policy. If `build_sizing_field` needs a river
distance field, it can derive that distance from the simplified river products
it consumes. At the same time, the first Polaris design should explicitly
retain the existing standalone use of river geometry in the final mesh step.

### Algorithm Design: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first sizing-field algorithm should be framed as a set of candidate fields
combined into a final mesh-spacing field.

The background field should be constructed first. A reasonable first design is
to use the land/ocean mask from `prepare_coastline` to choose between:

- an ocean background, which may be constant or may reuse existing Polaris
  latitude-dependent functions such as `EC_CellWidthVsLat()` or
  `RRS_CellWidthVsLat()`; and
- a land background, which may be constant at first.

Feature refinement should then be expressed as additional candidate fields:

- a coastline candidate derived from the signed coastal-distance field, with
  configurable transition widths and potentially different treatment on the
  land and ocean sides;
- a river candidate derived from distance to the simplified river-channel
  network or, in the simplest first pass, from the channel mask itself; and
- an outlet candidate derived from the river-outlet mask, since outlets may
  merit stronger or separate refinement.

The final sizing field should be the pointwise minimum of the background field
and all active feature candidates. This is a clearer design than sequential
overwrites because it makes each contribution explicit and guarantees that
adding a new feature control cannot accidentally coarsen the mesh.

For coastline refinement, this is also where the Polaris design can diverge
most clearly from the current standalone workflow by favoring explicit raster
candidate fields. For rivers, however, the first Polaris design should be more
conservative. In `mpas_land_mesh`, river influence is split between raster
products and separate geometry handling. Because that behavior is the least
well-understood part of the workflow, Polaris should preserve that division of
labor as much as practical in the early implementation.

In that formulation, `build_sizing_field` still owns the raster candidate
fields associated with rivers and outlets, and the final
`unified_base_mesh` step should additionally pass the simplified river
geometry to JIGSAW to preserve existing cell-placement behavior.

If abrupt changes remain after candidate-field composition, the first design
may include a light regularization or smoothing stage, but that should be a
small post-processing step on the final field, not a substitute for clear
feature definitions.

### Algorithm Design: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` should not choose its own grid resolution independently.
Instead, it should consume the selected workflow target-grid tier and produce
its output on that same grid.

The first design should therefore support a small discrete set of target-grid
tiers shared with `prepare_coastline` and `prepare_river_network`. This keeps
the interfaces between stages simple and makes cached reuse of expensive
preprocessing products practical.

### Algorithm Design: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should be a thin wrapper around the shared
`build_sizing_field` step rather than a separate implementation path.

The task should depend on the selected coastline and river products and should
write diagnostics that make the sizing-field composition easy to inspect, for
example the background field, coastline candidate, river candidate, outlet
candidate, and final field.

Because the task wraps the shared step, the same sizing-field products can
later be reused by the final mesh step and the full unified workflow when
configuration choices match.

## Implementation

### Implementation: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Detailed file naming and class layout should be deferred until the algorithmic
contract is settled further. The first implementation should prioritize a
clear gridded output that can be inspected independently of the final mesh
step.

### Implementation: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should keep step interfaces explicit and should avoid
reintroducing raw-dataset dependencies inside `build_sizing_field`.

### Implementation: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should write intermediate diagnostic fields whenever
practical so the effect of each refinement control can be inspected
independently.

### Implementation: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should use the shared target-grid tier directly in
file naming, work-directory layout, and cache keys so reuse across tasks is
predictable.

### Implementation: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should add a lightweight task wrapper around the
shared step and should avoid a separate task-specific code path.

## Testing

### Testing and Validation: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Detailed validation criteria should be added once the implementation plan is
more concrete. The main early check will be that the final mesh step can
consume the sizing field directly.

### Testing and Validation: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should show that `build_sizing_field` can run entirely from
shared preprocessing products without rereading raw topography or HydroRIVERS
inputs.

### Testing and Validation: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should focus on whether coastline, river-channel, and outlet
controls influence the sizing field in the intended locations and with the
intended relative strengths.

### Testing and Validation: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should confirm that the supported target-grid tiers produce
consistent dimensions and are reused correctly by dependent steps.

### Testing and Validation: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should eventually be validated as the primary place to
inspect the component refinement fields and the final sizing field before they
are used in the full unified workflow.
