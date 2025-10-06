(ocean-seamount)=

# seamount

The ``ocean/seamount`` test is a standard sigma coordinate test problem, which is documented in [Haidvogel and Beckmann (1993)](https://journals.ametsoc.org/view/journals/phoc/23/11/1520-0485_1993_023_2373_nsofaa_2_0_co_2.xml) and [Shchepetkin and McWilliams (2003)](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2001JC001047). This case tests the error due to pressure gradients in tilted layers. 

## suppported models

These tasks support only MPAS-Ocean.

(ocean-seamount-default)=

## default task

### description

The test case begins with a zero velocity field and is unforced, so the exact solution is to remain motionless. 
The seamount rises from a flat sea floor in the center of the domain. 
In a pure z-level vertical coordinate without partial bottom cells, the pressure gradient will remain zero to machine precision and induce no flow. When any layer tilting is added, including from partial bottom cells, some flow is introduced by the pressure gradient error. This is fundamentally because the pressure must be extrapolated vertically at cell centers to the mid-depth of the edge.

```{image} images/seamount_initial_temperature.png
:align: center
:width: 500 px
```

### mesh

The domain is planar and periodic on the zonal boundaries and solid on the
meridional boundaries. Only 5km resolution is tested by default, but the
resolution may be changed with the ``resolution`` config option. The domain is
20km by 250km, as given by the config options ``lx`` and ``ly``.

### vertical grid

There are no restrictions on the vertical grid inherent to the test case except
that there should be sufficient vertical levels to capture the stratification
structure.

```cfg
# Options related to the vertical grid
[vertical_grid]

# Depth of the bottom of the ocean (m)
bottom_depth = 5000.0

# Number of vertical levels
vert_levels = 10

# The type of vertical grid
grid_type = uniform

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None
```

### initial conditions

Salinity is constant throughout the domain at the value given by the config
option ``background_salinity`` (35 PSU by default).  The initial temperature
has a linear background stratification from 20.1 degrees C (config option
``surface_temperature``) to 10.1 degrees C (config option
``bottom_temperature``). There is a sinusoidal perturbation in the center of
the domain with amplitude given by the config option
``temperature_difference``, 2 degrees C by default. The width of the
perturbation is given by 2 times the config option ``amplitude_width_dist`` or
2 times the ``amplitude_width_frac`` times ``ly``.

### forcing

N/A

### time step and run duration

The time step for forward integration is 5 minutes. The run duration is 3 time steps.

```cfg
[seamount_default]

# Run duration (minutes)
run_duration = 12.

# Output interval (seconds)
output_interval = 1.
```

### config options

The following config section is specific to this test case:

```cfg
# Options related to the seamount case
[seamount]

# Timestep per km horizontal resolution (s)
dt_per_km = 10.

# Barotropic timestep per km horizontal resolution (s)
btr_dt_per_km = 2.5

# The width of the domain in the across-slope dimension (km)
ly = 320

# The length of the domain in the along-slope dimension (km)
lx = 320

# Distance from two cell centers (km)
resolution = 6.7

# Bottom depth at bottom of seamount
max_bottom_depth = ${vertical_grid:bottom_depth}

# Logical flag that controls how the vertical profile of tracers.  See Beckmann and Haidvogel 1993 eqn 15-16 (unitless)
# possible_values="linear, exponential"
seamount_stratification_type = exponential

# Density coefficient for linear vertical stratification (kg m^{-3})
seamount_density_coef_linear = 1024.0

# Density coefficient for exponential vertical stratification (kg m^{-3})
seamount_density_coef_exp = 1028.0

# Density gradient for linear vertical stratification, Delta_z rho in Beckmann Haidvogel eqn 15 (kg m^{-3})
seamount_density_gradient_linear = 0.1

# Density gradient for exponential vertical stratification, Delta_z rho in Beckmann Haidvogel eqn 16 (kg m^{-3})
seamount_density_gradient_exp = 3.0

# Density reference depth for linear vertical stratification (m)
seamount_density_depth_linear = 4500.0

# Density reference depth for exponential vertical stratification (m)
seamount_density_depth_exp = 500.0

# Density reference for eos to initialize temperature (kg m^{-3})
seamount_density_ref = 1028.0

# Reference temperature for eos to initialize temperature (C)
seamount_density_Tref = 5.0

# Linear thermal expansion coefficient to initialize temperature (kg m^{-3} C^{-1})
seamount_density_alpha = 0.2

# Height of sea mount, H_0 (m)
seamount_height = 4500.0

# Width parameter of sea mount, e-folding length (m)
seamount_width = 40.0e3

# Salinity of the water in the entire domain (PSU)
constant_salinity = 35.0

# Coriolis parameter for entire domain (s^{-1})
coriolis_parameter = -1.0e-4
```

### cores

The number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file.

