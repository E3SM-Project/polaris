(ocean-ice-shelf-2d)=

# ice shelf 2d

## description

The ``ice_shelf_2d`` tasks describe a series of very simplified ice-shelf test
cases where topography and initial conditions only vary in the y direction.
The Coriolis parameter `f` is zero.  This makes the test case quasi-two-
dimensional, with negligible variability in x.

Polaris includes three test cases, a default case, a restart case, and the
default case with visualization. Each case includes an `init` step to set up
the mesh and initial condition, a series of `ssh_adjustment` steps (see
{ref}`ocean-ssh-adjustment`), and a forward step. Some cases include additional
steps, described below.

All test cases include a relatively strenuous, iterative process to
dynamically adjust `landIcePressure` or `ssh` to be compatible with one
another in the `ssh_adjustment` steps. In this test case, we perform 10
iterations of adjustment, enough that changes in pressure should be quite
small compared to those in the first iteration. Reducing the number of
iterations will make the test case run more quickly at the risk of
having longer-lived transients at the beginning of the simulation.

```cfg
# Options related to ssh adjustment steps
[ssh_adjustment]

# Number of ssh adjustment iterations
iterations = 10

# Output interval for the ssh adjustment phase in hours
output_interval = 1.0

# Run duration of each ssh adjustment phase in hours
run_duration = 1.0

# Whether to adjust land ice pressure or SSH
adjust_variable = land_ice_pressure

# Time integration scheme
time_integrator = split_explicit

# Time step in seconds as a function of resolution
rk4_dt_per_km = 10

# Time step in seconds as a function of resolution
split_dt_per_km = 10

# Time step in seconds as a function of resolution
btr_dt_per_km = 2.5
```

If a baseline run of the test case was provided for comparison, we perform
validation of both the prognostic variables (layer thickness, velocity,
temperature and salinity) and a large number of variables associated with
freshwater and heat fluxes under ice shelves.

Frazil-ice formation is not included in the `ssh_adjustment` steps but is
included in the `forward` step of this test case.

## mesh

The test case currently supports only 5-km horizontal resolution. The x
direction is periodic and only 10 cells wide, whereas the y direction has
solid boundaries and is 44 cells long.  These dimensions are set in the config
file by `lx` and `ly`.

## vertical grid

The conceptual overlying ice shelf is described by a piecewise linear function.
The config options `y1`, `y2`, and `y3` dictate the inflection points in the
piecewise function and `y1_water_column_thickness` and
`y2_water_column_thickness` dictate the water column thickness at those
locations. The water column thickness at `y3` is always equal to the bottom
depth, indicating the ice shelf front location. By default, the ice shelf
depresses the sea surface height by as much as
1040 m (leaving a 10-m water column) for the first 30 km in y.  Over the next
30 km, it rises to 200 m, then fairly abruptly to zero over the next 15 km,
where it remains for the second half of the domain.  The ice shelf occupies
these first 75 km of the domain: fluxes from ice-shelf melting are only applied
in this region.

```{image} images/ice_shelf_2d.png
:width: 500 px
:align: center
```

The geometry does not represent a particularly realistic ice-shelf cavity but
it is a quick and useful test of the parameterization of land-ice melt fluxes
and of frazil formation below ice shelves.

Two vertical coordinates, `z-star` and `z-level`, are available. In each case, there are 20 vertical levels given by the config option `vert_levels`. In the open ocean, each level is 50 m thick.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 20

# The minimum number of vertical levels
min_vert_levels = 3

# Depth of the bottom of the ocean
bottom_depth = 2000.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = partial

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

# The minimum layer thickness in m
min_layer_thickness = 0.0
```

## initial conditions

The initial temperature for the whole domain is constant (1 degree Celsius),
while salinity varies linearly with depth from 34.5 PSU at the sea surface
to 34.7 PSU at the sea floor, which is at a constant at 2000 m depth. These
initial conditions can be modified with config options `temperature`,
`surface_salinity`, and `bottom_salinity` 

## forcing

N/A

## time step and run duration

The time step is determined by the config options `dt_per_km` so that the time
step is proportional to the resolution. By default, a 10 km-resolution test
has a time step of 5 min. Run duration will be specified for each test case.
Run duration will be discussed for individual test cases.

## config options

```cfg
# config options for 2D ice-shelf testcases
[ice_shelf_2d]

# width of domain in km
lx = 50

# length of domain in km
ly = 220

# How the land ice pressure at y<y1 is determined
y0_land_ice_height_above_floatation = 0.

# Temperature of the surface in the northern half of the domain
temperature = 1.0

# Salinity of the water in the entire domain
surface_salinity = 34.5

