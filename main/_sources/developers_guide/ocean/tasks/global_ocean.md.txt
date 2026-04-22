(dev-ocean-global-ocean)=

# global_ocean

The `global_ocean` tasks in `polaris.tasks.ocean.global_ocean` are intended
for preprocessing and initialization workflows that are upstream of any
particular MPAS mesh. The first task category under this framework is
`hydrography/woa23`, which builds a reusable hydrography product from the
World Ocean Atlas 2023 on its native 0.25-degree latitude-longitude grid.

(dev-ocean-global-ocean-framework)=

## framework

The shared config options for the WOA23 hydrography task are described in
{ref}`ocean-global-ocean` in the User's Guide.

The implementation is intentionally organized around reusable Polaris steps
rather than around the legacy Compass `utility/extrap_woa` multiprocessing
workflow. One notable design choice is that the task reuses the combined
topography product from `e3sm/init` rather than taking a raw topography
filename as a task-specific input.

### cached topography dependency

The helper
{py:func}`polaris.tasks.ocean.global_ocean.hydrography.woa23.get_woa23_topography_step`
creates a shared `e3sm/init` {py:class}`polaris.tasks.e3sm.init.topo.combine.step.CombineStep`
configured for a 0.25-degree lat-lon target grid. The
{py:class}`polaris.tasks.ocean.global_ocean.hydrography.woa23.task.Woa23`
task adds this step with a symlink `combine_topo` and prefers to use a cached
version of its outputs when matching entries are available in the
`e3sm/init` cache database.

This keeps the expensive topography blending logic in one place and makes the
ocean hydrography preprocessing task consistent with the broader Polaris
approach to shared, cacheable preprocessing steps.

(dev-ocean-global-ocean-woa23)=

## hydrography/woa23

The {py:class}`polaris.tasks.ocean.global_ocean.hydrography.woa23.task.Woa23`
task is the Polaris port of the WOA preprocessing part of the legacy Compass
workflow.

### combine

The class
{py:class}`polaris.tasks.ocean.global_ocean.hydrography.woa23.combine.CombineStep`
combines January and annual WOA23 temperature and salinity climatologies into
a single dataset. January values are used where they exist, and annual values
fill deeper levels where the monthly product is not available.

WOA23 supplies in-situ temperature and practical salinity, so this step uses
`gsw` to derive conservative temperature and absolute salinity for the
canonical `woa_combined.nc` product.

### extrapolate

The class
{py:class}`polaris.tasks.ocean.global_ocean.hydrography.woa23.extrapolate.ExtrapolateStep`
uses the cached combined-topography product on the WOA grid together with
`woa_combined.nc` to build a 3D ocean mask and then fill missing WOA values in
two stages:

1. Horizontal then vertical extrapolation within the ocean mask
2. Horizontal then vertical extrapolation into land and grounded-ice regions

The final output is `woa23_decav_0.25_jan_extrap.nc`.
