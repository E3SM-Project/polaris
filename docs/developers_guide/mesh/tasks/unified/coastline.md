(dev-mesh-coastline-tasks)=

# Coastline Steps and Tasks

This section of the Developer's guide covers the code for the coastline
extraction workflow.  The {ref}`users-mesh-coastline` section describes
the user-facing aspects of the workflow such as the conventions,
algorithms, and config options.

The `polaris.tasks.mesh.spherical.unified.coastline` module provides a
raster-first coastline workflow on latitude-longitude grids. It reuses the
shared `e3sm/init/topo/combine` workflow to create `topography.nc`, derives
convention-specific ocean masks from that dataset, and then computes
signed distance to the nearest raster coastline sample.

## Available tasks

The helper
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.add_coastline_tasks`
registers one standalone task for each supported latitude-longitude target
grid:

- `mesh/spherical/unified/coastline/lat_lon/0.25000_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.12500_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.06250_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.03125_degree/task`

Each task is an instance of
{py:class}`polaris.tasks.mesh.spherical.unified.coastline.LatLonCoastlineTask`.

Current testing suggests `0.25000_degree` is useful mainly as a cheaper
inspection tier and is too coarse for scientifically valid coastline products.
The finer `0.12500_degree`, `0.06250_degree`, and `0.03125_degree` tasks are
the supported science-oriented coastline tiers.

If a developer wants to add more resolutions, they can edit the list of
resolutions in `add_coastline_tasks()`. It would be best to also add
that resolution to the tasks for creating combined topography in
`polaris.tasks.e3sm.init.topo.resolutions.LAT_LON_RESOLUTIONS`, though
that isn't strictly required.

## Task structure and shared steps

`LatLonCoastlineTask` first requests the shared latitude-longitude combine
step from the `e3sm/init` component with
`get_lat_lon_topo_steps(..., include_viz=False)` and adds that step to the
task as `combine_topo`. It then calls
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.get_lat_lon_coastline_steps`
with `include_viz=True`, links the shared `coastline.cfg`, and adds:

- a shared
   {py:class}`polaris.tasks.mesh.spherical.unified.coastline.PrepareCoastlineStep` in
   `spherical/unified/coastline/lat_lon/<resolution>/prepare`; and
- a shared
   {py:class}`polaris.tasks.mesh.spherical.unified.coastline.VizCoastlineStep`
   in `spherical/unified/coastline/lat_lon/<resolution>/prepare/viz`.

This keeps the expensive combined-topography step shareable across tasks while
still making the coastline products and diagnostics visible from the task work
directory.

## Implementation map

`PrepareCoastlineStep.run()` reads `coastline.cfg`, opens `topography.nc`, and
dispatches the numerical work to
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.prepare.build_coastline_datasets`.
That helper operates on `(lat, lon)` NumPy arrays and, for each convention:

- builds a candidate ocean mask from `base_elevation`, `ice_mask`, and
  `grounded_mask`;
- calls
  {py:func}`polaris.tasks.mesh.spherical.unified.coastline.prepare._flood_fill_ocean`
  to retain only the connected ocean;
- calls
  {py:func}`polaris.tasks.mesh.spherical.unified.coastline.prepare._coastline_edges`
  to derive the transient raster edge diagnostics used for coastline
  sampling; and
- calls
  {py:func}`polaris.tasks.mesh.spherical.unified.coastline.prepare._signed_distance_from_mask`
  to compute the convention-specific signed-distance field.

The results are assembled by
{py:func}`polaris.tasks.mesh.spherical.unified.coastline.prepare._build_single_coastline_dataset`
into one raster dataset per convention, with metadata that records the
thresholds, flood-fill seed strategy, and sign convention. The detailed
algorithm is documented in the {ref}`users-mesh-coastline` page so that the
developer guide can stay focused on code organization and extension points.

The output contract is entirely raster-based. The workflow does not currently
write a persisted vector coastline product or a Natural Earth fallback.

## Visualization

`VizCoastlineStep` reads the coastline files and writes:

- global and Antarctic binary plots of the final `ocean_mask` for each
  convention; and
- global and Antarctic signed-distance plots for each convention.

It also writes `debug_summary.txt`, which records convention-specific counts
such as ocean and land cells and the min/max signed distance.

## Extension points

The current implementation is intentionally narrow: lat-lon target grids,
three coastline conventions, and raster outputs. Common developer changes are:

- adding a new target resolution by updating `add_coastline_tasks()` and,
  ideally, the matching shared `e3sm/init/topo/combine` tasks;
- adding a new convention by extending `CONVENTIONS`, the `candidate_masks`
  dictionary in `build_coastline_datasets()`, the visualization step, and the
  associated tests; and
- extending the output contract by updating
  `_build_single_coastline_dataset()`, the plotting code in `viz.py`, and the
  tests that validate dataset contents and behavior.

## Configuration plumbing

The coastline workflow is configured through `coastline.cfg`.

`PrepareCoastlineStep` consumes `[coastline]` options:

- `resolution_latlon`
- `include_critical_transects`
- `mask_threshold`
- `sea_level_elevation`
- `distance_chunk_size`

`VizCoastlineStep` consumes `[viz_coastline]` options:

- `antarctic_max_latitude`
- `dpi`
- `signed_distance_limit`

The {ref}`users-mesh-coastline` page explains how these options affect the
user-visible behavior of the workflow.

The reusable coastline-building functions now live in
`polaris.mesh.spherical.coastline`, and
`PrepareCoastlineStep` is responsible only for task-level configuration,
shared critical-transect loading, and writing outputs. Shared default
critical transects are loaded from
`polaris.mesh.spherical.critical_transects` and, when enabled, are rasterized
onto the target lat-lon grid before flood fill.

## Example usage

To register the default coastline tasks for the `mesh` component:

```python
from polaris.tasks.mesh.spherical.unified.coastline import \
   add_coastline_tasks

add_coastline_tasks(component)
```

To reuse the shared coastline steps inside another workflow:

```python
from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.topo.combine.steps import get_lat_lon_topo_steps
from polaris.tasks.mesh.spherical.unified.coastline import \
   get_lat_lon_coastline_steps

combine_steps, _ = get_lat_lon_topo_steps(
    component=e3sm_init,
    resolution=0.25,
    include_viz=False,
)
combine_topo_step = combine_steps[0]

coastline_steps, config = get_lat_lon_coastline_steps(
    component=component,
    combine_topo_step=combine_topo_step,
    resolution=0.25,
    include_viz=True,
)
```

## Test coverage

Unit tests in `tests/mesh/spherical/unified/test_coastline.py` currently
validate the public coastline dataset contract, convention-specific Antarctic
behavior, exclusion of disconnected inland water, and the use of the
northernmost latitude row for flood-fill seeding. There is not yet a
task-level smoke test for the full standalone workflow.