(dev-ocean-baroclinic-channel)=

# baroclinic_channel

The `baroclinic_channel` test group
({py:class}`polaris.ocean.tests.baroclinic_channel.BaroclinicChannel`)
implements variants of the Baroclinic Eddies test case
(see {ref}`ocean-baroclinic-channel`) at 3 resolutions (1, 4 and 10 km).  Here,
we describe the shared framework for this test group and the 5 test cases.

(dev-ocean-baroclinic-channel-framework)=

## framework

The shared config options for the `baroclinic_channel` test group
are described in {ref}`ocean-baroclinic-channel` in the User's Guide.

Additionally, the test group has a shared `forward.yaml` file with
a few common model config options related to run duration and default 
horizontal  and vertical momentum and tracer diffusion, as well as defining 
`mesh`, `input`, `restart`, and `output` streams.

### baroclinic_channel_test_case

The class {py:class}`polaris.ocean.tests.baroclinic_channel.BaroclinicChannelTestCase`
defines a superclass for all baroclinic channel test cases.  This class sets
up the appropriate subdirectory for the given resolution, adds an initial
state step (see the following) used by all test cases, sets some config options
related to the mesh size and resolution in the
{py:meth}`polaris.ocean.tests.baroclinic_channel.BaroclinicChannelTestCase.configure()`
method, and performs validation of the initial condition in the
{py:meth}`polaris.ocean.tests.baroclinic_channel.BaroclinicChannelTestCase.validate()`
method.

### init

The class {py:class}`polaris.ocean.tests.baroclinic_channel.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  A vertical grid is generated,
with 20 layers of 50-m thickness each by default.  Finally, the initial
temperature field is computed along with uniform salinity and zero initial
velocity.

### forward

The class {py:class}`polaris.ocean.tests.baroclinic_channel.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step.  If `nu` is provided as an argument to the
constructor, the associate namelist option (`config_mom_del2`) will be given
this value. Namelist and streams files are updated in
{py:meth}`polaris.ocean.tests.baroclinic_channel.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.ocean.tests.baroclinic_channel.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that tests
have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Finally, the ocean 
model is run.

(dev-ocean-baroclinic-channel-default)=

## default

The {py:class}`polaris.ocean.tests.baroclinic_channel.default.Default`
test performs a 15-minute run on 4 cores.  Then, validation of `temperature`, 
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`.

(dev-ocean-baroclinic-channel-decomp-test)=

## decomp

The {py:class}`polaris.ocean.tests.baroclinic_channel.decomp.Decomp`
performs a 15-minute run once on 4 cores and once on 8 cores.  It
ensures that `temperature`, `salinity`, `layerThickness` and
`normalVelocity` are identical at the end of the two runs (as well as with a
baseline if one is provided when calling {ref}`dev-polaris-setup`).

(dev-ocean-baroclinic-channel-restart-test)=

## restart

The {py:class}`polaris.ocean.tests.baroclinic_channel.restart.Restart`
performs a 10-minute run once on 4 cores, saving restart files every time step
(every 5 minutes), then it performs a restart run starting at minute 5 for 5
more minutes.  It ensures that `temperature`, `salinity`,
`layerThickness` and `normalVelocity` are identical at the end of the two
runs (as well as with a baseline if one is provided when calling
{ref}`dev-polaris-setup`).

Restart files are saved at the test-case level in the `restarts` directory,
rather than within each step, since they will be used across both the `full`
and `restart` steps.

The `full.yaml` file is used to set up the run  duration and restart frequency 
of the full run, while `restart.yaml` makes sure that the restart step begins 
with a restart at minute 5 and runs for 5 more minutes.

(dev-ocean-baroclinic-channel-thread-test)=

## threads

The {py:class}`polaris.ocean.tests.baroclinic_channel.threads.Threads`
performs a 15-minute run once on 4 cores, each with 1 thread and once on 4
cores, each with 2 threads.  It ensures that `temperature`, `salinity`,
`layerThickness` and `normalVelocity` are identical at the end of the two
runs (as well as with a baseline if one is provided when calling
{ref}`dev-polaris-setup`).

:::{note}
The `ocean/baroclinic_channel/10km/thread/1thread` step is identical 
to `ocean/baroclinic_channel/10km/default/forward`. If
`ocean/baroclinic_channel/10km/thread` is included in a test suite, 
it would be redundant to include `ocean/baroclinic_channel/10km/default` in the
suite as well.
:::

(dev-ocean-baroclinic-channel-rpe-test)=

## rpe

The {py:class}`polaris.ocean.tests.baroclinic_channel.rpe.Rpe`
performs a longer (20 day) integration of the model forward in time at 5
different values of the viscosity.  Versions of the test case exist at each of
the 3 default horizontal resolutions (1, 4 and 10 km).

The `analysis` step defined by
{py:class}`polaris.ocean.tests.baroclinic_channel.rpe.analysis.Analysis`
makes plots of the final results with each value of the viscosity.

This test is resource intensive enough that it is not used in regression
testing.
