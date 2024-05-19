(ocean-drying-slope)=

# drying slope

The drying_slope tasks test wetting-and-drying algorithms in domains designed
to represent a coastline with sloping bathymetry.

## config options

There are a number of config options that are common to all drying_slope tasks:

```cfg
# config options for all drying slope test cases
[drying_slope]

# time integration scheme
time_integrator = RK4

# time step per resolution (s/km), since dt is proportional to resolution
rk4_dt_per_km = 30

split_dt_per_km = 30

# barotropic time step per resolution (s/km), since btr_dt is proportional to
# resolution
btr_dt_per_km = 1.5

# Coriolis parameter
coriolis_parameter = 0.0
```

(ocean-drying-slope-baroclinic)=

## baroclinic

The baroclinic drying_slope task is designed to test wetting-and-drying
algorithms in a multi-layer configuration with vertial gradients in scalars.

### description

Description of the test case. Images that show the test case configuration or
results are particularly welcome here.

```{image} images/cosine_bell_convergence.png
:align: center
:width: 500 px
```

### mesh

Specify whether the mesh is global or planar and the resolution(s) tested. If
planar, specify the mesh size. If global, specify whether the mesh is
icosohedral or quasi-uniform. Specify any relevant options in the config file
pertaining to setting up the mesh.

### vertical grid

If there are no restrictions on the vertical grid specifications inherent to
the test case, then the config section may be provided without any further
description.

Examples of restrictions or special conditions warranting description may
include:

* Whether the topography is variable
* Whether the test pertains to shallow water dynamics, in which case the
minimum number of vertical levels may be used
* Whether there are several test cases in the test group investigating the
effects of different vertical coordinates (`coord_type`)

The minimum layer thickness for this case is determined by the minimum column thickness
from the config option `drying_slope_baroclinic:min_column_thickness`.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = sigma

# Number of vertical levels
vert_levels = 10

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

# The minimum number of vertical levels for multi-layer cases
min_vert_levels = 3

# Minimum thickness of each layer
min_layer_thickness = ${drying_slope_barotropic:thin_film_thickness}
```

### initial conditions

The initial conditions should be specified for all variables requiring
initial conditions (see {ref}`dev-ocean-models`).

### forcing

If applicable, specify the forcing applied at each time step of the simulation
(in MPAS-Ocean, these are the variables contained in the `forcing` stream).
If not applicable, keep this section with the notation N/A.

### time step and run duration

The time step for forward integration should be specified here for the test
case's resolution. The run duration should also be specified.

### config options

The config options define the geometry of the domain.

```cfg
# config options for barotropic drying slope test cases
[drying_slope_baroclinic]

# the width of the domain in km
lx = 12.

# the length of the domain in km
ly = 55.

# Length over which wetting and drying actually occur in km
ly_analysis = 50.

# Bottom depth at the right side of the domain in m
right_bottom_depth = 2.5

# Bottom depth at the left side of the domain in m
left_bottom_depth = 0.

# Initial SSH at the right side of the domain in m
right_tidal_height = 0.

# salinity at the right side of the domain
right_salinity = 35.0

# salinity at the left side of the domain
left_salinity = 1.0

# manning coefficient used in mannings bottom drag type
manning_coefficient = 5.0e-2

# The column thickness in the thin film region, used to determine thin film
# thickness
min_column_thickness = 0.05
```

Include here any further description of each of the config options.

### cores

Specify whether the number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file or whether the
default and minimum number of cores is given in arguments to the forward step,
and what those defaults are.

## barotropic

### vertical grid

The vertical grid is the same as baroclinic except a single layer may be used and
the minimum layer thickness given in `drying_slope_barotropic:thin_film_thickness`
is used.

### config options

The config options define the geometry of the domain.

```cfg
# config options for barotropic drying slope test cases
[drying_slope_barotropic]

# the width of the domain in km
lx = 6.

# Length over which wetting and drying actually occur in km
ly_analysis = 25.

# the length of the domain in km
ly = 28.

# Bottom depth at the right side of the domain in m
right_bottom_depth = -10.

# Bottom depth at the left side of the domain in m
left_bottom_depth = 0.

# Initial SSH at the right side of the domain in m
right_tidal_height = ${drying_slope_barotropic:right_bottom_depth}

# Plug width as a fraction of the domain
plug_width_frac = 0.0

# Plug temperature
plug_temperature = 20.0

# Background temperature
background_temperature = 20.0

# Background salinity
background_salinity = 35.0

# Thickness of each layer in the thin film region
thin_film_thickness = 1.0e-3
```

## convergence

### config options

The config options define the resolutions to use in the convergence test:

```cfg
# config options for drying slope convergence task
[drying_slope_convergence]

# horizontal resolutions in km
resolutions = 0.25, 0.5, 1, 2
```

