(dev-ocean-drying-slope)=

# drying_slope

The drying slope tests in `polaris.ocean.tasks.drying_slope` are
variants of the drying slope test case (see {ref}`ocean-drying-slope`).
Here, we describe the test cases and their shared framework.

(dev-ocean-drying-slope-framework)=

## framework

The shared config options for `drying_slope` tests  are described in
{ref}`ocean-drying-slope` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to tidal forcing and wetting and drying, as well as
defining `mesh`, `input`, `restart`, and `output` streams.

### init

The class {py:class}`polaris.ocean.tasks.drying_slope.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  The bathymetry is generated
with a linearly sloping bed and ssh is set to be consistent with the initial
tidal forcing. A vertical grid is then generated, according to the
`vertical_grid` config options for each task.  Next, the initial
temperature field is computed with a horizontal anomaly.
The salinity field is uniform in the case of the `barotropic` test and has
vertical gradients in the case of the `baroclinic` test. The initial velocity
field is zeros.  Finally, the initial fields are plotted.
 
The same `init` step is shared by all tasks at a given resolution.

### forward

The class {py:class}`polaris.ocean.tasks.drying_slope.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step.  The time integration scheme, drag options, and tidal forcing
are set here. Namelist and streams files are updated in
{py:meth}`polaris.ocean.tasks.drying_slope.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.ocean.tasks.drying_slope.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run.

### validate

The class {py:class}`polaris.ocean.tasks.drying_slope.validate.Validate`
defines a step for validating outputs in two step directories against one
another.  This step ensures that `temperature`, `salinity`, `layerThickness`
and `normalVelocity` are identical in `output.nc` files in the two steps.

### viz

The class {py:class}`polaris.ocean.tasks.drying_slope.viz.Viz`
defines a step for visualizing horizontal fields and transects from the
forward step as well as the ssh forcing and reference solutions.

(dev-ocean-drying-slope-baroclinic)=

## baroclinic

The {py:class}`polaris.ocean.tasks.drying_slope.baroclinic.Baroclinic`
test runs a drying test at a linear tidal forcing rate with vertical
stratification.

(dev-ocean-drying-slope-barotropic)=

## barotropic

The {py:class}`polaris.ocean.tasks.drying_slope.barotropic.Barotropic`
test runs one sinusoidal cycle of tidal forcing.

(dev-ocean-drying-slope-decomp)=

## decomp

The {py:class}`polaris.ocean.tasks.drying_slope.decomp.Decomp`
performs a 3-time-step run once on 4 cores and once on 8 cores. The
`validate` step ensures that the two runs produce identical results.

(dev-ocean-drying-slope-convergence)=

## convergence

The {py:class}`polaris.ocean.tasks.drying_slope.convergence.Convergence`
tests the convergence of the barotropic test with resolution and time step
against a reference solution.

The `analysis` step defined by
{py:class}`polaris.ocean.tasks.drying_slope.convergence.analysis.Analysis`
produces a figure of the RMSE as a function of resolution.
