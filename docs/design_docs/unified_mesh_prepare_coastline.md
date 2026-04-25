# Coastline Preparation for Unified Base Mesh Workflow

date: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design describes the shared `prepare_coastline` step and an associated
task that can run that shared step on its own for the unified global base-mesh
workflow. The purpose of the step is to create a single coastline
interpretation that downstream steps can reuse, especially
`prepare_river_network` and `build_sizing_field`.

The implementation is being added on the `add-prepare-coastline` branch in
Polaris pull request <https://github.com/E3SM-Project/polaris/pull/545>.

The preferred first source for coastline information is the combined
topography already used in `e3sm/init/topo`, because that gives the strongest
consistency with downstream topography remapping and culling. The resulting
coastline products should be defined on the same regular lon/lat grid that
`build_sizing_field` will consume.

The implementation keeps the shared coastline interface raster-first. In
particular, the public output contract uses target-grid masks and
coastal-distance fields rather than a persisted polygonal coastline product.
If temporary contour extraction is ever needed internally, it should remain an
implementation detail rather than the main workflow artifact.

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

Date last modified: 2026/04/25

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

The coastline workflow shall support critical ocean passages and critical land
blockages that are applied before flood fill. Critical passages are needed to
keep semi-enclosed seas such as the Mediterranean connected to the ocean
domain when the remapped topography would otherwise close them; critical land
blockages are needed to close known artificial openings that should remain
land for the selected coastline interpretation.

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
product is useful as a cheaper inspection tier, but testing shows it is too
coarse for scientifically valid coastline preparation because semi-enclosed
basins such as the Mediterranean can disappear. The 1-degree product is
valuable mainly for very coarse mesh workflows such as smoke-test meshes near
240 km, but `prepare_coastline` should support four coastline target-grid
tiers: 0.25, 0.125, 0.0625, and 0.03125 degree. The shared lat-lon combine
workflow should support those same four resolutions plus the 1.0-degree
smoke-test tier.

The shared output contract should remain raster-first. The first design should
assume outputs such as:

- combined topography on the target grid, either as a direct dependency or as
  a shared input artifact, not necessarily a new coastline output;
- one convention-specific coastline product per supported Antarctic
  convention, each containing exclusive land/ocean masks on the shared target
  grid;
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

Date last modified: 2026/04/25

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

The coastline step should expose these variants through separate but
simultaneously generated products, and downstream steps should explicitly
choose which convention to consume through workflow configuration. This is
expected to align naturally with different unified-mesh variants, such as
meshes that exclude Antarctic ice-shelf cavities and meshes that include them.

An exclusive ocean mask should not be inferred solely from a local threshold
such as `base_elevation < 0`. Instead, each Antarctic convention should first
define a candidate ocean mask and then perform a flood fill from trusted
ocean-side seed cells to determine the connected ocean region. Before flood
fill, default critical transects from `geometric_features` should be
rasterized onto the target grid. Transects tagged as critical land blockages
remove cells from the candidate ocean mask, while transects tagged as critical
passages add cells to it. This gives the flood fill enough connectivity
information to include major semi-enclosed seas and enough blockage
information to prevent known false ocean connections.

The first design should seed from all candidate-ocean cells on the
northernmost latitude row. Cells that are below sea level but disconnected
from the global ocean should remain on the land side of the partition unless a
later workflow explicitly decides otherwise. This flood-fill step is important
both in Antarctica and elsewhere for preserving a contiguous ocean
interpretation.

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

Date last modified: 2026/04/18

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation adds a shared coastline-preparation workflow in
`polaris.tasks.mesh.spherical.unified.coastline` and reuses the shared lat-lon
combined-topography steps through `get_lat_lon_topo_steps()` rather than
adding a separate remap path.

