(ocean-merry-go-round)=

# merry-go-round

The `ocean/merry_go_round` test group induces a convective cell in a horizontal
domain in order to verify tracer advection.

```{image} images/merry_go_round_section.png
:align: center
:width: 500 px
```

## supported models

These tasks only support MPAS-Ocean.

(ocean-merry-go-round-default)=

## default

### description

For the initial conditions described below, tracer concentration contours match
the streamlines of the convective cell, such that an accurate tracer advection
scheme would result in no change in the tracer field in time.

The init step generates the mesh and initial condition for the requested
resolution.

The forward step runs the model for the requested length of time. Tendencies
for normal velocity and layer thickness are disabled, such that these fields
remain fixed at their initial conditions throughout the simulation.

The visualization step produces a plot illustrating the horizontal velocity,
vertical velocity, simulated `tracer1` concentration, the error in simulated
tracer concentration at the end of the forward simulation.
(See above for an example).

### mesh
The mesh is planar and the resolution is specified by config option
`convergence:base_resolution`, which defaults to 5 m. The horizontal
dimensions of the domain are set by config options `merry_go_round:lx` and
`merry_go_round:ly`, defaulting to 500 m by 5 m. The domain is solid on the
zonal boundaries and periodic on the meridional boundaries.

### vertical grid

The vertical coordinate is fixed throughout the simulation.

```cfg
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels for base resolution
vert_levels = 50

# Depth of the bottom of the ocean
bottom_depth = 500.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

### initial conditions

Salinity is constant throughout the domain as specified by
`merry_go_round:salinity_background`, which defaults to 35 PSU. The initial
temperature is high on the right side (`merry_go_round:temperature_right`) of
and low on the left side (`merry_go_round:temperature_left`) of the domain,
with defaults of 30 degC and 5 degC respectively. This field initiates
a convective cell in the zonal and vertical dimensions. Debug tracer, `tracer1`
, is initialized with a high value in the center of domain and gradually
transitions to a lower value at the edges of the domain.

### forcing
N/A

### time step and run duration

The time step is determined by the config option `merry_go_round:dt_per_km`
according to the mesh resolution (i.e. `convergence:base_resolution`).
The run duration is determined by the config option
`merry_go_round:run_duration` as measured in hours.

### config options

The following config options are available for this case:

```cfg
[merry_go_round]

# the size of the domain in km in the x direction
lx = 0.5

# the size of the domain in km in the y direction
ly = 0.005

# temperature on the right of the domain
temperature_right = 30.

# temperature on the left of the domain
temperature_left = 5.

# background salinity
salinity_background = 35.

# background tracer2 concentration
tracer2_background = 10.

# background tracer3 concentration
tracer3_background = 20.

# Time step per resolution (s/km), since dt is proportional to resolution
dt_per_km = 72000.0

# Convergence threshold below which the test fails
conv_thresh = 1.2

# Run duration in hours
run_duration = 6.
```

### cores

The number of cores is determined according to the config options
``max_cells_per_core`` and ``goal_cells_per_core``.

(ocean-merry-go-round-convergence)=

## convergence tasks

There are three versions of the convergence test case: `convergence_space`,
`convergence_time`, and `convergence_both` corresponding to space, time, and
space and time convergence tests. All settings are the same as the
{ref}`ocean-merry-go-round-default` case, but now the resolution and/or time step
are refined to asses the order of convergence for tracer advection. Tests
involving spatial convergence have a horizontal resolution of
`convergence:base_resolution` times `convergence:refinement_factors_space`.
Tests involving just temporal convergence use the parameter
`merry_go_round:dt_per_km` at the `convergence:base_resolution` multiplied by
`convergence:refinement_factors_time`. Tests invoking both spatial and temporal
convergence do both types of refinement described above simultaneously (see
{ref}`dev-ocean-convergence` for more details on how to change resolutions or
time steps tested).

The init and forward steps are analogous to what is described above for
{ref}`ocean-merry-go-round-default`.

The analysis step computes the `convergence:error_type` of your choosing,
between the simulated `tracer1` field and the exact solution at the end
of the simulation. Because tracer concentration contours match the streamlines
of the convective cell the exact solution is equivalent to the initial
condition. It also computes the convergence rate with resolution and/or
time step, producing a plot like:

```{image} images/merry_go_round_convergence.png
:align: center
:width: 500 px
```
The visualization step plot the numerical solution, exact solution, and their
difference for each resolution and/or time step simulated.