# Salinity of the water in the entire domain
bottom_salinity = 34.7

# Coriolis parameter
coriolis_parameter = 0.

# GL location in y in km
y1 = 30.0

# ice shelf inflection point in y in km
y2 = 90.0

# ice shelf front location in y in km
y3 = 90.0

# Vertical thickness of ocean sub-ice cavity at GL
y1_water_column_thickness = 10.0

# Vertical thickness of water column thickness at y2
y2_water_column_thickness = 1050.0
```

You can modify the horizontal mesh, vertical grid, geometry, and initial
temperature and salinity of the test case by altering these options.

(ocean-ice-shelf-2d-default)=

## default

### description

`ocean/planar/ice_shelf_2d/${RES}/default` is the default version of the
ice shelf 2-d test case for a short (10 min) test run and validation of
prognostic variables for regression testing.  

### mesh

See {ref}`ocean-ice-shelf-2d`.

### vertical grid

See {ref}`ocean-ice-shelf-2d`.

### initial conditions

See {ref}`ocean-ice-shelf-2d`.

### forcing

See {ref}`ocean-ice-shelf-2d`.

### time step and run duration

The time step is configured by `ice_shelf_2d_default:rk4_dt_per_km` or
`ice_shelf_2d_default:split_dt_per_km` and `ice_shelf_2d_default:btr_dt_per_km`
depending on the time integration scheme given by `ice_shelf_2d:time_integrator`.
The run duration is determined by the config option `forward_run_duration` and
is 10 minutes by default.

### config options

See {ref}`ocean-ice-shelf-2d` for config options used by all `ice_shelf_2d`
test cases.

```cfg
# Options specific to the ice_shelf_2d/default case
[ice_shelf_2d_default]

# Time integration scheme
time_integrator = split_explicit

# Run duration of the forward step in minutes
forward_run_duration = 10.0

# Time step in seconds as a function of resolution
rk4_dt_per_km = 60

# Time step in seconds as a function of resolution
split_dt_per_km = 60

# Time step in seconds as a function of resolution
btr_dt_per_km = 10
```

### cores

The number of processors is hard-coded to be 4 for this case.

## default_with_restart

### description

`ocean/planar/ice_shelf_2d/$RES/default/with_restart` runs a short (10 min)
integration of the model forward in time (`forward` step), saving a restart
file every time step.  Then, a second run (`restart` step) is performed
from the restart file 5 minutes into the simulation.
Prognostic variables, variables related to
sub-ice-shelf fluxes, and variables related to frazil formation are compared
between the "full" and "restart" runs at minute 10 of the simulation to
make sure they are bit-for-bit identical.

### mesh

See {ref}`ocean-ice-shelf-2d`.

### vertical grid

See {ref}`ocean-ice-shelf-2d`.

### initial conditions

See {ref}`ocean-ice-shelf-2d`.

### forcing

See {ref}`ocean-ice-shelf-2d`.

### time step and run duration

The time step is the same as {ref}`ocean-ice-shelf-2d-default`. The full run is
ten minutes as given by `ice_shelf_2d_default:forward_run_duration`
and the restart run is half the duration of the full run.

### config options

See {ref}`ocean-ice-shelf-2d` and .

### cores

See {ref}`ocean-ice-shelf-2d-default`.

## default_tidal_forcing

### description

`ocean/planar/ice_shelf_2d/5km/default` is the default version of the
ice shelf 2-d test case for a short (10 min) test run and validation of
prognostic variables for regression testing.  

### mesh

See {ref}`ocean-ice-shelf-2d`.

### vertical grid

See {ref}`ocean-ice-shelf-2d`.

### initial conditions

See {ref}`ocean-ice-shelf-2d`.

### forcing

This test has tidal forcing at the open ocean boundary in the y-dimension. The
amplitude and period of the tidal forcing are set at test case set-up to be 1 m
and 10 days, respectively, but may be changed by the user in the namelist at
runtime.

### time step and run duration

Determined by config options in the `ice_shelf_2d_default_tidal_forcing`
section described below.

### config options

See {ref}`ocean-ice-shelf-2d` for config options used by all `ice_shelf_2d`
test cases.

```cfg
# Options specific to the ice_shelf_2d/default_tidal_forcing case
[ice_shelf_2d_default_tidal_forcing]

_tidal_forcing# Time integration scheme
time_integrator = RK4

# Run duration of the forward step in days
forward_run_duration = 0.01

# Time step in seconds as a function of resolution
rk4_dt_per_km = 5

# Time step in seconds as a function of resolution
split_dt_per_km = 5

# Time step in seconds as a function of resolution
btr_dt_per_km = 1
```

### cores

See {ref}`ocean-ice-shelf-2d-default`.

