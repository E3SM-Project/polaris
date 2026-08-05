(dev-ocean-realistic-global)=

# realistic_global

The `realistic_global` tasks in `polaris.tasks.ocean.realistic_global` use
realistic global ocean meshes, bathymetry and forcing.  They fall into seven
groups:

- `hydrography/woa23`, a mesh-independent preprocessing task that builds a
  reusable hydrography product from the World Ocean Atlas 2023 on its native
  0.25-degree latitude-longitude grid.
- `forcing/jra55`, a mesh-independent preprocessing task that builds a reusable
  wind-stress product from JRA55-do 10-m winds.
- `init`, which creates mesh-specific ocean initial conditions using that
  hydrography and forcing together with the culled mesh from `e3sm/init`.
- `forward`, short forward runs on the meshes `init` builds.
- `cached_forward`, the same forward runs on E3SM initial conditions cached in
  the Polaris input database instead, a temporary task.
- `analysis_output`, one-year Omega runs on either source of initial
  condition that write what the ocean analysis reads.
- `restart`, a short Omega run continued from a restart, checking that it
  matches the uninterrupted run, history output included.

Tasks are added to the ocean component by
{py:func}`polaris.tasks.ocean.realistic_global.add_realistic_global_tasks`,
which registers the `woa23` and `jra55` tasks, one `init` task per MPAS mesh,
a `forward` task per mesh for each of
{py:data}`polaris.tasks.ocean.realistic_global.forward.TIME_INTEGRATORS`, the
same `cached_forward` variants for each mesh in
{py:data}`polaris.tasks.ocean.realistic_global.forward.tasks.CACHED_MESHES`,
an `analysis_output/1_year` task for every mesh of either kind, and a single
`restart` task on `e3sm-qu240`.  Adding a cached mesh requires an entry in that
dictionary, keyed by the E3SM mesh's name in lower case with an `e3sm-` prefix,
giving the name the database files carry, the MPAS-Ocean and Omega
initial-condition IDs, the minimum resolution and the cell count, and a
`<mesh_name>.cfg` in `mesh_configs` giving the split and RK4 time steps and the
run duration.  A mesh coarser than
about a degree should also set fewer MOC latitude bins for its `1_year` run
(`moc_num_bins` in `[analysis_output]`).

`forward` and `cached_forward` run the same physics.  Comparing MPAS-Ocean
with Omega is opt-in, through the options in `forward/compare_with_omega.cfg`,
which Polaris never reads on its own and a unit test keeps honest; see
{ref}`ocean-realistic-global-forward-purposes` in the User's Guide.

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
— is shared, including the physics, so a cached mesh's config gives only
its time steps, viscosities and run duration.

The package is deliberately split three ways, so that adding a new source of
initial condition, a new run setting, or a new consumer each touches one place:

| module | answers |
|---|---|
| `initial_condition.py` | *where do the model input files come from?* |
| `stage.py` | *what settings does this run use?* |
| `forward.py` | *run the model* |

{py:class}`~polaris.tasks.ocean.realistic_global.forward.task.RealisticGlobalForward`
takes a `time_integrator`, `split_explicit` or `rk4`, which names the task's
directory under `forward` or `cached_forward`.  The `rk4` variant adds
`rk4.cfg` after the per-mesh config file, so that it sets both models'
integrators whatever the mesh config says.

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

