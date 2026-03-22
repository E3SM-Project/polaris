# E3SM Init Component Inputs

date: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

## Summary

This design document describes a new Polaris capability for porting Compass'
`compass/ocean/tests/global_ocean/files_for_e3sm` workflow into the
`e3sm/init` component. The Compass name `files_for_e3sm` is too vague for the
new framework and incorrectly suggests that the capability belongs in the
ocean component. In Polaris, the capability should instead be represented as
an `e3sm/init` task family called `component_inputs`, because its purpose is
to prepare component-specific input and diagnostics assets for coupled E3SM
workflows rather than to initialize the ocean model itself.

The new design should consume outputs from several upstream workflows. At
minimum, it will need the culled mesh and topography products from
`e3sm/init`, as well as ocean-state products from the global-ocean
initialization and dynamic-adjustment workflows when ocean packaging is
requested. The dynamic-adjusted restart should be treated as the authoritative
source for packaged ocean initial conditions in the common production
workflow, while sea-ice products should be designed to come entirely from
`e3sm/init` mesh, mask, and topography outputs plus shared remapped forcing
datasets.

Unlike the Compass workflow, the Polaris design should not bundle ocean,
sea-ice, diagnostics, and model-specific packaging steps into a single opaque
task. It should separate ocean products, sea-ice products, and diagnostics or
mapping products into clearer subtasks or step groups. It should also make the
selected ocean and sea-ice models explicit so MPAS-specific steps such as
graph partitioning and reconstruction-coefficient generation are included only
when those models are actually part of the target coupled configuration. In
particular, workflows involving Omega should not automatically inherit
MPAS-Ocean-specific packaging steps.

This design is successful if Polaris provides a cleanly named and inspectable
`e3sm/init` capability that can stage E3SM-compatible inputs for ocean,
sea-ice, and diagnostics; clearly separates shared products from
model-specific ones; uses outputs from ocean initialization and dynamic
adjustment through explicit dependencies; and leaves a straightforward path for
supporting both MPAS-Ocean-based and Omega-based coupled workflows.

## Requirements

### Requirement: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall provide this capability within the `e3sm/init` component rather
than the ocean component.

The workflow shall consume required inputs from upstream tasks through explicit
step dependencies and declared files rather than by assuming Compass-style
directory layouts.

The design shall treat the culled mesh and topography from `e3sm/init` as the
authoritative source for horizontal geometry, masks, and land-ice metadata.
The design shall consume the global-ocean initial condition and
dynamic-adjustment outputs as explicit sources for ocean packaging only.
Sea-ice packaging shall instead rely on `e3sm/init` products and quantities
that can be computed directly from them.

### Requirement: Ocean, sea-ice, and diagnostics products can be generated independently

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall separate the current mixed workflow into logically distinct
products for ocean, sea-ice, freshwater-forcing, and diagnostics or mapping
support.

Users and developers shall be able to generate only the needed subset of
products for a given coupled configuration without having to run unrelated
steps.

The design may still provide a convenience task for producing the full bundle,
but that aggregate entry point shall be composed from smaller, more focused
tasks or step groups.

### Requirement: Model-specific packaging is gated by the selected component models

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall distinguish between shared products, MPAS-Ocean-specific
products, Omega-specific products, MPAS-Seaice-specific products, and
diagnostics products.

Steps that are specific to MPAS-Ocean, such as ocean graph partitioning or
`coeffs_reconstruct` generation, shall not be included when the selected ocean
model is Omega.

Similarly, steps that are specific to MPAS-Seaice, such as sea-ice graph
partitioning, shall only be included when MPAS-Seaice is part of the target
configuration.

### Requirement: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall produce outputs that can be staged into an E3SM-compatible
directory structure for inputdata and diagnostics products.

At the same time, the workflow shall preserve inspectable step-local products
so developers can examine intermediate files before they are staged into the
assembled directory tree.

The design shall favor clear, named products over a monolithic staging step
that hides where each file came from.

### Requirement: Required remapped forcing and diagnostics assets are supported

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The port shall support the freshwater-forcing and diagnostics assets currently
produced by the Compass workflow, to the extent that they remain relevant to
the selected component models.

This includes ocean and sea-ice inputs derived from remapped observational or
climatological datasets, SCRIP files, mapping files for diagnostics, and mask
products used by MPAS-Analysis or related diagnostics workflows.

