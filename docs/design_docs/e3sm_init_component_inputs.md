# E3SM Init Component Inputs

date: 2026/03/22

Contributors: Xylar Asay-Davis, Codex, Claude

## Summary

This design document describes a new Polaris capability for porting Compass'
`compass/ocean/tests/global_ocean/files_for_e3sm` workflow into the
`e3sm/init` component. The Compass name `files_for_e3sm` is too vague for the
new framework and incorrectly suggests that the capability belongs in the
ocean component. In Polaris, the capability should instead be represented as
an `e3sm/init` task family called `component_inputs`, because its purpose is
to prepare component-specific input and mesh-derived support assets for
coupled E3SM workflows rather than to initialize the ocean model itself.

The new design should consume outputs from several upstream workflows. At
minimum, it will need the culled mesh and topography products from
`e3sm/init`, as well as ocean-state products from the global-ocean
initialization and dynamic-adjustment workflows when ocean packaging is
requested. The upstream ocean initialization and dynamic-adjustment tasks each
target a single ocean model, selected by the `[ocean] model` config option;
the component-inputs workflow consumes that one model's products. It does not
attempt to build initial conditions for multiple ocean models in a single task.
The dynamic-adjusted restart should be treated as the authoritative source for
packaged ocean initial conditions in the common production workflow, while
sea-ice products should be designed to come entirely from `e3sm/init` mesh,
mask, and topography outputs plus shared remapped forcing datasets.

Unlike the Compass workflow, the Polaris design should not bundle ocean,
sea-ice, mapping-and-mask support, and model-specific packaging steps into a
single opaque task. It should separate ocean products, sea-ice products, and
mapping, mask, and other analysis-support products into clearer subtasks or
step groups. It should also make the
selected ocean and sea-ice models explicit so MPAS-specific steps such as
graph partitioning and reconstruction-coefficient generation are included only
when those models are actually part of the target coupled configuration. In
particular, workflows involving Omega should not automatically inherit
MPAS-Ocean-specific packaging steps.

A requirement that is specific to unified meshes has also emerged since this
document was first written. Every mesh needs its base mesh — the mesh before
land or ocean culling — staged as an E3SM input in its own right. For unified
meshes, where one base mesh is culled to both the ocean and sea-ice domain and
the land and river domain, the staged base mesh must additionally carry index
maps from each base-mesh element to the corresponding element on each culled
component mesh, so that E3SM components sharing the base mesh can relate their
fields to one another without re-deriving the culling.

This design is successful if Polaris provides a cleanly named and inspectable
`e3sm/init` capability that can stage E3SM-compatible inputs for ocean,
sea-ice, and mesh-derived support assets; clearly separates shared products from
model-specific ones; uses outputs from ocean initialization and dynamic
adjustment through explicit dependencies; and leaves a straightforward path for
supporting both MPAS-Ocean-based and Omega-based coupled workflows.

The first branch has landed for MPAS-Ocean and MPAS-Seaice on unified meshes,
and has been run end to end on `u.oi240.lr240` and `u.oi30.lr10`, with
`u.oi6to18.lr6to10` and `u.oi.so12to30.lr10` following. Four things the
implementation changed are recorded in the sections below:

1. The MOC basin masks moved out of the analysis products and into the
   component inputs. MPAS-Ocean reads them at run time and says nothing when
   they are missing, which makes them a component input by the definition this
   document already uses.
2. The culled meshes are staged beside the base mesh in
   `share/meshes/mpas/unified/`, not under a component's own inputdata
   directory, and the sea-ice mesh is not staged at all.
3. The assembly step rebuilds its tree from empty each run, and offers a script
   for copying into an inputdata directory rather than doing it.
4. Graph partitioning grew a per-mesh bound and the ability to resume, both
   forced by the finest unified mesh.

Date last modified: 2026/08/13

### Implementation sequencing

This design describes the complete `component_inputs` capability. It is being
implemented over more than one development branch, and this section records
which parts land first. Nothing described in this document has been dropped.

The first branch covers the products that an E3SM *run* needs: the shared
base-mesh and SCRIP staging described above, the MPAS-Ocean mesh and
initial-condition files, the MPAS-Seaice initial-condition file, the ocean and
sea-ice graph partitions, and — added during implementation — the MOC basin
masks and southern-boundary transects.

The MOC masks were originally listed below as part of `diagnostic_masks`, with
the analysis products. They are not analysis products. E3SM points two streams
at a single per-mesh file, `regionalMasksInput` and `transectMasksInput`, and
two analysis members that are on by default read them: `mocStreamfunction`,
enabled per mesh and `.true.` for every mesh since `EC30to60E2r2`, and
`meridionalHeatTransport`, enabled for every mesh. With no file, `nRegions`
and `nRegionGroups` fall back to their Registry definition of 1, the MOC member
logs that its region group was not found, and the run continues, writing output
computed against a meaningless region. A missing input that announced itself
would be caught by a run; this one would not, which is why it belongs with the
products a run needs rather than with the products an analysis needs.

Only the `MOC Basins` group moved. The rest of `diagnostic_masks` stays with
the analysis products.

Follow-up branches will cover the products whose purpose is post-processing,
analysis, or forcing from remapped datasets: `diagnostic_maps`, the remainder
of `diagnostic_masks`, `e3sm_to_cmip_maps`, `remap_iceberg_climatology`,
`remap_ice_shelf_melt`, `add_total_iceberg_ice_shelf_melt`,
`remap_sea_surface_salinity_restoring`, `remap_tidal_mixing`, and
`write_coeffs_reconstruct`.

Where a section below describes work that a follow-up branch will do, it says
so. Those notes are about ordering; the requirements, algorithm design and
implementation guidance they accompany remain in force.

