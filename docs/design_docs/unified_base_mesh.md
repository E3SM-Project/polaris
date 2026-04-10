# Unified Global Base Mesh Workflow

date: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design proposes a Polaris workflow for creating a global, spherical MPAS
base mesh for the E3SM land, river, ocean and sea-ice models using JIGSAW. The
starting point is the work-in-progress `mpas_land_mesh` package,
which currently combines geospatial preprocessing, JSON-based configuration,
JIGSAW setup, mesh generation and ad hoc job creation in a single standalone
workflow.

The Polaris implementation should preserve the relevant parts of that workflow
while translating them into shared steps, Polaris configuration files and
existing MPAS/JIGSAW infrastructure. In particular, the design should reuse
existing functionality in `polaris.mesh`, `mpas_tools` and the existing
`e3sm/init` topography remap and cull tasks wherever practical, rather than carrying
forward the standalone workflow's JSON configuration system or broad utility
modules.

The initial focus is a feature-aware global base mesh whose resolution can be
informed by coastline and river-network data and whose output is directly
usable by downstream Polaris tasks such as `e3sm/init` topography remapping and mesh
culling. This design is intentionally a first draft because `mpas_land_mesh`
is still evolving. The document therefore emphasizes interfaces, workflow
decomposition and reuse strategy more than it fixes every implementation
detail. In particular, the exact component boundary between generic mesh work
and land/river-specific preprocessing remains an open design choice.

This document should be treated as an umbrella design for the overall workflow.
As the work is refined, we expect to add more focused design documents for
stages such as `prepare_coastline`, `prepare_river_network`,
`build_sizing_field`, and possibly `unified_base_mesh` if that stage proves
complex enough to warrant its own design. These stage names are only working
names for now and should not be treated as final task, step, class or
component names.

The stage-level shared products should be built on a small set of supported
regular lon/lat target grids rather than on arbitrary default resolutions. A
short list of supported target-grid tiers is likely important for caching and
reuse of expensive shared steps such as coastline preparation,
river-network preparation, and topography remapping.

Success means that Polaris gains a documented path to build a global MPAS base
mesh with feature-aware resolution controls, using Polaris-native setup and run
machinery, and that the resulting mesh can be consumed by existing downstream
E3SM workflows without an extra conversion stage.

## Requirements

### Requirement: Global Spherical MPAS Base Mesh

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall support creation of a global, spherical MPAS base mesh suitable
for the needs of the E3SM land, river, ocean and sea-ice models.

The workflow shall support meshes whose resolution varies spatially in response
to model needs rather than being limited to quasi-uniform meshes.

The primary output of the workflow shall be an MPAS mesh in standard MPAS form.

### Requirement: Downstream E3SM Interoperability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The generated base mesh shall be usable as input to downstream E3SM and
Polaris tools, including the existing topography remap and cull workflows.

The workflow shall not require a separate ad hoc conversion step before the
mesh can be passed to those downstream tools.

### Requirement: Feature-Aware Resolution Control

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow shall support resolution control based on geospatial features that
are important for a unified land-river-ocean mesh. At a minimum, the first
implementation shall support coastline and river-network information.

The design shall allow additional feature classes such as watershed
boundaries, lakes or dams to be added later without redesigning the full
workflow.

### Requirement: Shared Target-Grid Tiers and Cacheable Preprocessing

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The shared preprocessing stages of the workflow shall operate on a small
discrete set of supported regular lon/lat target grids rather than on an
arbitrary default resolution.

Within a given workflow instance, the same selected target-grid tier shall be
used consistently by `prepare_coastline`, `prepare_river_network`, and
`build_sizing_field`.

The first design should favor a short supported list, likely two or three
tiers, so shared-step outputs can be cached and reused effectively.

### Requirement: Polaris-Native Configuration and Execution

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow shall be expressed as Polaris steps and tasks and configured with
Polaris' ini-style configuration files.

The workflow shall support standard Polaris setup, shared-step reuse,
provenance and machine execution patterns.

### Requirement: Selective Migration and Maintainability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The Polaris implementation shall prefer existing Polaris, `mpas_tools`,
JIGSAW and conda-forge capabilities wherever practical.

Migration from `mpas_land_mesh` shall focus on the specific algorithms and
helpers needed for the Polaris workflow rather than wholesale reuse of general
utility modules or standalone workflow infrastructure.

