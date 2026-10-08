(dev-ocean-single-column)=

# single_column

The single column tests in `polaris.tasks.ocean.single_column` exercise
the vertical dynamics of the ocean model only. The test cases are:

- Testing the vertical mixing library, CVMix, under surface forcing
- Testing the Ideal Age tracer under surface forcing
- Testing the Coriolis term by quantifying the inertial frequency
- Testing the Ekman solution under wind forcing
- Testing KPP boundary-layer regimes; see
  {ref}`dev-ocean-single-column-kpp`.

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

(dev-ocean-single-column-kpp)=

## KPP regimes

The {py:class}`polaris.tasks.ocean.single_column.kpp_regimes.KPPRegimes`
task class creates all nine regimes documented in
{ref}`ocean-single-column-kpp`. Their physical goals, literature
attributions, profile values and forcing signs are described there.
This section covers configuration composition, model-specific controls
and validation; the regimes are not additional implementations of KPP.

### registration and shared initialization

`add_single_column_tasks()` in
`polaris/tasks/ocean/single_column/__init__.py` registers each regime's
forcing and profile configuration lists. It starts with `single_column.cfg`
and `neutral_temperature_salinity.cfg`, adds forcing files, then adds
`stable_temperature_strong.cfg` and finally the regime-specific profile
files. Later entries override earlier ones. In particular, the file named
`neutral_temperature_salinity.cfg` does not make the final wind or
suppression profile neutral: the strong profile is loaded afterward.

`KPPRegimes` adds `kpp_regimes.cfg` and `polaris.ocean.eos/teos10.cfg` to
the shared configuration. Shared initialization steps are keyed by regime,
at `ocean/column/init/kpp/<regime>/stable`, and linked into each task as
`init`. Do not key them on forcing alone: cooling and mixed-layer cooling
share forcing but have different initial profiles.

The common {py:class}`polaris.tasks.ocean.single_column.init.Init` writes
the mesh, initial tracers, vertical coordinate and forcing described in
{ref}`dev-ocean-single-column-framework`. The named-grid branch of
{py:func}`polaris.ocean.vertical.grid_1d.generate_1d_grid` crops the JSON
interface depths instead of scaling them. Document and inspect the
generated layer count, not just `vert_levels`, when changing a named grid.

The suppression profile override is currently loaded after `evap_strong.cfg`.
It zeros the inherited evaporation, latent and shortwave terms and sets
sensible heating to +125 W/m². Removing those overrides would change the
experiment, even if the task name remained unchanged.

### forward steps and model controls

All cases use the shared
{py:class}`polaris.tasks.ocean.single_column.forward.Forward`. The KPP
constructor explicitly supplies `match_technique='SimpleShapes'`; the
second ordinary forward step overrides it with `MatchBoth`. Their paths
are `forward_no_vadv_no_hadv_simpleshapes` and
`forward_no_vadv_no_hadv_matchboth`. Langmuir instead creates two
`SimpleShapes` steps, distinguished by the `_langmuir` suffix for the
enabled run. Visualization and analysis consume these paths through the
constructor's `comparisons` dictionary.

Keep KPP defaults scoped to this task package. Non-KPP single-column
steps retain their original names and explicitly disable KPP and its
non-local tendency; changing a shared default must not rename their
forward outputs or activate additional physics.

`kpp_regimes/forward.yaml` supplies common KPP parameters and model-specific
options. `Forward.dynamic_model_config()` provides template replacements
and explicit enable flags. Important controls are:

| Control | Setting |
|---------|---------|
| Critical bulk Richardson number | 0.25 |
| Surface-layer extent | 0.1 |
| Background diffusivity / viscosity | $10^{-5}$ / $10^{-4}$ m²/s |
| Shear Richardson-number smoothing | Two loops |
| MPAS-Ocean BLD interpolation | Linear |
| EOS | TEOS-10 in Omega; `jm` in MPAS-Ocean |
| Ordinary Langmuir setting | Disabled |
| Enabled Langmuir variant | Omega `UseLangmuirTurbulence`; MPAS-Ocean theory-wave estimate, `LWF16` mixing and `LF17` entrainment |
| Sea-ice minimum BLD | 30 m in both sea-ice forward steps |

