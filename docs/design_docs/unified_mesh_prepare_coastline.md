# Coastline Preparation for Unified Base Mesh Workflow

date: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design proposes a shared `prepare_coastline` step and an associated task
that can run that shared step on its own for the unified global base-mesh
workflow. The purpose of the step is to create a single coastline
interpretation that downstream steps can reuse, especially
`prepare_river_network` and `build_sizing_field`.

The preferred first source for coastline information is the combined
topography already used in `e3sm/init/topo`, because that gives the strongest
consistency with downstream topography remapping and culling. The resulting
coastline products should be defined on the same regular lon/lat grid that
`build_sizing_field` will consume.

This document intentionally emphasizes requirements and algorithm design more
than implementation or testing. A key design choice is to keep the shared
coastline interface raster-first if possible. In particular, the public output
contract should prefer target-grid masks and coastal-distance fields over a
persisted polygonal coastline product. If temporary contour extraction is ever
needed internally, it should remain an implementation detail rather than the
main workflow artifact.

Success means that Polaris gains a documented, reusable coastline-preparation
workflow whose outputs can be consumed directly by downstream steps and whose
standalone task makes it practical to inspect and iterate on coastline choices
without running the full unified mesh workflow.

## Requirements

### Requirement: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_coastline` shall provide a shared coastline representation that can
be consumed directly by both `prepare_river_network` and
`build_sizing_field`.

The shared product shall retain both land/ocean classification and coastal
proximity information over the global domain.

The downstream steps shall not need to reinterpret raw coastline or raw
topography source datasets independently.

### Requirement: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The preferred coastline definition shall be consistent with the combined
topography interpretation already used by the existing `e3sm/init/topo`
workflow.

The treatment of floating Antarctic ice shall be explicit and reproducible,
rather than being left implicit in overlapping land and ocean masks.

If the topography-derived coastline proves unsuitable for some workflows, the
design shall allow an alternate source such as Natural Earth without changing
the downstream interface.

### Requirement: Global Coastal Distance on the Sphere

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The coastline product shall support smooth coastal transition zones for mesh
sizing on the sphere, including across the antimeridian.

The coastal-distance definition shall be suitable for the regular lon/lat grid
used by `build_sizing_field`.

The first design shall avoid assuming that planar buffering or planar
Euclidean distance is adequate on a periodic global grid.

### Requirement: Standalone Coastline Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide a task that runs the shared `prepare_coastline` step and
the shared steps it depends on (e.g. `e3sm/init/topo/combine`).

The standalone task shall make it practical to inspect coastline outputs and
compare coastline options without running the full unified mesh workflow.

The same shared step and configuration shall be reusable from the full unified
workflow when settings match.

## Algorithm Design

### Algorithm Design: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The authoritative coastline products should be defined on the same regular
lon/lat grid that `build_sizing_field` will use. This implies that target-grid
selection should happen once in shared configuration, not independently inside
each downstream step.

The preferred upstream source is the existing `e3sm/init/topo/combine`
workflow, because `CombineStep` already supports `target_grid = lat_lon`.
Rather than inventing a separate remap path, the coastline workflow should
reuse that capability to obtain combined topography on the target grid.

The shared output contract should remain raster-first. The first design should
assume outputs such as:

- combined topography on the target grid, either as a direct dependency or as
  a shared input artifact, not necessarily a new coastline output;
- an exclusive land/ocean mask on that grid;
- a coastline-edge indicator on that grid or its cell edges; and
- a signed coastal-distance field on that grid.

With this contract, `prepare_river_network` can use the mask or coastline-edge
information for outlet and coastline-consistency checks, while
`build_sizing_field` can consume the signed-distance field directly.

This approach avoids making a polygonal coastline product part of the public
interface. If temporary contour extraction is ever needed for an internal
experiment, it should not become the required downstream artifact.

### Algorithm Design: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The preferred coastline definition should start from the combined topography
fields already used downstream, especially `base_elevation`, `ice_mask`, and
`grounded_mask`.

Outside Antarctica, or more generally where floating ice is absent, the coast
can be interpreted as the zero contour of `base_elevation` after remapping to
the target lon/lat grid.

Around Antarctica, the existing topography masking logic does not define a
single exclusive coastline by itself because floating ice contributes to the
land interpretation while the water below it may still contribute to the ocean
interpretation. The coastline workflow should therefore define an explicit
Antarctic convention instead of inheriting that ambiguity.

