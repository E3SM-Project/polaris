(dev-ocean-barotropic-channel)=

# barotropic_channel

The barotropic channel task group is currently comprised of one `default` task for quick
testing of lateral boundary conditions.

## framework

The shared config options for `barotropic_channel` tests  are described in
{ref}`ocean-barotropic-channel` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, and Laplacian
viscosity, as well as defining `mesh`, `input`, `restart`, and `output`
streams.

### init

The class {py:class}`polaris.tasks.ocean.barotropic_channel.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  The bottom topography
is defined along with a vertical grid with 3 layers by default.  Next, the
ocean state is generated with spatially uniform properties. The forcing
stream is also generated with wind stress fields.

### forward

The class {py:class}`polaris.tasks.ocean.barotropic_channel.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.overflow.forward.Forward.dynamic_model_config()`.
The number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.barotropic_channel.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run.

### viz

The {py:class}`polaris.tasks.ocean.barotropic_channel.viz.Viz` plots the initial and
final velocity components, relative vorticity, and circulation at the bottommost
vertical layer.

(dev-ocean-overflow-default)=

## default

The {py:class}`polaris.tasks.ocean.barotropic_channel.default.Default`
test runs the `init` step, a short `forward` step, and the `viz` step.

