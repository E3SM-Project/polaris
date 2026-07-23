(ocean-overflow)=

# overflow

The ``ocean/overflow`` test group induces a density current flowing down a
continental slope and includes the following test cases:

1. ``smoke_test_horiz_adv_order_2`` — short (12 min) smoke test using horizontal advection order = 2 for rapid CI checks.
2. ``smoke_test_horiz_adv_order_2_del4`` — same as (1) but with del4 viscosity enabled with the default viscosity value.
3. ``smoke_test_horiz_adv_order_3`` — short (12 min) smoke test using horizontal advection order = 3 for rapid CI checks.
4. ``smoke_test_horiz_adv_order_4`` — short (12 min) smoke test using horizontal advection order = 4 for rapid CI checks.
5. ``rpe`` — long run (40 days) exploring Resting Potential Energy (RPE) evolution for a set of Laplacian viscosities.

Each of these tasks (plus the `_del4` variants of orders 3 and 4) is
available in three variants that combine the equation of state (EOS) with
the vertical coordinate used for the initial condition:

- ``ocean/planar/overflow/linear/zstar`` — linear EOS with a z-star
  initial condition (the original configuration).
- ``ocean/planar/overflow/linear/pstar`` — linear EOS with a p-star
  initial condition, to isolate the effect of the vertical coordinate.
- ``ocean/planar/overflow/nonlinear/pstar`` — nonlinear EOS with a p-star
  initial condition, mirroring the configuration of the realistic global
  tasks in a small, fast-running idealized setting.

The nonlinear EOS is TEOS-10 for Omega and Jackett-McDougall (`jm`), the
closest available nonlinear EOS, for MPAS-Ocean.

## supported models

These tasks support MPAS-Ocean and Omega.

## description

