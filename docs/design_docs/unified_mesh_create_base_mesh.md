# Unified Mesh: Base-Mesh Creation and Downstream Integration

date: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design describes the shared final `create_base_mesh` step for the
unified global mesh workflow, the standalone tasks that run that step for each
named unified mesh, and the downstream workflow variants that consume the new
base meshes for topography remapping and mesh culling.

The [`add-build-sizing-field`](https://github.com/E3SM-Project/polaris/pull/561)
branch already includes implementations of the shared `prepare_coastline`,
`prepare_river_network`, and `build_sizing_field` stages. It also adds
`UnifiedCellWidthMeshStep`, which can already read `sizing_field.nc` and hand
that raster cell-width field to the existing spherical JIGSAW machinery. What
remains is the final stage that turns those shared products into complete
unified MPAS base meshes, adds the required direct use of retained river
geometry during final mesh generation, and hooks those meshes into downstream
E3SM workflows.

The first implementation should provide standalone base-mesh tasks for the
three currently defined named unified meshes in
`polaris.mesh.spherical.unified`, all of which currently use the
`calving_front` Antarctic coastline convention. At the same time, the shared
infrastructure should remain compatible with any supported coastline
convention, even if only `calving_front` is exercised in the first automated
tests.

Success means that Polaris can create each current unified base mesh as a
standard MPAS mesh, inspect the result together with the input sizing field
and retained river geometry, and pass the produced mesh directly into explicit
downstream topography-remap and land or ocean culling task variants without
an ad hoc conversion stage.

## Workflow Context

The overall unified-mesh workflow is described in
[Unified Mesh: Global Base Mesh Workflow](unified_base_mesh.md).

The upstream unified-mesh workflow designs are:

- [Unified Mesh: Coastline Preparation](unified_mesh_prepare_coastline.md)
- [Unified Mesh: River Network Preparation](unified_mesh_prepare_river_network.md)
- [Unified Mesh: Sizing-Field Construction](unified_mesh_build_sizing_field.md)

There are no later stage-specific unified-mesh design documents downstream of
this one in the current series. This document itself covers the final
base-mesh stage together with downstream remap and culling integration.

## Requirements

### Requirement: Final JIGSAW-to-MPAS Unified Base Mesh

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall support a final unified-mesh stage that creates a global,
spherical MPAS base mesh from the shared unified-mesh products.

The primary output of that stage shall be a standard MPAS base mesh that can
be consumed directly by existing MPAS and E3SM tooling.

The final stage shall preserve the spatially varying resolution described by
the unified sizing field.

### Requirement: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The final base-mesh stage shall consume the outputs of `build_sizing_field`
and `prepare_river_network` through explicit shared interfaces.

The standard workflow shall not need to re-read or reinterpret raw topography,
raw coastline, or raw HydroRIVERS source datasets inside the final mesh
generation stage.

The downstream remap and culling workflow variants shall likewise consume the
resulting MPAS base mesh through explicit task interfaces rather than through
manual work-directory edits.

### Requirement: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Retained river geometry shall influence final mesh generation directly rather
than only through the raster sizing field.

The requirement is on the resulting behavior, namely that final cell placement
can reflect the retained river network, especially along important channels and
near outlets.

The design shall not require one particular mechanism for applying that
geometry, as long as the retained river geometry has a direct influence on the
final mesh-generation process.

### Requirement: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide one shared final base-mesh step that can be reused by
multiple workflows.

Polaris shall also provide one standalone task per named unified mesh defined
by the config files in `polaris.mesh.spherical.unified`.

The first implementation shall cover the three currently defined named meshes.
The shared design shall remain compatible with additional named meshes and with
supported Antarctic coastline conventions without requiring a different code
path for each one.

The standalone tasks shall run the shared final step together with the shared
prerequisite steps they depend on.

### Requirement: Standalone Visualization for Mesh and Inputs

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone unified base-mesh task shall include a visualization step that
makes it practical to inspect the generated mesh together with the main inputs
that controlled it.

At a minimum, the standalone visualization shall show the final MPAS mesh, the
input lat-lon sizing field, and the retained river geometry.

That visualization step shall run in the standalone base-mesh task but shall
not run by default in other workflows that reuse the shared final step.

### Requirement: Downstream Remap and Culling Variants for Unified Meshes

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide explicit downstream workflow variants that use each
unified base mesh as input to topography remapping and mesh culling.

These downstream variants shall cover remapped topography on the unified base
mesh, land and ocean masks on that base mesh, and the resulting culled land
and ocean meshes.

The downstream variants shall be expressed as standard Polaris tasks rather
than as manual follow-on instructions.

## Algorithm Design

### Algorithm Design: Final JIGSAW-to-MPAS Unified Base Mesh

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The sizing-field stage already defines the main raster contract for the final
mesh stage: a regular lon/lat `cellWidth` field in `sizing_field.nc`. The
final mesh stage should treat that product as the authoritative raster spacing
input and should reuse the existing Polaris spherical-mesh path for converting
JIGSAW output into a standard MPAS mesh.

In other words, the final stage should add only the logic that is truly new to
the unified workflow: consuming the shared products, incorporating retained
river geometry into final mesh generation, and wiring the result into
standalone and downstream tasks. It should not redesign the existing
JIGSAW-to-MPAS conversion path already present in `SphericalBaseStep` and
`QuasiUniformSphericalMeshStep`.

### Algorithm Design: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The intended final-stage input contract is:

- `sizing_field.nc` from `build_sizing_field` as the authoritative raster
  spacing field;
- retained vector river geometry and outlet metadata from
  `prepare_river_network` for direct final-stage geometry use and for
  visualization; and
- the named unified-mesh configuration, including the selected target-grid
  tier and Antarctic coastline convention, for consistent downstream labeling
  and task selection.

The final stage should not go back to raw source data to infer these products
again. That keeps the workflow layered in the same way as the earlier design
documents: source interpretation belongs in shared preprocessing steps, sizing
policy belongs in `build_sizing_field`, and final mesh generation belongs in
`create_base_mesh`.

The downstream topography-remap and culling variants should then consume the
generated `base_mesh.nc` through the same standard interfaces used by existing
Polaris `e3sm/init` workflows. The design should favor task composition over
special one-off scripts.

### Algorithm Design: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The key extra requirement beyond the current branch state is that retained
river geometry must influence final mesh generation directly. The sizing field
already expresses raster refinement around rivers and outlets, but the
standalone reference workflow suggests that raster refinement alone is not the
whole story when the goal is to place cell centers well along river channels.

The design should therefore keep two distinct river signals in the final mesh
stage:

- a raster resolution signal from `build_sizing_field`; and
- a vector geometry signal from the retained river network.

How those signals are combined should remain flexible. Plausible mechanisms
include explicit JIGSAW geometry constraints, river-centered attractors or
guides, or another approach that causes vertices or cell centers to align more
closely with retained river flowlines. For the first Polaris implementation,
the design should closely match the algorithmic approach used by the standalone
reference solution in
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
for using river-network geometry to place cell centers. We do not require a
byte-for-byte match to the standalone implementation, but we do want to
preserve that reference workflow's basic geometry-driven approach rather than
replace it with an unrelated first-cut method.

Because outlet regions are especially sensitive, the geometry path should also
leave room for stronger treatment near retained outlets than along the generic
channel network if later tuning shows that is needed.

### Algorithm Design: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The final stage should follow the same pattern as the new coastline, river,
and sizing-field stages: one shared implementation plus thin standalone task
wrappers.

The shared step should be parameterized by the named unified-mesh config. The
code that registers standalone tasks should iterate over the named mesh configs in
`polaris.mesh.spherical.unified` and register one standalone task per mesh.
With the current configs, that means one standalone task each for:

- `ocn_240km_lnd_240km_riv_240km`;
- `ocn_30km_lnd_10km_riv_10km`; and
- `ocn_rrs_6to18km_lnd_12km_riv_6km`.

Each standalone task should compose the shared prerequisite steps in the same
workflow instance: coastline preparation, river-network preparation,
sizing-field construction, final mesh creation, and standalone visualization.
The design should still permit other workflows to reuse the shared final step
without paying the cost of standalone diagnostics by default.

### Algorithm Design: Standalone Visualization for Mesh and Inputs

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone visualization step should combine the most important views that
would otherwise require multiple task families to inspect together.

At a minimum, the visualization should include:

- the generated MPAS mesh, preferably in a way that makes local resolution and
  feature alignment easy to see;
- the input sizing field on its lat-lon grid, because the sizing-field
  workflow's own visualization may not be run in the same work directory; and
- the retained river geometry overlaid with the mesh or with a closely related
  diagnostic view.

The step may also include coastline or mask diagnostics, but those are not the
core requirement for this design because the dedicated coastline workflow
already covers them. The important point is that the final-stage standalone
task must make it possible to see both the requested raster resolution pattern
and the realized mesh in one place.

### Algorithm Design: Downstream Remap and Culling Variants for Unified Meshes

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Once a unified base mesh exists as a standard MPAS mesh, the next workflow
steps are conceptually straightforward. The design should therefore treat them
as part of the same planned capability even if they are implemented as
separate task families.

For each named unified mesh, Polaris should provide downstream task variants
that:

- remap topography to the new base mesh;
- derive land and ocean masks on that base mesh using the selected coastline
  interpretation; and
- produce culled land and ocean meshes.

These downstream variants should reuse as much of the existing `e3sm/init`
task machinery as practical. Their main new responsibility should be to wire in
the unified base mesh and any mesh-specific configuration, not to reimplement
topography remapping or culling algorithms.

## Implementation

### Implementation: Final JIGSAW-to-MPAS Unified Base Mesh

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The current branch already contains a useful starting point in
`polaris.mesh.spherical.unified.cell_width.UnifiedCellWidthMeshStep`. That
class reads `cellWidth`, `lat`, and `lon` from `sizing_field.nc` and reuses
the existing spherical mesh-generation machinery.

The next implementation step should build on that capability rather than
replace it. A likely structure is a shared unified base-mesh step that extends
`UnifiedCellWidthMeshStep` with the additional river-geometry logic.

The important point is to keep the raster sizing-field handoff simple and to
isolate the new behavior in the final unified-mesh stage.

### Implementation: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

A likely software layout is a new package under
`polaris/tasks/mesh/spherical/unified/base_mesh/` with modules such as:

- `viz.py` for standalone visualization;
- `steps.py` for shared-step setup helpers;
- `task.py` and `tasks.py` for standalone task wrappers; and
- `base_mesh.cfg` for shared configuration options specific to final mesh
  generation and visualization.

A new shared step is not needed because that is already in
`polaris.mesh.spherical.unified.cell_width`.

The shared build step should link upstream `sizing_field.nc` and the retained
river vector products from the river workflow, rather than re-reading raw
source datasets. The standalone task should compose the already established
shared prerequisites in the same style as the current sizing-field task.

For downstream workflows, the implementation should favor thin task variants
around existing `e3sm/init/topo` remap and cull machinery, with the unified
base mesh linked as the upstream mesh input.

### Implementation: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

This is the part of the design where the implementation should remain least
overconstrained.

The first implementation should read the retained river geometry already
produced by `prepare_river_network` and apply it during final mesh creation.
It is reasonable to start with the smallest mechanism that can demonstrate
direct influence on final cell placement, even if later tuning produces a more
refined approach.

A pragmatic path is to keep the existing raster HFUN workflow intact and add a
geometry-aware adjustment or geometry constraint layer on top of it. That
approach minimizes risk because it builds on the part of the branch stack that
already exists while still satisfying the new requirement that river geometry
matter directly.

The implementation should not aim for byte-for-byte parity with the standalone
reference. However, it should preserve the same basic algorithmic approach for
using river-network geometry to influence cell-center placement, with the
standalone reference serving as the primary guide for river alignment and
outlet treatment.

### Implementation: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task registration should follow the same mesh-config discovery
pattern already used by the current unified sizing-field and river tasks.

In practice, the code that registers standalone tasks should iterate over
`UNIFIED_MESH_NAMES` from `polaris.mesh.spherical.unified.configs`, load each
named config with `get_unified_mesh_config()`, and register one standalone
base-mesh task per mesh.

The standalone tasks should include the visualization step by default. Other
workflows that reuse the shared final step should depend only on the build step
unless they explicitly opt into diagnostics.

The first implementation should assume the currently defined named meshes use
`calving_front`, but the shared-step and task-registration code should avoid hard-coding that
convention so future mesh configs can select others.

### Implementation: Standalone Visualization for Mesh and Inputs

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The visualization step should write a small set of durable, easy-to-review
artifacts rather than relying on interactive inspection alone.

A reasonable first set is:

- one or more figures of the MPAS mesh at global and regional scales;
- a figure of the lat-lon `cellWidth` field from `sizing_field.nc`; and
- figures that overlay retained river geometry on top of the mesh or on top of
  a related final-stage diagnostic.

The implementation does not need to duplicate every diagnostic already present
in the upstream coastline or river workflows. Its job is to make the final
handoff from requested mesh controls to realized mesh structure easy to assess.

### Implementation: Downstream Remap and Culling Variants for Unified Meshes

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The downstream work should be organized as explicit task variants keyed by the
same named unified meshes used by the standalone base-mesh tasks.

The implementation should prefer thin wrappers that point the existing
topography-remap and cull steps at the unified base mesh output, rather than a
parallel reimplementation of those workflows. Where the downstream workflows
need mesh-specific defaults, those should come from the same named unified-mesh
configs or closely related companion configs.

This design is intentionally broader than "just create the base mesh" because
the real value of the new mesh appears only when the mesh enters the existing
topography and culling pipeline. Treating those downstream task variants as
part of the same planned capability keeps the workflow boundary honest.

## Testing

### Testing and Validation: Final JIGSAW-to-MPAS Unified Base Mesh

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The first automated coverage should include a coarse end-to-end smoke test of
the standalone unified base-mesh task, verifying that it produces an MPAS mesh
and supporting outputs such as `graph.info`.

Validation should confirm that the final task uses the standard
JIGSAW-to-MPAS conversion path and that the result is a valid MPAS mesh.

### Testing and Validation: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that the final build step links only the shared upstream
products it needs, especially `sizing_field.nc` and retained river vector
artifacts, and does not reach back to raw source datasets.

Task-level tests should verify that downstream remap and cull variants accept
the produced unified base mesh through standard task interfaces.

### Testing and Validation: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

This requirement needs more than a file-exists test. Automated validation
should include at least one focused check that would fail if the final stage
ignored retained river geometry and used only the raster sizing field.

The precise check can evolve with the implementation. Examples include a
comparison against a raster-only control mesh, a diagnostic that measures mesh
alignment near retained channels, or a small regression case that verifies a
known outlet or main-stem placement pattern.

### Testing and Validation: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that task registration produces one standalone base-mesh
task per named unified mesh and that the tasks load the intended named config.

Coverage should also verify that the shared final step is reused when multiple
dependent tasks request the same mesh product.

### Testing and Validation: Standalone Visualization for Mesh and Inputs

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task tests should verify that visualization artifacts are
produced and that the visualization step reads both the input sizing field and
the generated base mesh.

If practical, tests should also verify that river geometry is included in the
visualization path so the final diagnostic package really covers the mesh,
resolution field, and retained river inputs together.

### Testing and Validation: Downstream Remap and Culling Variants for Unified Meshes

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

At least one integration-style test should run a coarse unified base mesh into
the downstream topography-remap and cull variants and verify that the expected
intermediate and final products are produced.

Success for this requirement is not tuned scientific quality on the first
attempt. It is that the unified mesh products pass cleanly into the existing
downstream pipeline and produce the expected remapped topography, masks, and
culled land and ocean meshes.