(dev-ocean-barotropic-gyre)=

# barotropic_gyre

The barotropic_gyre task group is currently comprised of one `default` task.

## framework

The shared config options for `barotropic_gyre` tests  are described in
{ref}`ocean-barotropic-` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, and Laplacian
viscosity, as well as defining `mesh`, `input`, `restart`, and `output`
streams.

### init

The class {py:class}`polaris.ocean.tasks.barotropic_gyre.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the x and y directions.  A vertical grid is
generated, with 1 layer by default.  Next, the wind stress forcing field is
generated.

### forward

The class {py:class}`polaris.ocean.tasks.barotropic_gyre.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.ocean.tasks.barotropic_gyre.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.ocean.tasks.barotropic_gyre.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris 
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean 
model is run. If `run_time_steps` is provided then this determines the run
duration, otherwise the duration is 3 years. Finally, validation of
`layerThickness` and `normalVelocity` in the `output.nc` file are performed 
against a baseline if one is provided when calling {ref}`dev-polaris-setup`.

### analysis

The {py:class}`polaris.ocean.tasks.barotropic_gyre.analysis.Analysis`
computes the L2 error norm at the final time step of the simulation against
the analytical solution for the linearized dynamics. This step also produces a
figure with the model solution, the analytical solution, and the difference
between the two.

(dev-ocean-baroclinic-channel-default)=

## default

The {py:class}`polaris.ocean.tasks.baroclinic_channel.default.Default`
test performs a test of the linearized dynamics. 
