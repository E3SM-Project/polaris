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
straightforward to build on top of it later, but neither is implemented here.

A forward run must be able to obtain its model inputs (horizontal mesh, vertical
coordinate, initial state, and graph) from either of two sources: a file staged
in the Polaris input-file database and referenced by name, or the outputs of the
upstream `realistic_global/init` steps. It must express the per-run controls —
run duration, output and restart cadence, time step, and damping — in a
model-agnostic form and translate them, in a single place, to the configuration
options of the configured model. It must also write restart files, so that a
sequence of forward runs can be chained.

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

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

A forward run shall be able to obtain the model inputs it consumes (horizontal
mesh, vertical coordinate for Omega, initial state, and, for MPAS-Ocean, a graph
partition file) from either of two sources:

1. A file staged in the Polaris input-file database and referenced by name.
2. The outputs of the upstream `realistic_global/init` steps for the same mesh
   and configured model.

The choice of source shall be a property of how the task is assembled, not a
branch inside the forward step. Adding a third source in the future shall not
require modifying the forward step or the run-settings logic.

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
   `mesh`, `vertical coordinate`, `initial state`, and `graph` files from the
   initialization step's work directory. This is the source exercised by the
   first runnable task, since those outputs already exist in the same run.
2. A source backed by the Polaris input-file database, which constructs the input
   filename from the mesh, the configured model, and the equation of state, and
   registers it as a database input.

Because the required filenames and the model-specific handling of the vertical
coordinate and graph depend on the configured model, the source applies its input
files when the model is known (during step setup) rather than at construction
time.

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

Date last modified: 2026/07/03

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
from the mesh input file when it exists, and otherwise a configured
`approx_cell_count`; the base class turns this into `ntasks`/`min_tasks` using the
existing `goal_cells_per_core`/`max_cells_per_core` options.

The runnable task is `RealisticGlobalForward`, added once per supported mesh by a
factory `add_realistic_global_forward_tasks`, following the structure of the init
factory in `polaris/tasks/ocean/realistic_global/init/tasks.py`. Its work
directory is mesh-first, `spherical/realistic_global/{mesh_name}/forward`,
matching the init layout. The factory is registered from
`polaris/tasks/ocean/realistic_global/__init__.py`.

### Implementation: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/07/03

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
`add_init_input_file(database=..., target=...)`. This source is implemented and
unit-tested but is not wired into a registered task until the corresponding
initial-condition files are staged in the database; the exact handling of the
MPAS-Ocean graph for this source (building it from the mesh versus downloading a
prebuilt graph) is finalized at that time.

### Implementation: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The settings structure is a small dataclass, `ForwardStage`, in
`forward/stage.py`, with a class method that builds one from a
`[realistic_global_forward]` config section. Its fields cover the run duration,
output interval, restart interval, time integrator, optional explicit `dt`/`btr_dt`,
`dt_per_km`/`btr_dt_per_km`, a damping (Rayleigh) coefficient, and the restart-in
fields (`do_restart`, `start_time`, `restart_in`). Durations are duration strings
of the form `DDDD_HH:MM:SS`, matching the schedule format in
[global_ocean_dynamic_adjustment.md](global_ocean_dynamic_adjustment.md).

The mapping onto model configuration happens only in the forward step's
`dynamic_model_config`, which renders `forward/forward.yaml` with template
replacements derived from the stage. Durations are formatted with
`polaris.ocean.model.get_time_interval_string`; where the time step is not given
explicitly it is computed as the per-kilometer value times the mesh minimum
resolution. The time-integrator name is mapped to Omega where needed, exactly as
`ConvergenceForward` does. The template's model-neutral `ocean:` block is
auto-translated to Omega through the existing `mpaso_to_omega.yaml` map, while the
barotropic time step, Rayleigh damping, and restart controls appear under the
`mpas-ocean:` section (with Omega equivalents in the `Omega:` section left as a
documented future refinement).

```python
def dynamic_model_config(self, at_setup):
    super().dynamic_model_config(at_setup=at_setup)
    replacements = self.stage.model_replacements(self.config, self.min_res)
    self.add_yaml_file(self.package, self.yaml_filename,
                       template_replacements=replacements)
```

### Implementation: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