The files the run writes are given as `output_filenames`, each declared as an
output; the default is the single `output.nc`.  `stream_dirs` lists the
directories under the step's work directory that Omega's streams write into,
which the step creates in `dynamic_model_config()` because Omega does not.
MPAS-Ocean needs no equivalent, since the MPAS framework creates stream
directories itself.  Both are for a subclass like the one-year
`analysis_output` step, which writes one file per month into `output/`.

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
An explicit `dt` and `btr_dt` are the steps of a split integrator, and `rk4_dt`
the step of a non-split one, so that one mesh config can give both.
The MPAS-Ocean-only physics is separated into
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.mpaso_physics_options`
from the options both models share in
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.horiz_mixing_options`
and
{py:meth}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage.vert_mixing_options`.
An option belongs in the MPAS-Ocean-only bucket only while
`mpaso_to_omega.yaml` has no Omega counterpart for it.  Once it has one, it
has to move to a shared bucket: otherwise Omega never sees it and runs its own
default, which is how Omega came to run KPP in tasks that had turned it off.  A
unit test fails if a mapped option is left behind, but it cannot see an Omega
option that is on by default and not yet mapped, so check `Default.yml` when
updating the Omega submodule.

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
plots, for each field, the minimum, maximum and mean over time along with a
shaded standard-deviation envelope, and a companion panel showing the same
quantities as anomalies relative to their initial values.  The fields are the
ones named by `[realistic_global_forward_stats] fields`, or, when that is left
empty, every field the run wrote statistics for.  The variable names are built
from the field and the statistic by `polaris.ocean.global_stats_names` rather
than mapped one by one, so a field that one model writes and the other does not
needs no special handling.

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
- **Standard deviation.** Omega writes a standard deviation
  (`<Field>_SpatialStdDev`), while MPAS-Ocean writes a true root-mean-square
  (`<field>Rms`), so for MPAS-Ocean the standard deviation is recovered as
  $\sigma = \sqrt{\mathrm{rms}^2 - \mathrm{mean}^2}$.

(dev-ocean-realistic-global-analysis-output)=

## analysis_output

The {py:class}`polaris.tasks.ocean.realistic_global.analysis_output.AnalysisOutput`
task runs a year of Omega, writing what the ocean analysis reads.  It takes an
initial condition and optional `init_steps` as `RealisticGlobalForward` does,
so it is registered on the cached meshes and on every mesh the `init` workflow
builds.  Its config is built in layers, each overriding the ones before it:

1. `forward.cfg`, the forward tasks' config;
2. `analysis_output.cfg`, with the default `moc_num_bins`;
3. the mesh's file in `mesh_configs`, which sets fewer bins on a coarse mesh;
4. `one_year.cfg`, which sets only the run duration.

So the run is a `split_explicit` `forward` or `cached_forward` run a year long.

Its step,
{py:class}`~polaris.tasks.ocean.realistic_global.analysis_output.AnalysisOutputForward`,
is a forward-package `Forward` whose `dynamic_model_config()` adds
`monthly_output.yaml` after the forward step's own yaml files, so that it
overrides them.  The fragment replaces the `History` stream with monthly
snapshots in `output/`, turns on the `MonthlyAverages` and `MOC` analysis
groups with `moc_num_bins` latitude bins, adds kinetic energy and
sea surface height to `GlobalStats`, and makes restarts monthly.  A stream's
options merge across yaml files, so the fragment has to set the `History`
stream's `FileFreq` explicitly: the forward step's value of 9999 years would
put every snapshot into one file.  The step appends `output` to `stream_dirs`
and raises at setup unless the model is Omega.

Every monthly file is declared as an output, so that a run whose analysis
groups did not write is reported as a missing output rather than found later
by the analysis.  Omega names a time-mean file for the instant it was
finalized (E3SM-Project/Omega#554), so a run that starts on `0001-01-01`
writes the files covering year 1 as `0001-02` through `0002-01`;
`get_monthly_filenames()` builds the names that way, and the snapshots, taken
at those instants, are named the same way.

(dev-ocean-realistic-global-restart)=

## restart

The {py:class}`polaris.tasks.ocean.realistic_global.restart.Restart` task is
shaped like CIME's ERS (exact restart) test, since Omega's restarts will be
tested that way once Omega runs in E3SM.  A `full_run` covers the whole period
and writes a restart partway through; a `restart_run` continues from that
restart to the end; and `validate` checks that the two histories agree.  It is
also a regression test for
[Omega #482](https://github.com/E3SM-Project/Omega/issues/482), which ERS
alone would not catch: CIME's restart run writes history files of its own,
whereas #482 broke appending to a history file that already held the frames
from before the restart.  So the full run also writes its history up to the
restart to a file of its own, and the restart run appends to a copy of it.

The run lengths live as module-level constants in the task rather than in the
config file, since they are chosen to make the failure visible -- two history
frames on each side of the restart, so that a restart run that clobbered
rather than appended would be obvious -- rather than to be tuned by a user.

Everything else comes from the `[realistic_global_forward]` config options,
as for any other forward run, including the time steps and viscosity in
`e3sm-qu240`'s per-mesh config file; the task's `restart.cfg` sets only the
equation of state.  Both forward steps are `RestartStep`s, so that the two run
the same model.

### restart_step

The class
{py:class}`polaris.tasks.ocean.realistic_global.restart.restart_step.RestartStep`
extends the
{py:class}`~polaris.tasks.ocean.realistic_global.forward.forward.Forward` step
with what the full run and the restart run need.  `dynamic_model_config()`
builds the step's
{py:class}`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage`
from config with the step's run duration and the task's history interval, so
that config changes after setup still take effect, and then layers the task's
`full_run.yaml` or `restart_run.yaml` on top of the shared `forward.yaml`;
because model config data is processed in the order it was added, the task's
overrides win.  `setup()` rejects any model other than Omega, since the
failure being tested cannot arise in MPAS-Ocean.

`full_run.yaml` writes a restart every `restart_freq` seconds, so once at the
restart time and again at the end, with no pointer file.  It also adds a
`HistoryBeforeRestart` stream: a copy of the base `History` stream, writing
`output_before_restart.nc`, that stops with an end time between the frame at
the restart time and the next one, since Omega writes nothing once a stream's
end time has passed.  A unit test checks that the copy matches `History` in
everything else, since the restart run appends to that file with the
`History` stream.

`restart_run.yaml` continues from the full run's restart at the restart time,
read by name rather than through a pointer file, since the full run writes
another restart at its end.  The restart's file name is computed in
`restart_file()` the way Omega stamps it.  Both steps declare that restart to
Polaris, the full run as an output and the restart run as an input, so a
missing restart is caught before the model launches.  It does not use the
`restart_in`/`restart_out` chaining of `ForwardStage`, which is for chaining
whole runs one after another.

`runtime_setup()` creates the restart directory the step writes into, which
Omega does not create itself, and, for the restart run, copies the full run's
`output_before_restart.nc` into place as `output.nc`.  Each step gets a
directory of its own under the task's `restarts`, named for the step, so the
restart run's restart at its end cannot replace one the full run wrote.  The
copy is what makes the #482 check meaningful: it reproduces what a continuing
run finds on disk, a history file that already holds the earlier frames.  It
is a copy rather than a symlink so that appending to it cannot reach back into
the full run's work directory.  The full run's history up to the restart is
also added as an input file under the name `previous_output.nc`, which both
establishes the dependency between the two steps and keeps the symlink out of
the way of the copy.

### the start time

The one subtlety in `restart_run.yaml` is that the restart run is given the
same `StartTime` as the full run, the start of the simulation, rather than the
restart time.  Omega measures the history time axis from the clock's start
time, so a run that moves the start time restarts that axis at zero, and its
first frame then collides with the first frame already in the file.  That
collision is what silently overwrote the earlier frames in #482.  On a
`Continue` the clock's current time comes from the restart file instead, so
the start time does not need to move.

### validate

The class
{py:class}`polaris.tasks.ocean.realistic_global.restart.validate.Validate`
compares the history of the restart run with that of the full run.  It reads
the elapsed-time coordinate with `xarray` directly, rather than through the
Omega-to-MPAS-Ocean renaming in `open_model_dataset()`, because that coordinate
is the variable under test; it then compares the state variables with
{py:func}`polaris.validate.compare_variables` as any other exact-restart test
would.  A restart run whose history has fewer frames than the full run's is
reported as the #482 failure specifically, since that is the shape the bug
takes.  It also checks that the history up to the restart holds fewer frames
than the full run's and matches its first ones; otherwise the restart run
would have had nothing to append to, and the time-axis check would pass
without testing anything.

(dev-ocean-realistic-global-dynamic-adjustment)=

## dynamic_adjustment

The `dynamic_adjustment` task family (steps under
`spherical/realistic_global/{mesh_name}/dynamic_adjustment`) runs a
restart-chained sequence of forward stages from a mesh's realistic initial
condition.  One
{py:class}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.task.RealisticGlobalDynamicAdjustment`
task is registered per MPAS mesh.

