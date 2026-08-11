# Realistic Ocean Initial Conditions

Creation date: 2026/03/22

Contributors: Xylar Asay-Davis, Codex, Claude

## Summary

This design document describes a new Polaris capability for generating realistic
ocean initial conditions in Python, starting from an ocean mesh and topography
that have already been culled by the `e3sm/init` workflow. This capability
belongs to the `ocean/spherical/realistic_global` framework, which collects task families focused
on observationally-constrained ocean initialization and evaluation, in contrast
to the idealized task families elsewhere in the ocean component. The intent is to
port the required functionality from the MPAS-Ocean init mode, especially
`mpas_ocn_init_global_ocean.F`, and from the Compass workflows in
`compass/ocean/tests/global_ocean/init` and
`compass/ocean/tests/utility/extrap_woa`.

Each task initializes the single ocean model selected by the `[ocean] model`
config option (resolved to `omega` or `mpas-ocean` during component setup).
The new workflow produces scientifically consistent initial conditions for the
configured model. In the first phase, the same capability supports MPAS-Ocean
tracers based on potential temperature and practical salinity and Omega tracers
based on conservative temperature and absolute salinity. The initial phase does
not need to support ice-shelf cavities, Haney-number vertical coordinates under
ice shelves, or SSH adjustment below ice shelves, but the design should preserve
a clean path to add those features later.

A key challenge specific to the Omega p-star coordinate is that the
geometric seafloor depth cannot be prescribed directly: `BottomPressure` (related
to the pseudo-height of the seafloor) must be found iteratively so that the geometric
depth recovered from the coordinate matches observed bathymetry. Because CT and
SA must be initialized on the p-star grid before specific volume can be
evaluated, the vertical coordinate and the tracer state are tightly coupled. The
algorithm for this joint initialization is described in the companion design
document [pstar_init.md](pstar_init.md). Its existence means the vertical
coordinate and tracer initial state cannot be produced in isolation from each
other; the decomposition into Polaris steps must reflect this coupling.

Because the p-star iteration is model-independent — the converged geometric
vertical grid depends only on bathymetry and hydrography, not on which ocean
model is the final target — running the task for different models on the same
mesh and hydrography produces the same geometric layer thicknesses. This makes
direct model comparison possible by running the task once per model: the
geometric grids at initialization will be identical, and differences in
simulated state can be attributed to model formulation rather than to different
initial geometries. The p-star iteration runs even when the configured model is
MPAS-Ocean; there is no separate z-star path.