The first design should allow at least two Antarctic conventions:

- `calving_front`, where floating ice is treated as land for coastline
  purposes, so the coastline follows the seaward edge of ice shelves; and
- `grounding_line`, where floating ice is treated as ocean for coastline
  purposes, so the coastline follows the grounding line.

If one default must be chosen early, `calving_front` appears to be the safer
first choice for a shared coastline product because it gives a single
land-ocean partition that is more naturally aligned with land and river outlet
logic. However, the standalone task should make it easy to compare that choice
with `grounding_line` before the full workflow commits to one default.

If the topography-derived coastline proves too noisy, too expensive, or
otherwise unsuitable, a fallback source such as Natural Earth should be
rasterized onto the same target grid and normalized into the same output
contract. In this way, downstream steps can remain agnostic about the
coastline source.

### Algorithm Design: Global Coastal Distance on the Sphere

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The preferred first algorithm is to compute coastal distance directly from the
exclusive raster mask on the periodic lon/lat grid, rather than requiring a
persisted vector geometry product.

The basic formulation should be:

1. Construct an exclusive land/ocean mask on the target grid using the chosen
   coastline convention.
2. Identify coastline transitions wherever neighboring grid cells switch
   between land and ocean, wrapping in longitude across the antimeridian.
3. Represent each coastline transition by one or more boundary samples located
   on the corresponding grid-cell edges.
4. Convert the boundary samples and all target-grid points to Cartesian
   coordinates on the sphere.
5. Use nearest-neighbor search in Cartesian space to estimate the unsigned
   distance from each grid point to the nearest coastline sample.
6. Apply the sign from the exclusive land/ocean mask.

This formulation has two advantages for the present design. First, it keeps
the public interface raster-based. Second, it turns antimeridian handling into
a periodic-neighbor problem on the target grid rather than a vector-topology
problem.

The initial distance estimate can follow the same boundary-sample and KD-tree
style already used in `mpas_tools.mesh.creation.signed_distance`, but with the
boundary samples extracted from raster coastline transitions instead of from
vector geometry. If later testing shows that this approximation is too noisy
or too inaccurate, we can refine the boundary sampling or temporarily extract
contours internally without changing the external workflow contract.

The sign convention should be recorded explicitly. For example, the workflow
can define negative distance over land and positive distance over ocean, or the
reverse, as long as `build_sizing_field` interprets it consistently.

### Algorithm Design: Standalone Coastline Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should be a thin wrapper around the shared
`prepare_coastline` step rather than a separate implementation path.

The task will likely depend on a shared target-grid topography product, ideally
reused from the existing `combine_topo` capability on a lat/lon grid. From
there, the task can run the shared coastline step and any lightweight
diagnostic or visualization steps that prove useful.

This standalone task is important for design iteration. It provides a place to
compare topography-derived and fallback coastlines, to compare Antarctic
conventions, and to inspect the target-grid mask and signed-distance products
without also running river preprocessing, sizing-field construction, or mesh
generation.

Because the task wraps the shared step, the same outputs can later be reused
by the full unified workflow when configuration choices match.

## Implementation

### Implementation: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Detailed class layout, file naming, and output caching strategy should be
deferred until the requirements and algorithm design settle further. The first
implementation should favor a small raster-based output contract over a broad
set of derived artifacts.

### Implementation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should keep the Antarctic convention configurable and
record the chosen convention in output metadata. A fallback coastline source
should be normalized into the same raster-based interface as the preferred
topography-derived path.

### Implementation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should prototype raster-boundary sampling and
spherical nearest-neighbor distance before introducing any custom vector
workflow or custom spherical distance library.

### Implementation: Standalone Coastline Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should add a lightweight task wrapper around the
shared step and should avoid a separate task-specific code path.

## Testing

### Testing and Validation: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Detailed validation criteria should be added once the implementation plan is
more concrete. The main early check will be that downstream steps can consume
the shared coastline outputs without reinterpreting source data.

### Testing and Validation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should compare the preferred topography-derived coastline
against fallback products and should make Antarctic convention differences
explicit in diagnostics.

### Testing and Validation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Early validation should focus on antimeridian behavior, sign convention, and
whether the raster-based spherical distance is smooth enough to drive mesh
sizing.

### Testing and Validation: Standalone Coastline Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should eventually be validated as the primary place to
inspect and compare coastline choices before they are used in the full unified
workflow.
