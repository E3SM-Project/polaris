(ocean-seamount)=

# seamount

The ``ocean/seamount`` test is a standard sigma coordinate test problem, which is documented in 
[Beckmann and Haidvogel (1993)](https://journals.ametsoc.org/view/journals/phoc/23/8/1520-0485_1993_023_1736_nsofaa_2_0_co_2.xml), [Haidvogel et al. (1993)](https://journals.ametsoc.org/view/journals/phoc/23/11/1520-0485_1993_023_2373_nsofaa_2_0_co_2.xml) and [Shchepetkin and McWilliams (2003)](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2001JC001047).
This case tests the error due to pressure gradients in tilted layers. 

## supported models

These tasks support both MPAS-Ocean and Omega.

The vertical coordinate is built in geometric height in either case, and is
converted to the pseudo-height (`RefPseudoThickness`) that Omega's p-star
dynamics read when `model = omega`.  Both models therefore start from the same
geometric layer positions, which is what makes the two comparable.  The
conversion integrates gauge pressure down each column through the configured
equation of state, so it needs no p-star-specific initialization and no
reference pseudo-grid.

Because Omega's linear equation of state has no reference temperature or
salinity, `eos_linear_Tref` and `eos_linear_Sref` must both be zero; the
Beckmann and Haidvogel reference state is folded into `eos_linear_rhoref`
instead.

Omega has no split time stepper, so it is limited by the barotropic gravity
wave.  Rather than let the two models use different integrators, MPAS-Ocean
gives up its split-explicit scheme and both run RK4 at the same `dt_per_km`
until Omega gains a split time stepper.  `btr_dt_per_km` therefore has no
effect unless `time_integrator` is set back to a split-explicit scheme.

(ocean-seamount-variants)=

## variants

Each task exists in eight trees, combining the equation of state, the
stratification and the vertical coordinate used for the initial condition:
`planar/seamount/{eos}/{stratification}/{coord}`, or in full
`planar/seamount/{linear,nonlinear}/{exponential,linear_pressure}/{sigma,zstar}`.

The stratification chooses whether a finite-volume pressure gradient is exact
on the profile:

- `exponential` — the realistic profile, Beckmann and Haidvogel eqn 16, with
  the stratification concentrated in the upper 500 m over a nearly
  unstratified abyss.  It is in no pressure-gradient scheme's exact set, so
  both schemes carry a truncation error and the comparison is on a profile
  the ocean actually has.
- `linear_pressure` — temperature linear in pressure, salinity constant.  A
  finite-volume pressure gradient is exact here, so its spurious velocity
  should collapse while the centered scheme's does not, and anything that
  survives the finite-volume run is not pressure-gradient truncation error.
  See {ref}`ocean-seamount-linear-in-pressure`.

```{warning}
**Compare the two schemes in the `nonlinear` trees, not the `linear` ones.**
Under the linear equation of state, specific volume depends only on
temperature and salinity, so a temperature linear in pressure makes specific
volume linear in pressure as well -- and the same function of pressure in
every column, which leaves the ocean horizontally homogeneous in pressure
coordinates.  That nulls the *centered* scheme too, and the configuration
stops being a test of anything.  Measured on this case, specific volume
departs from a straight line in pressure by 4.6e-4 of its range under the
linear equation of state against 8.6e-3 under TEOS-10, whose compressibility
keeps the dependence nonlinear no matter what the tracers do.

This is the same trap one level down from the one in
{ref}`ocean-seamount-linear-in-pressure`: a null configuration is null only
for the scheme it was built for, and here an equation of state quietly
extends it to both.  The `linear` / `linear_pressure` trees remain useful as
regression tests; they are not a scheme comparison.
```

The two span the same density range under the linear equation of state,
3.0 kg m^{-3}, so a spurious velocity measured on one is comparable to the
other.

The coordinate chooses how much the layers tilt:

- `sigma` — the terrain-following coordinate, and the main target.  Every
  layer is tilted relative to the isobars by construction, so the pressure
  gradient error is exercised throughout the water column.
- `zstar` — the control.  Layers are nearly level, so the spurious velocity
  should be much smaller.  Partial bottom cells are used here: z-star cuts
  the reference grid at the seafloor, and without snapping the seamount
  flanks produce bottom cells only centimetres thick.  Set
  `partial_cell_type = full` for the limiting case in which the layers are
  exactly level and the pressure gradient vanishes to machine precision.

The equation of state chooses whether density depends on pressure:

- `linear` — `rho = rhoref - alpha * (T - Tref) + beta * (S - Sref)`, with
  no pressure dependence at all.
- `nonlinear` — TEOS-10 for Omega and Jackett-McDougall (`jm`) for
  MPAS-Ocean, the closest nonlinear equation of state it has.  The thermal
  expansion coefficient then varies along a tilted layer, which the linear
  trees cannot represent.

Under the `exponential` stratification the two equations of state are given
the same buoyancy stratification, as described under
{ref}`ocean-seamount-init`, so a difference in spurious velocity between the
`linear` and `nonlinear` trees is attributable to the equation of state and
not to a different `N^2`.  Under `linear_pressure` the tracer is prescribed
directly rather than inverted from a density, so the two trees span the same
temperature range instead and their densities differ.

One caveat on cross-model comparison: TEOS-10 and Jackett-McDougall are
genuinely different functions, not two implementations of one, so the two
models are only expected to agree qualitatively in the `nonlinear` trees.
In the `linear` trees they solve the same equation of state and can be
compared directly.

(ocean-seamount-default)=

## default task

### description

The test case begins with a zero velocity field and is unforced, so the exact solution is to remain motionless. 
The seamount rises from a flat sea floor in the center of the domain. 
In a pure z-level vertical coordinate without partial bottom cells (`partial_cell_type = full`), the pressure gradient will remain zero and induce no flow to machine precision. When any layer tilting is added, including from partial bottom cells, some flow is introduced by the pressure gradient error. This is fundamentally because the pressure must be extrapolated vertically at cell centers to the mid-depth of the edge. The default setting is the sigma coordinate. These are the images produced in the `viz_centered` folder, which runs by default in this task because the 6 day forward run is too long to want to repeat just to get the plots.

```{image} images/seamount_velocity_max_t.png
:align: center
:width: 700 px
```

```{image} images/seamount_final_kineticEnergyCell_section.png
:align: center
:width: 700 px
```

```{image} images/seamount_final_normalVelocity.png
:align: center
:width: 400 px
```

(ocean-seamount-schemes)=

#### pressure-gradient schemes

Under Omega the task performs a second forward run, `forward_finite_volume`,
with `PressureGradType: FiniteVolume` instead of the centered scheme
`forward_centered` uses.  Both start from the same `init` step, so the two
schemes are compared at an identical state rather than at two states that
also differ in their initial condition.

The step is added only when `model = omega`.  MPAS-Ocean has only the
centered scheme, so under MPAS-Ocean the task is `init`, `forward_centered`,
`viz_centered` and `analysis`.

Every forward step is named for its scheme, including in the `short` task
which runs only the centered one, so an output directory says which scheme
produced it without anyone having to open the model config.  The scheme is
also written into the Omega config explicitly rather than left to Omega's
default, for the same reason.

Each forward step gets its own `viz` step — `viz_centered` and
`viz_finite_volume` — and an `analysis` step compares whichever schemes were
run.

(ocean-seamount-metrics)=

#### spurious-circulation metrics

The exact solution is a resting ocean, so every velocity in this task is
error.  The `analysis` step writes `metrics.csv` and `spurious_velocity_t.png`
with, for each scheme and output time:

- `max_speed`, the maximum `|normalVelocity|` over the whole domain;
- `max_speed_level`, the level index at which that maximum sits.  The
  centered scheme's error accumulates downward, so a maximum that is not at
  the bottom is worth noticing rather than averaging away;
- `max_speed_bottom`, the same maximum restricted to the deepest valid level
  of each edge.  An edge has water only where both its cells do, so on the
  seamount flanks this follows the bathymetry rather than a fixed level;
- `mean_kinetic_energy`, volume-weighted over the domain;
- `implied_acceleration` and `acceleration_ratio`;
- `unstable_pairs` and `max_density_inversion`, described below.

```{warning}
**`unstable_pairs` greater than zero invalidates every other metric from that
time on.**  All vertical mixing including convection is off in this task, so
nothing restores a column that overturns.  Once one does, the run is no longer
measuring a spurious circulation against a resting exact solution; it is
measuring an unbounded convective response with the response removed, and the
velocity grows without any physical bound.  The `analysis` step logs the day
this first happens and plots the count against time, and the last panel of
`spurious_velocity_t.png` is where to look before reading any of the others.

This has been observed: on the 6 day `linear/exponential/sigma` run the
finite-volume integration first overturned at day 4 on the seamount flank and
reached 232 unstable layer pairs and a 0.15 kg m^{-3} inversion by day 6,
while max |u| grew exponentially with an e-folding time of 1.2 days.  The
centered integration on the same configuration stayed stable throughout.
```

An absolute spurious velocity says little on its own.  What gives it meaning
is how it compares to a pressure gradient a realistic configuration actually
carries in the layer where the problem shows up, which is what
`reference_bottom_pressure_grad` is for.  The conversion from velocity to
acceleration is `|f| * max|u|` — the acceleration a flow of that speed would
be in balance with.  That is a balanced-state estimate: it is meaningful once
the flow has adjusted and overstates the acceleration while it is still
spinning up, so read the ratio with the time series in front of you rather
than as a single number.

No thresholds are applied.  They are meant to be set from what these metrics
measure rather than in advance; a threshold guessed before the first
measurement is a guard that either cannot fail or fails for the wrong reason.

`interface_tilt_<scheme>.png` shows how each layer interface's tilt evolves.
Sigma interfaces follow the bathymetry, so the surface starts level and the
deepest interfaces start at the full bathymetric slope — but the free surface
moves the layers and `vertCoordMovementWeights` is uniform, so every
interface takes a share of the surface-pressure change and the top interface
can acquire a tilt it did not start with.  The upper panel plots the change
since the first output time rather than the tilt itself, which is dominated
by the bathymetry and barely moves on its own scale; the lower panel plots
the surface tilt against the maximum over all levels, which is where a
barotropic adjustment would show up.


### mesh

The domain is planar and periodic on the zonal and the
meridional boundaries. The 6.4 km resolution is tested by default,
which is set by the ``resolution`` config option. The domain is
320 km by 320 km, as given by the config options ``lx`` and ``ly``,
which at 6.4 km is exactly 50 cells across; the hexagonal mesh is 58 cells
in the other direction, for 321.5 km.

Neither the domain size nor the resolution is prescribed by Beckmann and
Haidvogel — only the seamount shape and the stratification are. The
quantity that determines how hard this case is on a tilted coordinate is
the discrete steepness of the seamount, `max |dh| / (h1 + h2)` between
adjacent cells, which for a Gaussian seamount is about
`1.5 * resolution / seamount_width`, or 0.21 here.

### vertical grid

The coordinate is set by the task tree, `sigma` or `zstar`, as described in
{ref}`ocean-seamount-variants`. `coord_type` therefore lives in
`seamount_sigma.cfg` / `seamount_zstar.cfg` rather than in the shared config
below. One may also test `coord_type = z-level`.

All of these are geometric coordinates, so all of them reach Omega through
the same pseudo-height conversion, under either equation of state.

The 32 levels divide the 5000 m bottom depth into exact 156.25 m layers. That
is a multiple of 16, which Omega prefers, and it sits in the range the
literature uses for this case (20 in Beckmann and Haidvogel, 20-30 in
Shchepetkin and McWilliams). It also keeps the z-star tree usable: with the
10 levels this task used previously, the 500 m summit column would have had a
single level.

`partial_cell_type = None` means no alteration, so the original bottom depth
is used; `partial` snaps the bottom cell to at least `min_pc_fraction` of a
full cell, and `full` snaps it to a whole cell. The z-star tree overrides the
default below to `partial`, because without snapping the seamount flanks
produce bottom cells only centimetres thick.

```cfg
# Options related to the vertical grid
[vertical_grid]

# Depth of the bottom of the ocean (m)
bottom_depth = 5000.0

# Number of vertical levels
vert_levels = 32

# The type of vertical grid
grid_type = uniform

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

(ocean-seamount-init)=

### initial conditions

Salinity is constant throughout the domain at the value given by the config
option ``constant_salinity`` (35 by default), read as practical salinity in
the `linear` trees and as absolute salinity in the `nonlinear` ones.  The
initial density
is based on the formulas given in [Beckmann and Haidvogel (1993)](https://journals.ametsoc.org/view/journals/phoc/23/8/1520-0485_1993_023_1736_nsofaa_2_0_co_2.xml) equations 15-16.
Temperature is then back-computed from that density, so the profile rather
than the temperature is what the two equations of state have in common.

In the `linear` trees the inversion is algebraic: the equation of state that
Polaris and both ocean models apply,
`rho = rhoref - alpha * (T - Tref) + beta * (S - Sref)`, is solved for `T`
using the `eos_linear_*` options in the `ocean` section. The salinity term
matters: dropping it would leave the model's density offset from the
Beckmann and Haidvogel profile by `beta * S`, which is harmless in
MPAS-Ocean but not in Omega, where the geometric-to-pseudo-height mapping
depends on the absolute density.

In the `nonlinear` trees the profile is read as a **potential density
referenced to the surface**, and conservative temperature comes from
`gsw.CT_from_rho` at zero reference pressure.  It cannot be read as in-situ
density: TEOS-10 in-situ density at 5000 m is near 1050 kg m^{-3} from
compression alone, well outside the 1025-1028 kg m^{-3} range the profile
spans, so no temperature would reproduce it below about 1000 m.  Referencing
to the surface also means the `linear` and `nonlinear` trees share a
buoyancy stratification exactly while their in-situ densities differ by more
than 20 kg m^{-3} at depth — which is the point, since that difference is
what a nonlinear equation of state contributes to the pressure gradient
error.

Omega receives conservative temperature and absolute salinity directly.  For
MPAS-Ocean the `nonlinear` tracers are converted to potential temperature and
practical salinity at a nominal lon/lat location (config options
`ocean:nominal_lon` and `ocean:nominal_lat`, both defaulting to 0 degrees)
since the planar mesh has no geographic location.

(ocean-seamount-linear-in-pressure)=

#### a stratification linear in pressure

`seamount_stratification_type = linear_pressure` replaces the Beckmann and
Haidvogel profile with one prescribed on temperature rather than on density:

```
T = seamount_temperature_coef_linear_pressure
    - seamount_temperature_gradient_linear_pressure
      * p / seamount_pressure_ref_linear_pressure
```

with salinity constant as before.  A finite-volume pressure gradient
reconstructs the tracers as polynomials in pressure and is exact when the
continuous profile is linear in pressure, so its error vanishes on this
configuration and a spurious velocity that survives has some other source.
Running it alongside the centered scheme, and alongside the realistic
exponential profile, is what makes that a measurement rather than an
assumption.

Two things are needed for the exactness to hold, and both are checked by
`tests/ocean/seamount/test_linear_in_pressure.py`:

- **The layer values are exact layer means, not point samples.** Both models
  carry a layer-mean tracer, and the mean is over the mass of the layer,
  which is the same as over its pressure range. For a profile linear in
  pressure that mean is the value at the layer's mid-pressure, so no
  quadrature is needed — but a sample at the geometric mid-depth would leave
  an `O(h^2)` error that the exactness argument does not allow for.
- **The profile is a fixed point, not a formula.** Temperature is a function
  of pressure, pressure follows from the geometric layer thicknesses through
  the specific volume, and the specific volume follows from the temperature.
  The initial condition iterates all three to round-off, so the profile is
  linear in the pressure the model itself carries.

Neither Beckmann and Haidvogel profile has this property, and the `linear`
one is close enough to be mistaken for it. A density linear in geometric
depth makes pressure quadratic in depth, since specific volume varies down
the column, so temperature departs from a straight line in pressure by
8.5e-6 of its range under the linear equation of state and 6.9e-4 under
TEOS-10 — small, but ten orders of magnitude above the round-off that an
exactness argument needs. The `linear_pressure` profile reaches 7e-15 on the
same measure.

The temperature range defaults to 15 degC over 5000 dbar, which under the
linear equation of state spans 3.0 kg m^{-3} — the same density range as the
exponential Beckmann and Haidvogel profile, so the two runs have the same
total buoyancy range and a spurious velocity measured on one is comparable to
the other. The stratification is spread uniformly rather than concentrated in
the upper 500 m, so the deep layers are more strongly stratified than in the
exponential profile, not less.

Because the tracer is prescribed directly rather than inverted from a
density, the `linear` and `nonlinear` trees span the same *temperature* range
here, not the same density range — the reverse of the Beckmann and Haidvogel
profiles.

### forcing

N/A

### horizontal and vertical mixing, and bottom drag

Laplacian momentum viscosity at `nu = 1000` m^2 s^-1 is the only horizontal
mixing.  Hyperviscosity and tracer diffusion, both Laplacian and biharmonic,
are switched off explicitly rather than left to a model default.  Setting only
the del2 options let each model fall back to its own for the rest, which had
Omega running with `ViscDel4 = 1.2e11` m^4 s^-1 and `EddyDiff2 = 10` m^2 s^-1
while MPAS-Ocean ran with neither -- an unintended difference in a case whose
point is partly to compare the two models.  Tracer diffusion matters most: it
acts along the coordinate surfaces, and on a sigma coordinate over a seamount
those are tilted, so at a slope of 0.1 it is an effective diapycnal
diffusivity of order 0.1 m^2 s^-1 in a case whose exact solution is a resting
ocean.

All vertical mixing is off in both models. The exact solution is a resting
ocean, so the only thing that would trigger convection is a spurious pressure
gradient — the quantity being measured — and convection is a known source of
MPAS-Ocean/Omega divergence, since Omega uses a single coefficient for both
convective diffusivity and viscosity. Convection and shear mixing are
switched off explicitly and the background diffusivity and viscosity are
zeroed, because Omega defaults them on; MPAS-Ocean additionally sets
`config_use_cvmix = false`, which leaves its vertical viscosity and
diffusivity at zero.

Only the coefficients are zeroed. The implicit vertical mixing solve itself
stays on in both models, because that is what applies the implicit bottom
drag; Omega aborts if the vertical mixing tendency is disabled while the
bottom drag is implicit.

Bottom drag is implicit and constant in both models, at
`bottom_drag_coeff = 1.0e-3`. That is an order of magnitude below the value
comparable idealized planar cases use. The implicit drag damping timescale is
`h_bot / (Cd * |u|)`, and the bottom layer over the seamount summit is only
about 16 m thick, so at `1.0e-2` a 5 cm/s spurious velocity would damp in
under half a day against a 6 day run — capping a bad pressure gradient while
leaving a good one untouched, and compressing the dynamic range this test
exists to measure.

### time step and run duration

The time step for forward integration is automatically computed based on the gridcell size. The run duration is as follows.

```cfg
[seamount_default]

# Run duration (hours)
run_duration = 144.

# Output interval (hours)
output_interval = 1.
```

### config options

The following config section is specific to this test case:

```cfg
# Options related to the seamount case
[seamount]

# Timestep per km horizontal resolution (s), shared by both models
dt_per_km = 4.0

# Barotropic timestep per km horizontal resolution (s), MPAS-Ocean only, and
# unused unless time_integrator is a split-explicit scheme
btr_dt_per_km = 2.5

# Time integrator, shared by both models
time_integrator = RK4

# Horizontal tracer advection order, shared by both models
horiz_adv_order = 3

# Constant bottom drag coefficient
bottom_drag_coeff = 1.0e-3

# The width of the domain in the across-slope dimension (km)
ly = 320

# The length of the domain in the along-slope dimension (km)
lx = 320

# Distance between two cell centers (km)
resolution = 6.4

# Bottom depth at bottom of seamount
max_bottom_depth = ${vertical_grid:bottom_depth}

# The vertical profile of the tracers
# possible_values="linear, exponential, linear_pressure"
seamount_stratification_type = exponential

# Density coefficient for linear vertical stratification (kg m^{-3})
seamount_density_coef_linear = 1024.0

# Density coefficient for exponential vertical stratification (kg m^{-3})
seamount_density_coef_exp = 1028.0

# Density gradient for linear vertical stratification, Delta_z rho in Beckmann and Haidvogel eqn 15 (kg m^{-3})
seamount_density_gradient_linear = 0.1

# Density gradient for exponential vertical stratification, Delta_z rho in Beckmann and Haidvogel eqn 16 (kg m^{-3})
seamount_density_gradient_exp = 3.0

# Density reference depth for linear vertical stratification (m)
seamount_density_depth_linear = 4500.0

# Density reference depth for exponential vertical stratification (m)
seamount_density_depth_exp = 500.0

# Temperature at zero pressure for the linear_pressure stratification (degC)
seamount_temperature_coef_linear_pressure = 20.0

# Temperature change over seamount_pressure_ref_linear_pressure (degC)
seamount_temperature_gradient_linear_pressure = 15.0

# The pressure the temperature gradient is spanned over (dbar)
seamount_pressure_ref_linear_pressure = 5000.0

# Height of sea mount, H_0 (m)
seamount_height = 4500.0

# Width parameter of sea mount, e-folding length (m)
seamount_width = 40.0e3

# Salinity of the water in the entire domain, read as practical salinity
# (PSU) for the linear trees and as absolute salinity (g kg^-1) for the
# nonlinear ones
constant_salinity = 35.0

# A physical bottom-layer horizontal pressure-gradient acceleration (m s^-2)
# for the analysis step to report the spurious circulation as a fraction of
reference_bottom_pressure_grad = 2.1e-6
```

The `nonlinear` trees add no config options of their own; they take their
equation of state from `polaris.ocean.eos`'s `teos10.cfg` and the nominal
location for the salinity conversion from the shared `ocean` section.

The Coriolis parameter is set in the shared `coriolis` section:

```cfg
# config options for Coriolis
[coriolis]

# type of Coriolis: zero, constant, beta_plane, spherical, or rotated_sphere
type = constant

# the constant Coriolis parameter
constant_f = -1.0e-4
```

The `linear` trees configure their equation of state in `ocean`, through
`seamount_linear_eos.cfg`. `eos_linear_Tref` must be zero, because Omega's
linear equation of state has no reference temperature; the Beckmann and
Haidvogel reference state (1028 kg m^{-3} at T = 5 C, S = 35 PSU) is folded
into `eos_linear_rhoref` instead, as
`1028.0 + 0.2 * 5.0 - 0.8 * 35.0 = 1001.0`. `eos_linear_beta` and
`eos_linear_Sref` come from `polaris.ocean.eos`'s `linear.cfg`. These
options have no meaning in the `nonlinear` trees, which is why they live in
a per-variant config rather than the shared one.

```cfg
# Options related the ocean component
[ocean]

# Equation of state reference density when T and S are the reference values
eos_linear_rhoref = 1001.

# Equation of state -drho/dT
eos_linear_alpha = 0.2

# Equation of state reference temperature
eos_linear_Tref = 0.
```

The `nonlinear` trees instead pick up `polaris.ocean.eos`'s `teos10.cfg`,
which sets `eos_type = teos-10` and nothing else; Polaris maps that to `jm`
for MPAS-Ocean.

### cores

The number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file.

(ocean-seamount-short)=

## short task

### description

The `short` task is the `default` task run for 1 hour instead of 6 days.  It
exists for regression testing: an hour is far too short for the spurious
circulation to develop, so it says nothing about the pressure gradient error,
but it is long enough to catch a change in the answer cheaply.  It is
otherwise identical to the `default` task — same mesh, vertical grid, initial
condition, time step and physics — except that it runs the centered scheme
only, and it exists in all eight trees.

The `viz_centered` step is present but does not run by default here, since
re-running the task to get the plots costs almost nothing.  There is no
`analysis` step: an hour of a resting ocean is not a measurement.

Three of the eight are in the `mpaso_pr` and `omega_pr` suites:

- `planar/seamount/linear/exponential/zstar/short`
- `planar/seamount/nonlinear/exponential/sigma/short`
- `planar/seamount/nonlinear/linear_pressure/sigma/short`

The first two cover both equations of state and both vertical coordinates in
two runs rather than four.  The third covers the linear-in-pressure initial
condition, whose fixed-point iteration is the only part of the initial
condition that has to converge rather than evaluate; TEOS-10 is what makes it
have to, since the specific volume depends on pressure.

### time step and run duration

The time step is computed from the gridcell size exactly as in the `default`
task.  Only the duration and output interval differ:

```cfg
[seamount_short]

# Run duration (hours)
run_duration = 1.

# Output interval (hours)
output_interval = 0.5
```

The output interval is half the run duration so that the time series the
`viz_centered` step plots has more than a single point in it.

### config options

The short task adds no config options beyond the `[seamount_short]` section
above; everything else comes from the shared options listed under
{ref}`ocean-seamount-default`.

