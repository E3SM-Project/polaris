(dev-landice-mismip-plus)=

# mismip_plus

The `mismip_plus` tasks in `polaris.tasks.landice.mismip_plus` spin MALI up
to the MISMIP+ steady state and run the MISMIP+ experiments from it (see
{ref}`landice-mismip-plus`).  `add_mismip_plus_tasks()` adds a `spin_up`
task and a task for each experiment in `EXPERIMENTS`, in
`polaris.tasks.landice.mismip_plus.experiments`.

(dev-landice-mismip-plus-framework)=

## framework

What other components reuse is in `polaris.landice.mismip_plus`, which
imports nothing from `polaris.tasks`:

- `geometry`: the protocol's constants and the bed,
  {py:func}`polaris.landice.mismip_plus.geometry.bed_topography()`;
- `mesh`: the mesh, ported from Compass,
  {py:func}`polaris.landice.mismip_plus.mesh.make_mismip_plus_mesh()`;
- `diagnostics`: the ice volume, volume above flotation, grounded area and
  centerline grounding line of any dataset with MALI's thickness, bed and
  mesh variables,
  {py:func}`polaris.landice.mismip_plus.diagnostics.compute_diagnostics()`.

The tasks share a config file, `mismip_plus.cfg`, and the steps below.
{py:func}`polaris.tasks.landice.mismip_plus.steps.get_mismip_plus_steady_state_steps()`
returns the config and the `mesh`, `init`, `spin_up_run` and `spin_up`
steps, so tasks in other components can start from the cached steady state
with the same shared steps.

### mesh

The class {py:class}`polaris.tasks.mesh.planar.mismip_plus.MismipPlusMesh`
is a step of the `mesh` component, at `mesh/planar/mismip_plus/1km/mesh`,
which {py:func}`polaris.tasks.mesh.planar.mismip_plus.get_mismip_plus_mesh_steps()`
returns.  It writes the planar mesh, `planar_mesh.nc`, and the MALI mesh
made from it with {py:func}`polaris.landice.mesh.make_mali_mesh()`,
`mali_mesh.nc`, along with its graph file.  Its config file is
`mismip_plus_mesh.cfg`.

### init

The class {py:class}`polaris.tasks.landice.mismip_plus.init.Init` adds the
bed, a 100-m slab of ice, the accumulation, the friction coefficient and
effective pressure, the calving mask and the Dirichlet mask that makes the
walls free-slip to the MALI mesh.

### MismipPlusModelStep

The class {py:class}`polaris.tasks.landice.mismip_plus.model.MismipPlusModelStep`
is a {py:class}`polaris.landice.model.MaliModelStep` with the first-order
velocity solver, the package's `namelist.landice`, `streams.landice` and
`albany_input.yaml`, and the number of MPI tasks from config options.  It
sets MALI's rate factor from `flow_param_a`, and turns on MALI's global
statistics, which it writes to `globalStats.nc` every time step.  The Albany
input file does not set the rate factor, so Albany takes MALI's.

### run

The class {py:class}`polaris.tasks.landice.mismip_plus.spin_up.SpinUpRun`
runs MALI from the starting state for `run_years`.  In `runtime_setup()`,
it writes the starting state, `landice_grid.nc`, unless MALI has written a
restart, in which case it continues from the latest one.  MALI writes
`output.nc` every 50 years, adding to it when it continues, and a restart
every 250 years.  Its time steps land on both.

### spin_up

The class {py:class}`polaris.tasks.landice.mismip_plus.spin_up.SpinUp`
computes the diagnostics from `output.nc` in the `run` step's directory,
checks that the spin-up has converged and that the grounding line is within
10 km of 450 km on the centerline, and copies the final restart to
`steady_state.nc`, adding global attributes that describe it.  The step
has `default_cached = True`, so tasks other than `spin_up` read its outputs
from the cache.  Then the steps that make its inputs are left out of them.

### forward

The class {py:class}`polaris.tasks.landice.mismip_plus.forward.Forward`
runs an experiment, from the steady state or as a restart from the end of
the experiment it starts from.  It is named for its experiment, such as
`ice1r_forward`, since a task may include the step of the experiment it
starts from as well.  It copies the steady state to `landice_grid.nc` with
its time set to the experiment's start, since MALI reads its starting state
only at that time, and makes its own graph file from it, so it does not
depend on the mesh step.  MALI takes Ice2's melt rate as a heat flux, which
the step computes with the latent heat of a standalone MALI build.  It also
has MALI calve floating ice thinner than 10 m, the thickness below which
MALI's ice is not dynamic by default, and icebergs.

### cornford2020

The class {py:class}`polaris.tasks.landice.mismip_plus.cornford.Cornford2020`
downloads the supplement of Cornford et al. (2020) and writes a file for
each experiment with the time series of every entry, padded to a common
length, and the grounding line of MALI's 2017 entry.  An entry's grounding
line on the centerline is its most upstream point within 1 km of
$y = 40$ km.

### analysis

The class {py:class}`polaris.tasks.landice.mismip_plus.analysis.Analysis`
computes an experiment's diagnostics from its output and plots them, with
those of the experiment it starts from and with the entries of
Cornford et al. (2020).  It also plots MALI's global statistics from both
experiments with
{py:func}`polaris.tasks.landice.mismip_plus.plot.plot_global_stats()`.
{py:func}`polaris.tasks.landice.mismip_plus.output.read_output()` reads
MALI's output with its time in years, keeping the last record at each time,
since a continued run may write some times again.

### viz

The class {py:class}`polaris.tasks.landice.mismip_plus.spin_up.SpinUpViz`
plots the steady state, the diagnostics over the spin-up and MALI's global
statistics from the `run` step.

(dev-landice-mismip-plus-spin-up)=

## spin_up

The class {py:class}`polaris.tasks.landice.mismip_plus.spin_up.SpinUpTask`
includes the `mesh`, `init`, `run`, `spin_up` and `viz` steps, and adds the
`spin_up` step to its `free_running_steps`, so that it makes the steady
state rather than reading it from the cache.

(dev-landice-mismip-plus-experiments)=

## experiments

The class {py:class}`polaris.tasks.landice.mismip_plus.experiment.ExperimentTask`
includes the shared steps of the spin-up, the `forward` step of the
experiment it starts from, if any, its own `forward` step, the
`cornford2020` step and an `analysis` step.
