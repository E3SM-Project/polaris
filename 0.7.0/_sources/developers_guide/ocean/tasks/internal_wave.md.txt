(dev-ocean-internal-wave)=

# internal_wave

The internal wave tests in `polaris.tasks.ocean.internal_wave` are
variants of the Internal Wave test case (see
{ref}`ocean-internal-wave`) at 5km horizontal resolution.  Here,
we describe the 4 test cases and their shared framework.

(dev-ocean-internal-wave-framework)=

## framework

The shared config options for `internal_wave` tests  are described in
{ref}`ocean-internal-wave` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to run duration and default horizontal  and vertical
momentum and tracer diffusion, as well as defining `mesh`, `input`, `restart`,
and `output` streams.

### init

The class {py:class}`polaris.tasks.ocean.internal_wave.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  A vertical grid is generated,
with 20 layers of 50-m thickness each by default.  Next, the initial
temperature field is computed along with uniform salinity and zero initial
velocity.  Finally, if a baseline is available, the step ensures that of
`temperature`, `salinity` and `layerThickness` in the `initial_state.nc` file
identical to those same fields from the baseline run.

The same `init` step is shared by all tasks at a given resolution.

### forward

The class {py:class}`polaris.tasks.ocean.internal_wave.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step.  If `nu` is provided as an argument to the
constructor, the associate namelist option (`config_mom_del2`) will be given
this value. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.internal_wave.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.internal_wave.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run. Finally, validation of `temperature`, `salinity`,
`layerThickness` and `normalVelocity` in the `output.nc` file are performed
against a baseline if one is provided when calling {ref}`dev-polaris-setup`.

### validate

The class {py:class}`polaris.tasks.ocean.internal_wave.validate.Validate`
defines a step for validating outputs in two step directories against one
another.  This step ensures that `temperature`, `salinity`, `layerThickness`
and `normalVelocity` are identical in `output.nc` files in the two steps.

(dev-ocean-internal-wave-default)=

## default

The {py:class}`polaris.tasks.ocean.internal_wave.default.Default`
test performs a 3-time-step run on 4 cores. Two versions of this test exist,
one with the flux-form vertical advection scheme (``standard``), and one with
vertical Lagrangian-remapping (``vlr``).

(dev-ocean-internal-wave-rpe-test)=

## rpe

The {py:class}`polaris.tasks.ocean.internal_wave.rpe.Rpe`
performs a longer (20 day) integration of the model forward in time at 4
different values of the viscosity. Two versions of this test exist,
one with the flux-form vertical advection scheme (``standard``), and one with
vertical Lagrangian-remapping (``vlr``).

The `analysis` step defined by
{py:class}`polaris.tasks.ocean.internal_wave.rpe.analysis.Analysis`
makes plots of the final results with each value of the viscosity.

This test is resource intensive enough that it is not used in regression
testing.
