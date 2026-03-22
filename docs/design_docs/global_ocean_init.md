# Global Ocean Initial Conditions

date: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

## Summary

This design document describes a new Polaris capability for generating global
ocean initial conditions in Python, starting from an ocean mesh and topography
that have already been culled by the `e3sm/init` workflow. The intent is to
port the required functionality from the MPAS-Ocean init mode, especially
`mpas_ocn_init_global_ocean.F`, and from the Compass workflows in
`compass/ocean/tests/global_ocean/init` and
`compass/ocean/tests/utility/extrap_woa`.

The new workflow should create scientifically consistent initial conditions for
both MPAS-Ocean and Omega. One important use case is to initialize the two
models on the same horizontal and vertical grid so their solutions can be
compared directly. To support this, the workflow should favor a common
initialized geometric vertical grid. In the shared-grid mode, this grid should
be the one represented by the initialized geometric layer thicknesses in
Omega's p-star initial condition and should also determine the MPAS-Ocean
reference state that is stretched and squashed with sea-surface height in the
same ALE manner used for z-star or Haney-number coordinates. Legacy
MPAS-Ocean z-star initialization as currently implemented is therefore not the
preferred target for the new workflow. In the first phase, the same capability
should support MPAS-Ocean tracers based on potential temperature and practical
salinity and Omega tracers based on conservative temperature and absolute
salinity. The initial phase does not need to support ice-shelf cavities,
Haney-number vertical coordinates under ice shelves, or SSH adjustment below
ice shelves, but the design should preserve a clean path to add those features
later.

The primary software challenges are to replace a large, monolithic Fortran
workflow with an inspectable sequence of Polaris steps; to define a common
intermediate representation that can serve both MPAS-Ocean and Omega; and to
keep the workflow performant on very large meshes through chunked xarray/dask
operations and materialized intermediate files. This design is successful if it
produces reusable, well-tested Polaris steps that scale to production global
meshes, can initialize MPAS-Ocean and Omega on a shared vertical grid when
desired, and can eventually replace the corresponding legacy Compass and
MPAS-Ocean init workflows for the supported open-ocean use case.

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

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Polaris shall provide a reusable hydrography product derived from the World
Ocean Atlas at 0.25-degree resolution. This product shall contain the
temperature and salinity fields needed to initialize the ocean state over the
full globe, including values in regions where the original product is missing
and extrapolation is required for later remapping.

The hydrography product shall be suitable for caching because it is expected to
be computationally expensive and because it should be reusable across many
meshes and tasks.

### Requirement: The workflow produces consistent tracer initial conditions for MPAS-Ocean and Omega

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Given a common hydrographic source, Polaris shall be able to produce initial
conditions that are thermodynamically consistent with the tracer conventions of
both supported ocean models.

For MPAS-Ocean, the workflow shall produce temperature and salinity fields in
the form expected by MPAS-Ocean. For Omega, the workflow shall produce
temperature and salinity fields in the form expected by Omega. The design shall
minimize duplicated logic between the two model targets.

### Requirement: Omega and MPAS-Ocean can be initialized on the same vertical grid

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

When the same horizontal mesh is used for both models, Polaris shall support
creating initial conditions for Omega and MPAS-Ocean that correspond to the
same initialized vertical grid in geometric space.

This shared-grid capability does not need to be the only supported mode, but it
shall be available and is expected to be the preferred mode for direct model
comparison.

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

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should create a canonical hydrography product on the native WOA
latitude-longitude grid before any remapping to an MPAS mesh. A likely approach
is:

1. Read the selected WOA fields and normalize them to a common representation.
2. Extrapolate horizontally within the ocean domain.
3. Extrapolate vertically to fill gaps that remain after horizontal filling.
4. Extrapolate into non-ocean source-grid regions if needed so later remapping
   to the MPAS mesh never samples missing data.

This is conceptually similar to the existing Compass `extrap_woa` utility but
the Polaris implementation should favor xarray-based operations and clear
intermediate products over multiprocessing code that is tightly coupled to the
legacy workflow.

### Algorithm Design: The workflow produces consistent tracer initial conditions for MPAS-Ocean and Omega

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

A common intermediate tracer representation should be used to avoid maintaining
two largely separate initialization pipelines. The leading candidate is a
canonical hydrographic state based on conservative temperature and absolute
salinity because those align naturally with Omega and with the desired WOA-based
source product.

