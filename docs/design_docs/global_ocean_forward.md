# Global Ocean Forward Runs

Creation date: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

## Summary

This design document describes a new Polaris capability: a reusable framework for
realistic, global-ocean forward runs with either MPAS-Ocean or Omega, selected by
the `[ocean] model` config option. The framework belongs to the
`ocean/spherical/realistic_global` family, alongside the initial-condition
workflow described in [global_ocean_init.md](global_ocean_init.md). Where that
workflow produces a model initial condition, this framework runs the configured
model forward from such a condition.

The intent is to replace and generalize the forward-run machinery of the legacy
Compass `global_ocean` test family (`compass/ocean/tests/global_ocean/forward.py`
and its test cases) using Polaris' shared-step design and its existing ocean
model abstraction. The single deliverable of the first phase is a reusable
forward step plus one runnable "simple forward" task (a run whose duration and
cadence come from config). The framework is deliberately shaped so that the two
other forward run types from Compass — a restart test and the staged dynamic
adjustment described in
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md) — are
straightforward to build on top of it later.

That first phase has landed, and so has more than it promised. Two runnable
task families exist rather than one — `forward` on a mesh the `init` workflow
builds, and `cached_forward` on an initial condition downloaded from the
Polaris input-file database — and they turned out to answer different
questions, which is what decides the physics each one runs. Restart chaining
landed as well and dynamic adjustment is built on it without modifying the
forward step, exactly as this document called for. A restart test is still not
implemented.

A forward run must be able to obtain its model inputs (horizontal mesh, vertical
coordinate, initial state, surface forcing, and graph) from either of two
sources: a file staged in the Polaris input-file database and referenced by
name, or the outputs of the upstream `realistic_global/init` steps. It must
express the per-run controls — run duration, output and restart cadence, time
step, damping, and the mixing and parameterization settings that vary with the
mesh — in a model-agnostic form and translate them, in a single place, to the
configuration options of the configured model. It must also write restart
files, so that a sequence of forward runs can be chained.

The primary software challenge is not the forward integration itself, which
Polaris' `OceanModelStep` already supports, but the workflow abstractions around
it: a clean separation between *where inputs come from*, *what a run should do*,
and *how that maps onto MPAS-Ocean versus Omega*. This design is successful if
Polaris can run a realistic global forward simulation for either model from
either initial-condition source, if the per-run settings are described once and
mapped to the model in one isolated location, and if restart and staged
dynamic-adjustment workflows can reuse the same forward step without modifying
it.

## Requirements

### Requirement: A reusable forward-run capability runs a realistic global ocean simulation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Polaris shall provide a reusable capability to run a realistic, global-ocean
simulation forward in time for the ocean model selected by the `[ocean] model`
config option (resolved to `omega` or `mpas-ocean` during component setup). A
given task targets exactly one model.

The capability shall include at least one runnable task: a simple forward run
whose duration and output cadence are set through config options rather than
Python source code. The task shall run to completion on at least one coarse
global mesh and produce a model output file.

The capability shall size its own parallel resources from the mesh so that the
same task can run on meshes of very different sizes without per-mesh code
changes.

### Requirement: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A forward run shall be able to obtain the model inputs it consumes (horizontal
mesh, vertical coordinate for Omega, initial state, surface forcing, and, for
MPAS-Ocean, a graph partition file) from either of two sources:

1. A file staged in the Polaris input-file database and referenced by name.
2. The outputs of the upstream `realistic_global/init` steps for the same mesh
   and configured model.

The choice of source shall be a property of how the task is assembled, not a
branch inside the forward step. Adding a third source in the future shall not
require modifying the forward step or the run-settings logic.

### Requirement: The two sources of initial condition answer different questions

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A run from a cached initial condition and a run from the `init` workflow are not
two sizes of the same test, and the framework shall not treat them as though
they were. This became clear only once both were runnable, so it is recorded
here rather than having been designed in.

A run on a cached initial condition exists to compare MPAS-Ocean with Omega on
one mesh and one initial condition, so it shall use only the physics both models
have: anything one model has and the other lacks works against the comparison. A
run on a mesh the `init` workflow builds exists to check that the mesh behaves
the way it will in a real E3SM configuration, so it shall use E3SM's physics for
that mesh.

