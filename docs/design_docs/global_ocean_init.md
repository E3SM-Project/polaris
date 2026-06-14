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

The Polaris ocean framework separates model inputs across three files: a horizontal
mesh file (`mesh.nc`), a vertical coordinate file (`vert_coord.nc`; Omega only), and an
initial-state file (`init.nc`). The realistic init workflow must respect this split: the
mesh file comes from the upstream `e3sm/init` cull workflow; the vertical coordinate and
initial state are written by the init steps using the framework's `write_vert_coord_dataset`
and `write_initial_state_dataset` helpers. For MPAS-Ocean, `write_vert_coord_dataset` is a
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

Date last modified: 2026/06/01

Contributors: Xylar Asay-Davis, Codex, Claude

The first implemented pieces of this part of the design are now in place.
`e3sm/init` can create combined topography on a native 0.25-degree
latitude-longitude grid, and `ocean/spherical/realistic_global/hydrography/woa23` builds the
corresponding reusable WOA23 product on that grid. The WOA23 task currently
consists of:

1. `combine`, which merges January and annual WOA23 climatologies into
   `woa_combined.nc`, using annual values at depths where the monthly fields
   are not available
2. `extrapolate`, which builds a 3D ocean mask from the combined topography and
   produces the reusable product `woa23_decav_0.25_jan_extrap.nc`
3. `viz`, an optional diagnostics step for maps and Antarctic transects

The task is currently implemented under
`polaris/tasks/ocean/global_ocean/hydrography/woa23` and must be renamed to
`polaris/tasks/ocean/spherical/realistic_global/hydrography/woa23` as part of adopting the
`realistic` framework name. All associated Python module paths, configuration
references, and any cached output paths that embed the task name will need to be
updated at the same time.

This provides a concrete implementation starting point for the reusable
hydrography portion of the broader design.

### Implementation: The workflow produces consistent tracer initial conditions for the configured model

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

The workflow should define a model-neutral intermediate dataset (the `pstar_init`
step output) and a thin model-specific writer or translator layer in
`initial_state`. That separation makes it possible for the p-star iteration,
WOA23 remapping, and chunking logic to be shared regardless of the configured
target model.

Existing Polaris utilities in `polaris.ocean.eos` are a natural place to keep
thermodynamic calculations that are independent of the task itself. If
additional conversions between tracer conventions are needed, they should be
implemented in similarly reusable utility modules rather than embedded directly
in a task step.

### Implementation: The p-star iteration yields a model-independent geometric vertical grid

Date last modified: 2026/06/14

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
current choice for the realistic global init task is the pre-defined
`80layerE3SMv1` grid. The `grid_type` option must be present in the config;
if it is absent, `generate_1d_grid` raises
`ValueError: Unexpected grid type: None`.

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
performs any model-specific tracer conversions, populates remaining required
fields (wind stress, restoring, etc.), and writes the final split output:

- `vert_coord.nc` via `write_vert_coord_dataset` (Omega only; no-op for
  MPAS-Ocean). For Omega this converts `restingThickness` to `RefPseudoThickness`
  and writes the five `InitialVertCoord` fields (`MinLayerCell`, `MaxLayerCell`,
  `BottomGeomDepth`, `RefPseudoThickness`, `VertCoordMovementWeights`).
- `init.nc` via `write_initial_state_dataset`, which strips horizontal mesh
  variables and (for Omega) vertical coordinate variables before writing.

The mesh file (`mesh.nc`) for the realistic init workflow comes from the upstream
`e3sm/init` cull step and is not produced by any step in this workflow.

The p-star iteration shall run even when the configured model is MPAS-Ocean,
since the converged geometric grid is always defined through the p-star
iteration.

The MPAS-Ocean path derives `restingThickness` from the converged geometric
layer thicknesses rather than falling back to the legacy z-star resting-thickness
construction.

### Implementation: The capability is decomposed into inspectable Polaris steps

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Codex, Claude

An initial decomposition can now start from the pieces that have already been
implemented:

1. `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.2500_degree/task`:
   create combined topography on the native WOA grid; this step also supplies
   the culled `mesh.nc` consumed by all downstream steps
2. `ocean/spherical/realistic_global/hydrography/woa23/combine`: merge WOA23 climatologies
   on that grid
3. `ocean/spherical/realistic_global/hydrography/woa23/extrapolate`: create the reusable,
   extrapolated WOA23 product
4. `ocean/spherical/realistic_global/hydrography/woa23/viz`: optional hydrography
   diagnostics
5. `pstar_init`: perform the coupled p-star and hydrography
   initialization described in [pstar_init.md](pstar_init.md), producing
   the converged geometric grid, CT and SA on that grid, and all associated
   p-star coordinate fields; this step writes a single combined
   intermediate NetCDF file (`pstar_init.nc`) in neutral naming rather
   than the final split model files, so all outputs remain inspectable
   regardless of the target model
6. `initial_state`: consume the `pstar_init` intermediate dataset,
   apply model-specific tracer conversions, populate remaining required
   fields, and write the split output files: `vert_coord.nc` (via
   `write_vert_coord_dataset`; Omega only) and `init.nc` (via
   `write_initial_state_dataset`)
7. `diagnostics`: create any additional mesh-specific plots and lightweight
   summaries for sanity checking

This decomposition also suggests a preliminary division of work among
developers:

1. WOA preprocessing and caching.
2. Coupled hydrography interpolation, Omega pseudo-height iteration, and
   model-neutral geometric-grid construction (`RealisticPStarInitStep`).
3. MPAS-Ocean-specific tracer and ALE output support based on the shared grid.
4. Omega-specific tracer and p-star output support based on the shared grid.
5. Diagnostics, validation, and regression tests.

Within this decomposition, the `initial_state` step still needs to port several
pieces of legacy init-mode functionality that are not part of
`pstar_init` and are not already handled upstream in `e3sm/init`. For
the initial implementation, the responsibilities of `initial_state` should
likely include:

1. Consume the outputs of `pstar_init`, including the converged
   geometric layer thicknesses and the model-agnostic hydrographic state on the
   target mesh.
2. Convert that hydrographic state into the tracer conventions required by the
   configured model and populate the model's active tracer fields.
3. Populate quiescent dynamical initial conditions, such as setting
   `normalVelocity` to zero.
4. Populate model forcing and auxiliary fields that are still required for the
   open-ocean use case, most notably horizontally interpolated wind-stress
   fields and any associated output written alongside the initial state. For
   the initial implementation, the wind-stress source should remain the same
   NCEP climatological product currently used in Compass.
5. Populate restoring fields derived from the initialized tracer state, such as
   surface and interior restoring values and their associated restoring rates
   or piston velocities, when those are part of the supported workflow.
6. Compute any remaining derived fields required by the target model's initial
   condition or forcing files that are not already natural outputs of
   `pstar_init`, such as density-related diagnostics.
7. Write the final split output files using the Polaris ocean framework helpers:
   `write_vert_coord_dataset` to produce `vert_coord.nc` for Omega (a no-op for
   MPAS-Ocean, which keeps vertical coordinate variables in `init.nc`) and
   `write_initial_state_dataset` to produce `init.nc`. Any forcing file analogous
   to `init_mode_forcing_data.nc` is an additional output beyond the standard
   split.

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

Some details remain to be decided during implementation. In particular, we will
need to determine which legacy diagnostics, such as Haney-number-related fields
or density diagnostics, are still required as part of the final output schema
for the supported MPAS-Ocean and Omega workflows, and which should instead be
treated as optional diagnostics or validation products.

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

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The first level of testing should verify that the workflow can consume outputs
from an `e3sm/init` culled-mesh step and produce complete initial-condition
files for at least one supported global mesh. A small or moderate mesh should
be used for routine regression tests, with larger meshes reserved for
integration testing.

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

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Each major step should have at least one lightweight regression test or unit
test that verifies its primary output exists, has the expected variables, and
passes basic sanity checks. The diagnostics step should be validated with smoke
tests to make sure it continues to run as intermediate formats evolve.

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
