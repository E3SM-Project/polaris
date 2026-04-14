# Coastline Preparation for Unified Base Mesh Workflow

date: 2026/04/13

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

Date last modified: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

`prepare_coastline` shall provide a shared coastline representation that can
be consumed directly by both `prepare_river_network` and
`build_sizing_field`.

The shared product shall retain both land/ocean classification and coastal
proximity information over the global domain.

The target-grid topography and any coastline-derived sizing inputs shall be
finer than the local destination mesh resolution whenever coastline fidelity
matters, rather than merely matching it. In particular, coarse remapped
topography can produce an unacceptably degraded coastline because of bilinear
interpolation, so a 1-degree product should not be treated as generally
adequate for coastline preparation.

The downstream steps shall not need to reinterpret raw coastline or raw
topography source datasets independently.

### Requirement: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

The preferred coastline definition shall be consistent with the combined
topography interpretation already used by the existing `e3sm/init/topo`
workflow.

The treatment of floating Antarctic ice shall be explicit and reproducible,
rather than being left implicit in overlapping land and ocean masks.

The coastline workflow shall derive an exclusive ocean mask by starting from
the ocean side and flood filling connected ocean regions, so the ocean
interpretation remains contiguous and disconnected depressions are not
misidentified as ocean simply because their remapped topography falls below
sea level.

The coastline workflow shall support multiple explicit Antarctic coastline
definitions within the shared design rather than baking in only the first
consumer's needs.

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

Date last modified: 2026/04/14

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

The target-grid choice should be constrained by coastline fidelity, not only
by downstream convenience. Because the coastline is inferred from remapped
topography, the remapped product and any derived sizing array should be
meaningfully finer than the local destination mesh spacing. A 0.25-degree
product may be adequate for fairly coarse meshes, but it becomes a marginal
choice as the target mesh approaches roughly 30 km. The 1-degree product is
valuable mainly for very coarse mesh workflows such as smoke-test meshes near
240 km, but `prepare_coastline` should support all three shared target-grid
tiers from the lat-lon combine workflow: 1.0, 0.25, and 0.0625 degree.

The shared output contract should remain raster-first. The first design should
assume outputs such as:

- combined topography on the target grid, either as a direct dependency or as
  a shared input artifact, not necessarily a new coastline output;
- one multi-variant coastline product containing exclusive land/ocean masks
  for the supported Antarctic conventions;
- coastline-cell or coastline-edge indicators for those conventions, plus any
  lightweight boundary-sample diagnostics needed by downstream steps; and
- signed coastal-distance fields for those conventions.

With this contract, `prepare_river_network` can use the mask or coastline-edge
information for the convention chosen by workflow config, while
`build_sizing_field` can consume the corresponding signed-distance field
directly.

This approach avoids making a polygonal coastline product part of the public
interface. If temporary contour extraction is ever needed for an internal
experiment, it should not become the required downstream artifact.

### Algorithm Design: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/14

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

The first design should produce three related Antarctic coastline products from
the same remapped topography inputs and mask-building logic:

- `calving_front`, where floating ice is treated as land for coastline
  purposes, so the ocean excludes Antarctic ice-shelf cavities and the
  coastline follows the calving front;
- `grounding_line`, where floating ice is treated as ocean for coastline
  purposes, so the ocean includes Antarctic ice-shelf cavities and the
  coastline follows the grounding line; and
- `bedrock_zero`, where ocean additionally includes grounded Antarctic ice
  below sea level, so the coastline follows the zero contour of bedrock.

These three products should be generated together and cached together rather
than treated as separate future workflow branches. Omega may initially consume
only `calving_front`, but the unified mesh design should preserve the other two
because static cavities, wetting-and-drying, and dynamic grounding-line work
are expected downstream use cases.

The coastline step should expose these variants through one multi-variant
product, and downstream steps should explicitly choose which convention to
consume through workflow configuration. This is expected to align naturally
with different unified-mesh variants, such as meshes that exclude Antarctic
ice-shelf cavities and meshes that include them.

An exclusive ocean mask should not be inferred solely from a local threshold
such as `base_elevation < 0`. Instead, each Antarctic convention should first
define a candidate ocean mask and then perform a flood fill from trusted
ocean-side seed cells to determine the connected ocean region. The first design
should seed from all candidate-ocean cells on the northernmost latitude row.
Cells that are below sea level but disconnected from the global ocean should
remain on the land side of the partition unless a later workflow explicitly
decides otherwise. This flood-fill step is important both in Antarctica and
elsewhere for preserving a contiguous ocean interpretation.

If one default must be chosen early for existing downstream workflows,
`calving_front` appears to be the safer first shared product because it gives a
single land-ocean partition that is more naturally aligned with land and river
outlet logic. However, the standalone task should make it easy to compare that
default with the other two shared products before the full workflow commits to
consumer-specific assumptions.

If the topography-derived coastline proves too noisy, too expensive, or
otherwise unsuitable, a fallback source such as Natural Earth should be
rasterized onto the same target grid and normalized into the same output
contract. In this way, downstream steps can remain agnostic about the
coastline source.