Every model setting the two need to disagree on shall therefore be a Polaris
config option rather than a fixed value, and the defaults shall be the E3SM-like
ones. The two shall be registered as separate tasks so that one mesh could carry
both without them colliding.

### Requirement: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The controls that define a single forward run — run duration, output interval,
restart interval, time-step selection, and damping strength — shall be described
in a single, model-agnostic representation. Polaris shall translate that
representation into the configuration options appropriate for the configured
model in exactly one place, so that MPAS-Ocean and Omega differences are isolated
rather than scattered through the workflow.

Run, output, and restart durations shall be expressible as duration strings
compatible with the staged-adjustment schedule format so that a simple forward
run and a dynamic-adjustment stage can share the same representation. The time
step shall be derivable from mesh resolution (a value per kilometer scaled by the
mesh's minimum resolution) while still allowing an explicit override.

### Requirement: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The forward step shall be general enough that a restart test and the staged
dynamic-adjustment workflow can be built from it without changing the step
itself. In particular, the step shall be able to write a restart file at a
configured cadence, and it shall accept the settings needed to continue from an
existing restart (a restart flag, a start time, and a restart input file).

The framework itself is not required to implement the restart test or dynamic
adjustment in this phase; it is required only to leave clean seams for them,
consistent with
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md), which
decomposes dynamic adjustment into one restart-chained forward step per stage.

### Requirement: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

A forward step shall produce clearly named, inspectable outputs — at least a
model output file and, when a restart cadence is configured, restart files — that
users and developers can examine for sanity checking and debugging.

The step shall support basic validation of a small set of output variables
against a baseline and, where applicable, conservation-property checks, so that
regressions such as numerical blow-up or broken restart chaining can be detected.

### Requirement: Physics and mixing options vary with the mesh

Date last modified: 2026/07/21

Contributors: Xylar Asay-Davis, Claude

The horizontal mixing coefficients, the eddy parameterizations, and the way
mixing is scaled across a variable-resolution mesh all depend on the mesh a
forward run uses. A single, mesh-independent set of model config options is not
sufficient: a 240 km mesh needs a Leith closure and a reference cell width, while
a 6-to-18 km mesh needs a much smaller biharmonic viscosity, mesh-density
scaling, and no eddy parameterization at all.

These settings shall therefore be Polaris config options rather than fixed values
in the model-config template, with defaults in the task's own config file and
per-mesh overrides in `mesh_configs/<mesh_name>.cfg`, using the mechanism that
already carries the vertical grid and the ocean-culled cell count. Each mesh's
values shall follow how that mesh is configured in E3SM, rather than being chosen
to make MPAS-Ocean and Omega agree; the two models are expected to diverge where
one lacks a parameterization the other has.

Options that both models support shall be expressed once, in model-neutral form,
and translated automatically. Options with no counterpart in the other model
shall be emitted only for the model that has them.

## Algorithm Design

### Algorithm Design: A reusable forward-run capability runs a realistic global ocean simulation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The forward run should be a single reusable step built on Polaris' existing ocean
model abstraction (`OceanModelStep`), which already selects between MPAS-Ocean
namelists/streams and an Omega YAML configuration, partitions the graph for
MPAS-Ocean, and computes the number of MPI tasks dynamically from a mesh cell
count. The closest existing precedent is the spherical convergence forward
(`polaris.ocean.convergence.forward.ConvergenceForward` and its spherical
subclass), which renders a task-level YAML template with run duration, output
cadence, and time step drawn from a config section and overrides a
`compute_cell_count` method to size resources. The realistic global forward step
follows the same shape, but sources its cell count from the actual global mesh
rather than a convergence resolution heuristic.

Resource sizing should use the exact number of cells from the mesh when that file
is available (at run time) and fall back to a configured approximate cell count
during setup, before the initial condition has been produced. This mirrors the
approach used in the legacy Compass forward step.

### Algorithm Design: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The two initial-condition sources should be captured by a small abstraction — an
"initial condition" object — whose responsibility is to add the required input
files to a forward step and to point the step at the correct graph file. The
forward step holds one such object and defers all questions of provenance to it.

