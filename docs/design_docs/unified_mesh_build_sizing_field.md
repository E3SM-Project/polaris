# Sizing-Field Construction for Unified Base Mesh Workflow

date: 2026/04/13

Contributors:

- Xylar Asay-Davis
- Codex

## Summary

This design describes the shared `build_sizing_field` step and associated task
that can run that shared step on its own for the unified global base-mesh
workflow. The purpose of the step is to combine baseline mesh-resolution
choices with coastline and river controls into a single global lon/lat sizing
field that can be passed directly to the final spherical JIGSAW mesh step.

The implementation is being added on the `add-build-sizing-field` branch in
Polaris pull request <https://github.com/E3SM-Project/polaris/pull/561>.

The design assumes that `prepare_coastline` and `prepare_river_network` have
already converted raw source datasets into shared products with explicit
interfaces. Those stages are implemented in `add-prepare-coastline`
(<https://github.com/E3SM-Project/polaris/pull/545>) and
`add-prepare-river-network`
(<https://github.com/E3SM-Project/polaris/pull/556>). `build_sizing_field`
consumes those products directly rather than mixing raw-data interpretation,
feature preprocessing, and mesh-sizing logic in one place.

Feature refinement is expressed as clearly as practical in the sizing field
itself. For coastline refinement, this points strongly toward explicit raster
candidate fields. For rivers, the current implementation uses target-grid
river masks to drive sizing-field refinement. The separate direct use of river
geometry in final mesh generation, which exists in the standalone reference
implementation in
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh), remains a
follow-up decision for the final base-mesh stage.

Success means that Polaris gains a documented, reusable sizing-field workflow
whose inputs from earlier steps are clear, whose outputs are directly usable by
the final mesh step, and whose diagnostics make it easy to see why a given
region is refined.

## Requirements

### Requirement: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` shall produce a global sizing field on a regular lon/lat
grid that can be consumed directly by the final spherical mesh-generation
step.

The sizing field shall encode the raster part of the requested spatial
variation in target mesh resolution and shall interoperate cleanly with any
retained feature geometry that the final mesh step uses directly.

### Requirement: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` shall consume the outputs of `prepare_coastline` and
`prepare_river_network` through explicit interfaces.

The sizing-field step shall not need to re-read raw coastline, raw topography,
or raw HydroRIVERS source datasets in the standard workflow.

### Requirement: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The workflow shall support a baseline resolution pattern together with local
refinement controls for coastline and river features.

The first design shall support separate control of at least:

- background ocean resolution;
- background land resolution;
- coastline refinement and transition zones; and
- river-channel and river-outlet refinement.

The design shall allow additional feature classes such as watershed
boundaries, lakes, or dams to be added later without redesigning the full
sizing-field logic.

### Requirement: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The sizing field shall be defined on the same supported target-grid tier used
by the upstream shared preprocessing steps.

The first design shall work with a small discrete set of supported target-grid
resolutions rather than assuming arbitrary default resolutions.

### Requirement: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

Polaris shall provide a task that runs the shared `build_sizing_field` step
and the shared steps it depends on (e.g. `prepare_coastline` and
`prepare_river_network`).

The standalone task shall make it practical to inspect candidate refinement
fields and the final sizing field without running the full unified mesh
workflow.

The same shared step and configuration shall be reusable from the full unified
workflow when settings match.

## Algorithm Design

### Algorithm Design: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The sizing field should be built on a regular lon/lat grid using the shared
target-grid tier selected for the workflow. The resulting field should be in
the same basic form already expected by Polaris spherical mesh generation:
`cellWidth(lat, lon)` or an equivalent gridded `h(x)` product.

The output should therefore be a directly inspectable and cacheable artifact
rather than an implicit side effect of JIGSAW geometry handling. This makes
the final `unified_base_mesh` step simpler because it only needs to consume the
finished sizing field and convert it into a JIGSAW mesh and then an MPAS mesh.

### Algorithm Design: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The intended input contract should be explicit:

- from `prepare_coastline`: a land/ocean mask on the selected target grid and
  a signed coastal-distance field, together with any needed coastline-edge
  diagnostics; and
- from `prepare_river_network`: a simplified vector river network suitable for
  downstream geometry use, plus target-grid river-channel and river-outlet
  masks, together with outlet metadata.

With this contract, `build_sizing_field` can focus on mesh-resolution logic
rather than source-data interpretation.

The first design should avoid making `prepare_river_network` responsible for
the full river-refinement policy. If `build_sizing_field` needs a river
distance field, it can derive that distance from the simplified river products
it consumes. At the same time, the first Polaris design should explicitly
retain the existing standalone use of river geometry in the final mesh step.

### Algorithm Design: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The first sizing-field algorithm should be framed as a set of candidate fields
combined into a final mesh-spacing field.

The background field should be constructed first. A reasonable first design is
to use the land/ocean mask from `prepare_coastline` to choose between:

- an ocean background, which may be constant or may reuse existing Polaris
  latitude-dependent functions such as `EC_CellWidthVsLat()` or
  `RRS_CellWidthVsLat()`; and
- a land background, which may be constant at first.

Feature refinement should then be expressed as additional candidate fields:

- a coastline candidate derived from the signed coastal-distance field, with
  configurable transition widths and potentially different treatment on the
  land and ocean sides;
- a river candidate derived from distance to the simplified river-channel
  network or, in the simplest first pass, from the channel mask itself; and
- an outlet candidate derived from the river-outlet mask, since outlets may
  merit stronger or separate refinement.

The final sizing field should be the pointwise minimum of the background field
and all active feature candidates. This is a clearer design than sequential
overwrites because it makes each contribution explicit and guarantees that
adding a new feature control cannot accidentally coarsen the mesh.

For coastline refinement, this is also where the Polaris design can diverge
most clearly from the current standalone workflow by favoring explicit raster
candidate fields. For rivers, however, the first Polaris design should be more
conservative. In
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh), river
influence is split between raster products and separate geometry handling.
Because that behavior is the least well-understood part of the workflow,
Polaris should preserve that division of labor as much as practical in the
early implementation.