### shared steps

{py:func}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps.get_realistic_dynamic_adjustment_steps`
builds the whole chain — the shared `init` steps, one `Forward` stage per
schedule entry, a `StageCheck` after each, `validate` and `viz` — through
{py:meth}`polaris.Component.get_or_create_shared_step`, following the same
pattern as
{py:func}`polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`.
A downstream workflow that wants the adjusted restart — `e3sm/init`'s
component inputs — calls it and gets the same step instances rather than a
second copy of a very expensive chain.

It returns the stages alongside the steps and config, because which stage hands
off the adjusted state, and what that restart file is called, both depend on the
schedule: `stages[-1].restart_out` is what such a consumer is after.
`include_viz` follows the `init` convention — the step is always created, but
only returned, and so only in a task's `steps_to_run`, when asked for.  A figure
describing a completed adjustment is not what a workflow that only wants the
relaxed restart is asking about.

Two details are specific to this workflow.  The restart chain is wired with
{py:meth}`polaris.Step.add_dependency()` rather than through input/output files,
because a stage's restart filename comes from the schedule rather than from the
step.  Wiring it inside the step constructor — the pattern the `init` steps use
— is not available for a chain whose links only this helper knows, so it is
wired from here, which is safe because re-adding the same dependency is a no-op.

And because the set of steps depends on the schedule,
{py:meth}`...RealisticGlobalDynamicAdjustment.configure` rebuilds them when a
user's setup-time config changed it — a stage whose name survived the change
would otherwise be handed back from the shared-step cache still carrying its old
run duration.  It discards the adjustment steps from the component and then
simply asks for the whole chain again; the `init` steps upstream do not depend
on the schedule, so they come back unchanged.

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
`ForwardStage.restart_stream_replacements`.  Each stage writes its restart and
pointer file into a directory of its own under `restarts`, and
`ForwardStage.restart_files` gives the files `Forward.setup()` declares for
either model.

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
schedules and, on `u-oi6to18-lr12p5`, a single startup record for every stage
shorter than the 10-day output interval.

`schedule._check_stage_writes_its_records` rejects a `restart_interval` that
misses MPAS-Ocean's restart alarm (measured from the stream's fixed
`reference_time`, not the stage start) and a `stats_interval` longer than the
stage.  Both otherwise fail only after the model has run.

The statistics file is opened by relative path rather than declared as a step
input, so a stage that did not write one degrades to computing what it can from
`output.nc`.  Its name differs by model (`diagnostics.STATS_FILENAMES`): Omega
treats its `Filename` as a prefix and appends the reduction period with no `.nc`.

The checks live in
{py:mod}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.checks`,
because two kinds of step apply them.  The `temperature_max`, `salinity_max`
and `cfl_max` thresholds belong to
{py:class}`polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate.StageCheck`,
one per stage, added right after its forward step so the sequence stops at the
stage that broke.  `Validate` keeps only the cross-stage settling check on
`kinetic_energy_mean`.  Each is skipped, with a log line, when the model reports
no such metric.