The first branch also covers unified meshes only, since those are the meshes
headed for E3SM. Nothing in the design is specific to unified meshes apart from
the base-to-culled index maps, so adding the simple base meshes later should be
a matter of registering more mesh names.

## Requirements

### Requirement: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Polaris shall provide this capability within the `e3sm/init` component rather
than the ocean component.

The workflow shall consume required inputs from upstream tasks through explicit
step dependencies and declared files rather than by assuming Compass-style
directory layouts.

The design shall treat the base mesh, the culled meshes and the culled
topography from `e3sm/init` as the authoritative source for horizontal
geometry, masks, and land-ice metadata.
The design shall consume the global-ocean initial condition and
dynamic-adjustment outputs as explicit sources for ocean packaging only.
Sea-ice packaging shall instead rely on `e3sm/init` products and quantities
that can be computed directly from them.
Mesh-derived support assets such as SCRIP files, mapping files, and masks
shall also remain in `e3sm/init` because they are generated from mesh and
topography products before any simulation is run, even when they are later
consumed by post-processing tools.

Because the upstream products are shared steps in the ocean component, every
ocean-side product that `component_inputs` consumes shall be reachable through
a shared-step accessor rather than through a task that constructs its steps
privately. In particular, the dynamic-adjustment stages shall be available as
shared steps so that the final adjusted restart can be declared as a
dependency.

### Requirement: Ocean, sea-ice, and mesh-derived support products can be generated independently

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Polaris shall separate the current mixed workflow into logically distinct
products for shared mesh assets, ocean, sea-ice, freshwater-forcing, and
mapping/mask support assets.

Users and developers shall be able to generate only the needed subset of
products for a given coupled configuration without having to run unrelated
steps. In particular, the shared mesh assets shall not require the ocean or
sea-ice products, because they are needed even for a mesh whose ocean initial
condition has not yet been produced.

The design may still provide a convenience task for producing the full bundle,
but that aggregate entry point shall be composed from smaller, more focused
tasks or step groups.

The first branch builds the shared mesh assets and the ocean and sea-ice
products; the freshwater-forcing and mapping/mask products arrive in follow-up
branches. The decomposition shall leave a place for them so that adding them
does not restructure the task family.

### Requirement: The staged base mesh carries maps to the culled component meshes

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Claude

Polaris shall stage the base mesh — the mesh as it exists before land or ocean
culling — as an E3SM input alongside the component-specific culled meshes. The
base mesh is a shared asset: it is not owned by the ocean or by the land, and
it shall be staged in a shared location rather than under a single component's
inputdata directory.

For unified meshes, where a single base mesh is culled to both the ocean and
sea-ice domain and the land and river domain, the staged base mesh shall carry
additional fields mapping each base-mesh element to the corresponding element
on each culled component mesh.

These maps shall be provided for cells, edges and vertices, and for each of the
culled meshes that `e3sm/init` produces: the ocean mesh including ice-shelf
cavities, the ocean mesh excluding cavities, and the land mesh.

Base-mesh elements that are absent from a given culled mesh shall be marked
with an unambiguous fill value rather than with a valid index, so that a
consumer can distinguish "not in this component's mesh" from "the first element
of this component's mesh".

The maps shall be a property of the staged base mesh rather than a separate
file, because their purpose is to make the staged base mesh self-describing for
E3SM components that share it.

The maps are not required for meshes that are not unified, since in that case
the ocean and land meshes do not share a base mesh and the maps carry no
information that E3SM would use. The design shall nonetheless keep the map
generation independent of the mesh family so that it can be enabled for other
meshes without redesign.

### Requirement: Model-specific packaging is gated by the selected component models

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall distinguish between shared products, MPAS-Ocean-specific
products, Omega-specific products, MPAS-Seaice-specific products, and
mesh-derived support products.

Steps that are specific to MPAS-Ocean, such as ocean graph partitioning or
`coeffs_reconstruct` generation, shall not be included when the selected ocean
model is Omega.

Similarly, steps that are specific to MPAS-Seaice, such as sea-ice graph
partitioning, shall only be included when MPAS-Seaice is part of the target
configuration.

### Requirement: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Polaris shall produce outputs that can be staged into an E3SM-compatible
directory structure for inputdata and related support products.

At the same time, the workflow shall preserve inspectable step-local products
so developers can examine intermediate files before they are staged into the
assembled directory tree.

The design shall favor clear, named products over a monolithic staging step
that hides where each file came from.

Staged filenames shall be built from an E3SM mesh short name and a creation
date. Polaris mesh names such as `u.oi30.lr10` describe how a mesh was built
and are not the names E3SM uses, so the short name shall be an explicit config
option that the user is required to set before the workflow can be set up. The
workflow shall fail with a clear message when it is unset rather than guessing
a name or reading one out of a restart file's global attributes, as Compass
does.

The assembled tree shall place shared mesh assets under a shared meshes
directory rather than under the ocean's or the land's inputdata directory,
reflecting that the base mesh belongs to no single component.

### Requirement: Required remapped forcing and mesh-derived support assets are supported

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The port shall support the freshwater-forcing and mesh-derived support assets
currently produced by the Compass workflow, to the extent that they remain
relevant to the selected component models.

This includes ocean and sea-ice inputs derived from remapped observational or
climatological datasets, SCRIP files, mapping files, and mask products used by
MPAS-Analysis, `e3sm_to_cmip`, runtime analysis members, or related workflows.

Features that depend on ice-shelf cavities or land-ice forcing shall remain
conditional on the mesh and workflow configuration rather than being treated as
unconditional outputs.