This test case derives from
[Petersen et al. 2015](https://doi.org/10.1016/j.ocemod.2014.12.004). A cold,
dense block of water starts out on a flat continental shelf and flows down a
continental slope, ending up along a deep, flat seafloor. This test case is
generally used for evaluating spurious mixing associated with different
vertical coordinate systems in the presence of bottom topography.

```{image} images/overflow-sections-1h.png
:align: center
:width: 500 px
```

## mesh

The mesh is planar and the resolution is specified by config option
`overflow:resolution`, which defaults to 1 km.

The horizontal dimensions of the domain are set by config options
`overflow:lx` and `overflow:ly`, defaulting to 200 km by 40 km.

The domain is periodic on the zonal boundaries and solid on the meridional
boundaries.

## vertical grid

The topography includes a continental slope defined by

$$
z_{bed} = z_{shelf} + \frac{1}{2} (z_{floor} - z_{shelf}) (1 + \tanh((x - x_{slope})/L_{slope})
$$

where $z_{shelf}$ corresponds to config option `overflow:shelf_depth`,
$z_{floor}$ to `overflow:max_bottom_depth`, $x_{slope}$ to `overflow:x_slope`
and $L_{slope}$ to `overflow:L_slope`.

Any vertical coordinate and number of vertical levels above the minimum needed
for baroclinic dynamics may be used.

```cfg
# Options related to the vertical grid
[vertical_grid]

# Depth of the bottom of the ocean (m)
bottom_depth = 2000.0

# Number of vertical levels
vert_levels = 60

# The type of vertical grid
grid_type = uniform

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None
```

The two `pstar` trees override the vertical grid to use the p-star
coordinate.  Pseudo-depth is not geometric depth, so the pseudo-height grid
must reach deeper than the pressure at the deepest geometric bathymetry or
the domain would be artificially truncated.  The grid is 2400 m deep with
72 uniform levels (a ~19% buffer over the worst case while preserving the
~33.3 m layer spacing of the z-star grid and making the number of levels
a multiple of 16, preferred for Omega performance), and the geometric
bottom depth remains 2000 m:

```cfg
# Options related to the vertical grid
[vertical_grid]

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = p-star

# Pseudo-depth of the bottom of the pseudo-height grid (m)
bottom_depth = 2400.0

# Number of vertical levels
vert_levels = 72


# Options related to the overflow case
[overflow]

# Bottom depth at bottom of overflow (m): the geometric bottom depth,
# decoupled from the deeper pseudo-depth grid above
max_bottom_depth = 2000.0
```

## initial conditions

Salinity is constant throughout the domain (at 35 PSU).  The
initial temperature is bimodal with low temperature throughout the continental
shelf region set by the config option `overflow:low_temperature` (default value of 10
$^{\circ}$C) and high temperature over the slope and deep ocean set by the config
option `overflow:high_temperature` (default value of 20 $^{\circ}$C). The transition between
the two zones is set by the config option `overflow:x_dense` (default value of 20 km).
This perturbation initiates slumping of the cold, denser water mass and flow
down the slope as a bottom boundary current.

The initial state is at rest. The coriolis parameter is set to 0.

In the `nonlinear` tree, the temperature and salinity profiles are
interpreted as conservative temperature (CT) and absolute salinity (SA).
Omega receives CT and SA directly.  For MPAS-Ocean, CT is converted to
potential temperature and SA to practical salinity using the
[GSW toolkit](https://teos-10.github.io/GSW-Python/), evaluated at a
nominal lon/lat location (config options `overflow:nominal_lon` and
`overflow:nominal_lat`, both defaulting to 0 degrees) since the planar
mesh has no geographic location.  The Polaris-side (diagnostic) density
uses TEOS-10 for both models; this is a documented approximation of
MPAS-Ocean's Jackett-McDougall EOS, acceptable because neither model
reads the initial density.

## forcing

N/A

## vertical mixing

The tasks run with constant background vertical mixing (diffusivity
1.0e-5 m$^2$/s, viscosity 1.0e-4 m$^2$/s).  Convective and shear mixing
are disabled: the compass version of this test also used convective
mixing, but this test should not produce convection, so background
mixing suffices.  MPAS-Ocean uses CVMix (the `constant` background
scheme); Omega uses its implicit `VertMix` background mixing, which is
equivalent for this configuration.

Both models run with explicit bottom drag (drag coefficient 0.01).  For
Omega, the bottom-drag tendency is enabled through the mapped MPAS-Ocean
debug flag `config_disable_vel_explicit_bottom_drag = false`, an interim
approach until Omega supports implicit bottom drag.  Compared with the
compass version of this test, split-explicit time stepping and implicit
bottom drag remain disabled because they are not yet available in Omega:
the tasks use the RK4 time integrator, and implicit bottom drag will be
enabled in both models once Omega supports it.

## config options

These config options are common to all overflow tests:

```cfg
# Options related to the overflow case
[overflow]

# Time integration scheme
time_integrator = RK4

# Timestep per km horizontal resolution (s)
dt_per_km = 7.5

# Barotropic timestep per km horizontal resolution (s)
btr_dt_per_km = 2.5

# The width of the domain in the across-slope dimension (km)
ly = 40

# The length of the domain in the along-slope dimension (km)
lx = 200

# Distance from two cell centers (km)
resolution = 2.0

# Bottom depth at bottom of overflow
max_bottom_depth = ${vertical_grid:bottom_depth}

# Shelf depth (m)
shelf_depth = 500.0

# Cold water range (km)
x_dense = 20.0

# Lateral position of the shelf-break (km)
x_slope = 40.0

# Length-scale of the slope (km)
L_slope = 7.0

# Constant salinity (PSU)
salinity = 35.0

# Lower temperature (deg C)
lower_temperature = 10.0

# Higher temperature (deg C)
higher_temperature = 20.0

# Default viscosity (m^2/s)
default_viscosity = 1000.0

# Default biharmonic (del4) viscosity (m^4/s), scaled ~ dx^3 for 2 km resolution
default_del4_viscosity = 5.0e7

# Default horizontal advection order
default_horiz_adv_order = 2
```

The two `linear` trees use the shared linear EOS from
`polaris.ocean.eos` `linear.cfg` (see the `[ocean]` config section), which
is convenient for computing RPE.  The `nonlinear` tree instead uses the
shared `teos10.cfg`, which sets `eos_type = teos-10` (mapped to
Jackett-McDougall for MPAS-Ocean).

## cores

The number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file.

## smoke_test

### description

There are three smoke test cases corresponding to horizontal advection orders
2, 3, and 4: `smoke_test_horiz_adv_order_2`, `smoke_test_horiz_adv_order_3`,
and `smoke_test_horiz_adv_order_4`. Each smoke test is the same as described
above except the run is stopped before it is allowed to reach equilibrium to
facilitate rapid testing. The horizontal advection order is controlled by the
`horiz_adv_order` argument to the `SmokeTest` task and passed through to the
forward step.

### mesh

See {ref}`ocean-overflow`.

### vertical grid

See {ref}`ocean-overflow`.

### initial conditions

See {ref}`ocean-overflow`.

### forcing

See {ref}`ocean-overflow`.

### time step and run duration

The time step for forward integration is set by `dt_per_km` and the model
resolution. The run duration is 12 minutes.

### config options

The config options specific to the smoke test cases are:

```cfg
[overflow_smoke_test]

# Run duration
run_duration = 12.

run_duration_units = minutes

# Output interval
output_interval = 1.

output_interval_units = seconds
```

### cores

See {ref}`ocean-overflow`.

## rpe

### description

The `rpe` case is similar to the smoke tests except it runs to 40 days by which
time the dense blob is mostly at depth. It also includes several forward runs
corresponding to different values of the Laplacian viscosity specified by the
config option `overflow_rpe:viscosities`. The analysis step is a substitute for the viz step as
it includes the same cross-section visualizations of temperature but also
includes a computation and plot of the evolution of the Resting Potential
Energy (RPE) for each forward run.

```{image} images/overflow-rpe-sections.png
:align: center
:width: 500 px
```

```{image} images/overflow-rpe-t.png
:align: center
:width: 500 px
```

### config options

The config options specific to the RPE case are:

```cfg
[overflow_rpe]

# Run duration
run_duration = 40.

run_duration_units = days

# Output interval
output_interval = 6.

output_interval_units = hours

# Viscosity values to test for rpe test case
viscosities = 1, 5, 10, 100, 1000

# The time at which to plot cross-sections in the analysis step (days)
plot_time = ${overflow_rpe:run_duration}

# min and max temperature range for transect plots
min_temp = ${overflow:lower_temperature}
max_temp = ${overflow:higher_temperature}
```

Note that in the `nonlinear` tree, the RPE analysis sorts the in-situ
density from a nonlinear EOS, so the result is only an approximate RPE
measure (with a nonlinear EOS, the potential energy of the sorted state
depends on the pressure at which density is evaluated).