`StageCheck` is a step of its own rather than work the forward step does after
the model exits.  A Polaris step is sized for its MPI call and there is no good
mechanism for post-MPI Python, so folding the check in would hold the model's
whole allocation open to compare a few scalars.

The thresholds read the extreme reached at any point in the stage, so an
excursion the run recovered from is still caught, and
`diagnostics.extreme_and_day` returns the day it happened alongside the value.

Which samples a stage is judged on is decided in one place,
`diagnostics.first_judged_index`, which both that function and
`diagnostics._reduce` go through.  It always skips the stage's first sample,
written before any time step: for the first stage it is the initial condition
and for the rest it is the predecessor's final state, already checked, so the
extremes describe what each stage did.  Without this the `u-oi30-lr10` run
failed on a WOA23 source artifact in its initial condition.  It returns `None`
when a stage wrote nothing else, which the schedule's `stats_interval` check is
what prevents.

Its `exclude_days` argument is how the sequence's `startup_exclusion_duration`
reaches a stage.  `schedule.excluded_days_in_stage` turns that duration into a
number of days *into a given stage*, measuring from the first stage's
`start_time` and returning zero for a stage that begins after the window has
closed.  Measuring from the sequence rather than from each stage is deliberate:
what the window skips belongs to the initial condition, and a per-stage window
would stop watching the hours just after every damping change.  Expressing the
result relative to the stage is deliberate too — a stage's statistics count
time from their own first sample, and this way nothing depends on whether the
model restarted its clock.

