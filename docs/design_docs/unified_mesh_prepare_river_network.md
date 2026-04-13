# River Network Preparation for Unified Base Mesh Workflow

date: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design proposes a shared `prepare_river_network` step and an associated
task that can run that shared step on its own for the unified global
base-mesh workflow. The purpose of the step is to simplify a global river
dataset into products that can be consumed directly by `build_sizing_field`
without re-reading or reinterpreting the raw source data.

The preferred first source is HydroRIVERS or an equivalent global flowline
dataset. Unlike the standalone `mpas_land_mesh` workflow, the Polaris design
should make the downstream interface explicit. In particular, the workflow
should distinguish between the authoritative simplified river network and the
target-grid products needed by `build_sizing_field`, rather than overloading a
single raster with mixed semantics.

Because river-network simplification and river-driven meshing are the parts of
the workflow where Xylar's design intuition is currently weakest, the first Polaris
design should preserve the `mpas_land_mesh` river algorithms as closely as is
practical.

This document intentionally emphasizes requirements and algorithm design more
than implementation or testing. It also assumes that `prepare_river_network`
will be aligned with the shared target-grid tier and coastline interpretation
chosen for the workflow, so that river outlets and coastal refinement can be
made consistent.

Success means that Polaris gains a documented, reusable river-network
preprocessing workflow that preserves the major hydrographic controls relevant
for mesh generation and makes its outputs easy to inspect and easy for
downstream steps to consume.

## Requirements

### Requirement: Downstream-Ready River Network Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_river_network` shall provide products that can be consumed directly by
`build_sizing_field`.

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
`mpas_land_mesh` river-network algorithms rather than redesigning them.

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

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide a task that runs the shared `prepare_river_network` step
and the shared steps it depends on (e.g. `prepare_coastline`).

The standalone task shall make it practical to inspect retained basins,
outlets, and target-grid river products without running the full unified mesh
workflow.

The same shared step and configuration shall be reusable from the full unified
workflow when settings match.

## Algorithm Design

### Algorithm Design: Downstream-Ready River Network Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The step should consume a global river-flowline source together with the shared
coastline products and target-grid tier selected for the workflow. The output
contract should then separate authoritative hydrographic products from the
grid-specific products needed by `build_sizing_field`.

The authoritative hydrographic product should be a simplified vector river
network with attributes such as drainage area, stream segment, stream order,
downstream segment, and outlet type.

That simplified vector product should remain a first-class workflow artifact,
not just an intermediate used to create rasters. In particular, it is needed
both by `build_sizing_field` and by the final mesh step because the first
Polaris design intends to retain the current standalone use of river geometry
to influence cell placement.

For direct use by `build_sizing_field`, the workflow should also produce
target-grid river products on the same regular lon/lat grid used by
`prepare_coastline` and `build_sizing_field`, most likely:

- a river-channel mask;
- a river-outlet mask;
- outlet metadata or outlet points with drainage area and outlet type; and
- optionally other diagnostic rasters such as stream-order or basin IDs if
  they prove useful.

This is intentionally clearer than the current standalone workflow, which uses
one raster and a special outlet value. In Polaris, separate masks should be
preferred so the downstream contract is easy to interpret and extend.

### Algorithm Design: Hydrologically Meaningful Simplification

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The current `mpas_land_mesh` workflow provides a useful starting point. It
uses HydroRIVERS attributes such as `HYRIV_ID`, `MAIN_RIV`, `ORD_STRA`,
`UPLAND_SKM`, `NEXT_DOWN`, and `ENDORHEIC` to identify outlets, build basin
topology, and simplify the network with proximity and drainage-area criteria.

The first Polaris design should preserve that overall logic as directly as is
practical, while documenting it in a clearer staged form. For example:

1. Filter source flowlines by a minimum drainage-area threshold tied to the
   intended river-refinement scale.
2. Identify candidate outlets for both ocean-draining and endorheic basins.
3. Merge or suppress nearby candidate outlets based on a geodesic separation
   tolerance, generally keeping the larger drainage area when two outlets are
   too close.
