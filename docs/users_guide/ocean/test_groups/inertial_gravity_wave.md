(ocean-inertial-gravity-wave)=

# inertial gravity wave

The inertial gravity wave test group implements configurations for surface wave
propagation with the rotating, linear shallow water equations on a doubly
periodic domain. In this case there is an exact solution which can be used to
assess the numerical accuracy and convergence of the MPAS-Ocean discretization.
The implemenation is from
[Bishnu et al.(2023)](https://doi.org/10.22541/essoar.167100170.03833124/v1)

Currently, the test group contains one test case, which is a convergence test.

(ocean-inertial-gravity-wave-convergence)=

## convergence

### description

The `convergence` test case runs the inertial gravity wave simulation for 4
different resolutions: 200, 100, 50, and 25 km. Computes the error with respect
to the exact solution and calculates the convergence rate.

### mesh

For each resolution, the `initial_state` step generates and planar hexagonal
mesh that is periodic in both the x and y directions.

### vertical grid

Since this test case is a shallow water case, the vertical grid is set to a
single layer configuration.

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

### initial conditions

The initial conditions are set to the following:
$$
\eta = \\
u = \\
v = 
$$

### config options

The following config options are availiable for this case:

```cfg
[inertial_gravity_wave]

# The size of the domain in km in the x direction, (size in y direction =
# sqrt(3)/2*lx
lx = 10000

# The Corilois parameter (constant)
f0 = 1e-4

# Amplitude of the ssh initial condition
eta0 = 1.0

# Number of wavelengths in x direction
nx = 2 

# Number of wavelengths in y direction
ny = 2 

# Convergence threshold below which the test fails
conv_thresh = 1.8

# Convergence rate above which a warning is issued
conv_max = 2.2

```

### forward 

The forward step for each resolution runs the simulation for 10 hours. The
model is configured without vertical adection and mixing. No tracers are enabled
and the pressure gradient used is the gradient of the sea surface height.
Horizontal mixing and bottom friction are also neglected. The nonlinear momentum
terms are no included and the layer thickness equation is linearized.

### analysis

The analysis step computes 

### viz


 