Only the metrics with `Metric.startup_window` set — the tracer extremes — are
given it.  `cfl_max_in_stage` is not, because a time step too long for the flow
shows up in exactly the hours the window covers.  `Validate` passes the same
windows when it builds the summary, so the CSV a user reads and the checks that
passed cannot disagree.  This is what the `u-oi6to18` runs need: their
statistics are hourly, and the Sumatra artifact is still at 35.1 to 36.1 °C an
hour in.

`_check_ke_growth_decelerates` is deliberately not a check on the level of the
kinetic energy.  These runs start from rest and are wind-forced, so kinetic
energy rises throughout a 40-day adjustment; the first version of this check
compared levels and failed the healthy u-oi240-lr240 run.  It is also not a
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

The step is `default_cached = True`, with the product in the cache database,
so that the multi-GiB download happens only when the product is deliberately
regenerated.  The standalone `jra55` task marks the step free-running for
that purpose.

The product is deliberately **not** padded, in latitude or longitude.  Bilinear
remapping is center-based for ESMF but corner-based for mbtempest, and padding
a lat-lon source so that either its corners or its centers reach the pole
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
`[ocean] model` config option at run time.

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
   count via the `remap_cells_per_task` and `remap_min_cells_per_task`
   options in the `[realistic_global_init]` config section.  It and
   **jra55_map** are thin subclasses of
   {py:class}`~polaris.tasks.ocean.realistic_global.init.lat_lon_map.LatLonMapStep`,
   which links the source and culled mesh, sizes the task count and builds
   the weights; each subclass supplies only its source.
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
   pyremap's moab path hard-codes `--order 1`.