### Algorithm Design: Global Coastal Distance on the Sphere

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The preferred first algorithm is to compute coastal distance directly from the
exclusive raster mask on the periodic lon/lat grid, rather than requiring a
persisted vector geometry product.

The basic formulation should be:

1. For each requested coastline convention, construct a candidate ocean mask
   on the target grid from the remapped topography fields.
2. Flood fill from trusted ocean-side seed cells to obtain an exclusive,
   ocean-connected land/ocean mask.
3. Identify coastline transitions wherever neighboring grid cells switch
   between land and ocean, wrapping in longitude across the antimeridian.
4. Represent each coastline transition by one or more boundary samples located
   on the corresponding grid-cell edges.
5. Convert the boundary samples and all target-grid points to Cartesian
   coordinates on the sphere.
6. Use nearest-neighbor search in Cartesian space to estimate the unsigned
   distance from each grid point to the nearest coastline sample.
7. Apply the sign from the exclusive land/ocean mask.

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

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should add a shared coastline-preparation step that
depends on the shared lat-lon combined-topography steps from the sibling
`add-lat-lon-topo-combine` branch, most likely through a helper such as
`get_lat_lon_topo_steps()` rather than through an ad hoc local remap path.

That enabling branch already provides lat-lon combined-topography tasks and
shared steps at 0.0625, 0.25 and 1.0 degree, with combined outputs including
`base_elevation`, `ice_draft`, `ice_thickness`, `ice_mask`, and
`grounded_mask`. `prepare_coastline` should treat those fields as the
authoritative upstream inputs for the preferred topo-derived path. See Polaris
pull request <https://github.com/E3SM-Project/polaris/pull/526>.

The first implementation should support all three of these target-grid tiers
for coastline preparation. In practice, 1.0 degree is likely to be used only
for very coarse or smoke-test meshes, while 0.25 and 0.0625 degree are the
expected production tiers.

The shared coastline step should produce a multi-variant coastline product with
at least:

- land masks, ocean masks, coastline-cell masks, coastline-edge diagnostics,
  and signed coastal-distance fields for `calving_front`,
  `grounding_line`, and `bedrock_zero`; and
- metadata that records how downstream steps should identify the convention
  they intend to use.

The first implementation should also write lightweight metadata and diagnostic
artifacts that record the selected target-grid tier, selected Antarctic
convention names available in the product, source type, mask thresholds,
flood-fill seed strategy, and sign convention. If boundary samples are
generated for signed distance, the step should consider writing them to a
small diagnostic dataset so `prepare_river_network` can reuse them for outlet
snapping if that proves useful.

### Implementation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should always generate all three Antarctic coastline
products in one run and cache them together for downstream reuse. The
configuration choice should be which convention downstream steps consume from
the multi-variant product, not which convention `prepare_coastline` produces.

The topo-derived path should likely be organized around a small set of
explicit helpers:

1. load the shared combined-topography dataset and normalize its coordinate and
   metadata handling;
2. threshold remapped `ice_mask` and `grounded_mask` fields into binary masks,
   with a configurable threshold whose default is 0.5;
3. build candidate ocean masks for `calving_front`, `grounding_line`, and
   `bedrock_zero`;
4. flood fill from trusted ocean-side seed cells to derive an exclusive,
   ocean-connected ocean mask for each convention;
5. derive complementary land masks and coastline-edge diagnostics; and
6. write all three conventions into one multi-variant output in a form that
   downstream steps can select from explicitly.

The initial candidate-mask definitions should be straightforward and explicit:

- `calving_front`: below sea level and not covered by Antarctic ice;
- `grounding_line`: below sea level and not under grounded Antarctic ice; and
- `bedrock_zero`: below sea level, regardless of Antarctic ice state.

Outside Antarctica, where `ice_mask` is effectively zero, these definitions
reduce to the same open-ocean interpretation.

The flood-fill implementation should operate on the periodic lon/lat grid with
longitude wraparound and explicit treatment of the two latitude boundaries.
The first implementation should seed from candidate-ocean cells on the
northernmost latitude row.

Natural Earth fallback behavior does not need to be finalized in the first
implementation plan. The initial implementation should focus on the
topography-derived path and leave detailed fallback design work until a real
need arises.

The first implementation should write diagnostics that make the mask-building
process auditable. Useful examples include candidate-ocean masks, connected
ocean masks after flood fill, difference masks between Antarctic conventions,
and source-comparison masks when the fallback path is enabled.

### Implementation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should start from the raster land/ocean masks,
identify coastline locations where neighboring cells switch between land and
ocean, and compute spherical distance from each target-grid cell to the
nearest such coastline sample. This should be done before introducing any
custom vector-coastline workflow or custom spherical distance library.

In practice, that implementation should likely:

1. derive coastline transitions directly from the exclusive ocean and land
   masks for each supported convention;
2. emit a coastline-cell mask indicating cells adjacent to a land-ocean
   transition;
3. generate one or more boundary samples on the corresponding cell edges;
4. convert target-grid cell centers and boundary samples to 3D Cartesian
   coordinates on the unit sphere;
5. use a KD-tree or closely related nearest-neighbor method to compute
   unsigned distance; and