`forward/forward.yaml` declares a restart stream whose interval is the stage's
restart interval, and the model-neutral time block carries the start time and
restart flag. The simple forward task leaves the restart-in fields unset, so it
starts from the initial condition and (by default) writes a single restart at the
end of the run. A future restart test constructs two `Forward` steps with
different durations and restart settings; a future dynamic-adjustment task builds
a list of `ForwardStage`s from a per-mesh YAML schedule and chains restarts, in
both cases reusing `Forward` and `InitialCondition` unchanged.

### Implementation: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

The output and restart streams are declared in `forward/forward.yaml`: an
MPAS-Ocean `output` stream and `restart` stream, and the corresponding Omega
`IOStreams` (`History` and `RestartWrite`). The `Forward` step registers its
output file through `add_output_file` with an optional `validate_vars` list
(defaulting to a small set such as `temperature`, `salinity`, `layerThickness`,
`normalVelocity`) and optional `check_properties`, reusing the baseline-comparison
and conservation checks already implemented in `OceanModelStep`.

Surface forcing (wind stress and restoring) is intentionally out of scope for the
first forward runs because the current `realistic_global/init` workflow does not
yet produce those fields; the first runs are a spin-down from the initial
condition. Forcing is a clean future extension via a forcing step and additional
streams in the template.

### Implementation: Physics and mixing options vary with the mesh

Date last modified: 2026/07/21

Contributors: Xylar Asay-Davis, Claude

`realistic_global_forward.cfg` gains the mixing and parameterization options:
`mom_del2`, `mom_del4`, `tracer_del2` and `tracer_del4` (blank meaning off),
`use_Leith_del2`, `hmix_scaling` (`none`, `ref_cell_width` or
`scale_with_mesh`) with `hmix_ref_cell_width`, `use_GM` with `GM_closure` and
`GM_constant_kappa`, `use_Redi`, and `use_frazil_ice_formation`. The defaults
match the shared baseline of the Compass `global_ocean` forward runs that this
framework replaces.

`ForwardStage` gains the corresponding fields and two methods beside the existing
`bottom_drag_options`: `horiz_mixing_options` returns the neutral del2/del4
options for momentum and tracers, and `mpaso_physics_options` returns the
MPAS-Ocean-only Leith, horizontal-mixing-scaling, Gent-McWilliams, Redi and
frazil options. `Forward.dynamic_model_config` adds the first with
`config_model='ocean'`, so `OceanModelStep.map_yaml_options` translates it for
Omega, and the second with `config_model='mpas-ocean'`.

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

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

A `polaris setup` smoke test on a coarse global mesh, run for both
`[ocean] model = mpas-ocean` and `omega`, should confirm that the forward work
directory contains the expected input symlinks and that the generated namelist
and streams (MPAS-Ocean) or `omega.yml` (Omega) contain the expected run
duration, cadence, time step, and time integrator, without running the model.
Where a model build is available, a short end-to-end run on a coarse mesh should
confirm that the output file and a restart file are written.

### Testing and Validation: Forward runs can start from a database initial condition or from the init workflow

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Unit tests should confirm that `StepInitialCondition` registers the four inputs
and sets the graph target from the init step's work directory, and that
`DatabaseInitialCondition` constructs the expected database filename and target
for each configured model.

### Testing and Validation: Per-run settings are described in a common, model-agnostic form

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Unit tests should cover building a `ForwardStage` from config and its mapping onto
template replacements: correct duration strings, the time-integrator translation
for Omega, the derivation of the time step from `dt_per_km` and the mesh minimum
resolution versus an explicit override, and the presence of the barotropic time
step and Rayleigh damping only for MPAS-Ocean.

### Testing and Validation: The framework composes into restart and dynamic-adjustment workflows

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Tests in this phase should confirm that the restart stream is emitted with the
configured interval and that the restart-in settings render the expected restart
flag and start time. Full restart-test and dynamic-adjustment regression tests
belong to the later work that builds those workflows on this framework.

### Testing and Validation: Forward steps produce inspectable outputs and support basic validation

Date last modified: 2026/07/03

Contributors: Xylar Asay-Davis, Claude

Tests should confirm that the output file is registered with the expected
validation variables and that, when property checks are requested, they are wired
to the existing conservation checks. Baseline comparison of the validation
variables should be exercised through the standard Polaris validation path once a
baseline is available.

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