## Algorithm Design

### Algorithm Design: Global Spherical MPAS Base Mesh

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The existing spherical JIGSAW workflow in `polaris.mesh` should be the starting
point for the new capability. The current `SphericalBaseStep` already handles
the parts of the workflow that are generic to MPAS spherical mesh generation:
writing the JIGSAW inputs, invoking JIGSAW, converting the JIGSAW triangles to
an MPAS mesh, updating MPAS fields such as `cellWidth`, and creating
`graph.info`.

The unified base-mesh workflow should therefore focus on creating the
feature-aware mesh-spacing description rather than replacing the existing
JIGSAW-to-MPAS path. In the simplest formulation, the workflow builds a
global lon/lat-based sizing field and then reuses the existing spherical mesh
step to convert that sizing field into a JIGSAW mesh and finally into MPAS
form.

This keeps the core mesh-generation algorithm close to existing Polaris
patterns and minimizes the amount of new meshing infrastructure that must be
maintained on the E3SM timeline.

### Algorithm Design: Downstream E3SM Interoperability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The output contract for the workflow should be aligned with what downstream
Polaris tasks already consume. The immediate target is the standard MPAS base
mesh plus associated graph file used by the existing E3SM topography remap and
cull tasks.

Because the remap and cull tasks already operate on `base_mesh.nc`, the design
should treat that file as the primary authoritative output. Any additional
intermediate products needed for land or river workflows, such as cleaned
feature vectors or rasterized masks, should remain separate artifacts rather
than becoming a replacement mesh format.

This requirement argues for producing a standard base mesh first and layering
additional land/river products around it, not embedding workflow-specific
assumptions into the base-mesh format.

### Algorithm Design: Feature-Aware Resolution Control

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The feature-aware part of the workflow should be decomposed into two stages:
feature preprocessing and sizing-field construction.

Feature preprocessing converts raw source datasets into cleaned global inputs
that are stable enough to drive mesh sizing. Based on the current
`mpas_land_mesh` workflow, the first supported sources should be:

- a coastline mask derived first from the existing `e3sm/init/topo`
  topography product and its land/ocean masking logic, so the unified mesh
  uses the same coastline interpretation as downstream topography remap and
  cull workflows. A Natural Earth-derived coastline should remain available as
  a fallback if the topo-derived coastline proves unsuitable, and
- a simplified global river network derived from HydroRIVERS or an equivalent
  source.

Sizing-field construction then combines a baseline resolution with local
refinement targets derived from those preprocessed features. The precise blend
function can evolve, but the first implementation should be framed as a global
sizing field on a regular lon/lat grid because that matches the existing
Polaris spherical JIGSAW workflow.

For coastline-driven refinement, a signed-distance formulation on the sphere
should be considered the preferred first approach. If a coastline curve or
region can be derived cleanly from the `e3sm/init/topo` land/ocean
interpretation, `mpas_tools.mesh.creation.signed_distance` or a closely
related method can be used to build smooth coastal transition zones and inland
or oceanward buffers directly from spherical geometry. This approach is
promising because it matches existing Polaris mesh patterns and may avoid some
of the raster-buffer and antimeridian-complexity present in the standalone
workflow.

The design should assume that coastline and river controls are modular inputs
to the sizing-field builder. Additional controls for watersheds, lakes or dams
should enter through the same interface rather than through new one-off mesh
builders.

### Algorithm Design: Shared Target-Grid Tiers and Cacheable Preprocessing

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow should standardize on a small set of named target-grid tiers for
all shared preprocessing products. A reasonable first set is:

- `coarse`: 1.0 degree;
- `medium`: 0.25 degree; and
- `fine`: 1/16 degree, or 0.0625 degree.

These choices balance several competing needs. A 1-degree grid is inexpensive
and suitable for exploratory or coarse products. A 0.25-degree grid is already
useful for other E3SM preprocessing such as WOA 2023 extrapolation work. A
1/16-degree grid is fine enough to support mesh-resolution choices down to
roughly 5 km or so without making every workflow pay that cost by default.

The selected target-grid tier should be a cross-cutting workflow choice. It
should control the resolution used for shared `e3sm/init/topo/combine`
lat/lon products, coastline preprocessing, river-network preprocessing, and
the final sizing field. This avoids mismatched products between stages and
makes cache reuse straightforward.

