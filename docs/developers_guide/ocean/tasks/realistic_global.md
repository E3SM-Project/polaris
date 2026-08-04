(dev-ocean-realistic-global)=

# realistic_global

The `realistic_global` tasks in `polaris.tasks.ocean.realistic_global` use
realistic global ocean meshes, bathymetry and forcing.  They fall into five
groups:

- `hydrography/woa23`, a mesh-independent preprocessing task that builds a
  reusable hydrography product from the World Ocean Atlas 2023 on its native
  0.25-degree latitude-longitude grid.
- `forcing/jra55`, a mesh-independent preprocessing task that builds a reusable
  wind-stress product from JRA55-do 10-m winds.
- `init`, which creates mesh-specific ocean initial conditions using that
  hydrography and forcing together with the culled mesh from `e3sm/init`.
- `forward`, short forward runs on the meshes `init` builds.
- `cached_forward`, the same forward runs on initial conditions downloaded from
  the Polaris input database instead.

Tasks are added to the ocean component by
{py:func}`polaris.tasks.ocean.realistic_global.add_realistic_global_tasks`,
which registers the `woa23` and `jra55` tasks, one `init` and one `forward`
task per MPAS mesh, and one `cached_forward` task per mesh in
{py:data}`polaris.tasks.ocean.realistic_global.forward.tasks.CACHED_MESHES`.
Adding a cached mesh requires an entry in that dictionary giving the
MPAS-Ocean and Omega initial-condition IDs, the minimum resolution and the
cell count, plus a `<mesh_name>.cfg` in `mesh_configs` giving the time step and
run duration.

The two kinds of forward task serve different purposes, which is what decides
their physics; see {ref}`ocean-realistic-global-forward` in the User's Guide.

(dev-ocean-realistic-global-framework)=

## framework

The config options for these tasks are described in
{ref}`ocean-realistic-global` in the User's Guide.  The shared colormap
options for the `viz` step live in `realistic_global.cfg`.

(dev-ocean-realistic-global-forward)=

## forward

The `realistic_global.forward` package holds one forward-run capability that
both the `forward` and `cached_forward` tasks are built from.  They differ in
one argument: the
{py:class}`~polaris.tasks.ocean.realistic_global.forward.initial_condition.InitialCondition`
they are given.  Everything else — the step, the model config, the diagnostics
— is shared.  Why the two are configured differently is a question about
purpose rather than code; see
{ref}`ocean-realistic-global-forward-purposes` in the User's Guide.

The package is deliberately split three ways, so that adding a new source of
initial condition, a new run setting, or a new consumer each touches one place:

| module | answers |
|---|---|
| `initial_condition.py` | *where do the model input files come from?* |
| `stage.py` | *what settings does this run use?* |
| `forward.py` | *run the model* |

### Forward

{py:class}`~polaris.tasks.ocean.realistic_global.forward.forward.Forward` is an
{py:class}`~polaris.ocean.model.OceanModelStep` that defers both of those
questions rather than answering them itself.

`setup()` asks the initial condition to add its input files *before* calling
the base class, so that `OceanModelStep` sees a finalized `graph_target` and
input list.  A step whose graph comes from the input-file database rather than
an upstream work directory leaves `graph_target` unset and adds `graph.info`
itself; see {py:meth}`~polaris.ocean.model.OceanModelStep.setup`.

`compute_cell_count()` reads `nCells` from the mesh once it exists, and before
that falls back to the initial condition's `approx_cell_count`.  Both are
needed: resources are sized during setup, when an initial condition built by
the `init` workflow has not been produced yet.

`dynamic_model_config()` is the single place where model-agnostic settings
become model-facing ones.  It renders `forward.yaml` from the stage, always
adds `forcing.yaml` (every realistic global forward run is wind-forced, and
there is no option to turn that off), adds `forcing_streams.yaml` when the
initial condition stages a file for it, and applies the horizontal-mixing
options in MPAS-Ocean naming so that `mpaso_to_omega.yaml` translates them.

