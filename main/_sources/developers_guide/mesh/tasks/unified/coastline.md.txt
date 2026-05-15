(dev-mesh-unified-coastline)=

# Coastline Steps and Tasks

This section of the Developer's guide covers the code for the coastline
extraction workflow.  The {ref}`users-mesh-unified-coastline` section describes
the user-facing aspects of the workflow such as the conventions,
algorithms, and config options.

The `polaris.tasks.mesh.spherical.unified.coastline` module provides a
raster-first coastline workflow on latitude-longitude grids. It computes the
full coastline at the finest supported resolution (0.03125°) and remaps the
results to coarser resolutions rather than repeating the expensive computation
at each resolution tier.

## Available tasks

The helper
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.add_coastline_tasks`
registers one standalone task for each supported latitude-longitude target
grid:

- `mesh/spherical/unified/coastline/0.03125_degree/task`
- `mesh/spherical/unified/coastline/0.06250_degree/task`
- `mesh/spherical/unified/coastline/0.12500_degree/task`
- `mesh/spherical/unified/coastline/0.25000_degree/task`

Each task is an instance of
{py:class}`polaris.tasks.mesh.spherical.unified.coastline.LatLonCoastlineTask`.

`add_coastline_tasks` iterates over `LAT_LON_TARGET_GRID_RESOLUTIONS` in
sorted (ascending) order so that the finest-resolution task is registered
first.  This ensures the shared
{py:class}`polaris.tasks.mesh.spherical.unified.coastline.ComputeCoastlineStep`
is created before coarser tasks retrieve it via
`component.get_or_create_shared_step`.

## Task structure and shared steps

`LatLonCoastlineTask` has a uniform structure at all resolutions:

1. Calls
   {py:func}`polaris.tasks.mesh.spherical.unified.coastline.get_unified_mesh_coastline_steps`
   with `resolution`, `cached=False`, and `include_viz=True`.  That factory
   obtains the shared topography-combine step from `e3sm/init` internally,
   always creates or retrieves the shared
   {py:class}`polaris.tasks.mesh.spherical.unified.coastline.ComputeCoastlineStep`
   at the finest supported resolution (0.03125°), and for coarser-resolution
   tasks additionally creates a
   {py:class}`polaris.tasks.mesh.spherical.unified.coastline.RemapCoastlineStep`.
2. Sets the shared `coastline.cfg` and adds all returned steps, using the
   dict keys returned by the factory as symlink names in the task workdir.

**Finest resolution (0.03125°)**

The task workdir contains symlinks to:

- `combine_topo_lat_lon_0.03125_degree` — the shared topography-combine step
  at 0.03125°
- `coastline_final` — the shared `ComputeCoastlineStep`
- `viz_coastline` — the shared `VizCoastlineStep`

**Coarser resolutions (0.06250°, 0.12500°, 0.25000°)**

The task workdir contains:

- `combine_topo_lat_lon_0.03125_degree` — the same shared topography-combine
  step at 0.03125° (the finest combine step is always used by
  `ComputeCoastlineStep` regardless of which task instantiates it)
- `coastline_compute` — the shared `ComputeCoastlineStep` at 0.03125°
- `coastline_final` — a `RemapCoastlineStep` at the task's resolution
- `viz_coastline` — a `VizCoastlineStep` for the remapped output

The `ComputeCoastlineStep` is created once (by the finest-resolution task) and
shared via `component.get_or_create_shared_step`.  Coarser tasks retrieve the
existing instance; the `combine_topo_step` argument passed by a coarser task
has no effect once the step has already been created.

## Implementation map

### ComputeCoastlineStep (0.03125°)

`ComputeCoastlineStep.run()` reads `coastline.cfg`, opens `topography.nc`, and
dispatches the numerical work to
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.compute.build_coastline_datasets`.
That helper operates on `(lat, lon)` NumPy arrays and, for each convention:

- builds a candidate ocean mask from `base_elevation`, `ice_mask`, and
  `grounded_mask`;
- calls `_flood_fill_ocean` to retain only the connected ocean;
- calls `_coastline_edges` to derive the raster edge diagnostics used for
  coastline sampling; and
- calls `_signed_distance_from_mask` to compute the signed-distance field.

The results are assembled by `_build_single_coastline_dataset` into one raster
dataset per convention with metadata that records the thresholds, flood-fill
seed strategy, and sign convention.

The core numerical functions live in `polaris.mesh.spherical.coastline`;
`ComputeCoastlineStep` is responsible only for task-level configuration,
shared critical-transect loading, and writing outputs.

### RemapCoastlineStep (coarser resolutions)

`RemapCoastlineStep.run()` reads `coastline.cfg`, then for each convention:

1. Reads the 0.03125° `ocean_mask` (linked as `fine_coastline_{convention}.nc`)
   and `signed_distance`.
2. Block-averages the fine `ocean_mask` onto the coarser grid
   (`_block_average`), yielding an ocean fraction in [0, 1], then thresholds
   at `mask_threshold` to produce a binary `ocean_mask`.  No second flood fill
   is performed; connectivity is inherited from the 0.03125° result.
