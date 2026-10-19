(dev-ocean-mixed-layer-eddies)=

# mixed_layer_eddies

The `mixed_layer_eddies` tasks validate the submesoscale eddy
parameterization against an eddy-resolving run of a spinning-down
mixed-layer front.  The design is in the
[mixed-layer eddies design document](../../../design_docs/mixed_layer_eddies.md).

## framework

The shared config options are described in {ref}`ocean-mixed-layer-eddies`
in the User's Guide.  All tasks share one config file and the steps below,
which live in a directory for each resolution
(`ocean/planar/mixed_layer_eddies/<res>/`).  Each task links to the shared
steps it uses.

### init

The class {py:class}`polaris.tasks.ocean.mixed_layer_eddies.init.Init`
builds a doubly periodic planar hex mesh and initializes the p-star
coordinate with
{py:meth}`polaris.ocean.vertical.pstar_init.PStarInitStep.run_pstar_init()`.
Its `init_tracers()` evaluates the salinity profile at the geometric depths
the column's own density implies, refining them a few times within each
outer iteration.  The ITP77 profile is the packaged file `itp77.csv`.

### forward

The class {py:class}`polaris.tasks.ocean.mixed_layer_eddies.forward.Forward`
runs one segment of a run with one setting of the parameterization.  The
segment is `full` (the coarse runs), `spinup` (the resolved run to day 5),
`eddies` (days 5–7, with 3-hourly output) or `extended` (days 7–15).  Each
resolved segment after the first continues from the restart the one before
writes at its end, in a shared `restarts` directory beside the steps.  The
split exists because MPAS-Ocean streams cannot limit output to a time
window, and Polaris builds a task's steps before it knows the model.  The
restart alarms are anchored at each segment's start time, so a segment of
any length writes its restart at its end.  The parameterization's options are set only
when it is on; when it is off, each model's default (off) applies.

### diagnostics

The module `polaris.tasks.ocean.mixed_layer_eddies.diagnostics` computes the
eddy overturning, the parameterization's formula, potential energy and
mixed-layer stratification from output read with MPAS-Ocean names.
Overturning is computed across lines of constant y between rows of cells
with {ref}`dev-ocean-overturning`.  Transports use each model's flux
thickness: Omega's pseudo-thickness and MPAS-Ocean's layer thickness.

## resolved

The {py:class}`polaris.tasks.ocean.mixed_layer_eddies.resolved.Resolved` task
links the 500 m `init`, `spinup`, `eddies` and `extended` steps and adds
{py:class}`polaris.tasks.ocean.mixed_layer_eddies.resolved.analysis.Analysis`,
which diagnoses and normalizes the eddy overturning and checks $|\Psi^+|$.

## coarse

The {py:class}`polaris.tasks.ocean.mixed_layer_eddies.coarse.Coarse` task
links the `init`, `forward_off` and `forward_on` steps at each coarse
resolution and adds
{py:class}`polaris.tasks.ocean.mixed_layer_eddies.coarse.verify.Verify`,
which checks the parameterized stream function against its formula.

## comparison

The {py:class}`polaris.tasks.ocean.mixed_layer_eddies.comparison.Comparison`
task links every shared step and adds
{py:class}`polaris.tasks.ocean.mixed_layer_eddies.comparison.analysis.Analysis`,
which reports potential-energy release after the Rossby adjustment
relative to the resolved run and plots the runs side by side.  It has no
pass/fail check.
