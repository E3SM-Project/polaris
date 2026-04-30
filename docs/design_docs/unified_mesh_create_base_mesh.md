# Unified Mesh: Base-Mesh Creation and Downstream Integration

date: 2026/04/26

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design describes the shared final `create_base_mesh` step for the
unified global mesh workflow, the standalone tasks that run that step for each
named unified mesh, and the downstream workflow variants that consume the new
base meshes for topography remapping and mesh culling.

The shared `prepare_coastline`, `prepare_river_network`, and
`build_sizing_field` stages described in the earlier design documents are now
implemented, and the final stage described here is implemented as a shared
unified base-mesh step, standalone base-mesh tasks for each named mesh, and
explicit downstream topography-remap and cull task variants.

The current implementation provides standalone base-mesh tasks for the
four currently defined named unified meshes in
`polaris.mesh.spherical.unified`, all of which currently use the
`calving_front` Antarctic coastline convention. At the same time, the shared
infrastructure should remain compatible with any supported coastline
convention, even if only `calving_front` is exercised in the current automated
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

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The final base-mesh stage shall consume the outputs of `build_sizing_field`
and the mesh-conditioned river products from `prepare_river_network` through
explicit shared interfaces.

The standard workflow shall not need to re-read or reinterpret raw topography,
raw coastline, or raw HydroRIVERS source datasets inside the final mesh
generation stage, nor should it perform its own coastline-aware river clipping
inside the final mesh step.

The downstream remap and culling workflow variants shall likewise consume the
resulting MPAS base mesh through explicit task interfaces rather than through
manual work-directory edits.

### Requirement: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/26

Contributors:

- Xylar Asay-Davis
- Codex

Retained river geometry shall influence final mesh generation directly rather
than only through the raster sizing field.

The requirement is on the resulting behavior, namely that final cell placement
can reflect the retained river network, especially along important channels and
near outlets.

### Requirement: River Snapping Shall Not Refine Coastal Ocean Resolution

Date last modified: 2026/04/26

Contributors:

- Xylar Asay-Davis
- Codex

Snapping cell centers to retained river-network geometry shall not introduce
finer-than-intended ocean resolution along the coastline.

In particular, the final workflow shall prevent river-geometry treatment near
the coast from pulling neighboring ocean cells into a locally over-refined
state that would constrain the ocean time step relative to the requested mesh
design.

This requirement is on the realized ocean mesh, not just on the input sizing
field. The base-mesh stage shall preserve the intended coastal ocean
resolution even when river geometry is used to improve inland cell placement.

### Requirement: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/26

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide one shared final base-mesh step that can be reused by
multiple workflows.

Polaris shall also provide one standalone task per named unified mesh defined
by the config files in `polaris.mesh.spherical.unified`.

The first implementation shall cover the four currently defined named meshes.
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

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The intended final-stage input contract is:

- `sizing_field.nc` from `build_sizing_field` as the authoritative raster
  spacing field;
- mesh-conditioned vector river geometry and outlet metadata from
  `prepare_river_network` for direct final-stage geometry use and for
  visualization; and
- the named unified-mesh configuration, including the selected target-grid
  tier and Antarctic coastline convention, for consistent downstream labeling
  and task selection.

The final stage should not go back to raw source data to infer these products
again. That keeps the workflow layered in the same way as the earlier design
documents: source interpretation belongs in shared preprocessing steps, sizing
policy belongs in `build_sizing_field`, coastline-aware river conditioning
belongs in `prepare_river_network`, and final mesh generation belongs in
`create_base_mesh`.

The downstream topography-remap and culling variants should then consume the
generated `base_mesh.nc` through the same standard interfaces used by existing
Polaris `e3sm/init` workflows. The design should favor task composition over
special one-off scripts.

### Algorithm Design: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

Retained river geometry must influence final mesh generation directly. The
sizing field already expresses raster refinement around rivers and outlets, but
the
standalone reference workflow suggests that raster refinement alone is not the
whole story when the goal is to place cell centers well along river channels.

The design should therefore keep two distinct river signals in the final mesh
stage:

- a raster resolution signal from `build_sizing_field`; and
- a vector geometry signal from the conditioned river network prepared for the
  selected mesh.