Two concrete implementations are needed:

1. A source backed by the upstream `realistic_global/init` steps, which links the
   `mesh`, `vertical coordinate`, `initial state`, `forcing` and `graph` files
   from the initialization steps' work directories. This is the source used by
   the first runnable task, since those outputs already exist in the same run.
2. A source backed by the Polaris input-file database, which constructs the input
   filename from the mesh, the configured model, and the equation of state, and
   registers it as a database input.

Because the required filenames and the model-specific handling of the vertical
coordinate and graph depend on the configured model, the source applies its input
files when the model is known (during step setup) rather than at construction
time.

### Algorithm Design: The two sources of initial condition answer different questions

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The difference belongs in config rather than in code. Both tasks build the same
forward step from the same settings structure; what differs is the values that
structure is built from, which the per-mesh config file already supplies for
other reasons. No branch anywhere asks which kind of task it is in.

A consequence worth stating: the list of settings a cached run turns off
describes what Omega lacks today, not a considered choice of physics. It should
shrink as Omega gains capabilities, and keeping it in config is what makes
shrinking it a one-line change rather than a code change.

### Algorithm Design: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

A single, model-agnostic settings structure should describe one forward run: its
name, run duration, output interval, restart interval, time integrator, an
optional explicit time step (barotropic and baroclinic), per-kilometer time-step
scalings, a damping strength, and the fields needed to continue from a restart
(a restart flag, a start time, and a restart input file). A simple forward run
fills this structure from a config section; a future dynamic-adjustment workflow
fills a list of them from a schedule file. This is the "common internal
representation" called for in
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md).

The mapping from this structure onto model configuration should happen in one
place. Durations are formatted as model duration strings; the time integrator
name is translated where the models differ (for example `RK4` to
`RungeKutta4`). Controls that exist only for one model — the barotropic time step
and Rayleigh damping for MPAS-Ocean — are emitted only under that model's section
of the template. Where a model lacks a direct equivalent (for example Omega
damping), the mapping is the natural place to apply the closest available control
as the capability matures.

### Algorithm Design: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Restart chaining should be expressed through the same settings structure and the
same template. Writing a restart is a matter of the restart interval; continuing
from a restart is a matter of the restart flag, start time, and a restart input
file. A restart test then becomes two forward steps — a full run that writes a
restart partway through and a restart run that resumes from it — compared for
bit-for-bit agreement. A dynamic-adjustment workflow becomes an ordered list of
settings structures, each producing a restart consumed by the next, exactly as
laid out in [global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md).

The forward step does not need to know which of these workflows it participates
in; it only needs to honor the settings it is given. Keeping start and stop times
derived from cumulative durations, as in Compass, lets the higher-level workflow
compute restart filenames deterministically.

### Algorithm Design: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The output and restart streams should be declared in the task-level YAML template
so that the set of written variables is easy to inspect and change. The step
should register its output file as a Polaris output with an optional list of
variables to validate against a baseline and optional conservation-property
checks, reusing the validation and property-check machinery already provided by
the ocean model step base class.

### Algorithm Design: Physics and mixing options vary with the mesh

Date last modified: 2026/07/21

Contributors: Xylar Asay-Davis, Claude

The per-mesh settings should join the same `ForwardStage` structure that already
carries the per-run settings, so that a forward run continues to have a single
description of what it should do. They are read from the same
`[realistic_global_forward]` section, which means a per-mesh config file
overrides them by the ordinary config-precedence rules and a user can override
them again in a user config file.

A coefficient and its enable flag should be a single Polaris option: blank turns
the term off, a value turns it on with that coefficient. This follows the
convention the section already uses for the explicit time step and the damping
coefficient, and it removes the possibility of a config that enables a term
without a coefficient or sets a coefficient that is never used.

Where the model offers several independent booleans for what is really one
choice — MPAS-Ocean's reference-cell-width and scale-with-mesh flags for
horizontal mixing — Polaris should expose a single option whose value names the
scaling, so that the combinations that are not meaningful cannot be expressed.