5. **remap_jra55** ({py:class}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.RemapJra55Step`):
   applies those weights with `ncremap`, producing `jra55_on_mesh.nc`.  The
   stress is remapped in Cartesian components
   ({py:func}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.stress_to_cartesian`)
   and rotated back to zonal and meridional components at the cell centers
   ({py:func}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.cartesian_to_stress`),
   since the east/north basis rotates with longitude.  That also makes the
   result independent of `map_tool`: ESMF's default pole handling averages
   the source's outermost row, which would cancel a vector given in zonal and
   meridional components.
   `ncremap` writes zero rather than a missing value to a cell the weights
   do not reach, so
   {py:func}`~polaris.tasks.ocean.realistic_global.init.remap_jra55.check_no_missing_cells`
   reads each cell's coverage (`frac_b`) from the mapping file and fails the
   step if any cell is not fully covered or has a non-finite stress.
6. **pstar_init** ({py:class}`~polaris.tasks.ocean.realistic_global.init.pstar_init.RealisticPStarInitStep`):
   subclass of {py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep`
   that runs the fixed-point p-star iteration jointly with the vertical
   interpolation of the WOA23 tracers, writing a model-neutral
   `pstar_init.nc` with converged geometric layer interfaces and CT/SA
   tracers.  The target bathymetry is first clamped into the range of depths
   the reference grid can represent, and to no shallower than
   `min_bottom_depth` or `min_vert_levels` layers.  The column is anchored at
   the prescribed sea surface, so `ssh` matches its prescribed value (0 here)
   and any residual from partial-cell snapping goes into `bottomDepth`
   instead.  Isolated bathymetry holes, cells deeper than every ocean
   neighbor, are capped at their deepest neighbor's level and re-solved via
   {py:func}`polaris.ocean.vertical.bathymetry_holes.fill_max_level_holes`.
7. **initial_state** ({py:class}`~polaris.tasks.ocean.realistic_global.init.initial_state.InitialStateStep`):
   reads `pstar_init.nc` and the model resolved from `[ocean] model` to
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
   `dimensions="nCells Time"`, so a `Time` dimension of one is added there.
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
Omega variable names to their MPAS-Ocean equivalents — and
{py:meth}`~polaris.ocean.model.OceanIOStep.open_vert_coord_dataset`, so one
code path serves both models.  The titles and labels, by contrast, use each
model's own variable names (`Temperature`, `BottomGeomDepth`, `SshCell`, ...
for Omega), and temperature and salinity also say which quantity the model
holds: conservative temperature and absolute salinity for Omega, potential
temperature and practical salinity for MPAS-Ocean.  Output filenames keep the
MPAS-Ocean names for both models so that the two sets of plots line up.
Omega's initial state has no `SpecVol`, which `open_model_dataset` needs to turn `PseudoThickness`
into a geometric `layerThickness`, so the step derives the specific volume from
the equation of state itself.  It produces:

* `initial_state_summary.png`: histograms of the initial condition (a port
  of Compass' `plot_initial_state` without its Haney-number panel).  The
  prognostic layer-thickness panel shows each model's *native* variable —
  `layerThickness` for MPAS-Ocean and `PseudoThickness` for Omega — read from
  the raw output file and, like the other 3D panels, masked below the
  seafloor.
* `vertical_coordinate.png`: the vertical-coordinate structure derived from the
  geometric `restingThickness` of the deepest column (there are no
  `refMidDepth`/`refBottomDepth` reference profiles in this workflow).
* global native-mesh maps (via {py:func}`polaris.viz.plot_global_mpas_field`)
  of temperature and salinity at the depths listed in
  `[realistic_global_init_viz] depths`, plus surface and seafloor, and
  `bottomDepth`, `ssh`, `maxLevelCell` and column thickness.  For Omega the
  more native `SurfacePressure` and `BottomPressure` are also plotted when
  present.
* vertical transects (via `mpas_tools` `compute_transect`/`plot_transect`) of
  temperature and salinity along each transect in
  `[realistic_global_init_viz_transects]`.  Layer interfaces are not drawn,
  because the thin upper layers pack them into a band that hides the upper
  few hundred meters; `vertical_coordinate.png` shows the layer structure.
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
the plotting code.  Units come from the same defaults (Omega's `Density`
falls back on `density`), except that MPAS-Ocean's salinity is labeled PSU,
since it is practical rather than absolute salinity.  The limits, by
contrast, are computed per plot from the data range and written into
`[realistic_global_init_viz]` just before each call.  That is deliberate and
differs from the forward `viz` step, which reads fixed limits from
`realistic_global.cfg`: fixed limits are what you want to compare runs or
times against each other, and the data range is what you want when the
question is whether a brand-new initial condition is sane.  For a diverging
colormap the range is made symmetric about zero.