The design should follow the algorithmic approach used by the standalone
reference solution in
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
for using river-network geometry to place cell centers. We do not require a
byte-for-byte match to the standalone implementation, but we do want Polaris to
preserve that reference workflow's geometry-driven method for river alignment
and outlet treatment rather than substitute a different first-cut approach.

Because outlet regions are especially sensitive, the geometry path should also
leave room for stronger treatment near retained outlets than along the generic
channel network if later tuning shows that is needed.

### Algorithm Design: River Snapping Shall Not Refine Coastal Ocean Resolution

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The simplest way to satisfy this requirement is to trim or ignore retained
river geometry before it reaches the final base-mesh stage.

The design should therefore use the coastal signed-distance field already
produced on the shared lat-lon grid during river-network preparation to
evaluate retained river geometry points before they are written to the
base-mesh-facing river products.

Any river-network geometry that falls within the configured coastal clipping
zone should be excluded from the geometry-driven snapping path. In other words,
the river geometry consumed by `create_base_mesh` should already stop inland of
the coastline by a configurable clip distance consistent with the intended
coastal transition treatment.

The current implementation keeps this cutoff explicit in the river workflow as
`base_mesh_clip_distance_km` rather than deriving it directly from
`coastline_transition_land_km`.

Because the target field is periodic in longitude, the interpolation used for
this cutoff should account for longitude periodicity so that river features
near the dateline are handled consistently with those elsewhere on the globe.

### Algorithm Design: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/26

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
- `ocn_rrs_6to18km_lnd_12km_riv_6km`; and
- `ocn_so_12to30km_lnd_10km_riv_10km`.

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

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation uses
`polaris.mesh.spherical.unified.base_mesh.UnifiedBaseMeshStep`. That class
reads `cellWidth`, `lat`, and `lon` from `sizing_field.nc`, links the prepared
`clipped_river_network.geojson` product, and reuses the existing spherical
mesh-generation machinery.

The shared-step factory in
`polaris/tasks/mesh/spherical/unified/base_mesh/steps.py` wires the upstream
coastline, river source, river lat-lon, river base-mesh, and sizing-field
steps together for one named mesh, and `BaseMeshTask` exposes that chain as a
standalone task.

The important point is to keep the raster sizing-field handoff simple and to
isolate the new behavior in the final unified-mesh stage.

### Implementation: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The software layout under `polaris/tasks/mesh/spherical/unified/base_mesh/` is
now concrete, with modules such as:

- `viz.py` for standalone visualization;
- `steps.py` for shared-step setup helpers;
- `task.py` and `tasks.py` for standalone task wrappers; and
- `base_mesh.cfg` for shared configuration options specific to final mesh
  generation and visualization.

The shared build step should link upstream `sizing_field.nc` and the
conditioned river vector products from the river workflow, rather than
re-reading raw source datasets. In practice, `UnifiedBaseMeshStep.setup()` links
`sizing_field.nc` from `build_sizing_field` and `clipped_river_network.geojson`
from `PrepareRiverForBaseMeshStep`. The standalone task composes the already
established shared prerequisites in the same style as the current sizing-field
task.

For downstream workflows, the implementation favors thin task variants around
existing `e3sm/init/topo` remap and cull machinery, with the unified base mesh
linked as the upstream mesh input.

### Implementation: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation reads the conditioned river geometry produced by
`prepare_river_network` and applies it during final mesh creation.
`UnifiedBaseMeshStep.make_jigsaw_mesh()` follows the approach in
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh)
for using river-network geometry to influence cell-center placement, while
building on the existing Polaris raster HFUN workflow and JIGSAW-to-MPAS
conversion path.

The implementation should not aim for byte-for-byte parity with the standalone
reference. However, it should preserve the same basic algorithmic approach,
with the standalone reference serving as the primary guide for river alignment
and outlet treatment.

To keep river snapping from distorting coastal ocean resolution, the coastline-
aware clipping now happens upstream in `PrepareRiverForBaseMeshStep`. The final
base-mesh step consumes the already conditioned `clipped_river_network`
product and converts those line features into JIGSAW `edge2` constraints.

### Implementation: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task registration follows the same mesh-config discovery pattern
already used by the unified sizing-field and river tasks.

