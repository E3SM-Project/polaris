(dev-ocean-realistic-global)=

# realistic_global

The `realistic_global` tasks in `polaris.tasks.ocean.realistic_global` use
realistic global ocean meshes, bathymetry and forcing.  They fall into two
groups:

- `hydrography/woa23`, a mesh-independent preprocessing task that builds a
  reusable hydrography product from the World Ocean Atlas 2023 on its native
  0.25-degree latitude-longitude grid.
- `analysis_members`, short forward runs on realistic global meshes that
  exercise the global-statistics analysis member in both MPAS-Ocean and Omega.
- `analysis_test`, a one-year Omega run that writes what the analysis tasks
  in `polaris.tasks.ocean.analysis` read.

Tasks are added to the ocean component by
{py:func}`polaris.tasks.ocean.realistic_global.add_realistic_global_tasks`,
which registers the `woa23` task, one `analysis_members` task per mesh in
its `mesh_dict`, and the `analysis_test` task.  Adding a new mesh to
`analysis_members` requires only a new entry in that dictionary giving the
MPAS-Ocean and Omega initial-condition IDs and the cell count, plus a
matching entry in the `mesh_info` dictionary in
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

The files the run writes are given as `output_filenames`, each of which is
declared as an output; the default is the single `output.nc`.  A subclass
whose streams write one file per month, such as the `analysis_test` forward
step, passes the whole list.

The helper `_make_stream_dirs()` creates the directories Omega's streams
write into, listed in `stream_dirs`: `restart/` for the `RestartWrite`
stream, plus whatever a subclass appends.  Omega does not create these
directories itself, so without them the restart write fails at the end of the
run.  It is called from both `setup()` and `runtime_setup()` so the
directories exist whether or not setup and run happen in the same invocation.
MPAS-Ocean needs no equivalent because the MPAS framework creates stream
directories itself.

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

(dev-ocean-realistic-global-analysis-test)=

## analysis_test

The `analysis_test` subpackage is laid out the way the `forward`, `init` and
`dynamic_adjustment` subpackages on the `unified-mesh-dev` branch are:
`tasks.py` registers the tasks, `task.py` holds the task class, and the task
sits at `spherical/realistic_global/<mesh>/analysis_test/task` with its steps
beside it and a `realistic_global_analysis_test.cfg` shared at that level.
{py:func}`polaris.tasks.ocean.realistic_global.analysis_test.add_realistic_global_analysis_test_tasks`
registers one task, on the `QU.240km` mesh; adding a mesh means a new entry
in the `MESH_INFO` dictionary in
`polaris.tasks.ocean.realistic_global.analysis_test.forward` giving the
initial-condition IDs, the cell count and the time step, and a call to add
the task.

The
{py:class}`polaris.tasks.ocean.realistic_global.analysis_test.RealisticGlobalAnalysisTest`
task holds the `forward` step and nothing else yet.  The ocean analysis
design intends the analysis steps themselves to be added to the task, keyed
on the forward step's output, so that the `omega_analysis_test` suite runs the
simulation and its analysis together; until then the analysis is run
separately by pointing the `omega_analysis` suite at the forward step's
`omega.yml`.

### forward

The class
{py:class}`polaris.tasks.ocean.realistic_global.analysis_test.forward.Forward`
is a subclass of the shared {ref}`dev-ocean-realistic-global-framework`
`Forward`, which supplies the cached initial condition and the shared
`forward.yaml`.  Only Omega is supported; `setup()` raises for any other
model.

`setup()` adds this subpackage's `forward.yaml` after the shared one, so
that it overrides it.  The fragment replaces the `History` stream with
monthly snapshots in `output/`, turns on the `MonthlyAverages` and `MOC`
analysis groups, adds kinetic energy and sea surface height to
`GlobalStats`, and makes restarts monthly.  A stream's options merge across
yaml files, so the fragment has to set the `History` stream's `FileFreq`
explicitly: the shared value of 9999 years would put every snapshot into one
file.

Every monthly file is declared as an output, so that a run whose analysis
groups did not write is reported as a missing output rather than found later
by the analysis.  Omega names a time-mean file for the instant it was
finalized (E3SM-Project/Omega#554), so a run that starts on `0001-01-01`
writes the files covering year 1 as `0001-02` through `0002-01`;
`_monthly_filenames()` builds the names that way, and the snapshots, taken at
those instants, are named the same way.

The step appends `output` to the shared step's `stream_dirs`, so that the
directory the `History` stream writes into exists before the run.

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

The helper
{py:func}`polaris.tasks.ocean.realistic_global.hydrography.woa23.get_woa23_topography_step`
creates a shared `e3sm/init` {py:class}`polaris.tasks.e3sm.init.topo.combine.step.CombineStep`
configured for a 0.25-degree lat-lon target grid. The `Woa23` task adds this
step with a symlink `combine_topo`.

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