In that formulation, `build_sizing_field` still owns the raster candidate
fields associated with rivers and outlets. The final `unified_base_mesh` step
may additionally pass simplified river geometry to JIGSAW to preserve existing
cell-placement behavior, but that is not part of the implemented
`build_sizing_field` workflow yet.

If abrupt changes remain after candidate-field composition, the first design
may include a light regularization or smoothing stage, but that should be a
small post-processing step on the final field, not a substitute for clear
feature definitions.

### Algorithm Design: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

`build_sizing_field` should not choose its own grid resolution independently.
Instead, it should consume the selected workflow target-grid tier and produce
its output on that same grid.

The first design should therefore support a small discrete set of target-grid
tiers shared with `prepare_coastline` and `prepare_river_network`. This keeps
the interfaces between stages simple and makes cached reuse of expensive
preprocessing products practical.

### Algorithm Design: Standalone Sizing-Field Task

Date last modified: 2026/04/10

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task should be a thin wrapper around the shared
`build_sizing_field` step rather than a separate implementation path.

The task should depend on the selected coastline and river products and should
write diagnostics that make the sizing-field composition easy to inspect, for
example the background field, coastline candidate, river candidate, outlet
candidate, and final field.

Because the task wraps the shared step, the same sizing-field products can
later be reused by the final mesh step and the full unified workflow when
configuration choices match.

## Implementation

### Implementation: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The current implementation is organized under
`polaris/tasks/mesh/spherical/unified/sizing_field/` as:

- `build.py` for the shared `BuildSizingFieldStep` and
  `build_sizing_field_dataset()` composition function;
- `steps.py` for shared-step construction;
- `task.py` and `tasks.py` for standalone task registration;
- `configs.py` for unified-mesh config loading; and
- `viz.py` for diagnostic plots.

The shared step writes `sizing_field.nc`. The main output is `cellWidth` on the
shared `lat`/`lon` grid, with units of km. The dataset also includes
diagnostic fields:

- `background_cell_width`;
- `ocean_background_cell_width`;
- `land_river_cell_width`;
- `pre_coastline_cell_width`;
- `coastline_cell_width`;
- `coastal_transition_delta`;
- `river_channel_cell_width`;
- `river_outlet_cell_width`; and
- `active_control`.

The `add-build-sizing-field` branch also adds `UnifiedCellWidthMeshStep` in
`polaris.mesh.spherical.unified.cell_width`. This step reads `cellWidth`,
`lon`, and `lat` from `sizing_field.nc` and then reuses the existing spherical
mesh-generation machinery.

### Implementation: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The implementation keeps step interfaces explicit and avoids reintroducing
raw-dataset dependencies inside `build_sizing_field`.

The sibling `add-lat-lon-topo-combine` branch already implements the shared
lat-lon `e3sm/init/topo/combine` tasks at 1.0, 0.25, 0.125, 0.0625 and
0.03125 degree and the associated `CombineStep` support. That branch provides
the upstream target-grid topography path assumed by this design. See Polaris
pull request <https://github.com/E3SM-Project/polaris/pull/526>.