4. For each retained outlet, reconstruct upstream topology and assign stream
   segments and stream order.
5. Simplify upstream reaches recursively, preserving the main stem and major
   tributaries while dropping small, redundant, or too-close reaches.

The key point is that simplification should be basin-aware and topology-aware.
The Polaris design should preserve connectivity and confluences, not just apply
independent Douglas-Peucker style simplification to each source feature.

The current standalone code uses `pyrivergraph`, R-trees, and drainage-area
ratios to decide when a nearby tributary should still be kept. Because this is
the least well-understood part of the workflow by Polaris developers, Polaris
should preferentially preserve these river-specific algorithms through targeted
extraction or close reimplementation, rather than treating them as the first
place to simplify the overall design.

### Algorithm Design: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The simplified network should not be finalized independently of the coastline
step. Instead, the retained outlets should be checked against the land/ocean
mask and coastline-edge products from `prepare_coastline`.

For basins that drain to the ocean, the outlet should be matched to a
compatible coastline location on the shared target grid. If the river source
and coastline source disagree slightly, the workflow should reconcile them
through a controlled snapping or matching procedure and record the resulting
outlet location and any applied displacement.

Endorheic basins should bypass coastline matching and retain an explicit inland
sink classification. This distinction is important because downstream mesh
refinement may wish to treat inland sinks differently from ocean outlets.

If an ocean-draining outlet cannot be matched to a compatible coastline
location within a configured tolerance, the workflow should flag that basin for
diagnostics rather than silently leaving the inconsistency unresolved.

Once outlet reconciliation is complete, the simplified river network can be
rasterized onto the shared target grid. Rasterization should produce separate
channel and outlet masks rather than a single overloaded integer raster.

### Algorithm Design: Standalone River-Network Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should be a thin wrapper around the shared
`prepare_river_network` step rather than a separate implementation path.

The task will depend on the selected coastline and target-grid products
because outlet reconciliation requires a coastline interpretation. Beyond that,
the standalone task should focus on diagnostics and iteration: comparing
drainage-area thresholds, outlet-separation tolerances, and the resulting
retained basins and outlet masks.

Because the task wraps the shared step, the same simplified river products can
later be reused by `build_sizing_field` and the full unified workflow when
configuration choices match.

## Implementation

### Implementation: Downstream-Ready River Network Products

Date last modified: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

Detailed file naming and class layout should be deferred until the interface is
settled further. The first implementation should prioritize a clean output
contract over carrying forward the standalone workflow's mixed raster
conventions.

The sibling `add-lat-lon-topo-combine` branch already adds the shared lat-lon
`e3sm/init/topo/combine` tasks and `CombineStep` support that underpin the
preferred topo-driven coastline path in this design. That is enabling work
rather than a river-network implementation, but it reduces risk for aligning
outlets with shared target-grid coastline products. See Polaris pull request
<https://github.com/E3SM-Project/polaris/pull/526>.

### Implementation: Hydrologically Meaningful Simplification

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should preserve the basin-aware simplification logic
from `mpas_land_mesh` as directly as is practical while favoring smaller
focused helpers over broad utility-layer migration.

### Implementation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should keep coastline matching and inland-sink
classification explicit in metadata and diagnostics so outlet treatment is easy
to audit.

### Implementation: Standalone River-Network Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should add a lightweight task wrapper around the
shared step and should avoid a separate task-specific code path.

## Testing

### Testing and Validation: Downstream-Ready River Network Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Detailed validation criteria should be added once the implementation plan is
more concrete. The main early check will be that `build_sizing_field` can
consume the shared river products without rerunning source-data processing.

### Testing and Validation: Hydrologically Meaningful Simplification

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should focus on whether major outlets, main stems, and major
tributaries are retained in a way that scales sensibly with the chosen
thresholds.

### Testing and Validation: Coastline-Consistent Outlets and Explicit Inland Sinks

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should make outlet matching diagnostics explicit and should
show that endorheic basins remain distinct from ocean outlets.

### Testing and Validation: Standalone River-Network Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should eventually be validated as the primary place to
inspect river simplification choices before those products are used in the full
unified workflow.
