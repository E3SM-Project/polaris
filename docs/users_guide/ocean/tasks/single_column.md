(ocean-single-column)=

# single column

## description

The `single_column` tasks include any ocean tests of the vertical ocean 
dynamics.

## mesh

The mesh is planar and spans the minimum number of cells (16 for MPAS-Ocean).
The config options `lx` and `ly` are given arbitrarily small values of 1 m in
order to ensure that the minimum number of cells is chosen.

By virtue of testing the vertical dynamics, these tests should be insensitive
to the horizontal resolution. As such, only 10 km horizontal resolution is
currently supported.

## vertical grid

Currently, these tests feature a very fine vertical resolution of 4 m
with 100 vertical levels. Future work may want to examine vertical mixing or
advection at typical vertical resolutions.

## config options

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 100

# Depth of the bottom of the ocean
bottom_depth = 400.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

## initial conditions

The temperature and salinity profiles are defined using the following equations:

$$
\Phi(z) = \begin{cases}
    \Phi_0 &\text{ if } z = z[0]\\
    \Phi_0 + {d\Phi/dz}_{ML} z &
    \text{ if } z > z_{MLD}\\
    (\Phi_0 + {\Delta\Phi}_{ML}) + {d\Phi/dz}_{int} (z - z_{MLD}) &
    \text{ if } z \le z_{MLD}
\end{cases}
$$

where $\Phi_0 = $`surface_X`, ${d\Phi/dz}_{ML} = $`X_gradient_mixed_layer`,
$z_{MLD} = -$`mixed_layer_depth_X`, ${\Delta\Phi}_{ML} = $
`X_difference_across_mixed_layer`, and ${d\Phi/dz}_{int} = $
`X_gradient_interior`. `X` in the config options above is either `temperature`
or `salinity`.

The water column is initially stationary (`normalVelocity`$=0$).

The Coriolis parameter is spatially constant and set equal to
`coriolis_parameter`.

## config options

```cfg
# config options for single column testcases
[single_column]

# size of the domain (typically the minimum allowed size of 4x4 cells)
nx = 4
ny = 4

# resolution in km
resolution = 960.0

# Surface temperature
surface_temperature = 20.0

# Temperature gradient in the mixed layer in degC/m
temperature_gradient_mixed_layer = 0.0

# The temperature below the mixed layer
temperature_difference_across_mixed_layer = 0.0

# Temperature gradient below the mixed layer
temperature_gradient_interior = 0.01

# Depth of the temperature mixed layer
mixed_layer_depth_temperature =  25.0

# Surface salinity
surface_salinity = 35.0

# Salinity gradient in the mixed layer in PSU/m
salinity_gradient_mixed_layer = 0.0

# The salinity below the mixed layer
salinity_difference_across_mixed_layer = 1.0

# Salinity gradient below the mixed layer
salinity_gradient_interior = 0.0

# Depth of the salinity mixed layer
mixed_layer_depth_salinity = 0.0

# coriolis parameter
coriolis_parameter = 1.0e-4
```

See mesh section for a description of `lx` and `ly` and initial conditions section for a description of the remaining config options.

(ocean-single-column-cvmix)=

## cvmix

### description

The `cvmix` test exercises the [CVMix](https://github.com/CVMix/CVMix-src)
schemes for vertical mixing. 

The temperature and salinity profiles only evolve a small amount over the 1-
day duration of the test, so the 10-day profiles are shown here:

```{image} images/single_column_temperature_10day.png
:align: center
:width: 200 px
```
```{image} images/single_column_salinity_10day.png
:align: center
:width: 200 px
```

The namelist options for this test case dictate that the KPP scheme is tested.

### mesh

See {ref}`ocean-single-column`.

## vertical grid

See {ref}`ocean-single-column`.

### initial conditions

See {ref}`ocean-single-column`.

### forcing

The cvmix case has both surface forcing and restoring, which are controlled by
the following config options:

```cfg
# config options for forcing single column testcases
[single_column_forcing]

# Piston velocity to control rate of restoring toward temperature_surface_restoring_value
temperature_piston_velocity = 4.0e-6

# Piston velocity to control rate of restoring toward salinity_surface_restoring_value
salinity_piston_velocity = 4.0e-6

# Temperature to restore towards when surface restoring is turned on
temperature_surface_restoring_value = 15.0

# Salinity to restore towards when surface restoring is turned on
salinity_surface_restoring_value = 36.0

# Rate at which temperature is restored toward the initial condition
temperature_interior_restoring_rate = 1.0e-6

# Rate at which salinity is restored toward the initial condition
salinity_interior_restoring_rate = 1.0e-6

# Net latent heat flux applied when bulk forcing is used. Positive values indicate a net
# input of heat to ocean
latent_heat_flux = -50.0

# Net sensible heat flux applied when bulk forcing is used. Positive values indicate a
# net input of heat to ocean
sensible_heat_flux = -25.0

# Net solar shortwave heat flux applied when bulk forcing is used. Positive values
# indicate a net input of heat to ocean
shortwave_heat_flux = 200.0

# Net surface evaporation when bulk forcing is used. Positive values indicate a net
# input of water to ocean
evaporation_flux = 6.5E-4

# Net surface rain flux when bulk forcing is used. Positive values indicate a net input
# of water to ocean
rain_flux = 0.0

# Zonal surface wind stress over the domain
wind_stress_zonal = 0.1

# Meridional surface wind stress over the domain
wind_stress_meridional = 0.0
```

### time step and run duration

The time step is given as 10 min and the barotropic time step is 30s. The run
duration is 1 day.

### config options

See {ref}`ocean-single-column`. Currently, config options are only given in the
shared framework.

### cores

Both default and minimum number of cores are hard-coded as 1 given that the
domain is only 16 cells.

(ocean-single-column-ideal-age)=

## ideal age

The `ideal age` test exercises the ideal age tracers.

### description

Temperature and salinity profiles evolve in the same way as in the 
{ref}`ocean-single-column-cvmix` test case. 10-day profiles for the ideal age 
tracer are as follows:

```{image} images/single_column_ideal_age_tracer_10day.png
:align: center
:width: 200 px
```

### mesh

See {ref}`ocean-single-column`.

### vertical grid

See {ref}`ocean-single-column`.

### initial conditions

`idealAgeTracers` is initialized as zero seconds throughout the water column.

### forcing

`idealAgeTracers` is set to zero seconds within the first surface grid layer at
every time step.

### time step and run duration

See {ref}`ocean-single-column-cvmix`.

### config options

See {ref}`ocean-single-column`. Currently, config options are only given in the
shared framework.

### cores

See {ref}`ocean-single-column-cvmix`.