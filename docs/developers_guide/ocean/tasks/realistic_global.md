(dev-ocean-realistic-global)=

# realistic_global

The `realistic_global` tasks in `polaris.tasks.ocean.realistic_global` use
realistic global ocean meshes, bathymetry and forcing.  They fall into four
groups:

- `hydrography/woa23`, a mesh-independent preprocessing task that builds a
  reusable hydrography product from the World Ocean Atlas 2023 on its native
  0.25-degree latitude-longitude grid.
- `forcing/jra55`, a mesh-independent preprocessing task that builds a reusable
  wind-stress product from JRA55-do 10-m winds.
- `init`, which creates mesh-specific ocean initial conditions using that
  hydrography and forcing together with the culled mesh from `e3sm/init`.
- `analysis_members`, short forward runs on realistic global meshes that
  exercise the global-statistics analysis member in both MPAS-Ocean and Omega.

Tasks are added to the ocean component by
{py:func}`polaris.tasks.ocean.realistic_global.add_realistic_global_tasks`,
which registers the `woa23` and `jra55` tasks, one `init` task per MPAS mesh,
and one `analysis_members` task per mesh in its `mesh_dict`.  Adding a new mesh
to `analysis_members` requires only a new entry in that dictionary giving the
MPAS-Ocean and Omega initial-condition IDs and the cell count, plus a matching
entry in the `mesh_info` dictionary in
{py:class}`polaris.tasks.ocean.realistic_global.analysis_members.AnalysisMembers`
giving the time step and run duration.

(dev-ocean-realistic-global-framework)=

## framework

The config options for these tasks are described in
{ref}`ocean-realistic-global` in the User's Guide.  The shared colormap
options for the `viz` step live in `realistic_global.cfg`, while the
`analysis_members` tasks add `analysis_members.cfg`.

### forward

The class {py:class}`polaris.tasks.ocean.realistic_global.forward.Forward`
is a shared {py:class}`polaris.ocean.model.OceanModelStep` used by tasks in
this group.  Unlike most Polaris forward steps, it does not build its own
mesh and initial condition; instead it downloads cached, model-specific files
from the `realistic_global` section of the Polaris input database.

Because the file layout differs between the two models, the input files are
added in `setup()` rather than `__init__()`, once `config` is available and
the target model is known:

- For Omega, a single file is linked three times, as `mesh.nc`,
  `vert_coord.nc` and `init.nc`, because a single file contains the converted
  mesh, initial condition, and vertical coordinate from MPAS-Ocean.
- For MPAS-Ocean, a `zerovel` file is linked as both `mesh.nc` and `init.nc`,
  and the `time_integrator` template replacement is rewritten from
  `RungeKutta4` to MPAS-Ocean's `RK4`.

`setup()` also renders `forward.yaml` with the template replacements supplied
by the task, so the time step, run duration and output interval can be varied
per mesh.

The helper `_make_restart_dir()` creates the `restart/` directory that
Omega's `RestartWrite` stream writes into.  Omega does not create this
directory itself, so without it the restart write fails at the end of the run.
It is called from both `setup()` and `runtime_setup()` so the directory exists
whether or not setup and run happen in the same invocation.  MPAS-Ocean needs
no equivalent because the MPAS framework creates stream directories itself.

`compute_cell_count()` returns the cell count passed in by the task rather
than reading the mesh, since the mesh is not available at setup time.

### viz

The class {py:class}`polaris.tasks.ocean.realistic_global.viz.Viz` plots
global maps of each state variable at the start and end of the run, plus the
zonal and meridional wind stress from the initial condition.  The list of
variables comes from the ocean component's `state_vars`, with
`normalVelocity` replaced by `kineticEnergyCell` because the normal velocity
lives on edges and is not directly plottable as a cell field.  Variables
missing from a given file are logged and skipped, so the step does not fail
when a model writes a different subset of fields.

(dev-ocean-realistic-global-analysis-members)=

## analysis_members

The {py:class}`polaris.tasks.ocean.realistic_global.analysis_members.AnalysisMembers`
task runs the ocean model with the global-statistics analysis member enabled
and plots the resulting time series.  It contains a `forward` step, a
`global_stats` step and a `viz` step; only `forward` runs by default.

Each task builds its own {py:class}`polaris.config.PolarisConfigParser` from
`realistic_global.cfg` and `analysis_members.cfg` and shares it with all three
steps, so that a user editing the config file in the task work directory
affects the whole task.

### global_stats

The class
{py:class}`polaris.tasks.ocean.realistic_global.analysis_members.stats_analysis.StatsAnalysis`
plots, for each state variable, the minimum, maximum and mean over time along
with a shaded standard-deviation envelope, and a companion panel showing the
same quantities as anomalies relative to their initial values.