6. apply a recorded sign convention, preferably negative over land and
   positive over ocean unless downstream needs suggest the opposite.

The first implementation should generate and cache signed-distance fields for
all three Antarctic conventions so downstream steps can choose the convention
they need through configuration rather than by rerunning the coastline step.

The first implementation should include a `viz` step that runs by default and
writes high-resolution PNG diagnostics focused on the coastline itself rather
than on broader cartographic context. In particular, these plots should avoid
adding continents or other background features that would obscure close
inspection of the coastline. The first required plot set should include:

- three global coastline plots, one each for `calving_front`,
  `grounding_line`, and `bedrock_zero`; and
- three Antarctic stereographic coastline plots, again one for each of the
  three conventions.

### Implementation: Standalone Coastline Task

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should add a lightweight task wrapper around the
shared step and should avoid a separate task-specific code path.

The standalone task should depend on the selected shared lat-lon
combined-topography step and then run the shared coastline step plus a `viz`
step by default.

The `viz` step should write high-resolution PNG plots designed specifically to
inspect the coastline without distracting overlays. The first required plot set
should be:

- a global plot of the `calving_front` coastline;
- a global plot of the `grounding_line` coastline;
- a global plot of the `bedrock_zero` coastline;
- an Antarctic stereographic plot of the `calving_front` coastline;
- an Antarctic stereographic plot of the `grounding_line` coastline; and
- an Antarctic stereographic plot of the `bedrock_zero` coastline.

Additional plots such as land/ocean masks, coastline-cell indicators, or
signed-distance fields may still be useful, but they should be treated as
secondary diagnostics after the six coastline plots above.

This task should be the main place to inspect whether a target-grid tier is
adequate for a given intended mesh resolution before using the product in the
full unified workflow.

## Testing

### Testing and Validation: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first automated tests should verify the public output contract directly.
At a minimum, they should confirm that the multi-variant coastline product
exposes the variables and metadata required by downstream steps, including the
land/ocean masks, coastline-edge diagnostics, signed-distance fields,
available Antarctic conventions, target-grid tier, source type, flood-fill
seed strategy, and mask threshold.

Validation should also compare supported target-grid tiers and confirm that the
chosen remapped topography resolution is sufficiently finer than the intended
mesh resolution to preserve coastline fidelity in the resulting sizing field.
This should likely be done first through manual or baseline diagnostic
comparisons at 0.25 and 0.0625 degree rather than through a brittle numerical
threshold alone.

The first downstream contract checks should confirm that:

- `prepare_river_network` can consume the land/ocean mask and coastline-edge
  diagnostics for a chosen convention without rereading raw topography; and
- `build_sizing_field` can consume the land/ocean mask and signed
  coastal-distance field for a chosen convention without reconstructing
  coastline geometry itself.

### Testing and Validation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first automated tests in this area should be unit tests on synthetic
target-grid datasets rather than full global products. Small synthetic cases
should cover at least:

- a simple non-Antarctic coastline where all conventions agree;
- an Antarctic cavity case where `calving_front` and `grounding_line` differ;
- a grounded-below-sea-level Antarctic case where `grounding_line` and
  `bedrock_zero` differ; and
- a disconnected below-sea-level basin that should remain on the land side
  after flood fill.

Early validation should compare the preferred topography-derived coastline
and should make Antarctic convention differences explicit in diagnostics.

Validation should also confirm that the flood-fill step produces a contiguous
ocean mask for each Antarctic convention and that disconnected below-sea-level
regions do not leak into the ocean classification.

Where practical, synthetic tests should also exercise threshold sensitivity by
perturbing remapped `ice_mask` and `grounded_mask` values around the default
threshold and confirming that the resulting behavior is at least predictable
and metadata-tracked.

### Testing and Validation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The first automated tests should focus on the distance helper functions using
small synthetic masks where expected answers are easy to reason about. At a
minimum, tests should cover:

- a straight coastline on a regular lat-lon grid, where the sign and ordering
  of distances should be obvious;
- a coastline crossing the antimeridian, to confirm that longitude wraparound
  works correctly; and
- a compact island or cavity example, to confirm that boundary sampling works
  sensibly for closed shapes.

Early validation should focus on antimeridian behavior, sign convention, and
whether the raster-based spherical distance is smooth enough to drive mesh
sizing.

For manual or baseline validation on realistic datasets, the signed-distance
field should also be inspected for artifacts such as stair-stepping, isolated
distance spikes, or convention-dependent discontinuities around Antarctica.

### Testing and Validation: Standalone Coastline Task

Date last modified: 2026/04/14

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should eventually be validated as the primary place to
inspect and compare coastline choices before they are used in the full unified
workflow.

The first task-level validation should be a smoke test that confirms the task
can set up shared dependencies and write the expected coastline products and
the default `viz` outputs for at least one supported target-grid tier.

Beyond that smoke test, the task should be used for manual comparison of:

- 1.0, 0.25, and 0.0625 degree coastline fidelity;
- the three Antarctic coastline conventions;
- the resulting global and Antarctic stereographic coastline plots; and
- the resulting signed-distance fields used by downstream sizing.