Features that depend on ice-shelf cavities or land-ice forcing shall remain
conditional on the mesh and workflow configuration rather than being treated as
unconditional outputs.

### Requirement: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The design shall avoid hard-coding assumptions that coupled E3SM always uses
MPAS-Ocean plus MPAS-Seaice.

It shall remain possible to support future combinations of ocean and sea-ice
models, new diagnostics products, or revised staging conventions without
rewriting the full workflow.

## Algorithm Design

### Algorithm Design: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should be organized around explicit source products rather than a
single inherited Compass test case. A likely set of upstream inputs is:

1. A culled base mesh and graph file from `e3sm/init`.
2. Culled topography and masks from `e3sm/init`.
3. A global-ocean initial condition from the Polaris ocean-init workflow.
4. A final dynamic-adjustment restart from the Polaris dynamic-adjustment
   workflow, when available.

The packaging logic should make the source for each product explicit. For
example, mesh products should generally come from the initialized mesh and
topography state, ocean initial conditions should typically come from the final
dynamic-adjustment restart, and sea-ice products should come from culled mesh
and mask products produced within `e3sm/init`.

This explicit source mapping is important because the current Compass workflow
mixes `base_mesh.nc`, `initial_state.nc`, and `restart.nc` in ways that are
convenient but not obvious when viewed from outside the code.

### Algorithm Design: Ocean, sea-ice, and diagnostics products can be generated independently

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The port should decompose the existing workflow into a small family of tasks or
task modes under `e3sm/init/component_inputs`. A practical decomposition is:

1. `ocean`: produce ocean-model input assets and ocean-specific forcing
   datasets.
2. `seaice`: produce sea-ice-model input assets.
3. `freshwater_forcing`: produce remapped iceberg and ice-shelf freshwater
   products that may later be staged for ocean or sea-ice components.
4. `diagnostics`: produce SCRIP files, diagnostics masks, and mapping files.
5. `all`: an optional aggregate task that instantiates the needed subset of the
   above for a standard coupled configuration.

These tasks should share utility functions and, where helpful, cached
intermediate files, but they should not require each other unless a true data
dependency exists.

In particular, the `seaice` task should not depend on the `ocean` task. It
should construct sea-ice mesh and initial-condition products directly from the
culled mesh, cull masks, and other `e3sm/init` outputs, regenerating simple
derived quantities such as Coriolis fields as needed rather than reading them
from an ocean restart.

This separation will make it much easier to support configurations such as:

1. MPAS-Ocean only.
2. Omega only.
3. MPAS-Ocean plus MPAS-Seaice.
4. Omega plus MPAS-Seaice.
5. Diagnostics-only regeneration after a mesh or metadata change.

### Algorithm Design: Model-specific packaging is gated by the selected component models

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should first classify each product as shared or model-specific.
A useful starting point is:

1. Shared or nearly shared products:
   SCRIP files, freshwater-forcing products, and diagnostic mapping inputs
   that depend primarily on the horizontal mesh.
2. MPAS-Ocean-specific products:
   `mpaso.*.nc`, ocean graph partitions, and `coeffs_reconstruct`.
3. Omega-specific products:
   Omega ocean initialization products and any Omega-specific decomposition or
   mesh-packaging assets that may be required.
4. MPAS-Seaice-specific products:
   `mpassi.*.nc`, sea-ice mesh files, and sea-ice graph partitions.

Within this classification, sea-ice products should be treated as independent
of ocean products inside `component_inputs`, even when both consume the same
culled mesh and land-ice-mask metadata.

The task driver should build a product matrix from the selected ocean and
sea-ice models and then instantiate only the relevant steps. This design is
preferable to scattering `if ocean_model == ...` logic throughout unrelated
steps.

To support Omega cleanly, shared steps should consume a model-neutral mesh or
state representation wherever possible rather than assuming that every product
must be derived from an MPAS restart file.

### Algorithm Design: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The design should separate product generation from final staging. A likely
pattern is:

1. Each generation step writes one or more well-named local products.
2. A small staging step or helper links or copies those products into an
   `assembled_files` tree with E3SM-compatible paths and filenames.

This keeps the provenance of each generated file clear while still preserving
compatibility with the inputdata and diagnostics layouts expected by E3SM
developers.

It also provides a better foundation for future changes such as alternate
staging locations, publication workflows, or checksum manifests.

### Algorithm Design: Required remapped forcing and diagnostics assets are supported

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The remapping and diagnostics portion of the port should be divided by product
type rather than forcing all remapped fields into ocean or sea-ice ownership.
A likely grouping is:

