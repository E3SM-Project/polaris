(dev-ocean-galewsky-jet)=

# galewsky_jet

The {py:class}`polaris.tasks.ocean.galewsky_jet.GalewskyJet` tasks run the
barotropically unstable jet of Galewsky et al. (2004) in three stages:
`steady_state`, `adjustment` and `unstable`.  Each stage is a task on
icosahedral or quasi-uniform meshes at a sequence of resolutions.  The
User's Guide page, {ref}`ocean-galewsky-jet`, describes the test and its
config options.

## framework

The three tasks for one mesh type share a config file, `galewsky_jet.cfg`.
Options for a single task are in its `[galewsky_jet_<task>]` section, so
the forward steps of different tasks can share a config file while running
for different durations with different viscosities.

The tasks also use a `forward.yaml` file with the model config options for
both models, including the run duration, output interval and ∇² viscosity,
which are filled in from the task's config section.

### initial_state

The module `polaris.tasks.ocean.galewsky_jet.initial_state` holds
vectorized functions for the jet
({py:func}`~polaris.tasks.ocean.galewsky_jet.initial_state.jet_velocity`),
its balanced height
({py:func}`~polaris.tasks.ocean.galewsky_jet.initial_state.balanced_height`),
its streamfunction
({py:func}`~polaris.tasks.ocean.galewsky_jet.initial_state.streamfunction`)
and the height perturbation
({py:func}`~polaris.tasks.ocean.galewsky_jet.initial_state.height_perturbation`).
{py:func}`~polaris.tasks.ocean.galewsky_jet.initial_state.normal_velocity_from_streamfunction`
differences a streamfunction at vertices along each edge, taking the sign
from the geometry of the edge rather than from the order of its vertices.

### diagnostics

The module `polaris.tasks.ocean.galewsky_jet.diagnostics` computes
relative vorticity at vertices and divergence at cells from the normal
velocity, with the same operators for both models.  It also has the global
l2 norm of GSP04 eq. 6 and a helper that draws contours of a field at cells
or vertices on a longitude–latitude rectangle by triangulation, without
remapping.

### base_mesh

The tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.tasks.ocean.galewsky_jet.init.Init` defines a
step for the initial state at one resolution, with or without the height
perturbation.  `steady_state` uses the shared steps in
`init/balanced/<mesh>`, while `adjustment` and `unstable` share the steps
in `init/perturbed/<mesh>`.

### forward

The class {py:class}`polaris.tasks.ocean.galewsky_jet.forward.Forward`
descends from
{py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`.
It reads the run duration, output interval and viscosity from its task's
config section before the parent class fills in `forward.yaml`.  It turns
off MPAS-Ocean's scaling of viscosity with cell width; Omega's is off by
default in {py:class}`polaris.ocean.model.OceanModelStep`.

### analysis

In `steady_state`, the class
{py:class}`polaris.tasks.ocean.galewsky_jet.steady_state.SteadyStateAnalysis`
descends from
{py:class}`polaris.ocean.convergence.analysis.ConvergenceAnalysis`.  Its
exact solution is the balanced initial state, computed from the mesh.

In `adjustment` and `unstable`, the classes
{py:class}`polaris.tasks.ocean.galewsky_jet.comparison.AdjustmentAnalysis`
and {py:class}`polaris.tasks.ocean.galewsky_jet.comparison.UnstableAnalysis`
descend from
{py:class}`polaris.tasks.ocean.galewsky_jet.comparison.ComparisonAnalysis`.
They plot all resolutions in the style of the paper's figures and tabulate
the quantities in GSP04 Table 1.

### viz

The class
{py:class}`polaris.tasks.ocean.galewsky_jet.steady_state.SteadyStateViz`
plots the relative vorticity at the end of each `steady_state` run, and its
change from the initial state, with
{py:func}`polaris.viz.plot_global_mpas_field`.  See
{ref}`dev-visualization-global` for more details.