3. Bilinearly remaps the absolute value of the fine `signed_distance`
   (`_bilinear_zoom`) and re-signs using the coarser `ocean_mask`.
4. Writes the output with provenance attributes that record the source
   resolution and source step path.

Because all four grids are perfectly nested (each coarser resolution is an
exact 2ⁿ multiple of 0.03125°), block averaging is exact conservative
remapping with no ESMF or pyremap dependency.

## Visualization

`VizCoastlineStep` reads the coastline files and writes:

- global and Antarctic binary plots of the final `ocean_mask` for each
  convention; and
- global and Antarctic signed-distance plots for each convention.

It also writes `debug_summary.txt`, which records convention-specific counts
such as ocean and land cells and the min/max signed distance.

`VizCoastlineStep` is duck-typed on `output_filenames` and `path`, so it
works with both `ComputeCoastlineStep` (0.03125°) and `RemapCoastlineStep`
(coarser resolutions) as its `coastline_step`.

## Extension points

The current implementation is intentionally narrow: lat-lon target grids,
three coastline conventions, and raster outputs. Common developer changes are:

- **Adding a new target resolution.** Add the resolution to
  `LAT_LON_TARGET_GRID_RESOLUTIONS` in
  `polaris.mesh.spherical.unified.resolutions`. The new resolution must be an
  exact 2ⁿ multiple of 0.03125° so that `RemapCoastlineStep` can block-average
  from the finest grid. Also add the resolution to the `e3sm/init/topo/combine`
  tasks if combined topography at that resolution will be needed by other
  workflows.
- **Adding a new convention.** Extend `CONVENTIONS` and the `candidate_masks`
  dictionary in `build_coastline_datasets()`, then update the visualization
  step and the associated tests.
- **Extending the output contract.** Update `_build_single_coastline_dataset()`
  and `_coastline_remap_dataset()` in parallel so both the prepare and remap
  paths produce the new variable, then update the plotting code in `viz.py`
  and the tests.

## Configuration plumbing

The coastline workflow is configured through a single shared `coastline.cfg`
that covers all resolution tiers.

`ComputeCoastlineStep` consumes `[coastline]` options:

- `include_critical_transects`
- `mask_threshold`
- `sea_level_elevation`
- `distance_chunk_size`

`RemapCoastlineStep` consumes `[coastline]` options:

- `mask_threshold` — applied to the block-averaged ocean fraction

`VizCoastlineStep` consumes `[viz_coastline]` options:

- `antarctic_max_latitude`
- `dpi`
- `signed_distance_limit`

The {ref}`users-mesh-unified-coastline` page explains how these options affect the
user-visible behavior of the workflow.

## Example usage

To register the default coastline tasks for the `mesh` component:

```python
from polaris.tasks.mesh.spherical.unified.coastline import add_coastline_tasks

add_coastline_tasks(component)
```

To reuse the shared finest-resolution `ComputeCoastlineStep` inside another
workflow that needs the 0.03125° coastline products:

```python
from polaris.tasks.mesh.spherical.unified.coastline import (
    get_unified_mesh_coastline_steps,
)

steps, config = get_unified_mesh_coastline_steps(
    resolution=0.03125,
    cached=True,
    include_viz=False,
)
fine_coastline_step = steps['coastline_final']
```

To get coastline steps at a coarser resolution:

```python
from polaris.tasks.mesh.spherical.unified.coastline import (
    get_unified_mesh_coastline_steps,
)

steps, config = get_unified_mesh_coastline_steps(
    resolution=0.25,
    cached=True,
    include_viz=False,
)
# steps['coastline_compute'] is the shared ComputeCoastlineStep at 0.03125°
# steps['coastline_final'] is the RemapCoastlineStep at 0.25°
coarse_coastline_step = steps['coastline_final']
```

`get_unified_mesh_coastline_steps` returns a 2-tuple `(steps, config)`.  The
combine step is obtained internally by the factory; callers do not need to
provide it.  The `cached` parameter controls whether the returned steps have
their `cached` flag set (default `True` for use in downstream tasks; `False`
for standalone coastline tasks that run the steps unconditionally).

## Test coverage

Unit tests in `tests/mesh/spherical/unified/test_coastline.py` validate the
public coastline dataset contract, convention-specific Antarctic behavior,
exclusion of disconnected inland water, and the use of the northernmost
latitude row for flood-fill seeding.

Unit tests in `tests/mesh/spherical/unified/test_coastline_remap.py` validate
the remap helpers (`_block_average`, `_bilinear_zoom`, `_coarsen_coordinate`,
`_compute_scale`), the thresholding and sign convention of
`_coastline_remap_dataset`, end-to-end execution of `RemapCoastlineStep.run()`,
and that `get_unified_mesh_coastline_steps` creates a `RemapCoastlineStep` when
`resolution` differs from `FINEST_RESOLUTION`.
