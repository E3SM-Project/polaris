(ocean-manufactured-solution)=

# manufactured solution

The manufactured solution tasks implement configurations for surface wave
propagation with the rotating, nonlinear shallow water equations on a doubly
periodic domain. These tasks are intended to utilize tendency terms embedded
in the forward ocean model in order to produce the manufactured solution. This
solution can be then used to assess the numerical accuracy and convergence of
the discretized nonlinear momentum equation. 

Currently, the there is only one task, the convergence test from
[Bishnu et al.(2023)](https://doi.org/10.22541/essoar.167100170.03833124/v1)

(ocean-manufactured-solution-convergence)=

## convergence

### description

The `convergence` test case runs the manufactured solution simulation for 4
different resolutions: 200, 100, 50, and 25 km.
 
The forward step for each resolution runs the simulation for 10 hours. The
model is configured without vertical advection and mixing. No tracers are enabled
and the pressure gradient used is the gradient of the sea surface height.
Horizontal mixing and bottom friction are also neglected.

The analysis step computes the root mean-square-error of the difference between
the simulated SSH field and the exact solution at the end of the simulation. It
also computes the convergence rate with resolution

The visualization step produces two plots: the convergence of the RMSE with
resolution and a plan-view of the simulated, exact, and (simulated-exact)
SSH fields.

### mesh

For each resolution, the `init` step generates and planar hexagonal
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
\eta = \eta_0 \sin(k_x x + k_y y - \omega t)\\
u = \eta_0 \cos(k_x x + k_y y - \omega t)\\
v = u
$$

### forcing

N/A

### time step and run duration

The time step is determined by the config option ``dt_per_km`` according to the
mesh resolution. The run duration is 10 hours.

### config options

The following config options are availiable for this case:

```cfg
[manufactured_solution]

# the size of the domain in km in the x and y directions
lx = 10000.0

# the coriolis parameter
coriolis_parameter = 1.0e-4

# the amplitude of the sea surface height perturbation
ssh_amplitude = 1.0

# Number of wavelengths in x direction
n_wavelengths_x = 2

# Number of wavelengths in y direction
n_wavelengths_y = 2

# Time step per resolution (s/km), since dt is proportional to resolution
dt_per_km = 3.0

# Convergence threshold below which the test fails
conv_thresh = 1.8

# Convergence rate above which a warning is issued
conv_max = 2.2
```

### cores

The number of cores is determined according to the config options
``max_cells_per_core`` and ``goal_cells_per_core``.