The stage should sort the resulting model options into two buckets: those both
models support, emitted in neutral form and translated by the existing
MPAS-Ocean-to-Omega map, and those only MPAS-Ocean has, emitted for that model
alone. Gent-McWilliams and Redi fall permanently in the second bucket; Omega has
neither and is not expected to gain them.

## Implementation

### Implementation: A reusable forward-run capability runs a realistic global ocean simulation

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The framework lives under
`polaris/tasks/ocean/realistic_global/forward/`. The forward step,
`Forward`, subclasses `polaris.ocean.model.OceanModelStep` and is modeled closely
on `polaris.ocean.convergence.forward.ConvergenceForward`. Its constructor adds
the shared double-precision output YAML (`polaris.ocean.config/output.yaml`),
stores an initial-condition object and a settings structure, and registers the
output file. It does not read config in its constructor, because the target model
is not known until setup.

Resource sizing overrides `compute_cell_count` to return the exact `nCells` read
from the mesh input file when it exists, and otherwise an `approx_cell_count`;
the base class turns this into `ntasks`/`min_tasks` using the existing
`goal_cells_per_core`/`max_cells_per_core` options. The approximate count is a
property of the initial condition rather than a config option, since it is the
initial condition that knows which mesh it is for: a step-backed source takes it
from `mesh_info.estimate_ocean_cell_count`, and a database-backed one from the
count recorded for that cached mesh.

The runnable task is `RealisticGlobalForward`, added once per supported mesh by a
factory `add_realistic_global_forward_tasks`, following the structure of the init
factory in `polaris/tasks/ocean/realistic_global/init/tasks.py`. Its work
directory is mesh-first, `spherical/realistic_global/{mesh_name}/{subdir_name}`,
matching the init layout, with `subdir_name` distinguishing `forward` from
`cached_forward`. The factory is registered from
`polaris/tasks/ocean/realistic_global/__init__.py`.

The task holds three steps rather than one. The forward run itself is named
`short` rather than `forward`, because that is what it is: a brief run that
checks the model is stable on this mesh and initial condition, not a simulation
worth interpreting. Two diagnostic steps follow it, neither run by default:
`global_stats` plots time series of the run's global statistics, and `viz` plots
global maps of its state.

### Implementation: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The initial-condition abstraction lives in
`forward/initial_condition.py` as an `InitialCondition` base class with two
subclasses. `StepInitialCondition` wraps the `initial_state` step returned by
`get_realistic_init_steps` (in
`polaris/tasks/ocean/realistic_global/init/steps.py`) and, during the forward
step's setup, calls the mixin helpers `add_horiz_mesh_input_file`,
`add_vert_coord_input_file`, and `add_init_input_file` with `work_dir_target`
pointing into that step's work directory, and sets the forward step's
`graph_target` to the init step's exported graph file. The vertical-coordinate
input and the graph are handled correctly per model by the existing
`OceanModelFilesMixin` and `OceanModelStep` machinery: for MPAS-Ocean the graph
is linked and partitioned; for Omega the separate vertical-coordinate file is
used and the graph is not partitioned.

`DatabaseInitialCondition` constructs the input filename from the mesh name, the
configured model, and the equation of state, and registers it with
`add_init_input_file(database=..., target=...)`. It is now wired into the
`cached_forward` tasks described above. The MPAS-Ocean graph question was
settled in favor of downloading a prebuilt graph partition file alongside the
initial condition rather than building one from the mesh; Omega partitions
internally and needs neither.

Two things the design did not anticipate fell out of this abstraction once
surface forcing existed. The initial condition also answers *where the wind
stress lives*, through `get_forcing_filename()`: a source that stages a forcing
file of its own names it, and a source whose stress travels inside the
initial-condition file names that file instead, so the forcing streams are
pointed at the right place without the forward step knowing which case it is
in. And `StepInitialCondition` links the initial state only when the run
actually reads one, since a stage continuing from a restart does not — a detail
that belongs to the source rather than to the step for the same reason.

### Implementation: The two sources of initial condition answer different questions

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