In practice, `add_unified_base_mesh_tasks()` iterates over `UNIFIED_MESH_NAMES`
from `polaris.mesh.spherical.unified.configs` and registers one standalone
`base_mesh_<mesh_name>_task` per mesh.

The standalone tasks include the visualization step by default. Other
workflows that reuse the shared final step depend only on the build step unless
they explicitly opt into diagnostics.

The first implementation should assume the currently defined named meshes use
`calving_front`, but the shared-step and task-registration code should avoid
hard-coding that convention so future mesh configs can select others.

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

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

The downstream work is organized as explicit task variants keyed by the same
named unified meshes used by the standalone base-mesh tasks.

`add_remap_topo_tasks()` and `add_cull_topo_tasks()` both iterate over
`UNIFIED_MESH_NAMES`, retrieve the shared unified base-mesh step from the mesh
component, and register `e3sm/init` remap and cull tasks that reuse the
existing topography-remap and cull steps. Where the downstream workflows need
mesh-specific defaults, those come from the same named unified-mesh configs.

This design is intentionally broader than "just create the base mesh" because
the real value of the new mesh appears only when the mesh enters the existing
topography and culling pipeline. Treating those downstream task variants as
part of the same planned capability keeps the workflow boundary honest.

## Testing

### Testing and Validation: Final JIGSAW-to-MPAS Unified Base Mesh

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

Current automated coverage includes unit tests for `UnifiedBaseMeshStep` and
for standalone base-mesh task registration, but not yet a coarse end-to-end
smoke test that runs JIGSAW and produces `base_mesh.nc` and `graph.info`.

Validation should confirm that the final task uses the standard
JIGSAW-to-MPAS conversion path and that the result is a valid MPAS mesh.

### Testing and Validation: Explicit Consumption of Shared Unified-Mesh Products

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that the final build step links only the shared upstream
products it needs, especially `sizing_field.nc` and retained river vector
artifacts, and does not reach back to raw source datasets.

Current unit tests verify the first part of that contract by exercising the
base-mesh and river shared-step factories and by confirming that downstream
remap and cull variants are registered for each named unified mesh.

Task-level execution tests should still verify that the remap and cull variants
accept the produced unified base mesh through standard task interfaces.

### Testing and Validation: River-Geometry Influence on Final Cell Placement

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

This requirement needs more than a file-exists test. Automated validation
should include at least one focused check that would fail if the final stage
ignored retained river geometry and used only the raster sizing field.

The current unit tests verify that the prepared clipped river geometry is
converted into JIGSAW line constraints. The precise mesh-quality check can
still evolve. Examples include a comparison against a raster-only control mesh,
a diagnostic that measures mesh alignment near retained channels, or a small
regression case that verifies a known outlet or main-stem placement pattern.

### Testing and Validation: River Snapping Shall Not Refine Coastal Ocean Resolution

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

Validation for this requirement should include an ocean-focused check on the
realized mesh, not only on the retained river inputs or on the raster sizing
field.

One required diagnostic is that `dcEdge` after culling to the ocean-only mesh
must not show a band of higher resolution along the coastline than elsewhere
in the mesh, beyond what is expected from the intended ocean resolution
pattern.

Automated coverage should also include at least one focused regression test of
the river-conditioning step, verifying that river segments are clipped before
they reach the coastline clipping zone and that periodic longitude handling
does not break the cutoff near the dateline.

Current unit tests cover inland clipping of retained segments and outlet
removal near the coastline. What is still missing is a realized-ocean-mesh
regression that checks `dcEdge` after ocean culling.

### Testing and Validation: Shared Final Step and Per-Mesh Standalone Tasks

Date last modified: 2026/04/27

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that task registration produces one standalone base-mesh
task per named unified mesh and that the tasks load the intended named config.

Current unit tests verify that task registration produces one standalone
base-mesh task per named unified mesh, that the visualization step is included,
and that the shared final step and config are reused when multiple dependent
requests target the same mesh product.

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

Date last modified: 2026/04/27

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

Current unit tests already verify that the explicit unified remap and cull task
variants are registered for each named mesh and that the coarsest unified mesh
selects the expected low-resolution topography path.