Of these assets, the SCRIP descriptions of the culled meshes are the ones the
first branch stages. They are staged because a mesh is not usable in E3SM until
coupler mapping and domain files can be generated from it, and because the
`e3sm/init` cull workflow already produces them, so staging is bookkeeping
rather than new computation.

The remapped forcing datasets and the analysis-oriented mapping and mask
products arrive in follow-up branches. This requirement covers all of them and
remains in force; the ordering note says only when each is built.

### Requirement: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The design shall avoid hard-coding assumptions that coupled E3SM always uses
MPAS-Ocean plus MPAS-Seaice.

It shall remain possible to support future combinations of ocean and sea-ice
models, new support assets, or revised staging conventions without
rewriting the full workflow.

## Algorithm Design

### Algorithm Design: Component-input generation lives in `e3sm/init` and consumes explicit upstream products

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The workflow should be organized around explicit source products rather than a
single inherited Compass test case. Now that the upstream workflows exist, the
set of upstream inputs can be named concretely. From the `e3sm/init` cull-mesh
step:

1. The unculled base mesh, `base_mesh.nc`, taken from the base-mesh step that
   the cull step itself consumes.
2. The culled meshes `culled_ocean_mesh.nc`,
   `culled_ocean_no_cavities_mesh.nc` and `culled_land_mesh.nc`.
3. The culled-to-base index maps `{prefix}_map_culled_to_base.nc` for each of
   those meshes.
4. The SCRIP descriptions `culled_{prefix}_mesh.scrip.nc`.
5. The ocean graph files `culled_ocean_graph.info` and
   `culled_ocean_no_cavities_graph.info`.

From the `e3sm/init` cull-mask step and the ocean workflows:

6. Cull masks and land-ice metadata, for products that need to know which
   base-mesh elements were removed and which cells are under an ice shelf.
7. The final dynamic-adjustment restart for the selected ocean model, which is
   the source for the packaged ocean initial condition.

The packaging logic should make the source for each product explicit. Mesh
products should come from the cull step, ocean initial conditions from the
final dynamic-adjustment restart, and sea-ice products from the culled ocean
mesh plus quantities recomputed from it.

This explicit source mapping is important because the current Compass workflow
mixes `base_mesh.nc`, `initial_state.nc`, and `restart.nc` in ways that are
convenient but not obvious when viewed from outside the code. A concrete
example is the sea-ice initial condition, which in Compass reads `fCell`,
`fEdge` and `fVertex` out of an MPAS-Ocean restart file. Those are functions of
latitude alone, so the Polaris sea-ice step should compute them from the culled
mesh and avoid the dependency on the ocean entirely.

### Algorithm Design: Ocean, sea-ice, and mesh-derived support products can be generated independently

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The port should decompose the existing workflow into a small family of tasks or
task modes under `e3sm/init/component_inputs`. A practical decomposition is:

1. `shared`: stage the base mesh, its base-to-culled index maps, and the SCRIP
   descriptions of the culled meshes. These are the assets that belong to no
   single component.
2. `ocean`: produce ocean-model input assets and ocean-specific forcing
   datasets.
3. `seaice`: produce sea-ice-model input assets.
4. `forcing_from_dataset/freshwater`: produce remapped iceberg and ice-shelf freshwater
   products that may later be staged for ocean or sea-ice components
   (follow-up branch).
5. `mapping_and_masks`: produce mapping files, masks, and other mesh-derived
   support assets used by analysis workflows or runtime features (follow-up
   branch).
6. `all`: an optional aggregate task that instantiates the needed subset of the
   above for a standard coupled configuration.

The `shared` group starts as a set of steps rather than a separately runnable
task: both `ocean` and `seaice` need the staged base mesh, so both include
those steps, and Polaris' shared-step machinery means they are built once.
Promoting the group to its own task later, so a mesh can be staged before any
ocean initial condition exists, should not require restructuring anything else.

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
5. Shared-asset-only regeneration after a mesh or metadata change.
6. Mapping-and-mask-only regeneration after a mesh or metadata change.

### Algorithm Design: The staged base mesh carries maps to the culled component meshes

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Claude

The `e3sm/init` cull-mesh step already writes, for each culled mesh, a
`{prefix}_map_culled_to_base.nc` file containing `mapCulledToBaseCell`,
`mapCulledToBaseEdge` and `mapCulledToBaseVertex`. Each of these is indexed by
the culled mesh's dimension and holds the zero-based index of the corresponding
element on the base mesh. The maps required here are the inverse: indexed by
the base mesh's dimension, holding the index of the corresponding element on
the culled mesh.

Inverting the existing maps is preferable to recomputing the correspondence
from scratch. The forward maps are already an output of a step that
`component_inputs` depends on, they were built by a nearest-element query that
is far more expensive than a scatter, and reusing them guarantees that the two
directions agree by construction. The inversion is a scatter: allocate an array
over the base-mesh dimension filled with the "absent" marker, then assign the
culled index at each position named by the forward map.

The staged fields should follow MPAS conventions and be one-based, with zero
meaning that the base-mesh element is not present on that culled mesh. This
matches how MPAS index variables such as `cellsOnCell` already signal a missing
neighbor, so a consumer does not need to learn a new convention, and it leaves
the meaning of every value unambiguous. Note that this differs from the
zero-based convention of the upstream `mapCulledToBase*` fields, which are
intended for direct use as array indices in Python; the difference should be
stated explicitly wherever the new fields are documented.

Names should identify the target mesh and the element type, following the
pattern `mapBaseTo<Target><Element>` — for example `mapBaseToOceanCell`,
`mapBaseToOceanNoCavitiesEdge` and `mapBaseToLandVertex`. Nine fields result:
three target meshes by three element types.

The fields should be written into a copy of the base mesh rather than into the
cull step's own `base_mesh.nc`, so that the cull step's outputs stay exactly
what its own design says they are, and so that the staged file is a single
self-describing artifact.