1. Ocean-specific forcing assets:
   sea-surface salinity restoring and tidal mixing.
2. Freshwater-forcing assets:
   remapped iceberg climatology, remapped ice-shelf melt, and combined
   freshwater products derived from those fields.
3. Diagnostics assets:
   SCRIP files, E3SM-to-CMIP maps, region masks, transect masks, and other
   files consumed by MPAS-Analysis or comparable diagnostics.

This grouping should make it easier to determine which products remain relevant
for Omega-based workflows and which are tied specifically to MPAS analysis or
MPAS runtime requirements.

### Algorithm Design: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The task family should use explicit model selectors, product categories, and
shared metadata helpers rather than encoding assumptions in class names such as
`FilesForE3SM`.

A small shared metadata object or helper layer should carry information such as
mesh short name, creation date, cavity status, selected models, and upstream
source files. This should replace the current pattern in which many steps
autodetect key metadata from restart-file attributes or shared config options.

This more explicit approach will make it easier to add new model targets or
new staged products later without having to duplicate the entire workflow.

## Implementation

### Implementation: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The first implementation should add a new package under
`polaris/tasks/e3sm/init/component_inputs`. The package should be structured as
an `e3sm/init` capability from the start rather than first porting the Compass
layout into the ocean component and moving it later.

The implementation should define clear step inputs for:

1. The culled mesh, graph file, and topography products from `e3sm/init`.
2. The ocean initial-condition output from the global-ocean init workflow.
3. The final dynamic-adjustment restart, when present.

For common coupled workflows, the final dynamic-adjustment restart should be
the default source for packaged ocean initial-condition files. Sea-ice steps
should not use that restart as an input. Instead, they should consume the
culled mesh, `landIceMask` and related masks from `e3sm/init`, and any
topography-derived metadata needed for sea-ice packaging.

### Implementation: Ocean, sea-ice, and diagnostics products can be generated independently

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

An initial implementation should likely add four concrete tasks and one
optional aggregate task:

1. `component_inputs/ocean`
2. `component_inputs/seaice`
3. `component_inputs/freshwater_forcing`
4. `component_inputs/diagnostics`
5. `component_inputs/all`

Each task should consist of inspectable steps with narrow responsibilities.
One reasonable first-pass mapping from Compass is:

1. Ocean steps:
   `ocean_mesh`, `ocean_initial_condition`, `ocean_graph_partition` when
   relevant,
   `remap_sea_surface_salinity_restoring`, and `remap_tidal_mixing`.
2. Sea-ice steps:
   `seaice_mesh`, `seaice_initial_condition`, and `seaice_graph_partition`
   when relevant.
3. Freshwater-forcing steps:
   `remap_iceberg_climatology`, `remap_ice_shelf_melt`, and
   `add_total_iceberg_ice_shelf_melt`.
4. Diagnostics steps:
   `scrip`, `e3sm_to_cmip_maps`, `diagnostic_maps`,
   `diagnostic_masks`, and `write_coeffs_reconstruct` when relevant.

The exact grouping can evolve during implementation, but the first port should
avoid recreating the full Compass workflow as a single task class.

Within this first-pass mapping, the sea-ice and freshwater-forcing steps
should be implemented so they consume `e3sm/init` products directly rather
than outputs from the ocean subtask.

### Implementation: Model-specific packaging is gated by the selected component models

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The new task family should include explicit model selection in config or task
construction, for example through values conceptually like:

1. `ocean_model = mpas-ocean` or `omega`
2. `seaice_model = mpas-seaice` or `none`

The implementation should then construct the needed steps from a product
matrix. For example:

1. If `ocean_model = mpas-ocean`, include `ocean_initial_condition`,
   `ocean_graph_partition`, and `write_coeffs_reconstruct` as appropriate.
2. If `ocean_model = omega`, replace the MPAS-Ocean packaging step with an
   Omega-specific ocean packaging step and exclude MPAS-Ocean graph partition
   and reconstruction-coefficient steps.
3. If `seaice_model = mpas-seaice`, include `seaice_mesh`,
   `seaice_initial_condition`, and `seaice_graph_partition`, all driven from
   `e3sm/init` mesh and mask products.
4. If freshwater-forcing products are requested, include
   `component_inputs/freshwater_forcing`, independent of whether the final
   staged files are destined for ocean or sea-ice inputdata locations.