### ForwardStage

{py:class}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage` is
a dataclass of model-agnostic run settings — durations, cadences, time steps,
damping, mixing and the physics switches — built from a
`[realistic_global_forward]` config section by
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.from_config`.

A simple forward run uses one.  It is a *stage* rather than a *config* because
a multi-stage workflow such as dynamic adjustment builds a sequence of them and
sets the restart fields to chain one into the next; the step supports that
already even though nothing here uses it yet.

{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.model_replacements`
maps a stage onto template replacements, and is where the two models diverge:
the time integrator is chosen per model, the time step follows from that
choice, and a non-split integrator has to advance on the short barotropic step.
The MPAS-Ocean-only physics is separated into
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.mpaso_physics_options`
from the options both models share in
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.horiz_mixing_options`.

An unsupported `omega_time_integrator`, and a `damping` Omega cannot honor, are
errors at run time rather than at setup, so that a task can be set up and the
config changed before it is run.

### InitialCondition

{py:class}`~polaris.tasks.ocean.realistic_global.forward.initial_condition.InitialCondition`
is the abstraction the whole package is arranged around.  It knows where the
model input files come from, and the forward step asks rather than deciding.

- {py:class}`~polaris.tasks.ocean.realistic_global.forward.initial_condition.StepInitialCondition`
  links the mesh, vertical coordinate, initial state and forcing from the
  `init` workflow's step directories, and reuses the graph it already built.
  It links the initial state only when the run reads one, since a stage
  continuing from a restart does not.
- {py:class}`~polaris.tasks.ocean.realistic_global.forward.initial_condition.DatabaseInitialCondition`
  downloads a single cached file that supplies everything at once, plus a
  prebuilt graph for MPAS-Ocean.

`get_forcing_filename()` is what lets both work through one mechanism: a source
that stages a forcing file names it, and a source whose wind stress travels
inside the initial condition names that file instead, so the forcing streams
are pointed at the right place without the step knowing which case it is in.

### the model config files

| file | what it does |
|---|---|
| `forward.yaml` | a Jinja2 template: time management, time step, output/restart/statistics streams |
| `forcing.yaml` | turns wind forcing on; always added |
| `forcing_streams.yaml` | points each model's forcing stream at the staged file; added only when one is staged |
| `restart_streams.yaml` | the restart read/write side; added only for a stage in a restart chain |

`forward.yaml`'s `ocean:` section is model-neutral and reaches Omega through
`mpaso_to_omega.yaml`; a unit test checks that every option in it has an Omega
counterpart, since an unmapped option only warns and would silently give the
two models different physics.

### viz

The class {py:class}`polaris.tasks.ocean.realistic_global.forward.viz.Viz`
plots global maps of each state variable at the start and end of the run, plus
the zonal and meridional wind stress that forced it.  Which file the stress
comes from is the forward run's initial condition's business: a file of its
own when the `init` workflow produced one, or the initial condition itself
when the stress travels inside it.  The list of
variables comes from the ocean component's `state_vars`, with
`normalVelocity` replaced by `kineticEnergyCell` because the normal velocity
lives on edges and is not directly plottable as a cell field.  Variables
missing from a given file are logged and skipped, so the step does not fail
when a model writes a different subset of fields.

### global_stats

The class
{py:class}`polaris.tasks.ocean.realistic_global.forward.stats_analysis.StatsAnalysis`
plots, for each state variable, the minimum, maximum and mean over time along
with a shaded standard-deviation envelope, and a companion panel showing the
same quantities as anomalies relative to their initial values.

This step normalizes two differences between the models:

- **Output location.** MPAS-Ocean writes `global_stats.nc` as named, while
  Omega treats the name as a prefix and builds the real one from the analysis
  period and the kind of output: `global_stats_1DayInstants` for daily
  instantaneous samples, or `..._1DayTimeStats` had a temporal reduction been
  asked for.  Both names come from
  {py:meth}`polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.stats_filename`,
  which lives on the stage because the period does; this step only asks it, in
  `setup()`, once the model is known.  Anything else that reads a stage's
  statistics asks the same question the same way, so the two cannot drift
  apart.
- **Standard deviation.** Omega writes the standard deviation directly in its
  `Rms` field, while MPAS-Ocean writes a true root-mean-square, so the
  standard deviation is recovered as
  $\sigma = \sqrt{\mathrm{rms}^2 - \mathrm{mean}^2}$.

(dev-ocean-realistic-global-dynamic-adjustment)=

## dynamic_adjustment

The `dynamic_adjustment` task family (steps under
`spherical/realistic_global/{mesh_name}/dynamic_adjustment`) runs a
restart-chained sequence of forward stages from a mesh's realistic initial
condition.  One
{py:class}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.task.RealisticGlobalDynamicAdjustment`
task is registered per MPAS mesh.

### schedule parsing

{py:func}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule.load_schedule_stages`
reads a schedule YAML (the per-mesh `<mesh_name>.yaml` or `default.yaml`, or a
file named by the `schedule` config option) and returns a list of
{py:class}`polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage`
objects.

A stage is a forward run, so the base stage comes from
`ForwardStage.from_config` on the `[realistic_global_forward]` section and the
schedule is applied on top with `dataclasses.replace`.  The task's config
carries that section, this task's own, and the per-mesh overrides from
{py:mod}`polaris.tasks.ocean.realistic_global.mesh_configs`, so the physics
options and per-mesh tuning reach the stages without the schedule mentioning
them.  Keeping the schedule a delta is what stops it from becoming a second
configuration system that has to track `ForwardStage` field by field.

Schedule keys are validated against `SCHEDULE_FIELDS` — the `ForwardStage`
fields minus the ones the restart chain owns — and coerced to each field's
declared type, so a renamed or misspelled option raises at setup instead of
falling back to the config value.  The parser also computes the chain itself:
the cumulative `start_time`, `do_restart`, and the shared `restart_in` /
`restart_out` filenames (`restarts/rst.<stop-time>.nc`).

### restart chaining

Each stage is a
{py:class}`polaris.tasks.ocean.realistic_global.forward.forward.Forward` step
reused from the forward workflow.  When a stage's `ForwardStage` sets
`restart_out`, the step writes its restart to the shared `../restarts`
directory (via `restart_streams.yaml`) and declares it as an output; a stage
that sets `restart_in` declares its predecessor's restart as an input, so the
chain is explicit to Polaris and a missing link fails before the model
launches.  Consecutive stages are also linked with `add_dependency`.

For MPAS-Ocean the restart stream is both an input and an output stream, so one
`filename_template` serves both directions and the read side is just
`config_do_restart` / `config_start_time` from `forward.yaml`.  The start time
is explicit rather than `'file'` with a `restart_timestamp`, matching
`cosine_bell/restart` and `ice_shelf_2d`.

Omega needs a separate `RestartRead` stream, which the `Omega` block of
`restart_streams.yaml` supplies, switched on per stage by
`ForwardStage.restart_stream_replacements`.  That block is unrun: Omega restart
filenames carry no `.nc` extension and it is not established whether Omega
appends one, which is why the restart files are declared as step inputs and
outputs for MPAS-Ocean only.
[Omega#482](https://github.com/E3SM-Project/Omega/issues/482) will also change
how an Omega restart run has to be configured.  `split_explicit_ab2` remains
unsupported for Omega.

### setup-time rebuild

The stages are built in `__init__` from the built-in schedule (so `polaris
list` shows a representative set) and rebuilt in `configure()`, which runs after
the user config is merged, following the
{py:class}`polaris.tasks.ocean.cosine_bell.CosineBell` pattern.  This lets a
user's setup-time `schedule` override or edited stage options take effect.  The
step graph is therefore fixed at setup, not run time.

### diagnostics and validation

The
{py:class}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate.Validate`
step runs in two parts.  It first builds one row of diagnostics per stage with
{py:func}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics.collect_stage_diagnostics`
and writes `dynamic_adjustment_stats.csv`; it then makes its checks against
those rows, so the summary a user reads and the checks that passed or failed are
one calculation rather than two.

`diagnostics.METRICS` is the column list.  Each metric names the global-statistics
variable it reads (in MPAS-Ocean naming, which `open_model_dataset` maps Omega's
names onto), how to reduce that variable's time series over the stage, and the
`output.nc` field to fall back to when the model does not report the statistic.
A metric with no fallback is left blank instead: `output_var` is set only where
computing the metric from the 3-D field gives the same quantity, which is true of
a maximum and not of a volume-weighted mean.  The drift columns are derived
rather than read, from the change in a volume-weighted mean across the stage
divided by the stage's run duration, which is why `Validate` takes the
`ForwardStage` list rather than just the stage names.

The statistics cadence is `ForwardStage.stats_interval`, which drives the
`globalStatsOutput` stream and through it the analysis member's compute
interval.  It is separate from the 3-D `output_interval` on purpose: tying a few
scalars to the cadence of 3-D fields gave two samples per stage on the 10-day
schedules and, on `u.oi6to18.lr6to10`, a single startup record for every stage
shorter than the 10-day output interval.

`schedule._check_stage_writes_its_records` rejects a `restart_interval` that
misses MPAS-Ocean's restart alarm (measured from the stream's fixed
`reference_time`, not the stage start) and a `stats_interval` longer than the
stage.  Both otherwise fail only after the model has run.

The statistics file is opened by relative path rather than declared as a step
input, so a stage that did not write one degrades to computing what it can from
`output.nc`.  Its name differs by model (`diagnostics.STATS_FILENAMES`): Omega
treats its `Filename` as a prefix and appends the reduction period with no `.nc`.

The checks are per-stage `temperature_max` and `cfl_max` thresholds and, over
the last `ke_check_num_stages` transitions, that the fractional change in
`kinetic_energy_mean` is shrinking; each is skipped, with a log line, when the
model reports no such metric.  The thresholds read the `*_in_stage` columns, the
extreme reached at any point in the stage, so an excursion the run recovered
from is still caught.

`_check_ke_growth_decelerates` is deliberately not a check on the level of the
kinetic energy.  These runs start from rest and are wind-forced, so kinetic
energy rises throughout a 40-day adjustment; the first version of this check
compared levels and failed the healthy u.oi240.lr240 run.  It is also not a
check on the growth *ratio*: converging from above gives ratios rising towards
one, so the magnitude of the fractional change is what shrinks in both
directions.  The
final `simulation` stage additionally compares its `output.nc` against a baseline
via the forward step's `validate_vars`.

{py:class}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.viz.VizDynamicAdjustmentStep`
plots the same statistics as time series.  Its panels are declared in
`viz.PANELS`, each naming the variables it draws in MPAS-Ocean naming, so a
panel whose variables the configured model does not report is dropped and the
grid closes up around it.  Stages are placed on a common axis from their
schedule start times rather than from the time variable in the files, because a
restart may or may not reset what the model counts from.

Omega's temperature is conservative temperature where MPAS-Ocean's is potential
temperature, so `temperature_max` is not literally the same quantity in the two
models — immaterial against a blow-up threshold.


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

Colormaps come from the shared viz defaults in
{py:func}`polaris.viz.get_viz_defaults`, looked up by variable name, so a
variable gets the same colormap everywhere it is plotted; none are named in
the plotting code.  The limits, by contrast, are computed per plot from the
data range and written into `[realistic_global_init_viz]` just before each
call.  That is deliberate and differs from the forward `viz` step,
which reads fixed limits from `realistic_global.cfg`: fixed limits are what
you want to compare runs or times against each other, and the data range is
what you want when the question is whether a brand-new initial condition is
sane.  For a diverging colormap the range is made symmetric about zero.