### Algorithm Design: Model-specific packaging is gated by the selected component models

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The workflow should first classify each product as shared or model-specific.
A useful starting point is:

1. Shared or nearly shared products:
   the staged base mesh and its base-to-culled maps, SCRIP files,
   freshwater-forcing products, and mapping or mask inputs that depend
   primarily on the horizontal mesh.
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

From a framework point of view, this should be treated as another case of
task structure depending on setup-time choices, similar in spirit to Polaris
tasks that rebuild step lists from config-driven resolution choices. The main
requirement is simply that model selection be resolved before task setup is
finalized.

To support Omega cleanly, shared steps should consume a model-neutral mesh or
state representation wherever possible rather than assuming that every product
must be derived from an MPAS restart file.

### Algorithm Design: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

The design should separate product generation from final staging. A likely
pattern is:

1. Each generation step writes one or more well-named local products.
2. A staging step or shared helper assembles those products into an
   `assembled_files` tree with E3SM-compatible paths and filenames by mapping
   each declared product to its final relative path under `inputdata/` or the
   diagnostics tree.
3. That assembly should usually be implemented by registering the upstream
   products as inputs to the staging step and materializing symlinks in
   `assembled_files`, using copies only for products that genuinely need to be
   rewritten or duplicated.

This keeps the provenance of each generated file clear while still preserving
compatibility with the inputdata and diagnostics layouts expected by E3SM
developers.

It also provides a better foundation for future changes such as alternate
staging locations, publication workflows, or checksum manifests.

The staged layout follows the E3SM inputdata tree. Writing `<short>` for the
configured mesh short name, `<date>` for the creation date and `<features>` for
the `geometric_features` aggregation date:

1. `inputdata/share/meshes/mpas/unified/<short>.base.<date>.nc` — the base mesh
   with its base-to-culled index maps. Compass staged the base mesh under
   `share/meshes/mpas/ocean`, but for a unified mesh the base mesh is shared by
   the ocean, sea-ice, land and river components, so a component-neutral
   directory is the honest location.
2. `inputdata/share/meshes/mpas/unified/<short>.<region>.scrip.<date>.nc` — the
   SCRIP descriptions of the culled meshes, for the same reason.
3. `inputdata/share/meshes/mpas/unified/<short>.ocean.<date>.nc` and
   `<short>.land.<date>.nc` — the culled meshes themselves, beside the base
   mesh for the same reason again.
4. `inputdata/ocn/mpas-o/<short>/mpaso.<short>.<date>.nc` — the ocean initial
   condition, with graph partitions under `partitions/`.
5. `inputdata/ocn/mpas-o/<short>/<short>.mocBasinsAndTransects<features>.<date>.nc`
   — the MOC basin masks and southern-boundary transects.
6. `inputdata/ocn/mpas-o/<short>/<short>.scrip.<date>.nc` and
   `<short>.no_cavities.scrip.<date>.nc` — the two ocean SCRIP files again.
7. `inputdata/ice/mpas-seaice/<short>/mpassi.<short>.<date>.nc` — the sea-ice
   initial condition, with graph partitions under `partitions/`.

Three of these differ from what this document first described, and each
difference is a decision worth keeping.

**Meshes go where E3SM keeps meshes.** The first implementation staged the
ocean mesh as `inputdata/ocn/mpas-o/<short>/<short>.<date>.nc`, which is
nowhere E3SM looks for one: Compass files its ocean mesh under
`share/meshes/mpas/ocean/`, and a run reads the mesh from the initial
condition. A culled mesh describes a domain of the unified mesh rather than a
file one component reads, which is the same argument that puts the base mesh in
`share/meshes`. The land mesh is staged too, since staging the ocean mesh alone
would describe half the mesh.

**No sea-ice mesh is staged.** `seaice_mesh` is built from
`culled_ocean_mesh.nc`, so a `.seaice.` file beside `<short>.ocean.<date>.nc`
would be the same horizontal mesh twice, and MPAS-Seaice reads its mesh from
its initial condition. The step remains, because the graph-partition steps read
its output; only the staging is dropped. No mesh is staged for
`ocean_no_cavities` either: it exists to build mapping files, and under the
`calving_front` convention every current unified mesh uses it is identical to
the ocean mesh.

**The two ocean SCRIP files are staged twice.** Once in the shared mesh
directory under their full region names, and once beside the ocean products,
because developers look in both places and the shared directory holds every
unified mesh. In an ocean directory the `ocean` in a region name says nothing,
so it is dropped; `no_cavities` stays, being the whole distinction. Land has no
copy there. Both names link to the same file.

The MOC mask filename carries two dates because two things change
independently: `<features>` is the version of the `geometric_features`
aggregation the basins come from, upstream data shared by every mesh, and
`<date>` is when this mesh's file was staged. The aggregation date rides with
the product name, as it does in the files already on the inputdata server
(`oRRS18to6v3_mocBasinsAndTransects20210623.nc`), which keeps the rule that the
last dotted field of any staged filename is its creation date. Both dates are
also written into the file as global attributes, so the provenance survives a
copy or a rename.

The assembly step deletes `assembled_files/` and rebuilds it on every run.
Staging only ever adds links, so without this the tree is the union of every
assembly ever run in that work directory: a changed creation date, mesh short
name or product set leaves the earlier names in place, still resolving, now
pointing at newer content. This was not hypothetical — a re-setup restamped the
creation date and a tree ended up holding two dates side by side, with an
initial condition wearing the wrong one.

