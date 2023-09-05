(dev-ocean-single-column)=

# single_column

The single column tests in `polaris.ocean.tasks.single_column` exercise 
the vertical dynamics of the ocean model only. There are currently
two test cases: one that exercises CVMix, the other that exercises ideal age 
tracers with CVMix. Here, we describe the tests and their shared framework.

(dev-ocean-single-column-framework)=

## framework

The shared config options for the `single_column` tests
are described in {ref}`ocean-single-column` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with
a few common model config options related to run duration and horizontal
diffusion and cvmix, as well as defining `mesh`, `input`, `restart`, `output`,
`KPP_testing` and `mixedLayerDepthsOutput` streams.

An additional `forward.yaml` file is included in the ideal age tracer test case
for enabling on the ideal age tracers and ideal age surface forcing, as well as
for defining `idealAgeTracers` streams

### init

The class {py:class}`polaris.ocean.tasks.single_column.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  A vertical grid is
generated, with 100 layers of 4 m thickness each by default.  Finally, the
initial temperature and salinity field are computed with variability in the
vertical dimension only.

A forcing netCDF file is also created based on the config options given in the
`single_column_forcing` section.

For cases with ideal age tracers, an initial profile for the ideal age tracer is
also constructed and is equal to zero seconds throughout the column.

### forward

The class {py:class}`polaris.ocean.tasks.single_column.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step. The ocean model is run.

### viz

The class {py:class}`polaris.ocean.tasks.single_column.viz.Viz`
produces figures comparing the initial and final profiles of temperature and
salinity.

(dev-ocean-single-column-cvmix)=

## cvmix

The {py:class}`polaris.ocean.tasks.single_column.cvmix.CVMix`
test performs a 1-day run on 1 cores.  Then, validation of `temperature`, 
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`.

## ideal age

The {py:class}`polaris.ocean.tasks.single_column.cvmix.IdealAge` test
performs the same 1-day run on 1 cores as the 
{py:class}`polaris.ocean.tasks.single_column.cvmix.CVMix` test, but with a
single ideal age tracer included. An additional `forward.yaml` file is 
included in the ideal age tracer test case for enabeling on the ideal age 
tracers and ideal age surface forcing, as well as for defining 
`idealAgeTracers` streams. Validation of `temperature`, `salinity`, 
and `idealAgeTracers` are performed against a baseline if one is provided
when calling {ref}`dev-polaris-setup`.