That enabling work was already put in place on the sibling
`add-lat-lon-topo-combine` branch, which added shared lat-lon combined-
topography tasks and steps at 1.0, 0.25, 0.125, 0.0625, and 0.03125 degree,
with combined outputs including `base_elevation`, `ice_draft`,
`ice_thickness`, `ice_mask`, and `grounded_mask`. `prepare_coastline` now
treats those shared lat-lon topography products as the authoritative upstream
inputs for the preferred topo-derived path. See Polaris pull request
<https://github.com/E3SM-Project/polaris/pull/526>.

The implemented coastline workflow in the current branch supports those same
four coastline target-grid tiers other than the 1.0-degree smoke-test
product. Standalone coastline tasks exist for 0.25, 0.125, 0.0625, and
0.03125 degree. The expected usage is that 0.25 degree remains the cheaper
inspection tier, while 0.125, 0.0625, and 0.03125 degree are the scientifically
credible coastline tiers. See Polaris pull request
<https://github.com/E3SM-Project/polaris/pull/545>.

The shared coastline step writes one convention-specific NetCDF file for each
of `calving_front`, `grounding_line`, and `bedrock_zero`. Each file currently
contains:

- `ocean_mask` and `signed_distance`; and
- metadata including the coastline convention, target-grid type and
  resolution, source type, mask threshold, sea-level threshold, flood-fill
  seed strategy, sign convention, and text descriptions of the coastline-edge
  and distance definitions.

The current implementation also records the source combined-topography file
and source step in the output attributes. This satisfies part of the intended
lightweight metadata and diagnostics contract for recording the selected
target-grid tier, source type, mask thresholds, flood-fill seed strategy, and
sign convention. The implementation still does not write boundary samples as a
public product, so any later reuse of those samples by
`prepare_river_network` remains future work.

The implemented source path is only the topo-derived one so far. A Natural
Earth fallback has not been added yet.

### Implementation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/18

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation always generates all three Antarctic coastline
products in one run and writes them as separate files that downstream steps
can select from explicitly.

The implemented topo-derived path is organized around the following concrete
operations:

1. read `base_elevation`, `ice_mask`, and `grounded_mask` from the shared
  combined-topography dataset on the target lat-lon grid;
2. threshold the remapped `ice_mask` and `grounded_mask` arrays with the
  configurable `mask_threshold` option, whose default is 0.5;
3. build candidate ocean masks for `calving_front`, `grounding_line`, and
  `bedrock_zero`;
4. label connected candidate-ocean regions, merge labels that wrap across the
  eastern and western grid edges, and keep only regions connected to the
  northernmost latitude row;
5. optionally rasterize critical land blockages and passages from
   `geometric_features` and apply them to the candidate ocean masks before
   flood fill;
6. derive the transient coastline-edge diagnostics needed for signed-distance
   sampling; and
7. write one output file per convention.

The current candidate-mask definitions are:

- `calving_front`: below sea level and not covered by ice;
- `grounding_line`: below sea level and not covered by grounded ice; and
- `bedrock_zero`: below sea level, regardless of ice state.

Outside Antarctica, where `ice_mask` and `grounded_mask` are effectively zero,
the three candidate masks reduce to the same open-ocean interpretation.

The implemented workflow still does not include a Natural Earth fallback. It
does, however, write diagnostics that make the mask-building process auditable
through the `viz` step, including final ocean-mask and signed-distance plots
for each convention.

The default configuration sets `include_critical_transects = True`, so the
shared critical land blockages and passages are included in normal task runs.

### Implementation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/18

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation starts from the raster land/ocean masks, identifies
coastline locations where neighboring cells switch between land and ocean, and
computes spherical distance from each target-grid cell to the nearest such
coastline sample without introducing a persisted vector coastline product.

In practice, the implemented workflow:

1. derives coastline transitions directly from the exclusive ocean masks;
2. builds transient east-edge and north-edge coastline diagnostics;
3. places coastline samples at east-edge angular midpoints and north-edge
  latitudinal midpoints;
4. converts target-grid cell centers and coastline samples to Cartesian
  coordinates on the sphere;