Copying the tree into an inputdata directory is left to a person. The step
symlinks in a `sync_to_inputdata.sh` script that rsyncs the tree with
`--ignore-existing --copy-links` into a destination that must already exist,
then sets directories to `775` and files to `664` on the paths the tree
contributes — not by walking a shared destination, which would touch files
belonging to other meshes and other people.

The mesh short name is a required config option rather than a value read from a
restart file. Polaris mesh names describe construction (`u.oi30.lr10` says what
resolutions went into the mesh) whereas E3SM short names identify a released
mesh, and only a person can decide when a mesh has earned one. Setup should
fail with a message naming the option when it is unset, so the failure comes
before hours of computing rather than at staging time.

A `README` should be staged alongside the assembled tree, as in Compass,
stating that the tree is a subset of what E3SM needs for a new mesh and should
not be uploaded on its own.

### Algorithm Design: Required remapped forcing and mesh-derived support assets are supported

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

The remapping and support-asset portion of the port should be divided by product
type rather than forcing all remapped fields into ocean or sea-ice ownership.
A likely grouping is:

1. Ocean-specific forcing assets:
   sea-surface salinity restoring and tidal mixing.
2. Freshwater-forcing assets:
   remapped iceberg climatology, remapped ice-shelf melt, and combined
   freshwater products derived from those fields.
3. Mapping and mask support assets:
   E3SM-to-CMIP maps, region masks, transect masks, and other files consumed by
   MPAS-Analysis, `e3sm_to_cmip`, or comparable workflows. The MOC basin masks
   left this group during implementation: MPAS-Ocean reads them at run time, so
   they are a component input rather than an analysis product. See
   "Implementation sequencing" above.
4. Shared mesh descriptions:
   the SCRIP files for the culled meshes.

The fourth group is separated from the third because the SCRIP files are unlike
the rest of that list: they describe the mesh itself rather than a set of
analysis regions, they are already produced by the `e3sm/init` cull step, and
they are needed before coupler mapping and domain files can be generated at
all. That makes them part of what a mesh needs in order to be usable, not part
of what an analysis needs in order to be interpreted. They are staged in the
first branch; the other three groups follow later.

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

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The first implementation should add a new package under
`polaris/tasks/e3sm/init/component_inputs`. The package should be structured as
an `e3sm/init` capability from the start rather than first porting the Compass
layout into the ocean component and moving it later.

The implementation should define clear step inputs for:

1. The base mesh, culled meshes, culled-to-base maps, SCRIP files, graph files
   and topography products from `e3sm/init`.
2. The ocean initial-condition output from the global-ocean init workflow
   (a single model, selected by `[ocean] model`).
3. The final dynamic-adjustment restart for that same model, when present.

For common coupled workflows, the final dynamic-adjustment restart should be
the default source for packaged ocean initial-condition files. Sea-ice steps
should not use that restart as an input. Instead, they should consume the
culled mesh, `landIceMask` and related masks from `e3sm/init`, and any
topography-derived metadata needed for sea-ice packaging.

The `e3sm/init` products are reached through
`polaris.tasks.e3sm.init.topo.cull.steps.get_cull_topo_steps`, which returns
the cull-mask and cull-mesh steps along with the whole upstream remap chain.
The ocean products need an equivalent shared-step accessor for the
dynamic-adjustment stages, since the `RealisticGlobalDynamicAdjustment` task
currently builds its `Forward` stages privately and they cannot be depended on
from another task. Adding that accessor belongs to the upstream
dynamic-adjustment work, not to `component_inputs`; this design assumes it is
in place.

Because `component_inputs` lives in `e3sm/init` and consumes ocean products,
while `polaris.tasks.ocean.realistic_global` consumes `e3sm/init` cull
products, the import graph must be kept acyclic. It is, as long as
`component_inputs` imports from `polaris.tasks.ocean.*` and nothing under
`polaris.tasks.ocean` imports `component_inputs`: `polaris.tasks.e3sm.init` is
fully loaded before any `add_*_tasks` function runs. The direction of that
dependency should be stated in the module docstring so it is not reversed by
accident.

### Implementation: Ocean, sea-ice, and mesh-derived support products can be generated independently

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

The full implementation adds four concrete tasks and one optional aggregate
task:

1. `component_inputs/ocean`
2. `component_inputs/seaice`
3. `component_inputs/forcing_from_dataset/freshwater`
4. `component_inputs/mapping_and_masks`
5. `component_inputs/all`

The first branch builds tasks 1, 2 and 5, each per mesh, under
`e3sm/init/<mesh_name>/component_inputs/<task>`. Tasks 3 and 4 follow later.

Each task should consist of inspectable steps with narrow responsibilities.
One reasonable first-pass mapping from Compass is:

1. Shared steps, included by both the ocean and sea-ice tasks:
   `base_mesh` (the staged base mesh with base-to-culled maps), `scrip`, and
   `assemble` (the staging step).
2. Ocean steps:
   `ocean_mesh`, `ocean_initial_condition`, `ocean_graph_partition` when
   relevant, `moc_masks`,
   `remap_sea_surface_salinity_restoring`, and `remap_tidal_mixing`.
3. Sea-ice steps:
   `seaice_mesh`, `seaice_initial_condition`, `seaice_partition_map` and
   `seaice_graph_partition` when relevant.
4. Freshwater-forcing steps:
   `remap_iceberg_climatology`, `remap_ice_shelf_melt`, and
   `add_total_iceberg_ice_shelf_melt`.
5. Mapping-and-mask support steps:
   `e3sm_to_cmip_maps`, `diagnostic_maps`, `diagnostic_masks`, and
   `write_coeffs_reconstruct` when relevant.

Groups 1, 2 and 3 are the first branch; groups 4 and 5 follow later.