Model-specific tracer fields would then be derived late in the workflow:

1. Interpolate the canonical state onto the target mesh columns.
2. Convert to the tracer convention required by the target model.
3. Write the resulting fields using the variable names and metadata expected by
   the model.

The exact thermodynamic conversions should be finalized during implementation,
but the conversion logic should be isolated so it can be tested independently of
horizontal and vertical interpolation.

### Algorithm Design: Omega and MPAS-Ocean can be initialized on the same vertical grid

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The shared-grid capability suggests that the workflow should determine a common
geometric vertical grid as part of deriving model-specific state variables. The
shared description should be expressed in terms of initialized geometric layer
thicknesses and interface depths.

When both models are initialized on the same horizontal mesh, the design should
start from a reference profile in pseudo-thickness for Omega, derive the
corresponding initialized geometric layer thicknesses, and use those geometric
thicknesses in both models. In Omega, the geometric thicknesses are included in
the initial condition. In MPAS-Ocean, those same geometric thicknesses are
used as `refLayerThickness` and then participate in the ALE stretching and
squashing with SSH.

For the shared vertical-coordinate capability, the core algorithm should be
based on constructing an Omega vertical coordinate even when the final target
is MPAS-Ocean. In this case, horizontal remapping, vertical interpolation, EOS
evaluation, and the determination of the water-column bottom in
pseudo-height are tightly coupled.

A likely high-level sequence is:

1. Remap the source hydrography horizontally to each MPAS column on a source
   vertical grid.
2. Define a one-dimensional reference profile in pseudo-thickness for Omega.
3. For each water column, make an initial guess for the pseudo-height of the
   ocean bottom implied by the observed bathymetry.
4. Interpolate conservative temperature and absolute salinity to the resulting
   Omega pseudo-height coordinate.
5. Compute specific volume from the interpolated hydrography and use it to
   recover geometric layer thicknesses and geometric height.
6. Compare the recovered geometric bottom depth with the observed bathymetry
   and iteratively correct the pseudo-bottom-depth until the mismatch is small
   enough.
7. Use the resulting initialized geometric layer thicknesses in both models:
   as part of the Omega initial condition and as `refLayerThickness` in
   MPAS-Ocean.
8. Derive any remaining model-specific vertical state, including pseudo-height
   quantities for Omega and ALE layer-thickness fields for MPAS-Ocean.

This level of coupling means that the shared vertical coordinate is not
obtained by first constructing a geometric grid in isolation and only then
interpolating hydrography. Instead, the initialized geometric grid emerges as
part of an iterative solve involving hydrography, EOS evaluation, and the
mapping between pseudo-height and geometric height.

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

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

This requirement is a good candidate for a shared or cached Polaris step. A
first implementation should likely create a step analogous to `extrap_woa` that
produces a single preprocessed WOA product with well-defined fields and
metadata.

That step should be designed so it can later support additional hydrographic
products if needed, but the first implementation can focus on WOA23 at
0.25-degree resolution. The output should be versioned clearly enough that it
can be cached and invalidated when extrapolation logic changes.

### Implementation: The workflow produces consistent tracer initial conditions for MPAS-Ocean and Omega

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should define a model-agnostic intermediate dataset and a thin
model-specific writer or translator layer. That separation should make it
possible for most of the interpolation, masking, and chunking logic to be
shared between MPAS-Ocean and Omega.

Existing Polaris utilities in `polaris.ocean.eos` are a natural place to keep
thermodynamic calculations that are independent of the task itself. If
additional conversions between tracer conventions are needed, they should be
implemented in similarly reusable utility modules rather than embedded directly
in a task step.

### Implementation: Omega and MPAS-Ocean can be initialized on the same vertical grid

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

The workflow should include a reusable implementation of `shared_vert_coord`
that can produce the shared initialized geometric grid and expose it as an
inspectable intermediate product. That product should include at least
geometric layer thicknesses and associated reference depths or interfaces,
because those quantities are the key bridge between Omega and MPAS-Ocean in the
shared-grid use case. Model-specific reference quantities would then be
derived from that shared geometric description. In the MPAS-Ocean path, this
would include the model's `refLayerThickness` field.

Because this shared geometric grid is defined through the Omega pseudo-height
construction, the implementation should perform that iterative Omega solve even
when the final output requested by the user is only for MPAS-Ocean.