5. If `seaice_model = none`, exclude the sea-ice task entirely.

This implementation should make the "Omega should not inherit MPAS-only
steps" rule a first-class part of the design rather than an afterthought.

### Implementation: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The existing `FilesForE3SMStep` base class mixes metadata discovery, file
validation, directory creation, NetCDF writing, and staging. In Polaris, these
concerns should be separated more cleanly.

A better pattern is:

1. Shared helpers for metadata and filename conventions.
2. Product-generation steps that only create their own outputs.
3. A small staging helper or final step that populates `assembled_files`.

This pattern would make product provenance clearer and would also reduce the
amount of duplicated setup logic across steps.

### Implementation: Required remapped forcing and diagnostics assets are supported

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The first port should include the existing remapped datasets that are still
needed for E3SM workflows, but it should evaluate them product by product
rather than assuming they all belong to the ocean or sea-ice tasks.

In particular:

1. `remap_ice_shelf_melt` should remain conditional on cavity workflows and
   should not run for open-ocean meshes without cavities.
2. `remap_iceberg_climatology`, `remap_ice_shelf_melt`, and
   `add_total_iceberg_ice_shelf_melt` should live in a neutral
   `freshwater_forcing` subtask because they conceptually describe a shared
   freshwater source rather than belonging cleanly to ocean or sea-ice.
3. `diagnostic_masks` and `diagnostic_maps` should be treated as diagnostics
   assets, even if they continue to rely on MPAS-oriented tooling initially.
4. `scrip` and E3SM-to-CMIP mapping support should be implemented so they can
   remain shared across MPAS-Ocean and Omega when they depend only on the
   horizontal mesh description.
5. The `freshwater_forcing` subtask should use `landIceMask` and other
   cull-mask products from `e3sm/init` rather than reading them from ocean
   initial-condition or restart files.

One important implementation detail is that several current Compass steps
derive products from `restart.nc` simply because it is convenient. During the
port, we should revisit those dependencies and use more model-neutral source
files when that leads to cleaner support for Omega or cleaner separation
between the ocean and sea-ice subtasks.

### Implementation: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The first implementation should keep model-specific code behind small,
well-named interfaces. Likely candidates are:

1. A shared metadata or context helper.
2. Model-specific ocean packagers.
3. Model-specific sea-ice packagers.
4. A shared staging helper.

This will make it easier to add future model combinations or revise the staged
output set without restructuring the entire task family.

## Testing

### Testing and Validation: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Integration tests should verify that the new `e3sm/init/component_inputs`
tasks can consume outputs from the `e3sm/init` cull workflow and the new
global-ocean init and dynamic-adjustment workflows through declared inputs.

These tests should avoid hidden dependence on Compass-style work-directory
layout.

They should also verify that the sea-ice task can run without requiring the
ocean task, as long as the necessary `e3sm/init` mesh and mask products are
available.

### Testing and Validation: Ocean, sea-ice, and diagnostics products can be generated independently

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Regression tests should exercise at least:

1. An ocean-only configuration.
2. A sea-ice-only configuration.
3. A freshwater-forcing-only configuration.
4. A diagnostics-only configuration.
5. A full aggregate configuration.

This testing will help ensure the decomposition remains real rather than
allowing hidden coupling between the subtasks to creep back in.

### Testing and Validation: Model-specific packaging is gated by the selected component models

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Unit or lightweight integration tests should verify the product matrix for
several model combinations, especially:

1. MPAS-Ocean plus MPAS-Seaice.
2. Omega plus MPAS-Seaice.
3. Omega with no sea-ice component.

These tests should confirm that MPAS-Ocean-only steps such as graph partition
and `coeffs_reconstruct` are absent from Omega configurations.

### Testing and Validation: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Regression testing should confirm both that expected staged files appear in the
assembled directory tree and that the step-local source products are present
with predictable names.

This validation should include at least a few representative filenames from
the ocean, sea-ice, and diagnostics categories.

### Testing and Validation: Required remapped forcing and diagnostics assets are supported

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Tests should verify that each supported remapped dataset and diagnostics asset
is either produced when relevant or cleanly omitted when its prerequisites are
not part of the selected workflow.

Cavity-dependent products should be tested separately from open-ocean meshes so
their conditional behavior remains explicit and correct.

### Testing and Validation: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The code structure should be reviewed with the same criterion as the design:
adding a new component model or a new staged product should require extending a
small interface or product table, not cloning the entire task family.
