(dev-ocean-seamount)=

# seamount

The seamount task group is currently comprised of one `default` task.
## framework

The shared config options for `seamount` tests  are described in
{ref}`ocean-seamount` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, and Laplacian
viscosity, as well as defining `mesh`, `input`, `restart`, and `output`
streams.

### init

The class {py:class}`polaris.tasks.ocean.seamount.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`. The bottom topography
is defined along with a vertical grid with 10 layers by default.  Next, the
ocean state is generated with a vertical temperature stratification.

### forward

The class {py:class}`polaris.tasks.ocean.seamount.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.seamount.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.seamount.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run. The duration is set by `run_duration` in the config section
corresponding to the task (`seamount_default`). Finally,
the variables `kineticEnergyCell` and `normalVelocity` in the
`output.nc` file are visualized in the `viz` directory.


### viz

The {py:class}`polaris.tasks.ocean.seamount.viz.Viz` plots the maximum velocity
as a function of time; a horizontal cross-section of the normal velocity;
and a vertical cross-section of the kinetic energy. The vertical cross-section
is also convenient to see the vertical coordinate (sigma versus z-level) and
the bottom topography.


(dev-ocean-seamount-default)=

## default

The {py:class}`polaris.tasks.ocean.seamount.default.Default`
test runs the `init` step, a short `forward` step, and the `viz` step.

