(dev-ocean-single-column)=

# single_column

The single column tests in `polaris.tasks.ocean.single_column` exercise
the vertical dynamics of the ocean model only. The test cases are:

- Testing the vertical mixing library, CVMix, under surface forcing
- Testing the Ideal Age tracer under surface forcing
- Testing the Coriolis term by quantifying the inertial frequency
- Testing the Ekman solution under wind forcing

Here, we describe the tests and their shared framework.

(dev-ocean-single-column-framework)=

## framework

The shared config options for the `single_column` tests
are described in {ref}`ocean-single-column` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with
a few common model config options related to the initial state, coriolis
forcing, run duration and surface forcing, as well as defining `mesh`,
`input`, `restart`, and `output`, streams.

### init

The class {py:class}`polaris.tasks.ocean.single_column.init.Init`
defines a step for setting up the initial state for each test case.

4×4 planar hex mesh is generated for this task using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`. The number of cells in
each dimension can be modified with config options `single_column:nx`,
`single_column:ny`.
By default, the mesh is 960 m in horizontal resolution and is not intended to
resolve any lateral gradients. The horizontal resolution can be modified with
config option `single_column:resolution`

A vertical grid is
generated, with 100 layers of 4 m thickness each by default.

The
initial temperature and salinity field are computed with variability in the
vertical dimension only. The config options that determine these profiles are
located in section `single_column` and include:

| Option                                  | Description |
|-----------------------------------------|-------------|
| `surface_temperature`, `surface_salinity` | Initial surface values |
| `temperature_gradient_mixed_layer`, `salinity_gradient_mixed_layer` | Gradients within the mixed layer |
| `temperature_difference_across_mixed_layer`, `salinity_difference_across_mixed_layer` | Profile discontinuity across the mixed layer |
| `temperature_gradient_interior`, `salinity_gradient_interior` | Interior (below mixed layer) gradients |
| `mixed_layer_depth_temperature`, `mixed_layer_depth_salinity` | Mixed layer depths (typically ~40 m) |

For cases with ideal age tracers, an initial profile for the ideal age tracer is
also constructed and is equal to zero seconds throughout the column.

A forcing netCDF file is also created based on the config options given in the
`single_column_forcing` section. A subset of those options are:

| Option | Description |
|--------|-------------|
| `temperature_piston_velocity`, `salinity_piston_velocity` | Surface restoring rates |
| `temperature_surface_restoring_value`, `salinity_surface_restoring_value` | Target surface values |
| `temperature_interior_restoring_rate`, `salinity_interior_restoring_rate` | Interior restoring rates |
| `latent_heat_flux`, `sensible_heat_flux`, `shortwave_heat_flux` | Surface heat flux components |
| `evaporation_flux`, `rain_flux` | Surface freshwater fluxes |
| `wind_stress_zonal`, `wind_stress_meridional` | Wind stress values |

### forward

The class {py:class}`polaris.tasks.ocean.single_column.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step. The ocean model is run.

### viz

The class {py:class}`polaris.tasks.ocean.single_column.viz.Viz`
produces figures comparing the initial and final profiles of temperature and
salinity.

(dev-ocean-single-column-cvmix)=

## cvmix

The {py:class}`polaris.tasks.ocean.single_column.cvmix.CVMix`
test performs a 10-day run on 1 cores.  Then, validation of `temperature`,
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`.

## ekman

The {py:class}`polaris.tasks.ocean.single_column.cvmix.CVMix`
test performs a 5-day run on 1 cores.  Then, validation of `temperature`,
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`.

## ideal age

The {py:class}`polaris.tasks.ocean.single_column.cvmix.IdealAge` test
performs the same 10-day run on 1 cores as the
{py:class}`polaris.tasks.ocean.single_column.cvmix.CVMix` test, but with a
single ideal age tracer included. An additional `forward.yaml` file is
included in the ideal age tracer test case for enabeling on the ideal age
tracers and ideal age surface forcing, as well as for defining
`idealAgeTracers` streams. Validation of `temperature`, `salinity`,
and `idealAgeTracers` are performed against a baseline if one is provided
when calling {ref}`dev-polaris-setup`.

## inertial

The {py:class}`polaris.tasks.ocean.single_column.inertial.Inertial`
test performs a 10-day run on 1 cores.  Then, validation of `temperature`,
`salinity`, `layerThickness` and `normalVelocity` are performed against a
baseline if one is provided when calling {ref}`dev-polaris-setup`. Then, the
analysis step is run, and the viz step is optionally run.

### analysis

The {py:class}`polaris.tasks.ocean.single_column.inertial.analysis.Analysis`
compares the inertial frequency with its theoretical value and induces a
failure if the frequency is more than a given fractional difference from
theory, as determined by the config option
`single_column_inertial:period_tolerance_fraction`.
