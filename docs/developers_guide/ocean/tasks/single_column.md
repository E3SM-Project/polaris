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

The forcing file holds only these forcing fields and the initial condition
holds only the initial state, so both ocean models read their forcing from
`forcing.nc`.  The one exception is Omega's `TracersMonthlySurfClimoCell`,
the surface restoring climatology, which Omega registers as an auxiliary
state variable rather than a member of its `Forcing` group and reads from
the initial condition.

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

## thermo

The {py:class}`polaris.tasks.ocean.single_column.thermo.Thermo` test performs
a separate forward run of 3 time steps, with output written every time step,
for each supported surface thermodynamic forcing
variable (latent, sensible, shortwave and longwave heat fluxes; evaporation,
snow, rain, river- and ice-runoff and sea-ice freshwater fluxes; and the
sea-ice heat and salinity fluxes).  Each `init`/`forward` pair applies a single
nonzero forcing variable so that the individual forcing terms can be verified
in isolation.  Conservation is checked twice for each run: between the initial
condition and the first time step in the output file, and between the last two
time steps.  Then the analysis step is run, and the viz step is optionally
run.

### conservation_summary

The
{py:class}`polaris.tasks.ocean.single_column.thermo.conservation_summary.ConservationSummary`
step gathers the conservation results from each forward step's
`property_check_results.json` and writes `conservation_summary.log`, which
lists each forward step name along with its mass, salt and energy relative
error for each conservation interval.

### analysis

The {py:class}`polaris.tasks.ocean.single_column.thermo.analysis.Analysis`
verifies conservation of mass, heat and salt for each forward run.  For every
run it compares the change in the column-integrated content against the surface
forcing flux accumulated over the run.  For a budget driven by a nonzero flux
the error is measured relative to that accumulated flux; for a budget with no
expected flux the residual is compared against the config option
`single_column_thermo:conservation_error_tolerance` times the initial total
column content.  A failure is induced if any budget's error exceeds that
tolerance.

The budgets follow exactly what the model integrates.  For Omega, the mass
coordinate is the pseudo-thickness `h` (`RhoSw * h` is the mass per area), so
the checks use the native `PseudoThickness`, `Temperature` and `Salinity`
fields rather than the reconstructed geometric thickness.  The column budgets
per unit area are:

- mass: `RhoSw * sum_k(dh_k)` vs the accumulated freshwater plus sea-ice salt
  flux (both enter Omega's thickness equation),
- heat: `RhoSw * Cp0Sw * sum_k(d(h_k T_k))` vs the accumulated enthalpy flux,
- salt: `(RhoSw / 1000) * sum_k(d(h_k S_k))` vs the accumulated sea-ice
  salinity flux.

Because the freshwater mass fluxes (rain, river runoff, snow and ice runoff)
also carry an SST-/freezing-point-dependent enthalpy heat flux, the heat
budget is skipped for those runs.  For MPAS-Ocean (Boussinesq), which has no
pseudo-thickness, the geometric `layerThickness` is used instead.