`add_realistic_global_cached_forward_tasks` registers one task per entry of
`forward/tasks.py`'s `CACHED_MESHES`, with a `subdir_name` of `cached_forward`
rather than `forward` so that a mesh could carry both. Each entry gives the
MPAS-Ocean and Omega initial-condition IDs on the Polaris server, the minimum
resolution and the cell count. The two meshes are `QU.240km` and
`EC30to60E2r2`, whose initial conditions were converted from existing E3SM ones
by `utils/omega/convert_mpaso_ic_to_omega.py` and uploaded. A cached mesh also
needs a `mesh_configs/<mesh_name>.cfg` giving its time step and run duration,
since neither follows from a mesh Polaris did not build.

`QU.240km.cfg` is where the comparison intent is written down: `RK4` for
MPAS-Ocean as well as Omega, so the two advance the same way at the cost of
MPAS-Ocean taking the short step; and `use_GM`, `use_Redi`, `use_KPP`,
`use_submesoscale` and `pressure_gradient_type` turned off or left at the model
default. The unified meshes' configs do the opposite, stating E3SM's mixing and
parameterizations for their resolution.

The cached tasks are the only members of this family cheap enough for a PR
suite: `ocean/spherical/realistic_global/QU.240km/cached_forward/task` is in
both `mpaso_pr` and `omega_pr`. Nothing built on the `init` chain belongs in a
suite, since that chain is hours of preprocessing before the model starts.

`cached_forward` is expected to be temporary. Once Omega has the full physics
and the initialization workflow has been exercised end to end, the comparison
can be made on meshes Polaris builds itself and the hand-staged initial
conditions can go.

### Implementation: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The settings structure is a small dataclass, `ForwardStage`, in
`forward/stage.py`, with a class method that builds one from a
`[realistic_global_forward]` config section. Its fields cover the run duration,
output interval, restart interval, statistics interval, the two time
integrators, optional explicit `dt`/`btr_dt`, `dt_per_km`/`btr_dt_per_km`, a
damping (Rayleigh) coefficient, the mixing and parameterization options
described further below, and the restart fields (`do_restart`, `start_time`,
`restart_in`, `restart_out`). Durations are duration strings of the form
`DDDD_HH:MM:SS`, matching the schedule format in
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md).

The time integrator turned out to be the one setting that cannot be shared, so
there are two fields rather than one: `mpaso_time_integrator`, defaulting to
`split_explicit_ab2`, and `omega_time_integrator`, defaulting to `RK4`. Omega
has no split time stepper, while MPAS-Ocean needs one to make the month-long
spin-ups built on this framework affordable. The time step follows from that
choice rather than being chosen separately: a split integrator advances on the
long baroclinic step and subcycles the barotropic mode, and a non-split
integrator has to advance on the short barotropic step. With the defaults, the
two models therefore run the same mesh at very different time steps.

The mapping onto model configuration happens only in the forward step's
`dynamic_model_config`, which renders `forward/forward.yaml` with template
replacements derived from the stage. Durations are formatted with
`polaris.ocean.model.get_time_interval_string`; where the time step is not given
explicitly it is computed as the per-kilometer value times the mesh minimum
resolution. The time-integrator name is mapped to Omega where needed, exactly as
`ConvergenceForward` does. The template's model-neutral `ocean:` block is
auto-translated to Omega through the existing `mpaso_to_omega.yaml` map, while
the barotropic time step and Rayleigh damping appear under the `mpas-ocean:`
section. The restart controls did gain an Omega counterpart, in
`restart_streams.yaml` rather than in the main template; see below.