Two of these steps were not in the first-pass mapping. `moc_masks` is the MOC
basin masks discussed above. `seaice_partition_map` is the sea-ice partitioning
split in two: building the QU60km-to-mesh weights is an MPI job sized for the
mapping tool, while using them is serial, which is the same division
`realistic_global` makes between `Woa23MapStep` and `RemapWoa23Step`.

`moc_masks` takes its masks from the mesh component's feature-mask step and the
MOC-specific behavior — the `mocBasinsAndTransects` filename and the
southern-boundary transects — from a leaf module in the region-mask framework
that the ocean feature-mask step uses too. Subclassing the *ocean* feature-mask
step, which is where that behavior first lived, does not work from `e3sm/init`:
it inherits `OceanIOStep` to translate Omega's variable names, which reads
`[ocean] model`, and a `component_inputs` config has no `[ocean]` section by
design. Moving the shared behavior into a model-agnostic module was the fix;
overriding the I/O hooks one at a time was not, since `[ocean] model` is read
in four places along that inheritance path.

The exact grouping can evolve during implementation, but the first port should
avoid recreating the full Compass workflow as a single task class.

Within this first-pass mapping, the sea-ice and freshwater-forcing steps
should be implemented so they consume `e3sm/init` products directly rather
than outputs from the ocean subtask. Concretely, `seaice_mesh` should be built
from `culled_ocean_mesh.nc` and `seaice_initial_condition` should compute
`fCell`, `fEdge` and `fVertex` from the mesh's latitudes rather than copying
them out of an ocean restart, as Compass does.

### Implementation: The staged base mesh carries maps to the culled component meshes

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Claude

A `base_mesh` step under `component_inputs` should take as inputs the cull
step's `base_mesh.nc`, its three culled meshes, and its three
`{prefix}_map_culled_to_base.nc` files, and write a single
`base_mesh_with_maps.nc`.

The inversion itself is small enough to belong in a shared helper rather than
inside the step, so that it can be unit-tested without a work directory. A
function such as `map_base_to_culled(ds_map_culled_to_base, n_base)` returning
the nine one-based fields keeps the step to reading, calling and writing.

For each of the three culled meshes and each of cells, edges and vertices:

1. Read `mapCulledToBase{Element}`, whose values are zero-based base-mesh
   indices, one per culled element.
2. Allocate an array of length `n{Element}` on the base mesh, filled with zero.
3. Scatter: at each base index named in the forward map, store the one-based
   culled index (the position in the forward map, plus one).
4. Write the result as `mapBaseTo{Target}{Element}`, with a `long_name`
   recording both the target mesh and the one-based-with-zero-for-absent
   convention, so that the convention travels with the file.

The `nCells`, `nEdges` and `nVertices` dimensions of the output are those of
the base mesh, not of any culled mesh, which is what makes the fields
attachable to the base mesh in the first place.

Two properties are worth asserting rather than assuming, since a silent failure
here would produce a plausible-looking but wrong file: every value in the
forward map must be a valid base-mesh index, and no base index may appear
twice in one forward map. Both hold for a culled mesh derived from the base
mesh, so a violation means the two inputs do not belong together — most likely
a stale file from a previous mesh.

Whether to write the maps is decided from the mesh family: unified meshes get
them, and the helper is written so that enabling them for other meshes is a
matter of passing a flag rather than of changing the algorithm.

### Implementation: Model-specific packaging is gated by the selected component models

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The new task family should include explicit model selection in config or task
construction, for example through values conceptually like:

1. `ocean_model = mpas-ocean`, `omega` or `none`
2. `seaice_model = mpas-seaice` or `none`

The implementation should then construct the needed steps from a product
matrix. For example:

1. If `ocean_model = mpas-ocean`, include `ocean_mesh`,
   `ocean_initial_condition`, `ocean_graph_partition`, and
   `write_coeffs_reconstruct` as appropriate.
2. If `ocean_model = omega`, replace the MPAS-Ocean packaging step with an
   Omega-specific ocean packaging step and exclude MPAS-Ocean graph partition
   and reconstruction-coefficient steps.
3. If `seaice_model = mpas-seaice`, include `seaice_mesh`,
   `seaice_initial_condition`, and `seaice_graph_partition`, all driven from
   `e3sm/init` mesh and mask products.
4. If freshwater-forcing products are requested, include
   `component_inputs/forcing_from_dataset/freshwater`, independent of whether the final
   staged files are destined for ocean or sea-ice inputdata locations.
5. If `seaice_model = none`, exclude the sea-ice task entirely.

If the selected models come from config options that users may override at
setup time, the task should follow the same Polaris pattern used for other
dynamic task layouts: define the initial task structure in `__init__()` where
possible, then remove and re-add only the model-dependent steps in
`configure()` after config overrides have been applied. Shared steps whose
inputs and outputs do not depend on the selected models should remain stable so
that `configure()` is only responsible for the parts of the step graph that
actually vary.

This implementation should make the "Omega should not inherit MPAS-only
steps" rule a first-class part of the design rather than an afterthought.

Since Omega is not yet ready for full E3SM support, the first branch implements
the `mpas-ocean` and `mpas-seaice` arms of this matrix. The gating itself is
still built now, and an Omega selection should fail with a message saying the
packaging is not yet implemented rather than silently producing MPAS-Ocean
files. That way the branch that adds Omega support fills in a named gap instead
of retrofitting model selection into steps that assumed MPAS.

### Implementation: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

The existing `FilesForE3SMStep` base class mixes metadata discovery, file
validation, directory creation, NetCDF writing, and staging. In Polaris, these
concerns should be separated more cleanly.

A better pattern is:

1. Shared helpers for metadata and filename conventions.
2. Product-generation steps that only create their own outputs.
3. A final assembly step that takes those declared outputs as inputs and
   populates `assembled_files` with the expected directory structure, usually
   by issuing `add_input_file()` calls for each staged product and giving each
   one its E3SM-facing filename and location.