The design should not prevent future support for custom target-grid
resolutions. However, arbitrary resolutions should not be the default
workflow path until there is a clear need, because they weaken cache reuse and
make the shared-step product space harder to manage.

### Algorithm Design: Polaris-Native Configuration and Execution

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone workflow currently uses JSON templates, repeated key mutation
and explicit HPC-script generation. Polaris already has suitable
abstractions: config sections, shared steps, cached outputs, work-directory
layout and machine-aware job submission.

The algorithmic structure of the new workflow should therefore be a dependency
graph of Polaris steps, not a mutable configuration file plus a generated
driver script. A natural decomposition is:

1. preprocess coastline inputs;
2. preprocess river-network inputs;
3. assemble a unified sizing field;
4. generate the spherical JIGSAW mesh and convert it to MPAS form; and
5. optionally pass the base mesh into downstream remap and cull tasks.

This step decomposition matches Polaris' execution model and supports reuse of
shared expensive products across multiple tasks.

### Algorithm Design: Selective Migration and Maintainability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The migration strategy should begin with an audit of `mpas_land_mesh`
capabilities grouped into three categories:

- functionality already available in Polaris or `mpas_tools`,
- functionality available from direct use of conda-forge packages, and
- functionality that truly requires targeted extraction or reimplementation.

The current standalone package includes broad helper modules such as
`utilities/vector.py`, JSON configuration managers and job-script generators.
Those are useful in the standalone context but should not be treated as the
default implementation strategy in Polaris.

Instead, new shared helpers should be introduced only when a focused algorithm
cannot be expressed clearly with existing package APIs or current Polaris
utilities. This keeps the eventual Polaris implementation smaller, easier to
review and more adaptable as `mpas_land_mesh` continues to change.

River-network simplification and river-driven meshing deserve special caution
in this migration strategy. Because that part of the workflow is the least
well-understood, the first Polaris design should preserve the corresponding
`mpas_land_mesh` algorithms more closely than the coastline path whenever
practical.

## Implementation

### Implementation: Global Spherical MPAS Base Mesh

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The recommended implementation is a new feature-aware spherical base-mesh step
in `polaris.mesh` that builds on `SphericalBaseStep` rather than replacing it.
Two implementation paths both appear reasonable:

- a subclass of `QuasiUniformSphericalMeshStep` that overrides construction of
  the global `cellWidth` field, or
- a new sibling class whose responsibility is explicitly a feature-driven
  spherical sizing field.

In either case, the step should continue to rely on the existing
`SphericalBaseStep.run()` logic for JIGSAW invocation, conversion to MPAS form
and graph-file creation.

The output naming should match existing Polaris conventions, with
`base_mesh.nc` as the primary mesh product and `graph.info` produced alongside
it.

### Implementation: Downstream E3SM Interoperability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The new unified base-mesh step should be shaped so it can be passed directly to
existing E3SM tasks that expect a `SphericalBaseStep`-like dependency. In
practice, this means keeping the same mesh and graph-file outputs and the same
basic interface expected by the current remap and cull tasks.

The design should avoid introducing a special mesh post-processing task whose
only purpose is to translate the new workflow back into the format already
expected by `polaris.tasks.e3sm.init.topo.remap` and
`polaris.tasks.e3sm.init.topo.cull`.

For validation and adoption, the first Polaris task that exercises the new
workflow should likely connect the generated base mesh to one or both of those
existing downstream tasks.

### Implementation: Feature-Aware Resolution Control

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The likely first-pass step decomposition is:

- `prepare_coastline`: derive a coastline representation suitable for mesh
  refinement, using the `e3sm/init/topo` coastline as the first-choice source
  and Natural Earth as a fallback;
- `prepare_river_network`: simplify and filter a global river dataset into a
  refinement-ready product;
- `build_sizing_field`: combine baseline ocean and land resolution choices with
  coastline and river refinement controls on a global lon/lat grid, ideally
  using signed-distance fields where that simplifies the definition of
  transition zones and buffers; and
- `unified_base_mesh`: consume the sizing field and create the MPAS base mesh.

These names are intentionally provisional. They are useful labels for the
current design discussion but should not yet be interpreted as final public
interfaces or directory names in Polaris.

