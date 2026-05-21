(dev-mesh-unified-sizing-field)=

# Sizing-Field Steps and Tasks

This section of the Developer's guide covers the code for the unified-mesh
sizing-field workflow. The {ref}`users-mesh-unified-sizing-field` section
describes the user-facing behavior, configuration options, and output products.

The `polaris.tasks.mesh.spherical.unified.sizing_field` package assembles a
cell-width map on a shared lat-lon target grid from the coastline and river
products produced by the upstream workflows. The sizing-field dataset is the
key input to the JIGSAW mesh generator in the downstream base-mesh step.

## Available tasks

The helper
{py:func}`polaris.tasks.mesh.spherical.unified.sizing_field.add_sizing_field_tasks`
registers one standalone task for each mesh name in
`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`:

- {py:class}`polaris.tasks.mesh.spherical.unified.sizing_field.SizingFieldTask`
  at `mesh/spherical/unified/<mesh_name>/sizing_field/task`.

## Task structure and shared steps

`SizingFieldTask` calls
{py:func}`polaris.tasks.mesh.spherical.unified.sizing_field.get_unified_mesh_sizing_field_steps`
with `include_viz=True`, which in turn calls the river step factory (see
{ref}`dev-mesh-unified-river`) to obtain all upstream steps and then creates
{py:class}`polaris.tasks.mesh.spherical.unified.sizing_field.BuildSizingFieldStep`.

The task workdir contains symlinks for all upstream coastline and river steps
plus:

- `sizing_field` — the shared `BuildSizingFieldStep`
- `sizing_field_viz` — the shared `VizSizingFieldStep` (when
  `include_viz=True`)

## Implementation map

### `build.py`

`BuildSizingFieldStep.setup()` links the coastline convention file from
the upstream coastline step and `river_network.nc` from the upstream
lat-lon rasterize step.  It also calls the mesh-family hook
`setup_sizing_field_step()` so family-specific inputs (e.g. the Southern
Ocean high-resolution region GeoJSON for `so_region` meshes) can be
registered.

`BuildSizingFieldStep.run()` opens `coastline.nc` and `river_network.nc`,
delegates ocean-background construction to the mesh family via
`build_ocean_background()`, and calls the public helper
{py:func}`polaris.tasks.mesh.spherical.unified.sizing_field.sizing_field_dataset`
to compose the full sizing field.  The resulting dataset is written to
`sizing_field.nc`.

The public helper `sizing_field_dataset()` combines:

- the ocean background from the mesh family (a 2-D cell-width array on the
  lat-lon grid);
- the land background (`land_background_km`);
- an optional coastline-proximity refinement controlled by
  `enable_coastline_refinement` and `coastline_transition_land_km`; and
- optional river-channel refinement controlled by
  `enable_river_channel_refinement` and `river_channel_km`.

The result is a `cell_width` variable on the lat-lon grid, together with
provenance attributes recording the source coastline and river steps.

### `viz.py`

`VizSizingFieldStep` reads `sizing_field.nc` and writes a global overview
plot, an active-control diagnostic map (showing which refinement control
dominates at each grid cell), and a plain-text `debug_summary.txt` with
min/max cell widths and count statistics.

## Configuration plumbing

All sizing-field steps use mesh-specific configs built through
`get_sizing_field_config(mesh_name)`, which layers:

- the generic `unified_mesh.cfg` defaults;
- the shared `river_network.cfg` file;
- the family-specific config (e.g. `default.cfg` or `so_region.cfg`); and
- the mesh-specific config file (e.g. `u.oi30.lr10.cfg`).

`BuildSizingFieldStep` consumes the `[sizing_field]` section:

- `ocean_background_mode` — `'constant'` or `'rrs_latitude'` (or delegated
  to the mesh family)
- `ocean_background_min_km` and `ocean_background_max_km` — cell-width bounds
  for the ocean background
- `land_background_km` — cell width for land cells
- `enable_coastline_refinement` — toggle coastline-proximity refinement
- `coastline_transition_land_km` — width of the land-side transition zone
- `enable_river_channel_refinement` — toggle river-channel refinement
- `river_channel_km` — target cell width along river channels

`VizSizingFieldStep` consumes the `[sizing_field_viz]` section:

- `dpi` — output resolution for diagnostic plots
- `cell_width_cmap` — colormap for cell-width plots

The {ref}`users-mesh-unified-sizing-field` page explains how these options
affect the user-visible behavior of the workflow.

## Extension points

Common extension paths for future development are:

- **Adding a new named mesh.** Create a new `.cfg` file under
  `polaris.mesh.spherical.unified`. Task registration discovers mesh names
  from those config files automatically.
- **Adding a new ocean-background mode.** Implement the mode in
  `polaris.mesh.spherical.unified.base_mesh` (or a new mesh family) and
  handle it in `build_ocean_background()`.
- **Adding a new refinement control.** Add parameters to `sizing_field_dataset()`
  and the `[sizing_field]` config section, then update the visualization step
  and the associated tests.

## Test coverage

Unit tests in `tests/mesh/spherical/unified/test_sizing_field.py` validate
the public `sizing_field_dataset()` helper, the ocean-background construction
for each supported mode, and that `get_unified_mesh_sizing_field_steps`
creates the expected shared steps for each named mesh.