The Polaris ocean framework separates model inputs across staged files: a
horizontal mesh file (`mesh.nc`), a vertical coordinate file (`vert_coord.nc`;
Omega only), an initial-state file (`init.nc`) and — added after this document
was first written — a surface-forcing file (`forcing.nc`), described under
[Wind forcing](#wind-forcing). The realistic init workflow writes all of them,
through the framework's `write_horiz_mesh_dataset`, `write_vert_coord_dataset`,
`write_initial_state_dataset` and `write_forcing_dataset` helpers. The
horizontal geometry is entirely the upstream `e3sm/init` cull workflow's;
`mesh.nc` is that culled mesh with the fields the model's mesh stream needs but
the cull step does not produce. For MPAS-Ocean, `write_vert_coord_dataset` is a
no-op and the vertical coordinate variables remain in `init.nc`.

The primary software challenges are to replace a large, monolithic Fortran
workflow with an inspectable sequence of Polaris steps; to use a model-neutral
p-star intermediate step that produces the same geometric grid regardless of the
target model; and to keep the workflow performant on very large meshes through
chunked xarray/dask operations and materialized intermediate files. This design
is successful if it produces reusable, well-tested Polaris steps that scale to
production global meshes, initialize the configured model from a model-neutral
geometric vertical grid, and can eventually replace the corresponding legacy
Compass and MPAS-Ocean init workflows for the supported open-ocean use case.

## Requirements

### Requirement: Open-ocean global initial conditions can be created from a culled mesh

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall provide a workflow that begins from an ocean mesh and
corresponding culled topography produced by the `e3sm/init` cull workflow and
produces a global ocean initial condition suitable for use by a standalone
ocean model.

The initial supported use case is open ocean without ice-shelf cavities. The
workflow shall therefore assume that the culled mesh does not require cavity
geometry, land-ice pressure initialization, or SSH adjustment beneath floating
ice.

Any topography smoothing, minimum-depth logic, or related preparation of the
ocean topography needed for initialization shall be handled upstream in the
`e3sm/init` topography workflow rather than inside the ocean-initialization
workflow. This supports the goal of a unified MPAS mesh and a common
topographic description across E3SM components.

### Requirement: A reusable global hydrography product is available from WOA

Date last modified: 2026/04/14

Contributors: Xylar Asay-Davis, Codex

Polaris shall provide a reusable hydrography product derived from the World
Ocean Atlas at 0.25-degree resolution. This product shall contain canonical
conservative temperature and absolute salinity fields needed to initialize the
ocean state over the full globe, including values in regions where the original
product is missing and extrapolation is required for later remapping. Because
WOA23 supplies in-situ temperature and practical salinity rather than
conservative temperature and absolute salinity, the workflow shall derive the
canonical tracers during preprocessing.

The hydrography product shall be suitable for caching because it is expected to
be computationally expensive and because it should be reusable across many
meshes and tasks.

### Requirement: The workflow produces consistent tracer initial conditions for the configured model

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

Given a common hydrographic source, Polaris shall produce initial conditions
that are thermodynamically consistent with the tracer conventions of the
configured ocean model.

For MPAS-Ocean, the workflow shall produce temperature and salinity fields in
the form expected by MPAS-Ocean (potential temperature and practical salinity).
For Omega, the workflow shall produce temperature and salinity fields in the
form expected by Omega (conservative temperature and absolute salinity). The
design shall minimize duplicated logic between the two model targets by sharing
the p-star iteration and WOA preprocessing and branching only where tracer
conversion genuinely differs.

### Requirement: The p-star iteration yields a model-independent geometric vertical grid

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

The p-star initialization step shall produce a geometric vertical grid that
depends only on bathymetry and hydrography, not on which ocean model is the
final target. As a consequence, running the task for MPAS-Ocean and for Omega
on the same horizontal mesh and hydrography shall produce the same initialized
geometric layer thicknesses, enabling direct geometric comparison between the
two models.

This shared-grid property is a natural outcome of the p-star algorithm: the
converged geometric layer thicknesses emerge from a model-neutral iteration and
are then consumed by the model-specific `initial_state` step. The p-star
iteration runs even when the configured model is MPAS-Ocean; there is no
separate z-star resting-thickness path.

The workflow shall compute any density, pressure, or specific-volume fields
needed to translate hydrography defined with respect to geometric depth or
height into the model's native vertical representation.

Haney-number coordinates are out of scope for the initial implementation but
should remain feasible to add later.

### Requirement: The capability is decomposed into inspectable Polaris steps

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow shall be organized into multiple Polaris steps with clear,
meaningful outputs that users and developers can inspect independently for
sanity checking, visualization, and debugging.

Where appropriate, steps shall be reusable or cacheable so that expensive work
does not need to be repeated across tasks that use identical inputs.

### Requirement: The workflow is practical for very large global meshes

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow shall be implementable in a way that is practical for large
production meshes, including meshes on the order of uniform 5-km global
resolution.

The implementation shall avoid assumptions that require the full global state to
fit comfortably in memory on a single node. It shall support sensible
chunk-based execution and the use of intermediate files where needed to keep
the workflow robust.

### Requirement: The design preserves a path to future cavity support

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Although the first implementation does not need to support ice-shelf cavities,
the workflow shall not hard-code assumptions that make later support for
cavities, land-ice pressure consistency, or SSH adjustment unnecessarily
difficult.

## Algorithm Design

### Algorithm Design: Open-ocean global initial conditions can be created from a culled mesh

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should adopt the culled ocean mesh and associated topography from
the `e3sm/init` cull workflow as its starting point rather than reproducing the
mesh-culling logic inside the ocean task. This keeps responsibilities separated:
`e3sm/init` produces physically consistent meshes and masks, while the new ocean
initial-condition workflow consumes those products to build the 3D ocean state.

For the initial phase, the relevant topographic fields should be restricted to
open-ocean quantities needed for bathymetry, land masks, and any mesh-derived
auxiliary fields required by the target model.

This design also assumes that any topography smoothing or minimum-depth
enforcement needed for ocean initialization has already been applied in the
`e3sm/init` topography workflow, so the ocean task treats the incoming
topography as authoritative.

### Algorithm Design: A reusable global hydrography product is available from WOA

Date last modified: 2026/04/14

Contributors: Xylar Asay-Davis, Codex

The workflow should create a canonical hydrography product on the native WOA23
latitude-longitude grid before any remapping to an MPAS mesh. The current
implementation does this with a concrete sequence:

1. Create combined topography on the native 0.25-degree latitude-longitude
   grid.
2. Read WOA23 January and annual temperature and salinity climatologies and
   combine them into a single source product, using annual values at depths
   where the monthly fields are not available, then derive conservative
   temperature and absolute salinity from WOA23 in-situ temperature and
   practical salinity.
3. Build a 3D ocean mask on the WOA grid from the combined topography product.
4. Extrapolate horizontally and then vertically within the ocean mask.
5. Extrapolate horizontally and then vertically into land and grounded-ice
   regions so later remapping will not sample missing values.
6. Optionally produce visualization products for sanity checking.

This is conceptually similar to the existing Compass `extrap_woa` utility but
the Polaris implementation should favor xarray-based operations and clear
intermediate products over multiprocessing code that is tightly coupled to the
legacy workflow.

### Algorithm Design: The workflow produces consistent tracer initial conditions for the configured model

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

A common intermediate tracer representation should be used to avoid maintaining
two largely separate initialization pipelines. The leading candidate is a
canonical hydrographic state based on conservative temperature and absolute
salinity because those align naturally with Omega and with the desired WOA-based
source product.

Model-specific tracer fields are derived late in the workflow, in the
`initial_state` step:

1. Interpolate the canonical state onto the target mesh columns.
2. Convert to the tracer convention required by the configured model.
3. Write the resulting fields using the variable names and metadata expected by
   the model.

The exact thermodynamic conversions should be finalized during implementation,
but the conversion logic should be isolated so it can be tested independently of
horizontal and vertical interpolation.

### Algorithm Design: The p-star iteration yields a model-independent geometric vertical grid

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

The model-neutral geometric grid is determined by the `pstar_init` step.
The high-level outcome is:

1. Horizontally remap the source hydrography to each MPAS column on a source
   vertical grid.
2. For each water column, run the coupled p-star and tracer initialization to
   convergence (see [pstar_init.md](pstar_init.md)), producing the p-star
   coordinate, CT and SA at layer midpoints, specific volume, and the converged
   geometric layer thicknesses.
3. Use the resulting initialized geometric layer thicknesses in the configured
   model: as part of the Omega initial condition, or as `restingThickness` in
   MPAS-Ocean.
4. The `initial_state` step derives any remaining model-specific vertical state,
   including ALE layer-thickness fields for MPAS-Ocean.

Because the Omega p-star coordinate is defined in pseudo-height rather than
geometric height, the geometric seafloor depth cannot be prescribed directly.
The pseudo-height of the seafloor (`BottomPressure`) must be found iteratively
so that the geometric depth recovered from the coordinate matches observed
bathymetry. This requires initializing CT and SA on the p-star grid at each
iteration step so that specific volume can be evaluated, making the vertical
coordinate and the tracer state tightly coupled. Full and partial bottom cells
add further complexity by introducing discrete jumps in the pseudo-bottom depth.

The detailed fixed-point algorithm for this joint p-star and tracer
initialization — including the proportional-ratio update for `BottomPressure`,
the CT/SA initialization interface, the handling of full and partial bottom
cells, and the complete list of output variables produced — is specified in the
companion design document [pstar_init.md](pstar_init.md).

The initialized geometric grid emerges from the coupled iteration rather than
from a geometric grid constructed in isolation; the workflow steps must reflect
this coupling.

### Algorithm Design: The workflow is practical for very large global meshes

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should treat chunking and materialization as part of the algorithm
design rather than as a later optimization. Likely design principles are:

1. Chunk horizontally over cells and only keep the full vertical column when
   needed.
2. Use explicit intermediate files between major phases so dask graphs stay
   bounded in size.
3. Reuse interpolation weights or cached preprocessed products where practical.
4. Keep expensive EOS calculations localized to the phases that need them.

## Implementation

### Implementation: Open-ocean global initial conditions can be created from a culled mesh

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The new task should live under the ocean framework and consume outputs from a
culled-mesh step in `e3sm/init`, through explicit step inputs rather
than implicit filesystem assumptions. The initial task variant should target
open-ocean meshes without cavities and should accept a culled mesh,
corresponding graph file, and culled topography as inputs.

The first draft of the workflow should port only the parts of the current
Compass and init-mode logic that are required for this open-ocean use case.
Features related only to cavities, SSH adjustment, or ecosystem forcing can be
left out until a later requirement is added for them.

This implementation should not perform its own topography smoothing or
minimum-depth preparation. Those operations should be implemented in
`e3sm/init` so the same prepared topography can be shared consistently across
ocean, sea-ice, land, and river workflows.

### Implementation: A reusable global hydrography product is available from WOA

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

This part of the design has landed. `e3sm/init` creates combined topography on
a native 0.25-degree latitude-longitude grid, and the WOA23 steps under
`ocean/spherical/realistic_global/hydrography/woa23` build the corresponding
reusable product on that grid:

1. `combine_topo`, the shared `e3sm/init` `CombineStep` for the 0.25-degree
   lat-lon grid, cached by default so the expensive blending is not repeated
2. `combine`, which merges January and annual WOA23 climatologies into
   `woa_combined.nc`, using annual values at depths where the monthly fields
   are not available, and derives conservative temperature and absolute
   salinity from WOA23's in-situ temperature and practical salinity with `gsw`
3. `extrapolate`, which builds a 3D ocean mask from the combined topography and
   produces the reusable product `woa23_decav_0.25_jan_extrap.nc`
4. `viz`, a diagnostics step for maps and Antarctic transects, created as a
   shared step but not run by default

The steps are assembled by `get_woa23_steps(component, include_viz)`, which
returns them keyed by symlink name along with their shared config. A consumer
that needs only the hydrography product — the mesh-specific init steps, for
instance — gets the same step instances rather than a second copy of the
preprocessing.

The rename worked out differently from what this section anticipated. The work
directories did move under the `realistic_global` family, but the Python
package did not gain a `spherical` level: the code is
`polaris.tasks.ocean.realistic_global.hydrography.woa23`. Work-directory paths
and module paths are separate concerns in Polaris and only the first is what a
user navigates, so there was no reason to make the module path longer. The same
split holds throughout this workflow: mesh-specific steps run under
`ocean/spherical/realistic_global/{mesh_name}/init` and live in
`polaris.tasks.ocean.realistic_global.init`.

### Implementation: The workflow produces consistent tracer initial conditions for the configured model

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

The workflow defines a model-neutral intermediate dataset (the `pstar_init`
step output) and leaves the model-specific translation to the write. That
separation is what lets the p-star iteration, WOA23 remapping and chunking
logic be shared regardless of the configured target model.

The translator layer ended up in the framework rather than in `initial_state`:
`OceanIOStep.write_initial_state_dataset` takes the convention the dataset's
tracers are in and converts them to the one the configured model expects,
defaulting to the convention implied by `eos_type`. The task step supplies only
what the framework cannot know — the per-cell longitude and latitude the
conversion needs, which `pstar_init.nc` does not carry. Putting it there means
every task that writes an initial state converts tracers the same way, and a
step cannot forget to.

Thermodynamic calculations that are independent of the task live in
`polaris.ocean.eos` and `polaris.ocean.init_state`, as this section intended.

### Implementation: The p-star iteration yields a model-independent geometric vertical grid

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

The coupled p-star and tracer initialization described in
[pstar_init.md](pstar_init.md) shall be implemented as a concrete subclass of
`PStarInitStep` (defined in `polaris/ocean/vertical/pstar_init.py`). That
subclass, `RealisticPStarInitStep`, is defined in
`polaris/tasks/ocean/realistic_global/init/pstar_init.py`.
It implements the `init_tracers` method by interpolating CT and SA from the
pre-processed WOA hydrography product remapped to the MPAS horizontal mesh,
using the p-star layer midpoints from the current iteration as the vertical
interpolation target.

The reference 1D vertical grid that establishes the initial layer structure is
configured by setting `grid_type` in the `[vertical_grid]` section of
`realistic_global_init.cfg`. The `pstar_init` step passes this reference grid
to `generate_1d_grid` (in `polaris/ocean/vertical/grid_1d/__init__.py`),
which returns the interface depths used to dimension the p-star iteration. The
default for the realistic global init task is the pre-defined `80layerE3SMv1`
grid. The `grid_type` option must be present in the config; if it is absent,
`generate_1d_grid` raises `ValueError: Unexpected grid type: None`.

The vertical grid turned out to be one of the things that has to vary from mesh
to mesh, which this document did not anticipate. It is set per mesh through
`polaris.tasks.ocean.realistic_global.mesh_configs`: an optional
`<mesh_name>.cfg` whose options are added after the task's own config file and
therefore override it. The three 240 km meshes replace the 80-layer default
with a 16-level `tanh_dz` grid over a 3000 m bottom depth, because they exist
for fast smoke-testing rather than for realistic simulation. The same mechanism
carries the ocean-culled cell count used to size MPI tasks, and later the
per-mesh forward-run options described in
[global_ocean_forward.md](global_ocean_forward.md). Anything that describes
what the *ocean* does on a mesh belongs there rather than in the mesh
component's own per-mesh config, which describes the mesh itself.

Three behaviors of the iteration were settled during implementation rather than
in [pstar_init.md](pstar_init.md), which specifies the fixed-point algorithm
itself. The column is anchored at the prescribed sea surface, so `ssh` matches
its prescribed value to machine precision and any residual left by partial-cell
snapping adjusts the diagnosed `bottomDepth` — the representable bathymetry —
rather than `ssh`, mirroring z-star partial cells. Columns too shallow to hold
`min_vert_levels` layers, or shallower than `min_bottom_depth`, are clamped.
And isolated bathymetry holes — cells deeper than every ocean neighbor — are
capped at their deepest neighbor's level and re-solved, through
`polaris.ocean.vertical.bathymetry_holes.fill_max_level_holes`.

The output of the coupled initialization step — converged geometric layer
thicknesses, CT and SA, specific volume, and associated coordinate fields — shall
be exposed as an inspectable intermediate product (`pstar_init`). That
intermediate is a single combined dataset written in neutral (MPAS-Ocean) naming
and includes at least the full set of variables listed in the output table of
[pstar_init.md](pstar_init.md). The model-specific split into separate output
files happens in the downstream `initial_state` step rather than in
`pstar_init`, keeping the intermediate inspectable without model-specific
naming or variable filtering.

The `initial_state` step consumes the `pstar_init` intermediate dataset,
performs any model-specific tracer conversions, and writes the final split
output:

- `vert_coord.nc` via `write_vert_coord_dataset` (Omega only; no-op for
  MPAS-Ocean). For Omega this converts `restingThickness` to `RefPseudoThickness`
  and writes the five `InitialVertCoord` fields (`MinLayerCell`, `MaxLayerCell`,
  `BottomGeomDepth`, `RefPseudoThickness`, `VertCoordMovementWeights`).
- `init.nc` via `write_initial_state_dataset`, which strips horizontal mesh
  variables and (for Omega) vertical coordinate variables before writing.

Surface forcing is *not* written by `initial_state`. Wind stress is produced by
a separate `forcing` step and written to its own `forcing.nc`, described under
[Wind forcing](#wind-forcing) below. Restoring fields remain future work.

The mesh file (`mesh.nc`) is written by `initial_state` rather than linked from
upstream. The culled mesh from `e3sm/init` is not by itself a complete ocean
mesh stream: `add_coriolis_to_dataset` adds `fCell`, `fEdge` and `fVertex`,
and for Omega `write_horiz_mesh_dataset` merges in the cell-centered
vector-reconstruction weights, which have to be the *culled* mesh's since that
is the mesh the initial condition is built on. The horizontal geometry itself
is still entirely the cull step's; nothing here re-derives it.

The p-star iteration shall run even when the configured model is MPAS-Ocean,
since the converged geometric grid is always defined through the p-star
iteration.

The MPAS-Ocean path derives `restingThickness` from the converged geometric
layer thicknesses rather than falling back to the legacy z-star resting-thickness
construction.

### Implementation: The capability is decomposed into inspectable Polaris steps

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

The decomposition landed with more steps than this section first sketched,
because remapping turned out to be worth separating from the mapping files it
uses, and because wind forcing arrived as a second remapped source. The chain
is assembled by `get_realistic_init_steps(component, mesh_name, include_viz)`,
which builds every step with `Component.get_or_create_shared_step` and returns
them keyed by symlink name along with the per-mesh shared config. Steps run
under `ocean/spherical/realistic_global/{mesh_name}/init`, except the
mesh-independent preprocessing, which is shared across meshes:

1. the upstream `e3sm/init` cull-topography steps, from
   `get_cull_topo_steps`, which supply the culled ocean mesh, its graph and
   the remapped topography
2. the WOA23 hydrography steps described above, from `get_woa23_steps`
3. the JRA55-do wind-stress steps, from `get_jra55_steps` (see
   [Wind forcing](#wind-forcing))
4. `cull_topo`: reindex the remapped topography from the base mesh to the
   culled ocean mesh using `ocean_map_culled_to_base.nc`, producing
   `topography_culled.nc`, which is validated against a baseline when one is
   provided
5. `woa23_map`: build the bilinear mapping file from the 0.25-degree WOA23
   lat-lon grid to the culled MPAS mesh. This is the one MPI step of the
   hydrography chain, and its task count is sized from the approximate culled
   ocean cell count
6. `remap_woa23`: apply those weights with `ncremap`, producing
   `woa23_on_mesh.nc`
7. `jra55_map` and `remap_jra55`: the same two steps for the wind stress
8. `pstar_init`: perform the coupled p-star and hydrography initialization
   described in [pstar_init.md](pstar_init.md), producing the converged
   geometric grid, CT and SA on that grid, and all associated p-star
   coordinate fields; this step writes a single combined intermediate NetCDF
   file (`pstar_init.nc`) in neutral naming rather than the final split model
   files, so all outputs remain inspectable regardless of the target model
9. `initial_state`: consume the `pstar_init` intermediate dataset, apply
   model-specific tracer conversions, populate remaining required fields, and
   write `mesh.nc`, `vert_coord.nc` (Omega only) and `init.nc`
10. `forcing`: write the model-specific `forcing.nc` from `jra55_on_mesh.nc`
11. `viz`: plots and sanity checks of the initial condition, vertical
    coordinate and forcing

Each remap is two steps rather than one because the original single step both
reimplemented what `polaris.remap.MappingFileStep` already provides and ran an
MPI operation (`mbtempest`) and a serial one (`ncremap`) together, which does
not schedule well under task parallelism. Splitting them also lets the mapping
step size its own task count from the estimated ocean cell count while the
`ncremap` call stays serial.

The step this section called `diagnostics` landed as `viz`, matching the name
used elsewhere in Polaris. It is created as a shared step but returned — and so
run — only when `include_viz=True`, which the standalone `RealisticGlobalInit`
task passes and consumers that reuse the init outputs as dependencies do not.
Those consumers exist: the forward and dynamic-adjustment workflows and
`e3sm/init`'s component inputs all call `get_realistic_init_steps` and get the
same step instances rather than a second copy of a chain that costs hours.

Within this decomposition, `initial_state` is what ports the pieces of legacy
init-mode functionality that are neither part of `pstar_init` nor already
handled upstream in `e3sm/init`. As implemented, it:

1. Consumes the outputs of `pstar_init`, including the converged geometric
   layer thicknesses and the model-agnostic hydrographic state on the target
   mesh.
2. Converts that hydrographic state into the tracer conventions required by the
   configured model — CT and SA kept for Omega, converted to potential
   temperature and practical salinity for MPAS-Ocean. The conversion itself
   belongs to the framework's initial-state helpers; this step supplies the
   per-cell longitude and latitude they need, since `pstar_init.nc` carries no
   horizontal mesh fields.
3. Populates quiescent dynamical initial conditions, setting `normalVelocity`
   to zero.
4. Computes the remaining derived fields, notably in-situ density from the
   specific volume the p-star iteration produced.
5. Writes `mesh.nc` through `write_horiz_mesh_dataset`, `vert_coord.nc`
   through `write_vert_coord_dataset` (Omega only; a no-op for MPAS-Ocean,
   which keeps vertical coordinate variables in `init.nc`) and `init.nc`
   through `write_initial_state_dataset`.

Restoring fields did not land. Surface and interior restoring values and their
piston velocities are not part of the supported workflow yet, so nothing
computes them; the forcing file that replaces the legacy
`init_mode_forcing_data.nc` carries wind stress alone and is written by the
separate `forcing` step rather than by `initial_state`.

The first implementation should explicitly exclude or defer several categories
of legacy init-mode behavior that are present in
`mpas_ocn_init_global_ocean.F` but are not part of the current design scope:

1. Ice-shelf and land-ice-specific logic, including cavity temperature
   modification, land-ice pressure consistency, and SSH adjustment.
2. Ecosystem tracers, ecosystem forcing fields, and related pH or sediment
   initialization.
3. Shortwave-absorption auxiliary fields needed for the `ohlmann00`
   parameterization, such as chlorophyll, zenith angle, and clear-sky
   radiation.
4. Debug tracers and other optional tracer packages initialized only to simple
   default values in legacy init mode.
5. Any inland-sea culling or other mesh/topography correction that is more
   appropriately handled upstream in `e3sm/init`.

The legacy diagnostics this section left open were decided as follows.
Haney-number fields are not written at all — the `viz` step's port of Compass'
`plot_initial_state` drops those panels rather than reproducing them — since
Haney-number coordinates are out of scope. In-situ density is written, because
the p-star iteration already produces the specific volume it comes from and
because it is what the Omega stratification check reads.

(wind-forcing)=
### Implementation: Wind forcing

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Dynamic adjustment needs a realistic, constant-in-time wind stress so the ocean
can spin down fast waves against a sensible circulation. The forcing does not
need to be a defensible climate product, only realistic enough that the
adjusted state is dynamically sensible. Surface restoring, thermal and
freshwater fluxes, atmospheric and sea-ice pressure, time-varying forcing, and
all forward-model settings remain out of scope.

**Source.** JRA55-do v1.5.0 (`MRI-JRA55-do-1-5-0`), variables `uas` and `vas`:
10-m winds on the TL319 Gaussian grid (640 x 320), 3-hourly, distributed as
input4MIPs on ESGF and anonymously downloadable from the CEDA node. E3SM forces
G-cases with JRA55, so the adjusted state is adjusted against something close to
what a coupled run will apply, and the input4MIPs record pins version and
checksums. This supersedes the earlier intent to reuse the Compass NCEP
climatology, whose provenance is a 2015 filename and nothing more. The time
window is January 1958, the first month of the record and of an interannually
forced G-case, configurable via `year` and `month`.

**Winds to stress.** JRA55-do supplies winds, so a bulk formula is needed. Two
choices matter. First, the stress is averaged rather than the winds: computing
`tau(mean wind)` discards the gust contribution and underestimates stress in the
storm tracks, so stress is computed at each 3-hourly step and then averaged --
which is why the 3-hourly data is needed rather than a published monthly mean.
Second, the Large and Yeager (2004, 2009) neutral 10-m drag law is used with
`rho_air = 1.22` and the wind speed clamped below at 0.5 m/s, with the stability
correction, the current-relative wind, and sea-ice drag deliberately omitted as
second-order for this purpose.

**Remapping.** Bilinear, with `map_tool` at the Polaris default (`moab`), no
padding of the source grid, and a nearest-neighbor fill of the small residual
polar cap. Each of these was settled by measurement, and each has a failure mode
that is easy to reintroduce:

- Bilinear rather than conservative, because the ocean responds to wind stress
  *curl*; first-order conservative gives a piecewise-constant stress whose curl
  is grid-scale noise, and pyremap's moab path hard-codes `--order 1`.
- `moab` rather than ESMF, because ESMF's default pole handling builds its pole
  point from the zonal average of the source's outermost row. That is harmless
  for a scalar but destructive for a vector in zonal/meridional components,
  since the local basis rotates with longitude: a uniform physical vector of
  magnitude 1.0 measured 0.42 by 89.82 degrees N under ESMF, tending to zero at
  the pole, versus a flat 0.998 under mbtempest.
- No padding, because bilinear is center-based for ESMF but corner-based for
  mbtempest, and padding a lat-lon source so either its corners or its centers
  reach the pole aborts mbtempest. Duplicating a longitude column breaks both
  tools and is unnecessary, since TL319's longitude corners already span exactly
  360 degrees.
- mbtempest's coverage stops at the extrapolated corner, leaving 891 km^2
  uncovered at the North Pole -- under one cell for meshes coarser than about
  30 km -- which is filled from the nearest valid neighbor. Both stress
  components are taken from the same donor cell so the filled vector stays
  physical, and a missing count beyond `max_polar_fill_fraction` (with an
  absolute floor of `min_allowed_polar_fill` for coarse meshes) fails the step
  rather than being filled silently.

**Steps.** Deriving the global product is mesh-independent, and although the
reduction itself takes seconds it needs several GiB of raw winds, so the
product is cached and the work lives outside the `init` workflow, mirroring the
WOA23 hydrography product:

| subdir | step | output |
| --- | --- | --- |
| `forcing/jra55/stress` | `Jra55StressStep` | `jra55_stress.nc` |
| `forcing/jra55/viz` | `Jra55VizStep` | diagnostic plots |
| `{mesh}/init/jra55_map` | `Jra55MapStep` | bilinear weights |
| `{mesh}/init/remap_jra55` | `RemapJra55Step` | `jra55_on_mesh.nc` |
| `{mesh}/init/forcing` | `ForcingStep` | `forcing.nc` |

**Output.** Both models take zonal and meridional components at cell centers and
project onto edges themselves, so no vector rotation is needed. The field is
authored in MPAS-Ocean names and renamed on write through the existing
`mpaso_to_omega.yaml` mapping. The framework gains a fourth staged file
alongside the mesh, vertical coordinate and initial state: `forcing_filename` in
`[ocean_staged_files]`, a `forcing_variables` list, and a
`write_forcing_dataset` helper.

The two models differ on the time dimension. Omega's `SfcStressForcingVars`
registers 1-D fields on `NCells`, while MPAS-Ocean's Registry declares
`dimensions="nCells Time"`, so `write_forcing_dataset` adds `Time=1` for
MPAS-Ocean only.

`Jra55StressStep` is *intended* to be `default_cached`, so that the multi-GiB
download happens only when the product is deliberately regenerated. The flag is
not set until the product is in the cache database, because setting it first
makes any setup that does not include the standalone `jra55` task fail with
"has not been added to the cache database". It belongs in the same change that
adds the `cached_files.json` entry.

The read side -- staging `forcing.nc` as a model *input*, and the associated
namelist and config settings -- belonged to the forward-model work and landed
there; see [global_ocean_forward.md](global_ocean_forward.md).

### Implementation: The workflow is practical for very large global meshes

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The implementation should use xarray lazily by default for large fields and
should choose chunking with the target access pattern in mind. A reasonable
starting assumption is that horizontal chunking over `nCells` will be more
robust than attempting to process the full mesh at once.

Major stages should write intermediate NetCDF outputs rather than carrying a
single dask graph across the entire workflow. This is likely to be especially
important after WOA preprocessing, after `pstar_init`, and before final
model-specific output writing.

### Implementation: The design preserves a path to future cavity support

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Even though cavities are out of scope initially, the data model should not
assume that the free surface always coincides with sea level or that land-ice
pressure fields are absent forever. Interfaces between topography handling,
vertical-coordinate construction, and final state assembly should remain clean
enough that cavity-aware logic can later be inserted without rewriting the full
task.

## Testing

### Testing and Validation: Open-ocean global initial conditions can be created from a culled mesh

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

The first level of testing should verify that the workflow can consume outputs
from an `e3sm/init` culled-mesh step and produce complete initial-condition
files for at least one supported global mesh. A small or moderate mesh should
be used for routine regression tests, with larger meshes reserved for
integration testing.

That split landed differently than "small mesh in a regression suite" suggests.
The whole chain — culling, remapping and the p-star iteration — costs hours on
any mesh worth initializing, so no task in this family belongs in a PR suite;
routine regression testing is the unit tests above, and the workflow itself is
exercised by running it on a mesh. The 240 km meshes exist for exactly that,
which is why they override the vertical grid down to 16 levels. Initial
conditions built this way have been carried through dynamic adjustment on
`u.oi30.lr10` and `u.oi6to18.lr6to10`, which is where the WOA23 source
artifacts documented in
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md) were
found.

### Testing and Validation: A reusable global hydrography product is available from WOA

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Testing should verify that the preprocessed WOA product contains no missing
values in the regions needed for later remapping, that metadata and dimensions
are consistent, and that rerunning the step with the same inputs gives
reproducible results.

### Testing and Validation: The workflow produces consistent tracer initial conditions for the configured model

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

Unit tests should cover any tracer-conversion utilities independently of the
full task. Task-level validation should verify that model-specific outputs
contain the expected tracer variable names and are thermodynamically consistent
(e.g., potential temperature within physical bounds for MPAS-Ocean; conservative
temperature for Omega).

Where practical, outputs on a small mesh should also be compared against the
legacy Compass plus init-mode workflow, recognizing that exact bit-for-bit
agreement may not be the right success criterion if the new implementation uses
cleaner thermodynamic conversions.

### Testing and Validation: The p-star iteration yields a model-independent geometric vertical grid

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

Testing should verify that the `pstar_init.nc` intermediate file contains
consistent geometric and pseudo-height fields (layer thicknesses, interface
depths, valid-level masks) that respect bathymetry and minimum-thickness
constraints.

Running the task for both MPAS-Ocean and Omega configurations on the same mesh
and comparing the resulting `pstar_init.nc` intermediates (or the
`restingThickness` / `RefPseudoThickness` fields in the final outputs) should
confirm that the geometric vertical grid at initialization is identical.

For Omega, tests should also verify the convergence and stability of the
p-star iteration used to relate geometric height, pressure, and pseudo-height.

For MPAS-Ocean, tests should verify that the initialized layer-thickness state
is derived from the converged geometric grid from the p-star iteration rather
than silently falling back to the legacy z-star construction.

### Testing and Validation: The capability is decomposed into inspectable Polaris steps

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Codex, Claude

Each major step has unit tests under `tests/ocean/realistic_global/`, mirroring
the package layout: `init/test_woa23_map.py` and `init/test_jra55_map.py` for
the mapping steps and how their task counts scale, `init/test_remap_woa23.py`
and `init/test_remap_jra55.py` for what the remapped products contain and for
the polar fill, `init/test_pstar_init.py` for the column helpers,
`init/test_initial_state.py` for which upstream files the step reads, and
`init/test_forcing.py` for the per-model forcing file. `test_tasks.py` checks
that one task is registered per mesh and that its step list is what the
decomposition says, and `test_mesh_configs.py` that the per-mesh overrides
reach the right options without displacing the rest.

The `viz` step is covered by `init/test_viz_config.py` rather than by a smoke
test: it checks that the step reads only config sections that exist and that no
colormap is chosen by a literal in the plotting code. Rendering the plots needs
a real initial condition, so that part is exercised by running the task rather
than in CI.

### Testing and Validation: The workflow is practical for very large global meshes

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Performance testing should include at least one larger mesh case to assess
memory usage, wall-clock behavior, and whether intermediate-file boundaries are
sufficient to keep dask execution stable. These tests do not need to run in the
routine regression suite but should be documented and rerun periodically.

### Testing and Validation: The design preserves a path to future cavity support

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

This requirement is largely architectural in the first phase. Review-based
validation is appropriate initially: the workflow should be checked for
hard-coded open-ocean assumptions at module boundaries and in intermediate
dataset schemas. Later, this requirement should graduate to task-level tests
once cavity support is added.