Even if the final implementation uses several shared steps, Polaris should
present them as one coherent workflow rather than as unrelated utilities. The
cleanest first implementation is to keep the shared steps together under the
`mesh` component in one common subtree such as
`mesh/spherical/unified/...`. That mirrors existing Polaris practice where a
shared base-mesh step lives in the `mesh` component and tasks provide a thin
wrapper around it. A separate `river` component would make more sense only if
Polaris later grows river-focused workflows that stand on their own apart from
base-mesh generation.

As this workflow matures, more targeted design documents should be added for
the stage-level algorithms and interfaces, especially `prepare_coastline`,
`prepare_river_network`, and `build_sizing_field`. A separate design for
`unified_base_mesh` may or may not be needed depending on how much new logic
remains after reuse of the existing spherical JIGSAW infrastructure.

The preprocessing steps should write clear intermediate products that are
useful for debugging and caching, such as cleaned GeoJSON or raster files.
However, those products should be internal workflow artifacts, not new required
external interfaces for downstream users.

`build_sizing_field` needs a tighter contract than its working name suggests.
It should be defined as the step that takes:

- the selected target-grid tier;
- the background land and ocean resolution choices for the mesh;
- the outputs of `prepare_coastline`, such as coastline geometry, masks or
  signed-distance fields;
- the outputs of `prepare_river_network`, such as simplified flowlines,
  drainage-area filters or rasterized distance products; and
- configuration controlling how these refinement signals are blended,
  including minimum and maximum cell widths, transition distances and optional
  feature toggles.

Its output should be a single regular lon/lat `cellWidth` field in the format
already expected by the spherical JIGSAW workflow. Framing it this way makes
clear that `build_sizing_field` is not another ad hoc resolution option like
the current quasi-uniform mesh choices. Instead, it is the integration point
between shared feature preprocessing and the existing `SphericalBaseStep`
machinery. The downstream mesh-generation step should consume the resulting
`cellWidth` field without needing to know whether refinement came from
coastlines, rivers or later feature classes.

For coastline processing, the first implementation should attempt to derive the
coastline from the same topography inputs used in `e3sm/init/topo`, because
that gives the strongest consistency with downstream masking and culling. The
preferred next step would then be to construct a signed-distance field on the
sphere from that coastline and use it to define smooth resolution transitions,
including inland coastal buffers where the coastal or ocean resolution is
preserved for a configurable distance from shore. A fallback path based on
Natural Earth should be retained in case the topo-derived coastline is too
noisy, too expensive to generate, or otherwise unsuitable for driving mesh
refinement.

The first implementation should target coastline and river inputs only. The
configuration and internal APIs should nonetheless leave room for later steps
that prepare watershed boundaries, lake boundaries or dam data if those prove
necessary.

The selected target-grid tier should be treated as part of this interface. The
preprocessing and sizing-field steps should exchange products on one shared
grid, not on independently chosen grids.

### Implementation: Polaris-Native Configuration and Execution

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone JSON configuration files should be translated into Polaris
config sections, for example:

- `[unified_mesh]` for overall workflow choices, target-grid-tier selection,
  and supported feature toggles;
- `[coastline]` for coastline-source selection, fallback behavior and any
  thresholds related to coastline cleaning or simplification, as well as
  signed-distance transition and buffer parameters;
- `[river_network]` for river simplification and filtering controls; and
- `[sizing_field]` for background resolutions and feature-composition
  parameters; and
- `[spherical_mesh]` for the final JIGSAW and MPAS mesh settings already used
  by Polaris.

The workflow should rely on Polaris work directories and machine support rather
than carrying forward `jigsawcase`, `change_json_key_value()` or generated
standalone job scripts.

For the first implementation, the full shared-step chain should live in the
existing `mesh` component, because the workflow's primary public product is a
base mesh and because Polaris shared steps are organized most clearly when
their directories live at the highest common level where all consuming tasks
can find them. In practice, the task that exposes the workflow should be a
thin wrapper that links together shared steps such as `prepare_coastline`,
`prepare_river_network`, `build_sizing_field`, and the final
`unified_base_mesh` step, all under one mesh-oriented subtree.

