(dev-ocean-manufactured_solution)=

# manufactured_solution

The manufactured solution test in `polaris.ocean.tasks.manufactured_solution`
uses the Method of Manufactured Solutions (see 
{ref}`ocean-manufactured-solution`) at 4 resolutions (200, 100, 50, and 25 km).

The {py:class}`polaris.ocean.tasks.manufactured_solution.ManufacturedSolution`
test performs a 10-hour run. 

## framework

The config options for the `manufactured_solution` test are described in 
{ref}`ocean-manufactured-solution` in the User's Guide.

Additionally, the test uses a `forward.yaml` file with
a few common model config options related to run duration and default 
horizontal  and vertical momentum and tracer diffusion, as well as defining 
`mesh`, `input`, `restart`, and `output` streams.

### exact_solution

The class {py:class}`polaris.ocean.tasks.manufactured_solution.exact_solution.ExactSolution`
defines a class for storing attributes and methods relevant to computing the
exact manufactured solution.  The constructor obtains the parameters from the
config file. The
{py:meth}`polaris.ocean.tasks.manufactured_solution.exact_solution.ExactSolution.ssh()`
method computes the SSH field.  The
{py:meth}`polaris.ocean.tasks.manufactured_solution.exact_solution.ExactSolution.normal_velocity()`
method computes the `normalVelocity` field.

### init

The class {py:class}`polaris.ocean.tasks.manufactured_solution.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  A vertical grid is generated
with 1 layer.  Finally, the initial layerThickness field is computed from the
exact solution for the SSH field and the initial velocity is also assigned to
the exact solution. The tracer and coriolis fields are uniform in space.

### forward

The class {py:class}`polaris.ocean.tasks.manufactured_solution.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step.  Namelist and streams files are updated in
{py:meth}`polaris.ocean.tasks.manufactured_solution.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.ocean.tasks.manufactured_solution.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris tasks
have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean 
model is run.  Finally, validation of `temperature`, `layerThickness` and 
`normalVelocity` are performed against a baseline if one is provided when 
calling {ref}`dev-polaris-setup`.

### analysis

The class {py:class}`polaris.ocean.tasks.manufactured_solution.analysis.Analysis`
defines a step for computing the root mean-square-error from the final
simulated field and the exact solution. It uses the config options to determine
whether the convergence rate falls within acceptable bounds.

### viz

The class {py:class}`polaris.ocean.tasks.manufactured_solution.viz.Viz`
defines a step for visualization. It produces two plots: the convergence of the
RMSE with resolution and a plan-view of the simulated, exact, and (simulated -
exact) SSH fields.