This shared-grid path should likely become the default for tasks whose purpose
is direct comparison between the two models, even if other initialization modes
remain available later.

The MPAS-Ocean path should reuse the existing Polaris vertical-grid framework
where possible for ALE thickness updates, but it should not assume that the
legacy z-star resting-thickness construction is the preferred reference state.
Instead, it should accept the shared initialized geometric grid and derive the
MPAS-Ocean reference and layer-thickness fields from it in a way that
preserves the intended initialized geometric grid.

The Omega path should reuse or extend the pseudo-height utilities already
present in `polaris.ocean.vertical.ztilde`, pairing them with the same shared
initialized geometric grid used by MPAS-Ocean, even if the resulting Omega
reference quantities are represented differently from the MPAS-Ocean fields.

The design should avoid forking the whole task by model. A better pattern is to
share WOA preprocessing and the coupled hydrography/vertical-coordinate solve,
then branch into model-specific steps only where tracer conversion,
model-specific vertical-state fields, or output formatting genuinely differ.

### Implementation: The capability is decomposed into inspectable Polaris steps

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

An initial decomposition could be:

1. `extrapolate_woa`: build or download the cached, extrapolated WOA product.
2. `shared_vert_coord`: perform the coupled hydrography
   interpolation and Omega pseudo-height solve needed to determine the shared
   initialized geometric grid and retain inspectable intermediate products.
3. `initial_state`: construct model-specific tracers and the native vertical
   representation, then write the final initial-condition file or files.
4. `diagnostics`: create plots and lightweight summaries for sanity checking.

This decomposition also suggests a preliminary division of work among
developers:

1. WOA preprocessing and caching.
2. Coupled hydrography interpolation, Omega pseudo-height iteration, and shared
   geometric-grid construction.
3. MPAS-Ocean-specific tracer and ALE output support based on the shared grid.
4. Omega-specific tracer and p-star output support based on the shared grid.
5. Diagnostics, validation, and regression tests.

Within this decomposition, the `initial_state` step still needs to port several
pieces of legacy init-mode functionality that are not part of
`shared_vert_coord` and are not already handled upstream in `e3sm/init`. For
the initial implementation, the responsibilities of `initial_state` should
likely include:

1. Consume the outputs of `shared_vert_coord`, including the converged
   geometric layer thicknesses and the model-agnostic hydrographic state on the
   target mesh.
2. Convert that hydrographic state into the tracer conventions required by the
   target model and populate the model's active tracer fields.
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
   `shared_vert_coord`, such as density-related diagnostics.
7. Write the final model-specific initial-condition file or files, including
   any forcing file analogous to `init_mode_forcing_data.nc` that remains part
   of the supported workflow.

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
important after WOA preprocessing, after `shared_vert_coord`, and before final
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

### Testing and Validation: The workflow produces consistent tracer initial conditions for MPAS-Ocean and Omega

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

Unit tests should cover any tracer-conversion utilities independently of the
full task. Task-level validation should then compare model-specific outputs on a
shared mesh to make sure they are mutually consistent when interpreted through
their respective tracer conventions.

Where practical, outputs on a small mesh should also be compared against the
legacy Compass plus init-mode workflow, recognizing that exact bit-for-bit
agreement may not be the right success criterion if the new implementation uses
cleaner thermodynamic conversions.

### Testing and Validation: Omega and MPAS-Ocean can be initialized on the same vertical grid

Date last modified: 2026/03/22

Contributors: Xylar Asay-Davis, Codex

When the same horizontal mesh is used for both models, task-level validation
should compare initialized geometric layer interfaces or thicknesses to confirm
that Omega and MPAS-Ocean represent the same vertical grid at initialization.

These comparisons should be part of the core acceptance criteria for the
shared-grid mode because direct comparability between the models is one of its
main purposes.

Vertical-coordinate testing should check that layer thicknesses, valid-level
masks, initialized geometric layer thicknesses, and derived depth or
pseudo-height fields are internally consistent and respect bathymetry and
minimum-thickness constraints.

For Omega, tests should also verify the convergence and stability of any EOS
iteration used to relate geometric height, pressure, and pseudo-height.

For MPAS-Ocean, tests should verify that the initialized layer-thickness state
is derived from the shared initialized geometric grid in the intended ALE
stretching and squashing formulation rather than silently falling back to the
legacy z-star construction.

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