This recommendation does not rule out a later `river` or `land` component.
If Polaris eventually adds reusable river preprocessing, diagnostics or
standalone river-data products outside this mesh workflow, those could justify
a separate component. Even in that case, the interface should still make the
unified base-mesh workflow look like one pipeline, with `build_sizing_field`
remaining the explicit handoff from feature products to the generic spherical
mesh generator.

### Implementation: Shared Target-Grid Tiers and Cacheable Preprocessing

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first implementation should expose target-grid choice through a small
enumerated option such as `target_grid_tier = coarse`, `medium`, or `fine`
rather than by encouraging arbitrary floating-point defaults in every task.

Each tier should map to a specific regular lon/lat resolution and should be
used consistently in work-directory layout, shared-step cache keys, and output
file naming so it is obvious which products can be reused together.

### Implementation: Selective Migration and Maintainability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The implementation effort should begin with a short function-by-function audit
of `mpas_land_mesh` to decide what should be:

- reused from Polaris or `mpas_tools`,
- replaced with direct use of external packages, or
- extracted into small Polaris helpers.

The following parts of `mpas_land_mesh` appear unlikely to be appropriate for
direct migration:

- JSON configuration management in `utilities/config_manager.py`;
- standalone case and job infrastructure in `classes/jigsawcase.py`; and
- broad general-purpose utility layers such as
  `mpas_land_mesh/utilities/vector.py`.

Candidate targeted extractions may still be needed for items such as
geographic buffering, antimeridian-safe geometry handling or specific river
network simplification logic if those capabilities are not already available in
the chosen package stack. If helper code is brought over, it should remain
small, step-focused and colocated with the consuming workflow unless it quickly
proves reusable.

For the river-network path in particular, targeted extraction or close
reimplementation is likely preferable to an early redesign of the underlying
algorithm.

## Testing

### Testing and Validation: Global Spherical MPAS Base Mesh

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow should include an integration test that creates a coarse unified
global mesh and verifies that `base_mesh.nc` and `graph.info` are produced.

Validation should confirm that the resulting file is a valid MPAS mesh and that
the feature-aware step reuses the standard JIGSAW-to-MPAS conversion path.

### Testing and Validation: Downstream E3SM Interoperability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

At least one regression-style task should pass the generated base mesh into the
existing topography remap workflow, and ideally also the cull workflow, without
any manual conversion or edits in the work directory.

Success for this requirement is not that the unified mesh produces final tuned
science results on the first attempt, but that the mesh product is accepted by
the existing downstream infrastructure as a standard MPAS base mesh.

Because coastline consistency is a key motivation for the preferred source,
validation should also check that the coastline product used for refinement is
derived from the same topography interpretation used downstream when the
first-choice path is selected.

### Testing and Validation: Feature-Aware Resolution Control

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that the sizing-field builder responds to coastline and
river inputs as configured and that it behaves sensibly across the
antimeridian.

Where practical, unit or small-integration tests should be added for any new
geometry or raster helper functions that are extracted from the standalone
workflow, especially for antimeridian handling and feature buffering.

Tests should also cover coastline-source selection, including the preferred
topography-derived coastline path and the Natural Earth fallback path.

If a signed-distance coastline path is adopted, tests should verify that the
distance field and resulting coastal buffers behave as expected on both sides
of the coastline and across the antimeridian.

### Testing and Validation: Shared Target-Grid Tiers and Cacheable Preprocessing

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Tests should verify that the supported target-grid tiers produce the expected
lon/lat dimensions and that dependent shared steps reuse cached outputs when
the same tier is selected.

They should also verify that switching tiers produces separate products rather
than silently reusing incompatible cached artifacts.

### Testing and Validation: Polaris-Native Configuration and Execution

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The new workflow should be validated through standard Polaris setup and run
commands, showing that configuration is expressed entirely through Polaris
config files and that shared preprocessing steps can be reused by dependent
tasks.

If the workflow is split across multiple components, tests should also verify
that the dependency chain remains clear to users through `polaris list
--verbose` and standard work-directory links.

### Testing and Validation: Selective Migration and Maintainability

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Any helper code extracted from `mpas_land_mesh` should receive targeted tests
that protect the specific behavior Polaris depends on.

The first implementation should also document which external conda-forge
packages were chosen in place of direct code migration so future contributors
can understand why a given helper was or was not carried over from the
standalone workflow.
