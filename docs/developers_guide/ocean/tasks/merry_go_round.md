(dev-ocean-merry-go-round)=

# merry-go-round

The merry-go-round task group is currently comprised of one `default` task for
quick testing and three convergence tests testing the convergence in space,
time, and both space and time.

## framework

The shared config options for `merry_go_round` tests  are described in
{ref}`ocean-merry-go-round` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, and which
tendencies terms are active, as well as defining `mesh`, `input`, `restart`,
and `output` streams.

### init

The class {py:class}`polaris.tasks.ocean.merry_go_round.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction. The uniform bottom depth and
requested number of vertical layer (default of 50) are used to define a
vertical coordinate. Next, the ocean state is generated following the
initial condition description from {ref}`ocean-merry-go-round` in the User's
Guide.

### forward

The class {py:class}`polaris.tasks.ocean.merry_go_round.forward.Forward`
defines a step for running the ocean model from the initial condition produced
in the `init` step. The time step is determined algorithmically based on
config options (i.e. `dt_per_km`) and the type of refinement requested. The
number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.merry_go_round.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run. The duration is set by `run_duration` in the config section
corresponding to the task (`merry_go_round`). Finally, validation of
`normalVelocity`, `tracer1`, `tracer2`, and `tracer3` in the `output.nc`
file are performed against a baseline if one is provided when
calling {ref}`dev-polaris-setup`.

(dev-ocean-merry-go-round)=

## default

The {py:class}`polaris.tasks.ocean.merry_go_round.default.Default`
test runs the `init` step, the `forward` step, and a custom `viz` step.

### viz

The {py:class}`polaris.tasks.ocean.merry_go_round.default.viz.Viz` plots
transects of the horizontal velocity, vertical velocity, simulated tracer
concentration, and error in simulated tracer concentration at the end of the
forward run. This more detailed plotting step is only available for the
default test case.

(dev-ocean-merry-go-analysis)=

## convergence tasks

### analysis

The class {py:class}`polaris.tasks.ocean.merry_go_round.analysis.Analysis`
descends from {py:class}`polaris.ocean.convergence.analysis.ConvergenceAnalysis`
a step for computing the error from the final simulated field
and the exact solution. It uses the config options to determine whether the
convergence rate falls within acceptable bounds.

### viz

The class {py:class}`polaris.tasks.ocean.merry_go_round.viz.Viz`
defines a step for visualization. It produces transects of the simulated,
exact, and (simulated - exact) `tracer1` fields for each resolution.
