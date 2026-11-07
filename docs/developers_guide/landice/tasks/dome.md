(dev-landice-dome)=

# dome

The `dome` tasks in `polaris.tasks.landice.dome` evolve an ice dome on a flat
bed with MALI's shallow-ice and first-order velocity solvers (see
{ref}`landice-dome`).  `add_dome_tasks()` adds a `smoke_test`, `decomp` and
`restart` task for each solver.

(dev-landice-dome-framework)=

## framework

The tasks share a config file, `dome.cfg`, and the steps below.

### init

The class {py:class}`polaris.tasks.landice.dome.init.Init` is a step shared
by all the tasks.  It makes a planar hexagonal mesh, culls and converts it,
turns it into a MALI mesh with {py:func}`polaris.landice.mesh.make_mali_mesh()`
and adds the dome's thickness, a flat bed and zero surface mass balance.

### forward

The class {py:class}`polaris.tasks.landice.dome.forward.Forward` is a
{py:class}`polaris.landice.model.MaliModelStep` that runs MALI on the dome
mesh with a given velocity solver, from `namelist.landice` and
`streams.landice` in the package.  For the first-order solver, it uses the
package's `albany_input.yaml`.

### validate

The class {py:class}`polaris.tasks.landice.dome.validate.Validate` compares
the thickness and normal velocity in the output of two `forward` steps,
within given norms.

### viz

The class {py:class}`polaris.tasks.landice.dome.viz.Viz` plots the ice
thickness and surface speed at the end of a run.

(dev-landice-dome-smoke-test)=

## smoke_test

The class {py:class}`polaris.tasks.landice.dome.smoke_test.SmokeTest` runs
MALI on 4 cores, for 200 years with the shallow-ice solver and 2 years with
the first-order solver, and plots the results.

(dev-landice-dome-decomp)=

## decomp

The class {py:class}`polaris.tasks.landice.dome.decomp.Decomp` runs MALI on
1 and 4 cores and validates that the results are bit-for-bit with the
shallow-ice solver, and agree within Compass's norms with the first-order
solver.

(dev-landice-dome-restart)=

## restart

The class {py:class}`polaris.tasks.landice.dome.restart.Restart` runs MALI
for 2 years in `full_run`, and for 1 year in `restart_run` from the restart
file `full_run` writes after its first year.  Both runs write output only at
the end of year 2, using `streams.restart` in the package, and the outputs
must be bit-for-bit.  With the first-order solver on a machine and compiler
with GPUs, where Albany gives slightly different results each run, the
validate step uses the norms of `decomp` instead.