5. uses `scipy.spatial.cKDTree` to compute nearest-sample chord distances,
  then converts those to spherical arc distance; and
6. applies the sign convention of negative over land and positive over ocean.

Signed-distance fields are currently generated for all three conventions in
every run.

The implemented `viz` step writes global and Antarctic binary plots of the
final `ocean_mask`, signed-distance plots for each convention, and
`debug_summary.txt`.

The same rasterization machinery used for critical passages and land blockages
handles diagonal paths as four-connected raster paths and treats longitude as
periodic across the antimeridian.

### Implementation: Standalone Coastline Task

Date last modified: 2026/04/18

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation adds a lightweight task wrapper around the shared
steps and does not introduce a separate task-specific coastline algorithm.

`LatLonCoastlineTask` depends on the selected shared lat-lon combined-
topography step and then adds the shared coastline step plus the shared `viz`
step with `include_viz=True`. The shared-step helper for this path is
`get_lat_lon_coastline_steps()`.

The standalone task subdirectories are currently:

- `spherical/unified/coastline/lat_lon/0.25000_degree/task`
- `spherical/unified/coastline/lat_lon/0.12500_degree/task`
- `spherical/unified/coastline/lat_lon/0.06250_degree/task`
- `spherical/unified/coastline/lat_lon/0.03125_degree/task`

Each task links the shared `coastline.cfg` file and exposes the `combine_topo`,
`prepare`, and `viz` step directories within the task work directory.

The task is therefore the current place to inspect whether a target-grid tier
is adequate for a given intended mesh resolution before using the product in a
later unified workflow.

## Testing

### Testing and Validation: Raster-First Coastline Products for Downstream Steps

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Automated tests now verify the public output contract at the dataset-builder
level. In `tests/mesh/spherical/unified/test_coastline.py`, the current
coverage confirms that the convention-specific coastline products expose the
expected variables,
that the conventions are returned together in the expected order, and that the
output metadata records items such as the coastline convention and flood-fill
seed strategy.

There is not yet automated validation that compares different target-grid
tiers. Downstream contract coverage now exists at the unit-test level in the
river and sizing-field tests, but there is not yet a task-level integration
test that runs the full coastline-to-river-to-sizing-field chain.

### Testing and Validation: Topography-Consistent and Explicit Coastline Definition

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The current automated tests in this area are unit tests on synthetic target-
grid datasets rather than full global products.

Those tests currently cover:

- a case where `calving_front`, `grounding_line`, and `bedrock_zero` differ in
  Antarctica;
- a disconnected below-sea-level basin that remains on the land side after
  flood fill; and
- a case confirming that the northernmost latitude row is used for flood-fill
  seeding even when latitude values are ordered south to north;
- a critical land blockage that closes a narrow ocean connection; and
- a critical passage that connects an otherwise disconnected ocean region.

The current tests do not yet include dedicated threshold-sensitivity cases or
full-resolution comparisons against realistic global datasets.

### Testing and Validation: Global Coastal Distance on the Sphere

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The current automated coverage checks the signed-distance field indirectly in
synthetic dataset tests. Existing assertions confirm that the field is finite
for the tested cases and that the sign matches the intended convention of
negative over land and positive over ocean.

There is an antimeridian-specific automated test for critical-transect
rasterization, but not yet for the signed-distance field itself. There is also
not yet a task-level baseline that checks the smoothness of the signed-distance
field on realistic global products. Manual inspection is still needed for
those cases.

### Testing and Validation: Standalone Coastline Task

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task is the intended place to inspect and compare coastline
choices before they are used in a later unified workflow, but there is not yet
an automated task-level smoke test for it.

A test has been performed on Frontier, showing the expected behavior:

- comparing 0.25, 0.125, 0.0625, and 0.03125 degree coastline fidelity;
- comparing the three Antarctic coastline conventions;
- inspecting the global and Antarctic coastline and signed-distance plots; and
- reviewing `debug_summary.txt` for ocean-mask counts and signed-distance
  ranges.
