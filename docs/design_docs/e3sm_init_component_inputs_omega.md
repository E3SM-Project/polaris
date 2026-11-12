# E3SM Init Component Inputs for Omega

date: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

## Summary

The `e3sm/init` component-inputs tasks stage what an E3SM run needs for a
unified mesh, as described in the
[component-inputs design](e3sm_init_component_inputs.md). They support
MPAS-Ocean and MPAS-Seaice, and stop with a not-implemented error when the
ocean model is Omega. This design adds Omega, on the assumption that Omega is
an E3SM component that reads its inputs from `inputdata/ocn/omega/<grid>/`.

Omega's first unified-mesh inputs in E3SM were made by converting the
MPAS-Ocean initial conditions with `utils/omega/convert_mpaso_ic_to_omega.py`
([E3SM-Project/E3SM#9141](https://github.com/E3SM-Project/E3SM/pull/9141)).
That gives Omega a state adjusted by MPAS-Ocean, not by Omega. Here, Omega
gets its own dynamic adjustment, started from the same interpolated
hydrography as MPAS-Ocean's.

The main challenge is not the Omega files themselves. Polaris assumes one ocean
model per work directory: the model is chosen at setup, and every step has the
same directory whichever model it runs. Producing both models' inputs for a mesh
in one work directory therefore needs model-dependent steps to stop sharing
directories, while the hours of mesh, topography and hydrography work before
them stay shared.

Two terms are used throughout:

- A **model-dependent step** is one whose outputs, or the outputs of a step it
  depends on, are written for one ocean model.
- A **model-neutral step** is any other step. Graph partitioning is
  model-neutral even though only MPAS-Ocean reads its output.

This design is successful if one work directory can hold a unified mesh's
MPAS-Ocean and Omega inputs, each set up in its own `polaris setup`, with the
model-neutral steps run once. A second test is to produce Omega inputs for the
`u04` and `u05` meshes from model-neutral outputs that already exist, without
regenerating the meshes those outputs describe.

## Requirements

### Requirement: Polaris stages Omega's E3SM inputs for a unified mesh

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Polaris shall stage an Omega initial condition for each unified mesh, in the
directory where E3SM's Omega looks for the mesh's ocean grid.

The state shall be the one at the end of an Omega dynamic adjustment on the same
mesh, started from the same interpolated hydrography as the MPAS-Ocean initial
condition.

### Requirement: Omega's inputs hold what Omega reads, and nothing only MPAS-Ocean reads

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

The staged Omega inputs shall hold everything E3SM's Omega reads at startup,
including the shortwave extinction coefficients that penetrating shortwave
needs.

Products that only MPAS-Ocean reads, such as graph partitions, shall not be
staged for Omega.

### Requirement: Both models' inputs for a mesh can be produced in one work directory

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Polaris shall be able to produce MPAS-Ocean and Omega inputs for a mesh in one
work directory, with one setup per model.

A setup for one model shall not overwrite or change any step, config file or
task directory that the other model's steps use.

Model-neutral steps shall run once and be used by both models.

### Requirement: Setting up again does not rename staged products

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Setting up a work directory again, for either model, shall not change the names
of the products it stages.

Each model's initial condition shall carry the date it was made, independent of
the date on the mesh's model-neutral products.

## Algorithm Design

### Algorithm Design: Polaris stages Omega's E3SM inputs for a unified mesh

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

The Omega chain mirrors MPAS-Ocean's. The realistic-global `initial_state`
step writes Omega's mesh, vertical coordinate and initial state from the shared
`pstar_init` output. The dynamic adjustment then runs Omega on the same schedule
as MPAS-Ocean. A component-inputs step builds the initial condition from the
final stage's restart.

Omega's restart holds only the prognostic state, not the mesh or the vertical
coordinate. The initial condition is therefore a merge of four sources:

1. The horizontal mesh from `initial_state`'s `mesh.nc`.
2. The vertical coordinate from its `vert_coord.nc`.
3. The prognostic fields of Omega's `State` and `Base` groups, from the final
   stage's restart. The restart's time is dropped, as for MPAS-Ocean.
4. The shortwave extinction coefficients, remapped to the mesh.

Every source but the last is a file Polaris' own Omega runs already read through
the same stream. The diagnostic fields in `initial_state`'s `init.nc`, such as
`SshCell` and `Density`, are left out, since they describe the state before
the adjustment.

The extinction coefficients come from the realistic-global init steps, which
remap the dataset the converter uses to the mesh. Those steps bring the
converter's solar forcing to the realistic-global workflow, so Polaris' own
Omega runs can use penetrating shortwave as E3SM's do. They are separate work
that the Omega initial condition depends on ([D13](#decisions)).

### Algorithm Design: Omega's inputs hold what Omega reads, and nothing only MPAS-Ocean reads

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Each product is included in a task according to which models read it. Where its
step lives is a separate question, answered by the definitions in the Summary.

| Product | Its step is | Staged for |
| --- | --- | --- |
| base mesh, culled land mesh, SCRIP files | model-neutral | both |
| sea-ice initial condition and partitions | model-neutral | both |
| ocean graph partitions | model-neutral | MPAS-Ocean |
| MOC basin masks | model-neutral | MPAS-Ocean |
| shortwave extinction coefficients | model-neutral | Omega |
| culled ocean mesh with vertical coordinate | MPAS-Ocean's | MPAS-Ocean |
| ocean initial condition | per model | its model |

Omega partitions its mesh at run time, so it needs no graph partitions. Its MOC
analysis does not yet read region masks, so it gets none until it does
([D5](#decisions)).

### Algorithm Design: Both models' inputs for a mesh can be produced in one work directory

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

A model-dependent step lives under a directory named for its model, `mpas-ocean`
or `omega`, inside its family's directory. A model-neutral step keeps the one
directory it has now ([D1](#decisions)).

Three things a setup writes are shared today and must be separated:

1. **Step directories.** Separated by the model directories.
2. **Config files.** A step reads its family's shared config file at run time,
   and every setup rewrites that file with its own `[ocean] model` and build
   paths. Each model directory therefore holds its own copy of the family's
   config file ([D4](#decisions)). Model-neutral steps read no model options, so
   their config file can be rewritten safely.
3. **Task directories.** A task directory holds the task's pickle, job script,
   step links and logs. Tasks that include model-dependent steps are therefore
   either per model or set up again to switch models ([D2](#decisions),
   [D3](#decisions)).

The model is not known when tasks are built, only once the ocean component has
been configured at setup. A model-agnostic task builds the MPAS-Ocean chain
when it is constructed. Its `configure()` replaces the model-dependent steps with
the configured model's when that is Omega. The model-neutral steps are the same
instances either way, so they are shared between the two chains.

A setup into a work directory that already holds another model's steps also
rewrites the files at the work directory's root. A distinct suite name keeps the
pickle, job script and provenance apart ([D11](#decisions)).

### Algorithm Design: Setting up again does not rename staged products

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

There are two creation dates ([D8](#decisions)):

- The **mesh date**, on every product of a model-neutral step and on the culled
  ocean mesh.
- The **ocean date**, on one model's initial condition, one per model.

A date is taken from, in order: a user config that sets it; the work
directory's copy of the config file, if it records one; today's date. In a new
work directory set up for one model, both dates are today's, which is the
behavior before this design. A second model set up later in the same work
directory keeps the mesh date and gets a new ocean date.

## Implementation

### Implementation: Polaris stages Omega's E3SM inputs for a unified mesh

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

A new `OmegaInitialConditionStep` in `component_inputs/omega/ocean_initial_condition`
takes `mesh.nc` and `vert_coord.nc` from `init/omega/initial_state`, the
restart `ForwardStage.restart_files` names for Omega's final stage, and the
extinction coefficients. It depends on the final stage and on that stage's
check, as the MPAS-Ocean step does, so a failed check stops the restart from
being staged.

The step is not an `OceanIOStep`. A component-inputs config has no `[ocean]`
section, which is why the MOC-mask step could not subclass the ocean
feature-mask step. Its sources are already in Omega's names.

The extinction coefficients, `ExtinctionCoeffRedCell` and
`ExtinctionCoeffBlueCell`, are read from the realistic-global init step that
writes them. Their remapping depends only on the mesh, so that step is expected
to be model-neutral and to sit beside `remap_jra55`. If it writes them for
Omega only, it is model-dependent and goes under `init/omega/` instead. The
initial-condition step reads its output either way.

`polaris.e3sm.init.inputdata` gains `omega_dir(grid)` and
`omega_initial_condition_path(grid, ocean_date)`, which give
`inputdata/ocn/omega/<grid>/omega.<grid>.<date>.nc`. The Omega assembly
stages:

1. The model-neutral products every task stages, at the mesh date.
2. `ocn/omega/<grid>/omega.<grid>.<ocean date>.nc`.
3. The two ocean SCRIP files again under `ocn/omega/<grid>/`, at the mesh date
   ([D10](#decisions)).

E3SM's `input_files.yaml` lists the initial condition once, for the
`HorzMeshIn`, `InitialVertCoord`, `InitialState` and `ShortwaveExtinctionIn`
streams. Pointing it at these files is a follow-on change to E3SM, which
replaces the converted files.

### Implementation: Omega's inputs hold what Omega reads, and nothing only MPAS-Ocean reads

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

`get_component_inputs_steps()` takes the ocean model and a target. Its product
table, `TARGET_PRODUCTS` in `assemble.py`, becomes a table per model:

- `mpas-ocean`: `ocean_mesh`, `ocean_initial_condition`,
  `ocean_graph_partition`, `ocean_moc_masks`.
- `omega`: `ocean_initial_condition`, which carries the extinction
  coefficients.

The sea-ice products and the shared products are unchanged.
`models.check_ocean_model()` no longer rejects Omega. It now checks that the
ocean component's model is the one the task was built for.

### Implementation: Both models' inputs for a mesh can be produced in one work directory

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

`get_realistic_init_steps()` and `get_realistic_dynamic_adjustment_steps()`
take a `model` argument. They place the model-dependent steps and their copy of
the config file under the model's directory. The resulting layout, for one mesh:

```
ocean/spherical/realistic_global/<mesh>/
  init/                           init task; model-neutral steps
    cull_topo/  woa23_map/  remap_woa23/  jra55_map/  remap_jra55/
    pstar_init/  <shortwave-extinction steps>/  init.cfg
    mpas-ocean/  init.cfg  initial_state/  forcing/  viz/
    omega/       init.cfg  initial_state/  forcing/  viz/
  dynamic_adjustment/             dynamic-adjustment task
    mpas-ocean/  dynamic_adjustment.cfg  <stages>/  <stage>_check/
                 summary/  viz/  restarts/
    omega/       (the same)
e3sm/init/<mesh>/component_inputs/
  component_inputs.cfg  base_mesh/  scrip/  seaice_*/  assemble/seaice/
  ocean_graph_partition/  moc_masks/
  mpas-ocean/  component_inputs.cfg  ocean_mesh/  ocean_initial_condition/
               assemble/{ocean,all}/
  omega/       component_inputs.cfg  ocean_initial_condition/
               assemble/{ocean,all}/
  tasks/seaice/  tasks/mpas-ocean/{ocean,all}/  tasks/omega/{ocean,all}/
```

The realistic-global tasks that consume these chains are `init`,
`dynamic_adjustment`, `forward` and `analysis_output`. They stay model-agnostic.
Each builds its chain for `mpas-ocean` at construction. In `configure()`, if the
ocean component's model is Omega, each removes the steps under `mpas-ocean/`
and adds the Omega chain. This extends the schedule rebuild the
dynamic-adjustment task already does in `configure()`. `Task.remove_step()`
drops a step from the component only when no task still uses it, so the
model-neutral steps survive.

The component-input tasks are built per model ([D3](#decisions)). Each passes
its model to the factories at construction and needs no swap. A task whose
model differs from the ocean component's raises an error at setup that names
both models.

The forward and analysis-output tasks' own steps keep their model-agnostic
directories ([D12](#decisions)). They consume the model-dependent init steps,
so they take part in the swap. The restart task starts from a cached initial
condition and is unaffected.

Work directories set up before this change are not migrated. Setting one up
again puts the model-dependent steps in new directories, where they will run
again.

The layout change is in the ocean component and lands in its own pull request
from `main`, before the Omega staging that depends on it. The
shortwave-extinction steps also land in the realistic-global workflow first.
Until they do, everything up to the Omega adjustment's final restart can be
built and run; only the initial-condition step waits.

### Implementation: Setting up again does not rename staged products

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

`[component_inputs]` gains `ocean_creation_date` beside `creation_date`. Both
are blank by default. The mesh date is filled in for the model-neutral config
file, and the ocean date for each model's copy.

`set_creation_date()` in `polaris.e3sm.init.inputdata` reads
`<base_work_dir>/<config.filepath>` before falling back to today's date, so a
date already recorded in the work directory survives a new setup. The option
name becomes an argument, so MISOMIP's staging can use the same rule.

## Testing

### Testing and Validation: Polaris stages Omega's E3SM inputs for a unified mesh

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Unit tests build the initial condition from small stand-in files. They check
that every variable in the four sources arrives, that a variable in both the
initial state and the restart takes the restart's value, and that the
restart's time is gone.

Omega inputs for `u04` and `u05` are produced from the model-neutral outputs of
the work directories that made their MPAS-Ocean inputs. The new work directories
link to those outputs and never write into the originals. Every Omega stage
check must pass. The staged mesh must be identical to the mesh in the converted
files on the inputdata server, and the extinction coefficients close to theirs.

An E3SM case on each mesh must start from the staged file and run for a few
days.

### Testing and Validation: Omega's inputs hold what Omega reads, and nothing only MPAS-Ocean reads

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Unit tests check each model's step list: no graph partition, MOC-mask or
`ocean_mesh` step in an Omega task, and no shortwave-extinction step in an
MPAS-Ocean task.

The assembly test compares the whole staged Omega tree with the expected set,
as the MPAS-Ocean test does.

### Testing and Validation: Both models' inputs for a mesh can be produced in one work directory

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Unit tests check that the factories put model-dependent steps under the model's
directory and leave the model-neutral ones where they were. They also check
that both chains share the same model-neutral step instances, and that a
model-agnostic task set up for Omega keeps no step under `mpas-ocean/`.

On `u-oi240-lr240`, one work directory is set up and run for MPAS-Ocean, then
set up and run for Omega, then the MPAS-Ocean assembly is run again. Every file
under the MPAS-Ocean directories, and their config files, must be unchanged
after the Omega setup and run. The model-neutral steps must run once.

### Testing and Validation: Setting up again does not rename staged products

Date last modified: 2026/11/12

Contributors: Xylar Asay-Davis, Claude

Unit tests cover the three sources of a date and their order, including a work
directory whose recorded date differs from today's.

In the `u-oi240-lr240` test, the two trees must share the mesh date on every
model-neutral product.

## Decisions

### D1: Model directories for model-dependent steps only

Rejected alternatives:

- **A work directory per model.** It fails the one-work-directory requirement,
  and either runs the model-neutral steps twice or needs a way to link steps
  across work directories.
- **The model in every step's directory.** The model-neutral steps would run
  once per model, including the hours of mesh and topography work.
- **Directories resolved from the model at setup.** Steps build other steps'
  paths when they are constructed, such as the stage checks' `mesh_target`, so
  a directory that changes later would leave them pointing at the wrong place.

### D2: Model-agnostic ocean tasks swap their chain in `configure()`

The realistic-global tasks keep one name for both models, like every other
ocean task, and the suites refer to them that way. Registering them per model
would double the task list.

The cost is that a task directory reflects the most recent setup. Switching
models means setting up again, and nothing in a model directory changes when
that happens.

### D3: Component-input tasks are per model

An E3SM configuration is per model, like a compset, and these tasks produce the
files one configuration reads. Per-model tasks keep each model's task
directory, logs and results apart. Today's `tasks/ocean` and `tasks/all`
become `tasks/mpas-ocean/ocean` and `tasks/mpas-ocean/all`.

Keeping today's names and letting each setup choose the model was rejected. A
task directory would then reflect whichever model was set up last, as the
ocean tasks' do under [D2](#decisions).

The model in the task name can disagree with the ocean component's. Setup
raises an error rather than choosing one.

### D4: A config file per model directory

The model options written into a config file are what a step reads at run time.
A config file shared between models would hand one model's steps the other's
`[ocean] model` and build paths after the second setup.

### D5: Model-neutral steps that only one model needs stay model-neutral

The ocean graph partitions, MOC masks and extinction coefficients are computed
from the culled mesh and datasets alone. Where a step lives follows from its
inputs. Which tasks include it follows from what each model reads.

Omega gets MOC masks once its MOC analysis reads region masks. Nothing needs to
move then.

### D6: Build the initial condition from Omega's own adjustment

Converting the adjusted MPAS-Ocean state gives Omega a state balanced for
another model's physics and tracer conversion. The adjustment exists to remove
that kind of imbalance. Omega's adjustment passes its checks on every unified
mesh, so no reason remains to start from MPAS-Ocean.

### D7: One file per Omega initial condition

Every mesh in E3SM's `input_files.yaml` today has one file for all four
streams, and so does `mpaso.<grid>.<date>.nc` for MPAS-Ocean. Splitting the
extinction coefficients into a file of their own was considered. They change
only with the dataset, but a second file per mesh gains little.

The name, `omega.<grid>.<date>.nc`, follows MPAS-Ocean's and keeps the rule
that the last dotted field is the creation date. It leaves out the equation of
state, which is TEOS-10 for every initial condition Polaris builds. The
converted files' form, `omega.<grid>.<mesh date>.teos10.<date>.nc`, was
rejected: the mesh date already names the mesh's own files.

### D8: A mesh date and an ocean date

One date per work directory cannot work with two models. A product on the
inputdata server cannot change once uploaded, so a regenerated initial condition
needs a new name. With one date, that new name would also rename the
model-neutral products already uploaded. With a date per model and none for the
mesh, the two trees would stage the same model-neutral products under two names.

The culled ocean mesh takes the mesh date although an MPAS-Ocean step makes it,
because it describes the mesh.

### D9: No culled ocean mesh from an Omega-only work directory

The culled ocean mesh in the shared mesh directory is in MPAS format, with
MPAS-Ocean's vertical coordinate. It is made from MPAS-Ocean's initial state, so
an Omega task cannot make it without setting up an MPAS-Ocean step. Every
unified mesh headed for E3SM gets MPAS-Ocean inputs too, so the file exists.

This holds only while E3SM supports MPAS-Ocean. MPAS-Ocean is deprecated in
E3SM v4 and will be dropped in v5. These workflows will then need to produce
the culled ocean mesh, and the other model-neutral products that now come
through MPAS-Ocean, without it.

### D10: SCRIP copies beside Omega's products

The MPAS-Ocean tree stages the two ocean SCRIP files beside its products as well
as in the shared mesh directory, because developers look in both places. The
same holds for Omega's directory.

### D11: A suite name per model at the work directory's root

`polaris setup` names its pickle, job script and provenance file for the
suite, `custom` by default, so a second setup with the same name replaces the
first's. The User's Guide asks for a suite name per model.

Each job script loads the environment it was set up with, so the two setups
can use different compilers. Each model also builds into a default directory
of its own, so neither build overwrites the other.

### D12: Other realistic-global tasks keep model-agnostic step directories

The forward and analysis-output tasks test a model rather than produce
E3SM inputs, so they run in one work directory per model like the other ocean
tasks. Their own steps can move to model directories when that changes.

### D13: Shortwave extinction comes from the realistic-global workflow

Remapping the extinction dataset to the mesh could have been a component-inputs
step. It belongs with the realistic-global init steps instead, so that Polaris'
standalone Omega runs and the E3SM initial condition use the same coefficients.
The Omega initial condition then consumes an upstream product, like the rest of
component inputs.