In other words, the final step should mostly be bookkeeping and staging rather
than scientific processing: it should create the `inputdata/ocn/...`,
`inputdata/ice/...`, and support-asset subdirectories, link in outputs from
the relevant upstream steps, and keep the generated files in those upstream
step directories so they remain easy to inspect.

This pattern would make product provenance clearer and would also reduce the
amount of duplicated setup logic across steps.

Concretely, the filename convention belongs in one leaf module — something like
`component_inputs/names.py` — holding the mesh short name, creation date and
cavity flag read from config, plus one function per staged product returning
its E3SM-facing relative path. Every step and the assembly step then agree on
names by construction. Because the module is dependency-light, the naming rules
can be unit-tested without building any step.

Two behaviors of the Compass base class should not be carried over. It
autodetects the mesh short name and creation date from restart-file global
attributes, which is what makes staged filenames hard to predict at setup time;
both should instead be config options, with the short name required. It also
performs the staging inside each product step via `symlink()` calls, which is
what makes the `assembled_files` tree hard to reason about; staging should
happen only in the assembly step.

The `[component_inputs]` config section therefore carries `mesh_short_name`
(no default; setup fails if unset), `creation_date` (filled in with today's
date at setup and then recorded, so re-running does not silently rename files),
`ocean_model`, `seaice_model`, the graph-partition core-count bounds
`max_cells_per_core` and `min_cells_per_core`, and `plot_seaice_partitions`.

`creation_date` is filled in only when blank, which protects a re-run but not a
fresh setup: rebuilding the work directory's config stamps today's date. Pin
the option in a user config when a stamp needs to survive a re-setup.

Unified meshes register their short name as `[unified_mesh] e3sm_short_name` in
the per-mesh config, with `mesh_short_name` left as an override. The mesh with
no plans to reach E3SM master is registered under a deliberately invalid
placeholder ID, so a file staged for it is self-evidently a test artifact.

The core-count bounds are also per-mesh where they need to be. `gpmetis` fails
above roughly 750,000 parts, and the largest partition asked for is
`ncells / min_cells_per_core`, so a mesh above about 1.5 million ocean cells
needs the floor raised. `u.oi6to18.lr6to10` is the only unified mesh that large
and sets `min_cells_per_core = 6`, exactly as Compass does for `rrs6to18` and
for the same reason. The port brought Compass' `get_core_list` across verbatim
but not the per-mesh config that made it usable at that resolution.

Both partition steps resume. Partitioning the finest mesh takes most of a day,
and a job that runs out of walltime must cost only the partitions it was in the
middle of. A partition file counts as finished when it has one line per cell —
existence alone is not enough, since a kill mid-write leaves a file covering
part of the mesh, and trusting it would hand E3SM a broken partition.

### Implementation: Required remapped forcing and mesh-derived support assets are supported

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

The port should include the existing remapped datasets that are still needed
for E3SM workflows, but it should evaluate them product by product rather than
assuming they all belong to the ocean or sea-ice tasks.

In particular:

1. `remap_ice_shelf_melt` should remain conditional on cavity workflows and
   should not run for open-ocean meshes without cavities.
2. `remap_iceberg_climatology`, `remap_ice_shelf_melt`, and
   `add_total_iceberg_ice_shelf_melt` should live in a neutral
   `forcing_from_dataset/freshwater` subtask because they conceptually describe a shared
   freshwater source rather than belonging cleanly to ocean or sea-ice.
3. `diagnostic_masks` and `diagnostic_maps` should be treated as mesh-derived
   support assets, even if they continue to rely on MPAS-oriented tooling
   initially.
4. `scrip` and E3SM-to-CMIP mapping support should be implemented so they can
   remain shared across MPAS-Ocean and Omega when they depend only on the
   horizontal mesh description.
5. The `forcing_from_dataset/freshwater` subtask should use `landIceMask` and other
   cull-mask products from `e3sm/init` rather than reading them from ocean
   initial-condition or restart files.

Of these, item 4's `scrip` half is what the first branch implements, and it is
smaller in Polaris than in Compass. Compass regenerates SCRIP files from
`restart.nc` with `scrip_from_mpas`; the Polaris cull step already writes
`culled_{prefix}_mesh.scrip.nc` for the ocean, no-cavities ocean and land
meshes, so the step reduces to staging existing files under their E3SM-facing
names. Items 1, 2, 3 and the E3SM-to-CMIP half of item 4 come in follow-up
branches.

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

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Integration tests should verify that the new `e3sm/init/component_inputs`
tasks can consume outputs from the `e3sm/init` cull workflow and the new
global-ocean init and dynamic-adjustment workflows through declared inputs.

These tests should avoid hidden dependence on Compass-style work-directory
layout.

They should also verify that the sea-ice task can run without requiring the
ocean task, as long as the necessary `e3sm/init` mesh and mask products are
available. The sea-ice task's step list should contain no step from the ocean
task and no dependency on a dynamic-adjustment restart; asserting that
directly is a better guard than checking that it happens to run, since the
coupling this design removes is exactly the kind that creeps back in as a
convenient input file.

A test should also confirm that the ocean task's initial-condition step depends
on the final dynamic-adjustment stage's restart, and that both tasks reuse the
same shared cull steps rather than creating parallel copies.

### Testing and Validation: Ocean, sea-ice, and mesh-derived support products can be generated independently

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Regression tests should exercise at least:

1. An ocean-only configuration.
2. A sea-ice-only configuration.
3. A freshwater-forcing-only configuration.
4. A mapping-and-mask-only configuration.
5. A full aggregate configuration.