The MPAS-Ocean theory-wave switch alone does not enable Langmuir mixing:
the mixing and entrainment options must also differ from `NONE`. The
forward constructor keeps Omega's Coriolis tendency independent of the
horizontal-advection switch; `kpp_wind` removes Coriolis through the
initial mesh's `[coriolis] type = zero` setting.

The ordinary 600 s timestep and 3600 s output interval come from config.
For strong cooling, `run_duration_steps=36` overrides the run duration
and sets output every timestep. Omega's history frequency uses the
templated seconds interval. MPAS-Ocean disables its startup output, so
both first write after one interval. Use the actual initial-condition
file when a true time-zero state is needed.

### visualization

{py:class}`polaris.tasks.ocean.single_column.kpp_regimes.viz.KPPViz`
writes `boundary_layer_depth.png` and comparison-specific time-depth
figures for available Richardson-number, viscosity, diffusivity and
non-local-flux diagnostics. It uses the shared ocean I/O abstraction to
read model fields under MPAS-style names. Missing optional diagnostics
are skipped; absence of a figure is not a physical pass criterion.

### analysis and validation

{py:class}`polaris.tasks.ocean.single_column.kpp_regimes.analysis.Analysis`
reports cell-mean BLD at the output nearest day one and the relative
final diffusivity difference between matching variants. Regime-specific
checks are:

| Regime | Analysis diagnostic |
|--------|---------------------|
| Wind | Compare day-one BLD with $h=u_* (15t/N_0^2)^{1/3}$ using diagnosed stratification |
| Cooling, evaporation, mixed-layer cooling | Log initial/final BLD, finite tracer/density checks, F11 trajectory error and final non-local flux |
| Combined | Common BLD and matching comparison; no separate combined-forcing analytic check |
| Suppression | Warn if final maximum absolute non-local flux exceeds $10^{-10}$, or diffusivity is nonpositive |
| Langmuir | Warn if enabled day-one BLD is less than disabled BLD |
| Sea ice | Warn if the sampled BLD is below 30 m |
| Strong cooling | Warn if surface temperature does not decrease or final column-wide maximum $N^2$ is nonpositive |

These checks log information and warnings rather than asserting a
regime-specific accuracy tolerance. Missing diagnostics may skip checks.
The current F11 implementation is
$h=\sqrt{2.8 B t/N^2}$, with positive destabilizing flux magnitude $B$.
`initial_n_squared()` estimates temperature-driven stratification from
the configured EOS. It omits salinity gradients: for the uniform-temperature
evaporation case it returns zero and can produce division-by-zero/NaN
diagnostics. Its zero-mixed-layer formula is also only a reference for
the mixed-layer case. The strong-cooling maximum is not restricted to
the diagnosed BLD and cannot establish stability specifically within it.

Forward steps register baseline validation for `temperature`, `salinity`,
`layerThickness` and `normalVelocity` when a baseline is supplied. They
also register mass, salt and energy property checks, except combined
forcing and suppression, which currently register mass and salt only.
The KPP config sets energy tolerance to $10^{-6}$ and salt tolerance to
$10^{-10}$; mass uses the inherited tolerance. Consult each forward
step's `property_check_results.json` as well as the suite status: property
failures can be reported independently of task execution success.

### extending a regime

Add a registration entry with forcing and profile configurations and keep
its shared init path unique. Add any special paired-forward controls to
`KPPRegimes`, supplying matching `comparisons` paths to visualization and
analysis. Record whether the case adapts a published experiment or tests
a specific implementation feature, and distinguish its intended physical
signature from an enforced validation threshold.

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
