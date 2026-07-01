(dev-ocean-realistic-global)=

# realistic_global

The `realistic_global` tasks in `polaris.tasks.ocean.realistic_global` are
intended for preprocessing and initialization workflows that are upstream of
any particular MPAS mesh. The first task category under this framework is
`hydrography/woa23`, which builds a reusable hydrography product from the
World Ocean Atlas 2023 on its native 0.25-degree latitude-longitude grid.
The second category, `init`, creates mesh-specific ocean initial conditions
using that hydrography and the culled mesh from `e3sm/init`.

(dev-ocean-realistic-global-framework)=

## framework

The shared config options for the WOA23 hydrography task are described in
{ref}`ocean-realistic-global` in the User's Guide.

The implementation is intentionally organized around reusable Polaris steps
rather than around the legacy Compass `utility/extrap_woa` multiprocessing
workflow. One notable design choice is that the task reuses the combined
topography product from `e3sm/init` rather than taking a raw topography
filename as a task-specific input.

### cached topography dependency

{py:func}`polaris.tasks.ocean.realistic_global.hydrography.woa23.steps.get_woa23_steps`
internally creates a shared `e3sm/init`
{py:class}`polaris.tasks.e3sm.init.topo.combine.step.CombineStep`
configured for a 0.25-degree lat-lon target grid. The
{py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.task.Woa23`
task adds this step with a symlink `combine_topo`.

Because `CombineStep` sets `default_cached = True`, the `combine_topo` step
is automatically treated as cached during setup — no explicit opt-in is
needed.

This keeps the expensive topography blending logic in one place and makes the
ocean hydrography preprocessing task consistent with the broader Polaris
approach to shared, cacheable preprocessing steps.  See
{ref}`dev-step-default-cached` for a full description of the
`default_cached` / `free_running_steps` mechanism.

(dev-ocean-realistic-global-woa23)=

## hydrography/woa23

The {py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.task.Woa23`
task is the Polaris port of the WOA preprocessing part of the legacy Compass
workflow.

### combine

The class
{py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.combine.CombineStep`
combines January and annual WOA23 temperature and salinity climatologies into
a single dataset. January values are used where they exist, and annual values
fill deeper levels where the monthly product is not available.

WOA23 supplies in-situ temperature and practical salinity, so this step uses
`gsw` to derive conservative temperature and absolute salinity for the
canonical `woa_combined.nc` product.

### extrapolate

The class
{py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.extrapolate.ExtrapolateStep`
uses the cached combined-topography product on the WOA grid together with
`woa_combined.nc` to build a 3D ocean mask and then fill missing WOA values in
two stages:

1. Horizontal then vertical extrapolation within the ocean mask
2. Horizontal then vertical extrapolation into land and grounded-ice regions

The final output is `woa23_decav_0.25_jan_extrap.nc`.

(dev-ocean-realistic-global-init)=

## init

The `realistic_global/init` task family creates mesh-specific ocean initial
conditions using WOA23 hydrography and the culled mesh produced by
`e3sm/init`.  One
{py:class}`polaris.tasks.ocean.realistic_global.init.task.RealisticGlobalInit`
task is registered per MPAS mesh; the target ocean model is determined by the
``[ocean] model`` config option at run time.

### step dependency chain

{py:func}`polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`
composes the full chain:

1. **cull_topo** ({py:class}`~polaris.tasks.ocean.realistic_global.init.cull_topo.CullTopoStep`):
   reindexes remapped topography from the base mesh to the culled ocean mesh
   using `ocean_map_culled_to_base.nc`, producing `topography_culled.nc`.
2. **remap_woa23** ({py:class}`~polaris.tasks.ocean.realistic_global.init.remap_woa23.RemapWoa23Step`):
   uses pyremap to remap WOA23 conservative temperature and absolute salinity
   from the 0.25-degree lat-lon grid to the culled MPAS mesh, producing
   `woa23_on_mesh.nc`.  Task count scales with the approximate cell count
   recorded in the ``[unified_mesh]`` config section.
3. **pstar_init** ({py:class}`~polaris.tasks.ocean.realistic_global.init.pstar_init.RealisticPStarInitStep`):
   subclass of {py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep`.
   Runs the fixed-point p-star coordinate iteration jointly with WOA23 tracer
   interpolation, writing a model-neutral `pstar_init.nc` that contains
   converged geometric layer interfaces and CT/SA tracer fields.
4. **initial_state** ({py:class}`~polaris.tasks.ocean.realistic_global.init.initial_state.InitialStateStep`):
   reads `pstar_init.nc` and the model resolved from ``[ocean] model`` to
   produce model-specific output files (`init.nc` for both models;
   `vert_coord.nc` additionally for Omega).  Tracer fields are kept as CT/SA
   for Omega and converted to potential temperature / practical salinity for
   MPAS-Ocean via GSW.
5. **viz** ({py:class}`~polaris.tasks.ocean.realistic_global.init.viz.VizInitStep`):
   visualizes and sanity-checks the initial condition and vertical-coordinate
   datasets (see below).

### viz

The {py:class}`~polaris.tasks.ocean.realistic_global.init.viz.VizInitStep`
step is a *shared* step that is only added to a task's `steps_to_run` when
`get_realistic_init_steps` is called with `include_viz=True` (as the standalone
`RealisticGlobalInit` task does).  Other consumers that reuse the init outputs
as dependencies leave it out of their run list so the plots are not
regenerated.

The step is model-agnostic.  It reads through
{py:meth}`~polaris.ocean.model.OceanIOStep.open_model_dataset` — which maps
Omega variable names to their MPAS-Ocean equivalents and reconstructs the
geometric `layerThickness` from Omega's `PseudoThickness` — and
{py:meth}`~polaris.ocean.model.OceanIOStep.open_vert_coord_dataset`, so the
maps and transects use MPAS-Ocean names for both models.  It produces:

* `initial_state_summary.png`: histograms of the initial condition (a
  de-Haney'd port of Compass' `plot_initial_state`).  The prognostic
  layer-thickness panel shows each model's *native* variable —
  `layerThickness` for MPAS-Ocean and `PseudoThickness` for Omega — read from
  the raw output file.
* `vertical_coordinate.png`: the vertical-coordinate structure derived from the
  geometric `restingThickness` of the deepest column (there are no
  `refMidDepth`/`refBottomDepth` reference profiles in this workflow).
* global native-mesh maps (via {py:func}`polaris.viz.plot_global_mpas_field`)
  of temperature and salinity at the depths listed in
  `[realistic_global_init_viz] depths`, plus surface and seafloor, and
  `bottomDepth`, `ssh`, `maxLevelCell` and column thickness.  For Omega the
  more native `surfacePressure` and `bottomPressure` are also plotted when
  present.
* vertical transects (via `mpas_tools` `compute_transect`/`plot_transect`) of
  temperature and salinity along each transect in
  `[realistic_global_init_viz_transects]`.
* **Omega only**: a stratification check using the TEOS-10 in-situ `Density`
  (global surface/seafloor maps and transects).  Density is not plotted for
  MPAS-Ocean, whose equation of state differs and is not evaluated here.
* `xdmf/init/` and (Omega) `xdmf/vert_coord/`: XDMF/HDF5 exports for ParaView,
  produced with {py:class}`mpas_tools.viz.mpas_to_xdmf.MpasToXdmf`.  For Omega
  the native variable names are preserved and only the dimension names are
  renamed to their MPAS-Ocean equivalents, as required by the converter.