Where a model cannot honor a setting, the mapping raises rather than dropping
it: an `omega_time_integrator` Omega does not support, and a non-blank `damping`
under Omega, which has no Rayleigh damping at all
([Omega#495](https://github.com/E3SM-Project/Omega/issues/495)). Both raise at
run time rather than at setup, so that a task can be set up and its config
changed before it is run. Reporting success on a run that quietly dropped the
damping it was asked for is the failure mode this avoids.

```python
def dynamic_model_config(self, at_setup):
    super().dynamic_model_config(at_setup=at_setup)
    replacements = self.stage.model_replacements(self.config, self.min_res)
    self.add_yaml_file(self.package, self.yaml_filename,
                       template_replacements=replacements)
```

### Implementation: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The restart stream is declared in `restart_streams.yaml`, added only for a stage
that is part of a restart chain, and the model-neutral time block carries the
start time and restart flag. The simple forward task leaves the restart fields
unset, so it starts from the initial condition and writes a single restart at
the end of the run.

Dynamic adjustment is built on exactly this and needed no change to the forward
step: it builds a list of `ForwardStage`s from a per-mesh YAML schedule and sets
each one's `restart_in` and `restart_out` so that consecutive stages share a
`restarts` directory. For MPAS-Ocean the restart stream is both an input and an
output stream, so one `filename_template` serves both directions and the read
side is just `config_do_restart` and `config_start_time`; the start time is
stated explicitly rather than using a restart-pointer file. Omega needs a
separate `RestartRead` stream, which the `Omega` block of
`restart_streams.yaml` supplies, switched on per stage by
`ForwardStage.restart_stream_replacements`.

That Omega block is written but unrun: Omega's restart filenames carry no `.nc`
extension and it is not established whether Omega appends one, so the restart
files are declared as step inputs and outputs for MPAS-Ocean only.
[Omega#482](https://github.com/E3SM-Project/Omega/issues/482), where restarts
and history output interact badly, will also change how an Omega restart run has
to be configured.

A restart test — two `Forward` steps with different durations and restart
settings, compared for bit-for-bit agreement — is still not implemented. Nothing
about it needs the forward step to change.

### Implementation: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The 3-D output stream is declared in `forward/forward.yaml` — an MPAS-Ocean
`output` stream and the corresponding Omega `History` `IOStream` — and the
restart streams in `restart_streams.yaml`. The `Forward` step registers its
output file through `add_output_file` with an optional `validate_vars` list
(`temperature`, `salinity`, `layerThickness`, `normalVelocity`) and optional
`check_properties`, reusing the baseline-comparison and conservation checks
already implemented in `OceanModelStep`.

The output stream carries more than the prognostic state: kinetic energy and
relative vorticity for MPAS-Ocean, and for Omega the `AuxiliaryState`, `SshCell`
and `Eos` groups, which add the vorticity, divergence and del2 terms, the free
surface and the specific volume and buoyancy frequency. The extra fields cost
file size and are worth it, because a run that goes wrong can otherwise be seen
to have gone wrong but not diagnosed, and these runs exist partly to be compared
against each other. Density is the one field in that stream with a switch of its
own (`output_density`), because it is 3-D and roughly 13% of the output volume,
which starts to matter once a workflow writes the stream many times over.

Global statistics are the other output, and the more useful one. Both models
write a time series of the global minimum, maximum, mean and RMS of the state
variables — MPAS-Ocean through its `globalStats` analysis member and Omega
through its `GlobalStats` analysis group, plus the global CFL number for
MPAS-Ocean — on a `stats_interval` cadence deliberately separate from the 3-D
`output_interval`. They are a handful of scalars, so they can be written far
more often than 3-D fields, which is what makes an excursion *within* a run
visible rather than only at its end. Two model differences are handled once, in
`ForwardStage.stats_filename`, so that everything reading a stage's statistics
asks the same question the same way: Omega treats the configured name as a
prefix and appends its analysis period and the kind of output with no `.nc`
extension, and Omega's statistics are taken as instantaneous snapshots rather
than temporal reductions, both because that is what the mapped variable names
mean and because an averaging period would constrain the restart interval.

Surface forcing is no longer out of scope, and it is not optional either. Every
realistic global forward run is forced by the time-invariant JRA55-do wind
stress the `init` workflow produces: `forcing.yaml` is always added, and there
is no config option to run without it. `forcing_streams.yaml` points each model's
input stream at whichever file the initial condition names. There is still no
surface restoring and there are no thermal or freshwater fluxes, so the tracers
spin down from the initial condition while the momentum input holds up a
circulation.

Two diagnostic steps, neither run by default, read these outputs: `global_stats`
(`StatsAnalysis`) plots the statistics as time series with a
standard-deviation envelope and an anomaly panel, and `viz` plots global maps of
each state variable at the start and end of the run along with the wind stress
that forced it.

### Implementation: Physics and mixing options vary with the mesh

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

`realistic_global_forward.cfg` gains the mixing and parameterization options:
`mom_del2`, `mom_del4`, `tracer_del2` and `tracer_del4` (blank meaning off),
`mom_del4_div_factor`, `use_Leith_del2`, `hmix_scaling` with
`hmix_ref_cell_width`, `use_GM` with `GM_closure` and `GM_constant_kappa`,
`use_Redi`, `use_KPP`, `use_submesoscale`, `pressure_gradient_type`,
`use_frazil_ice_formation` and `output_density`. The list grew past what this
section first named once the `forward` tasks had to reproduce E3SM's
configuration rather than a Compass baseline: the defaults are now the
E3SM-like ones, and the `cached_forward` tasks override them for the reasons
given above. Several are off in MPAS-Ocean itself, so leaving them alone would
not have given E3SM's configuration either.

`hmix_scaling` has two values, `none` and `ref_cell_width`, not the three this
section anticipated. MPAS-Ocean's third combination — `scaleWithMesh` with
`use_ref_cell_width` false — scales by the legacy `meshDensity` field, which
every E3SM v4 mesh writes as uniformly 1.0, so that branch silently applies no
scaling at all. Offering it would only let a user ask for scaling and get none.
The two flags MPAS-Ocean does need are set together by `ref_cell_width`, since
`config_hmix_use_ref_cell_width` is read only inside
`if (config_hmix_scaleWithMesh)` and setting the first alone has the same silent
failure.

Settings that should *not* vary are pinned in `forward.yaml` rather than made
options, purely so that the two models agree: horizontal tracer advection order
3 (Omega defaults to 2), implicit constant bottom drag at 1e-3 (Omega has none
by default), the CVMix convection and shear-mixing parameters, and
`config_Redi_min_layers_diag_terms = 0`, which computes the Redi diagnostic
terms in the top layers the Registry default skips. Where the two models'
defaults differ, the MPAS-Ocean default wins.

`ForwardStage` gains the corresponding fields and two methods beside the existing
`bottom_drag_options`: `horiz_mixing_options` returns the neutral del2/del4
options for momentum and tracers, and `mpaso_physics_options` returns the
MPAS-Ocean-only options — the Leith closure, horizontal-mixing scaling, the
biharmonic divergence factor, Gent-McWilliams, Redi, KPP, the submesoscale
parameterization, the pressure-gradient formulation and frazil ice.
`Forward.dynamic_model_config` adds the first with `config_model='ocean'`, so
`OceanModelStep.map_yaml_options` translates it for Omega, and the second with
`config_model='mpas-ocean'`. Omega has no equivalent for anything in the second
bucket and is not expected to gain GM or Redi.

Per-mesh overrides live in `mesh_configs/<mesh_name>.cfg` under the same
`[realistic_global_forward]` section, applied by `add_realistic_global_mesh_config`
after the task config so that they take precedence. The values are ported from
the per-mesh `namelist.split_explicit_ab2` files of the corresponding Compass
meshes: `qu240` for the three 240 km meshes (`u.oi240.lr240`, `qu240km` and
`icos240km`, which are qualitatively the same mesh and share a block), `qu` for
`u.oi30.lr10`, `rrs6to18` for `u.oi6to18.lr6to10`, and `so12to30` for
`u.oi.so12to30.lr10`.

Two exceptions to that port are deliberate. The Compass `so12to30` time step is
not carried over: it is far more conservative than its resolution alone justifies,
almost certainly because the Compass mesh has ice-shelf cavities, and
`u.oi.so12to30.lr10` is for now a proof of concept for regional refinement rather
than a mesh run in earnest. And Compass's run durations and debug-tracer settings
are test-harness details that Polaris expresses through its own config options.

Because the neutral bucket can carry tracer diffusivities, the MPAS-Ocean-to-Omega
map also gains the two entries it was missing, `config_tracer_del2` to
`EddyDiff2` and `config_tracer_del4` to `EddyDiff4`; the corresponding enable
flags were already mapped, so without these a tracer diffusivity set from Polaris
would have been dropped for Omega with only a warning.

## Testing

### Testing and Validation: A reusable forward-run capability runs a realistic global ocean simulation

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A `polaris setup` smoke test on a coarse global mesh, run for both
`[ocean] model = mpas-ocean` and `omega`, should confirm that the forward work
directory contains the expected input symlinks and that the generated namelist
and streams (MPAS-Ocean) or `omega.yml` (Omega) contain the expected run
duration, cadence, time step, and time integrator, without running the model.
Where a model build is available, a short end-to-end run on a coarse mesh should
confirm that the output file and a restart file are written.

What landed is `tests/ocean/realistic_global/test_forward.py`, which renders the
model config for both models and checks it rather than requiring a setup, plus
`test_tasks.py`, which checks that a task is registered per mesh with the step
list this design calls for. Resource sizing is covered by tests that
`compute_cell_count` falls back to the initial condition's estimate before the
mesh exists, and raises rather than guessing when there is no estimate. The
end-to-end run is the cached `QU.240km` task in the two PR suites.

### Testing and Validation: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests confirm that `StepInitialCondition` registers its inputs and sets the
graph target from the init step's work directory, that it skips the initial
state on a stage continuing from a restart, and that it requires a forcing step
and wires the forcing file; and that `DatabaseInitialCondition` constructs the
expected database filename and target for each configured model, raising when an
Omega run has no Omega initial-condition ID. A further pair of tests checks the
seam between the two: that the forcing streams point at the staged file for one
source and at the initial condition itself for the other.

### Testing and Validation: The two sources of initial condition answer different questions

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests confirm that every cached mesh has a per-mesh config, that those
configs turn off what Omega lacks, that the model config a cached task renders
is what those options imply, and that the task's config carries what the
database source needs — the equation of state above all, since a cached run
never sets the `init` workflow's config up at all and still has to name the
equation of state to find the right file.

The end-to-end check is the PR suites, which run the cached `QU.240km` task for
both models on every pull request.

### Testing and Validation: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Unit tests should cover building a `ForwardStage` from config and its mapping onto
template replacements: correct duration strings, the time-integrator translation
for Omega, the derivation of the time step from `dt_per_km` and the mesh minimum
resolution versus an explicit override, and the presence of the barotropic time
step and Rayleigh damping only for MPAS-Ocean.

### Testing and Validation: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Tests confirm that the restart-in settings render the expected restart flag and
start time, that `restart_stream_replacements` switches Omega's read side on,
and that `restart_streams.yaml` requests Omega's `RestartRead` stream. Which
files a step declares is checked from the dynamic-adjustment side, where the
chain is built: that a stage in a chain declares both ends of it, that a lone
stage declares neither, and that an Omega stage declares no restart files at
all, matching the unrun state of that path.

### Testing and Validation: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Tests should confirm that the output file is registered with the expected
validation variables and that, when property checks are requested, they are wired
to the existing conservation checks. Baseline comparison of the validation
variables should be exercised through the standard Polaris validation path once a
baseline is available.

Two classes of test landed that this section did not anticipate, both guarding
against a failure that is silent by construction. An option in the neutral
`ocean:` block with no entry in `mpaso_to_omega.yaml` only warns, so a check
that every neutral option in `forward.yaml`, in `forcing.yaml` and in the
horizontal-mixing bucket has an Omega counterpart is what keeps the two models
from quietly running different physics. And the statistics filename moves for
Omega but not for MPAS-Ocean, and a name that is not found reads as a stage that
wrote no statistics, so tests pin the filename each model actually writes, that
it follows the statistics interval for Omega, and that Omega's statistics are
snapshots rather than reductions.

### Testing and Validation: Physics and mixing options vary with the mesh

Date last modified: 2026/07/21

Contributors: Xylar Asay-Davis, Claude

Unit tests should confirm that `ForwardStage.from_config` reads the new options,
that a blank coefficient turns its term off while a value turns it on, and that
the neutral and MPAS-Ocean-only buckets contain the options they are supposed to.
Because the coefficients are what keep a run stable, a test should also confirm
that each per-mesh config produces the expected values, and that the three
qualitatively identical 240 km meshes agree with one another so they cannot drift
apart unnoticed.

The end-to-end check is that a short forward run on each mesh completes without
producing NaNs, which is the failure mode these options exist to prevent.
