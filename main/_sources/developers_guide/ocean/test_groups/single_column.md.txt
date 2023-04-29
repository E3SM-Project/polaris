(dev-ocean-single-column)=

# single_column

The `single_column` test group
({py:class}`polaris.ocean.tests.single_column.SingleColumn`)
implements test cases that exercise vertical dynamics only. There is currently
one test case that exercises CVMix. Here, we describe the shared framework for
this test group and the CVMix test case.

(dev-ocean-single-column-framework)=

## framework

The shared config options for the `single_column` test group
are described in {ref}`ocean-single-column` in the User's Guide.

Additionally, the test group has a shared `forward.yaml` file with
a few common model config options related to run duration and horizontal
diffusion and cvmix, as well as defining `mesh`, `input`, `restart`, `output`,
`KPP_testing` and `mixedLayerDepthsOutput` streams.

### initial_state

The class {py:class}`polaris.ocean.tests.single_column.initial_state.InitialState`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  A vertical grid is
generated, with 100 layers of 4 m thickness each by default.  Finally, the
initial temperature and salinity field are computed with variability in the
vertical dimension only.

### forward

The class {py:class}`polaris.ocean.tests.single_column.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `initial_state` step. The ocean model is run.

### viz

The class {py:class}`polaris.ocean.tests.single_column.viz.Viz`
produces figures comparing the initial and final profiles of temperature and
salinity.

(dev-ocean-single-column-cvmix)=

## cvmix

The {py:class}`polaris.ocean.tests.single_column.cvmix.CVMix`
test performs a 1-day run on 1 cores.  Then, validation of `temperature`, 
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`.
