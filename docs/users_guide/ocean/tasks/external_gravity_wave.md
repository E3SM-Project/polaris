(ocean-external-gravity-wave)=

# external gravity wave

The external gravity wave task implements a test of an external gravity wave 
on a non-rotating aquaplanet.
The test is meant as a simple case on which the temporal convergence of
time-stepping schemes can be tested.
There is no exact solution, rather, for a given time-stepping scheme, the 
task calculates errors against a run with a time-step that is small 
relative to the time-steps used in subsequent runs.

Note that this is *not* a shallow water test case.
While the standard, non-linear shallow water thickness equation 
has been left alone, the normal velocity equation has had terms deleted so as
to only consider gravity wave effects. the resulting equations are given by
$$
\begin{align}
    &\partial_t \mathbf{u} = -g \nabla h \\
    &\partial_t h + \nabla \cdot (h\mathbf{u}) = 0.
\end{align}
$$

This is done to provide the simplest case on which to test the
convergence of a time-stepping scheme.
In particular, we use this task to test the convergence of local time-stepping
schemes (`LTS` and `FB_LTS`) that employ a operator splitting in which tendency 
terms other than those above are advanced with Forward Euler.
As a result, this task helps to show that these local time-stepping schemes 
are achieving the correct theoretical order of convergence is said splitting
was not used.

## description 

The `external_gravity_wave` task runs the external gravity wave simulation for
a number of user-defined time-steps in order to determine the order of temporal
convergence of the selected time-stepping scheme over those time-steps.
The first listed time-step should be very small relative to the proceeding
time-steps as the this will be used to produce a reference solution that the
other runs will be compared to.

This task implements separate cases for local and global time-stepping schemes.
Local time-stepping schemes require extra work during the init step that 
identifies each cell in the mesh with an appropriate label used during the
local time-stepping scheme.
These separate cases are identified by the appendices `_local_time_step`
and `_global_time_step` respectively.

The forward step runs the model for a given time-step. 

The analysis step calculates the L2-norm of the difference between the 
reference solution and model solution with the given time-steps
for both normal velocity and layer thickness.
This step then produces plots of the resulting temporal convergence.

## mesh

The init step generates both icosehedral and quasi-uniform meshes of the desired 
resolutions.

## vertical grid

This task is a single layer test case, so the vertical grid is set to a single 
layer configuration.

```cfg
[vertical_grid]

# The type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 1 

# Depth of the bottom of the ocean
bottom_depth = 1000.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

## initial conditions

The normal velocity is initialized to zero, while the layer thickness is set
to be a Gaussian bell centered at `lat_center = 0.0`, `lon_center = pi/2`,
with units in radians.
The exact form of the Gaussian bells is given by
$$ 
h = e^{ -100 \left( (x - \text{lat_center})^2 
                     + (y - \text{lon_center})^2 \right) } 
$$

## forcing 

N/A

## config options 

The following config options are available for this case:

```cfg

# config options for convergence forward steps
[convergence_forward]

# time integrator: {split_explicit, RK4, unsplit_explicit, split_implicit, split_explicit_ab2}
time_integrator = RK4

# time steps for temporal convergence test
# the first one is used for the reference solution
dt = 10.0, 120.0, 240.0, 480.0

# Run duration in hours
run_duration = 48.

# Output interval in hours
output_interval = 4.


# options for external gravity wave convergence test case
[gaussian_bump]

# the constant temperature of the domain
temperature = 15.0

# the constant salinity of the domain
salinity = 35.0

# the central latitude (rad) of the gaussian bump
lat_center = 0.0

# the central longitude (rad) of the gaussian bump
lon_center = 1.57079633

# convergence threshold below which the test fails
convergence_thresh = 1.8
```

## cores 

The number of cores is determined according to the config options 
`max_cells_per_core` and `goal_cells_per_core`.