This step normalizes two differences between the models:

- **Output location.** Omega writes the statistics to a separate
  `global_stats_1DayTimeStats` file, whereas MPAS-Ocean writes
  `global_stats.nc`.  The input file is therefore selected in `setup()`, once
  the model is known.
- **Standard deviation.** Omega writes the standard deviation directly in its
  `Rms` field, while MPAS-Ocean writes a true root-mean-square, so the
  standard deviation is recovered as
  $\sigma = \sqrt{\mathrm{rms}^2 - \mathrm{mean}^2}$.

(dev-ocean-realistic-global-woa23)=

## hydrography/woa23

The {py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.task.Woa23`
task is the Polaris port of the WOA preprocessing part of the legacy Compass
`utility/extrap_woa` workflow.

The implementation is intentionally organized around reusable Polaris steps
rather than around the legacy multiprocessing workflow. One notable design
choice is that the task reuses the combined topography product from
`e3sm/init` rather than taking a raw topography filename as a task-specific
input.

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

### viz

The class
{py:class}`polaris.tasks.ocean.realistic_global.hydrography.woa23.viz.Woa23VizStep`
plots horizontal maps of the extrapolated temperature and salinity at the
depths given by the `horizontal_plot_depths` config option, along with
vertical sections through Filchner Trough and the Ross Ice Shelf cavity.  It
is added with `run_by_default=False`.

(dev-ocean-realistic-global-jra55)=

## forcing/jra55

The {py:class}`polaris.tasks.ocean.realistic_global.forcing.jra55.task.Jra55`
task builds the reusable wind-stress product used by the `init` tasks.  Its
shared steps come from
{py:func}`polaris.tasks.ocean.realistic_global.forcing.jra55.steps.get_jra55_steps`.

### stress

{py:class}`polaris.tasks.ocean.realistic_global.forcing.jra55.stress.Jra55StressStep`
downloads the yearly JRA55-do `uas`/`vas` files through the
`initial_condition_database` mechanism, selects the configured month, and
computes the stress at every 3-hourly step before averaging.  Averaging the
stress rather than the wind preserves the gust contribution, which is why the
3-hourly data is needed; the drag law is
{py:func}`~polaris.tasks.ocean.realistic_global.forcing.jra55.stress.wind_stress`.
The time loop is chunked, since a month of 3-hourly TL319 winds is
248 x 320 x 640 per component.

The step is *intended* to be `default_cached = True`, so that the multi-GiB
download happens only when the product is deliberately regenerated.  The flag
is not set until the product is actually in the cache database: setting it
first makes any setup that does not include the standalone `jra55` task fail
at setup with "has not been added to the cache database".  Set the flag in the
same change that adds the `cached_files.json` entry.

The product is deliberately **not** padded, in latitude or longitude.  Bilinear
remapping is center-based for ESMF but corner-based for mbtempest, and padding
a lat-lon source so that either its corners or its centres reach the pole
aborts mbtempest; duplicating a longitude column makes the grid overlap itself
and breaks both map tools.  The output is `jra55_stress.nc`.

### viz

{py:class}`polaris.tasks.ocean.realistic_global.forcing.jra55.viz.Jra55VizStep`
plots global maps of the stress components and magnitude plus a zonal-mean
`taux` curve, which is the diagnostic that confirms the bulk formula and air
density are right.


(dev-ocean-realistic-global-init)=

## init

The `init` task family (whose steps live under
`spherical/realistic_global/{mesh_name}/init`) creates mesh-specific ocean
initial conditions using WOA23 hydrography and the culled mesh produced by
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
   The standard topography fields (see `TOPO_VARIABLES`) are validated
   against a baseline when one is provided.
2. **woa23_map** ({py:class}`~polaris.tasks.ocean.realistic_global.init.woa23_map.Woa23MapStep`):
   a {py:class}`polaris.remap.MappingFileStep` that builds the bilinear
   mapping file from the 0.25-degree WOA23 lat-lon grid to the culled MPAS
   mesh.  This is the only MPI step in the WOA23 chain (it runs `mbtempest`
   or ESMF).  Its task count scales with the approximate culled ocean cell
   count via the ``remap_cells_per_task`` and ``remap_min_cells_per_task``
   options in the ``[realistic_global_init]`` config section.
3. **remap_woa23** ({py:class}`~polaris.tasks.ocean.realistic_global.init.remap_woa23.RemapWoa23Step`):
   a serial step that applies the weights from **woa23_map** with `ncremap`,
   remapping WOA23 conservative temperature and absolute salinity to the
   culled MPAS mesh and producing `woa23_on_mesh.nc`.  The remapper is
   retrieved from **woa23_map** through the step dependency mechanism, so it
   is resolved only after that step has run.
4. **jra55_map** ({py:class}`~polaris.tasks.ocean.realistic_global.init.jra55_map.Jra55MapStep`):
   the bilinear mapping file from the JRA55-do TL319 grid to the culled MPAS
   mesh, sized the same way as **woa23_map**.  Bilinear rather than
   conservative, because the ocean responds to wind stress *curl* and
   first-order conservative remapping makes that curl grid-scale noise;
   pyremap's moab path hard-codes ``--order 1``.  ``map_tool`` is left at the
   Polaris default (``moab``): ESMF's default pole handling builds its pole
   point from the zonal average of the source's outermost row, which is
   harmless for a scalar but collapses a vector field to zero at the pole.
5. **remap_jra55** ({py:class}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.RemapJra55Step`):
   applies those weights with `ncremap`, producing `jra55_on_mesh.nc`.
   mbtempest's coverage stops at the source grid's extrapolated cell corner,
   leaving about 891 km^2 uncovered at the North Pole -- under one cell for
   meshes coarser than about 30 km.  Those cells are filled from their nearest
   valid neighbour by
   {py:func}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.fill_missing_from_nearest`,
   with both components taken from the same donor so the filled vector stays
   physical.  A missing count larger than
   ``max_polar_fill_fraction`` (with an absolute floor of
   ``min_allowed_polar_fill``) fails the step rather than being filled
   silently.  Padding the source grid to close the cap is not an option: it
   aborts mbtempest.
6. **pstar_init** ({py:class}`~polaris.tasks.ocean.realistic_global.init.pstar_init.RealisticPStarInitStep`):
   subclass of {py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep`.
   Runs the fixed-point p-star coordinate iteration jointly with WOA23 tracer
   interpolation, writing a model-neutral `pstar_init.nc` that contains
   converged geometric layer interfaces and CT/SA tracer fields.  The column
   is anchored at the prescribed sea surface, so `ssh` matches its prescribed
   value (0 here, because `SurfacePressure = 0`) to machine precision and
   `bottomDepth` is the diagnosed geometric depth of the column.  Where
   partial-cell snapping (enforced on the bottom layer's *pseudo*-thickness)
   prevents the geometric column from exactly matching the target bathymetry,
   the residual adjusts `bottomDepth` — the representable bathymetry — rather
   than `ssh`, mirroring z-star partial cells.  Isolated bathymetry "holes"
   (cells whose `maxLevelCell` is deeper than every ocean neighbor) are filled
   by capping each hole's seafloor at its deepest-neighbor level and
   re-solving, via
   {py:func}`polaris.ocean.vertical.bathymetry_holes.fill_max_level_holes`.
7. **initial_state** ({py:class}`~polaris.tasks.ocean.realistic_global.init.initial_state.InitialStateStep`):
   reads `pstar_init.nc` and the model resolved from ``[ocean] model`` to
   produce model-specific output files (`init.nc` for both models;
   `vert_coord.nc` additionally for Omega).  Tracer fields are kept as CT/SA
   for Omega and converted to potential temperature / practical salinity for
   MPAS-Ocean; the conversion itself is the framework's (see
   {ref}`dev-ocean-framework-init-state`), with this step supplying the
   per-cell longitude and latitude from the culled mesh because
   `pstar_init.nc` has no horizontal mesh fields.  It also writes `mesh.nc`,
   adding the Coriolis fields via {py:func}`polaris.coriolis.add_coriolis_to_dataset`.
   For Omega, `write_horiz_mesh_dataset()` merges in the cell-centered
   vector-reconstruction fields from `reconstruction_weights.nc`, so the step
   links **cull_mesh**'s `culled_ocean_reconstruction_weights.nc` under that
   name.  The weights have to be the *culled* mesh's, not the base mesh's,
   since that is the mesh the initial condition is built on.
8. **forcing** ({py:class}`~polaris.tasks.ocean.realistic_global.init.forcing.ForcingStep`):
   writes the model-specific `forcing.nc` from `jra55_on_mesh.nc` via
   {py:meth}`polaris.ocean.model.OceanIOStep.write_forcing_dataset`.  Omega
   reads 1-D fields on `NCells`; MPAS-Ocean's Registry declares
   ``dimensions="nCells Time"``, so a `Time` dimension of one is added there.
9. **viz** ({py:class}`~polaris.tasks.ocean.realistic_global.init.viz.VizInitStep`):
   visualizes and sanity-checks the initial condition, vertical-coordinate and
   forcing datasets (see below).

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
