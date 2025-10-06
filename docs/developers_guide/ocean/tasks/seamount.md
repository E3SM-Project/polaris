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
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the x and y directions.  The bottom topography
is defined along with a vertical grid with 60 layers by default.  Next, the
ocean state is generated with cold water on the continental shelf.

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
validation of `layerThickness`, `temperature` and `normalVelocity` in the
`output.nc` file are performed against a baseline if one is provided when
calling {ref}`dev-polaris-setup`.

### viz

The {py:class}`polaris.tasks.ocean.seamount.viz.Viz` plots the initial and
final temperature along a transect perpendicular to the continental slope.

(dev-ocean-seamount-default)=

## default

The {py:class}`polaris.tasks.ocean.seamount.default.Default`
test runs the `init` step, a short `forward` step, and the `viz` step.