This testing will help ensure the decomposition remains real rather than
allowing hidden coupling between the subtasks to creep back in.

Cases 1, 2 and 5 are testable as soon as the first branch lands; cases 3 and 4
arrive with the tasks they exercise.

### Testing and Validation: The staged base mesh carries maps to the culled component meshes

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Claude

The inversion helper should be unit-tested against a hand-built forward map
small enough to check by inspection, confirming that present elements get
one-based culled indices, that absent elements get zero, and that a map
covering every base element round-trips exactly.

The strongest available check is that the two directions compose to the
identity: for every culled element `i`, `mapBaseTo*[mapCulledToBase*[i]]`
must equal `i + 1`. This should be asserted in a unit test on synthetic maps
and again as a check on real cull-step output, since it catches an off-by-one
or a transposed scatter that eyeballing the file would not.

Tests should also confirm the shapes — the map fields are dimensioned by the
base mesh, not by any culled mesh — and that the malformed-input assertions
fire when given a forward map with an out-of-range or duplicated base index.

Finally, a test should confirm that the maps are written for a unified mesh and
that the mesh-family gate is what decides it, so the condition does not quietly
become "always" or "never".

Checked on real output for `u.oi240.lr240` and `u.oi.so12to30.lr10`, the latter
a 2,279,641-cell base mesh: the round trip is exact for all nine fields, the
nonzero count equals the culled element count, and zeros fall exactly off the
culled mesh. Two results were sharper than expected, both consequences of the
cull-mask invariants that arrived with the land-locked cell work. The ocean and
`ocean_no_cavities` maps are *identical*, which is the `calving_front` equality
those invariants imply rather than something asserted directly. And cells
partition exactly into ocean and land, while edges and vertices deliberately do
not: the coastline ones belong to both meshes — 1,795 of each on
`u.oi240.lr240`, 29,430 of each on `u.oi.so12to30.lr10` — and none are
orphaned. Equal boundary edge and vertex counts are what a coastline of closed
loops must give.

### Testing and Validation: Model-specific packaging is gated by the selected component models

Date last modified: 2026/08/05

Contributors: Xylar Asay-Davis, Codex, Claude

Unit or lightweight integration tests should verify the product matrix for
several model combinations, especially:

1. MPAS-Ocean plus MPAS-Seaice.
2. Omega plus MPAS-Seaice.
3. Omega with no sea-ice component.

These tests should confirm that MPAS-Ocean-only steps such as graph partition
and `coeffs_reconstruct` are absent from Omega configurations.
They should also confirm that changing the configured models at setup time
causes the task to rebuild the model-dependent portion of its step list
correctly, without perturbing shared steps unnecessarily.

Until Omega packaging exists, cases 2 and 3 test that selecting Omega raises a
clear not-implemented error rather than that it produces files. That is still
worth testing, because the failure it rules out — Omega silently inheriting
MPAS-Ocean packaging — is the one this requirement exists to prevent.

### Testing and Validation: The workflow produces E3SM-compatible staged outputs while retaining inspectable intermediate files

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

Regression testing should confirm both that expected staged files appear in the
assembled directory tree and that the step-local source products are present
with predictable names.

This validation should include at least a few representative filenames from
the ocean, sea-ice, and support-asset categories.

Because the naming rules live in a dependency-light module, the mapping from
product to E3SM-facing path should be unit-tested directly, including that a
missing `mesh_short_name` raises at setup with a message naming the option.
This is worth testing rather than assuming: the failure mode it guards against
is a mesh staged under a placeholder name after the expensive steps have
already run.

The assembly test runs the step over stand-in products and compares the whole
staged tree against the expected set, rather than checking a few representative
names. That is what caught the ocean mesh being staged where E3SM does not look
for it, and it is why adding a product now means stating where it lands.

Two behaviors need tests of their own because they are about what is *not*
there. Assembling twice under different creation dates must leave nothing from
the first, which is the tree-rebuilt-from-empty rule. And a re-run of a
partition step must rebuild a truncated partition file while skipping the
finished ones, since the failure that rule guards against — a file that exists
but covers half the mesh — is indistinguishable from success by an existence
check.

Verified on the staged trees themselves for three meshes: every product at its
expected path, every link resolving, one creation date across every filename,
and nothing staged outside the table above.

### Testing and Validation: Required remapped forcing and mesh-derived support assets are supported

Date last modified: 2026/08/13

Contributors: Xylar Asay-Davis, Codex, Claude

Tests should verify that each supported remapped dataset and support asset is
either produced when relevant or cleanly omitted when its prerequisites are
not part of the selected workflow.

Cavity-dependent products should be tested separately from open-ocean meshes so
their conditional behavior remains explicit and correct.

In the first branch this reduces to the SCRIP staging and the MOC masks. Tests
confirm that each culled mesh's SCRIP file is staged under its E3SM-facing name
in the shared mesh directory, that the two ocean ones are staged again beside
the ocean products under their shortened names and resolve to the same files,
and that the land SCRIP has no copy there. For the MOC masks, tests confirm
that they are built from the culled ocean mesh, that they are an ocean-only
product, that the filename and the southern-boundary transects come from the
shared helpers rather than a copy of them, and that the step reaches for no
ocean component — the last being a regression test for the coupling that broke
the first attempt.

The masks were also checked against what MPAS-Ocean actually reads: all eleven
variables of the two streams are present, with five basins and their
southern-boundary transects carrying signs of -1, 0 and +1.

The remaining datasets are tested as the branches that add them land.

### Testing and Validation: The design preserves a path for future coupled-model evolution

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The code structure should be reviewed with the same criterion as the design:
adding a new component model or a new staged product should require extending a
small interface or product table, not cloning the entire task family.
