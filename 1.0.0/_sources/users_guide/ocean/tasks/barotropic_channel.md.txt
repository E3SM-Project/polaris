(ocean-barotropic-channel)=

# barotropic channel

This test group is unified by being a singly-periodic domain with barotropic dynamics.
It is primarily designed to test lateral boundary conditions and can be configured to
be very computationally lightweight. A visualization step is included with the primary
purpose of inspecting the relative vorticity field at boundary vertices to verify
correct implementation of free slip boundary conditions, which would not be a source
of vorticity. The test group may also be useful in testing algorithms at the limit of
3 cells between boundaries such as occurs in narrow passages in the global ocean.

## suppported models

These tasks support both MPAS-Ocean and Omega.

## mesh

The mesh is planar with periodicity in the x direction and no-flow boundary condition
in the y direction. The default horizontal resolution is 10km, set by
cfg option `barotropic_channel:resolution` and the default dimensions are 100km by 30km, set by
cfg options `barotropic_channel:lx` and `barotropic_channel:ly`.

## vertical grid

The test case is currently hard coded to have a bottom depth equal to 2/3
times the cfg option `vertical_grid:bottom_depth` for all cells along the non-
periodic boundary and `vertical_grid:bottom_depth` for all other cells.

The default coordinate type given by cfg option `vertical_grid:coord_type` is
z-level so that layers terminate against the non-periodic boundary to test how
terms handle this condition.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 3

# Depth of the bottom of the ocean
bottom_depth = 100.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

## initial conditions

The velocity field is spatially uniform and set according to cfg options
`barotropic_channel:zonal_velocity` and `barotropic_channel:meridional_velocity`.

Temperature and salinity are spatially uniform and hard-coded to
1 degC and 35 PSU. These fields do not play a role in the dynamics. 

## forcing

This test case is forced by a spatially-uniform wind field of magnitude
determined by cfg options `barotropic_channel:zonal_wind_stress` and
`barotropic_channel:meridional_wind_stress`.

## time step and run duration

The time step for forward integration is 1 minute and the duration is 10 days.

## config options

```cfg
[barotropic_channel]

# the size of the domain in km in the x and y directions
ly = 30.0
lx = 100.0

zonal_velocity = 0.0
meridional_velocity = 0.0

zonal_wind_stress = 0.1
meridional_wind_stress = 0.0

resolution = 10.

horizontal_viscosity = 1.e-2

bottom_drag = 1.e2
```

## cores

The number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file.

(ocean-barotropic-channel-default)=

## default

### description

The default test case runs the `init`, `forward`, and `viz` steps and uses the
same config options as the test group.