`BuildSizingFieldStep.setup()` links only two upstream data products:
`coastline.nc` from the selected coastline convention and `river_network.nc`
from the corresponding river lat-lon step. It does not read raw topography or
HydroRIVERS data.

### Implementation: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The implementation builds the final field from explicit candidate fields. It
supports three ocean background modes: `constant`, `rrs_latitude`, and
`ec_latitude`. Land starts from a configurable constant background.

River channel and river outlet candidates are mask-based. They are controlled
separately with `enable_river_channel_refinement`, `river_channel_km`,
`enable_river_outlet_refinement`, and `river_outlet_km`.

Coastline refinement uses the signed-distance field from `prepare_coastline`.
The current algorithm composes land and river controls first, then applies a
linear coastline transition on the land side using
`coastline_transition_land_km`. The coastline target is the local ocean
background, so the coastal buffer can either coarsen or refine nearby land
and river controls depending on the adjacent ocean resolution.

`active_control` records the winning control with
`0=background 1=coastline 2=river_channel 3=river_outlet`. Dataset attributes
also count how many river-channel and river-outlet mask cells are finer than,
equal to, or coarser than the background.

### Implementation: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The implementation uses the named unified-mesh configs in
`polaris/mesh/spherical/unified/` to select the shared target-grid tier.
The currently implemented named meshes are:

- `ocn_240km_lnd_240km_riv_240km`, using 0.25 degree;
- `ocn_30km_lnd_10km_riv_10km`, using 0.125 degree; and
- `ocn_rrs_6to18km_lnd_12km_riv_6km`, using 0.03125 degree.

The sizing-field shared-step subdirectory includes the mesh name:
`spherical/unified/<mesh_name>/sizing_field/build`. This makes the mesh
configuration part of the work-directory layout and cache key.

### Implementation: Standalone Sizing-Field Task

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The implementation adds `SizingFieldTask`, a lightweight task wrapper around
the shared steps. For each named mesh, the standalone task links:

- the shared lat-lon topography combine step;
- the shared coastline step and an optional coastline visualization step;
- the mesh-specific shared river source step;
- the mesh-specific shared river lat-lon step; and
- the shared sizing-field build step plus its visualization step.

`add_build_sizing_field_tasks()` registers one standalone sizing-field task per
named mesh. The task-specific path is
`spherical/unified/<mesh_name>/sizing_field/task`.

## Testing

### Testing and Validation: JIGSAW-Ready Global Sizing Field

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Current unit tests in `tests/mesh/spherical/unified/test_sizing_field.py`
verify that `build_sizing_field_dataset()` writes a `cellWidth` field with
the expected values for representative configurations and that
`UnifiedCellWidthMeshStep` reads `cellWidth`, `lon`, and `lat` from
`sizing_field.nc`.

There is not yet an end-to-end task-level test that passes this sizing field
through JIGSAW and verifies `base_mesh.nc` and `graph.info`.

### Testing and Validation: Explicit Consumption of Shared Coastline and River Products

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Unit tests build synthetic coastline and river products and pass them directly
to `build_sizing_field_dataset()`. The step implementation links only
`coastline.nc` and `river_network.nc`, so raw topography and raw HydroRIVERS
inputs are outside the sizing-field interface.

The remaining validation gap is task-level: the full standalone sizing-field
task should be run on real shared coastline and river outputs for each named
mesh.

### Testing and Validation: Composable Feature-Based Resolution Controls

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Current unit tests check:

- a uniform 240 km case with no active refinement;
- a split 30 km ocean and 10 km land/river case;
- an RRS latitude-dependent ocean background;
- coastline transition composition using signed distance;
- river outlet controls composed before coastline transitions; and
- `active_control` values for representative cells.

There is not yet validation on full global products showing that coastline,
river-channel, and outlet controls influence the intended real-world regions
with the intended relative strengths.

### Testing and Validation: Compatibility with Shared Target-Grid Tiers

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

Current unit tests verify that `get_sizing_field_config()` uses the unified
mesh configs, that the sizing-field step factory uses mesh-specific
subdirectories, and that the registered standalone task count matches the
number of named unified-mesh configs.

There is not yet a full run validating all supported target-grid dimensions or
cache reuse across setup/run workflows.

### Testing and Validation: Standalone Sizing-Field Task

Date last modified: 2026/04/25

Contributors:

- Xylar Asay-Davis
- Codex

The standalone task is now implemented as the primary place to inspect the
component refinement fields and the final sizing field before they are used in
the full unified workflow. Unit tests verify task registration for each named
mesh. The visualization step writes `sizing_field_overview.png`.

Smoke tests for the full sizing-field workflow is being performed on Frontier.
An update will follow once satisfactory results are available.
