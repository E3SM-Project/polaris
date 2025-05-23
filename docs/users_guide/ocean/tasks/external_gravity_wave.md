(ocean-external-gravity-wave)=

# external gravity wave

The `external_graivty_wave_*_time_step/convergence_time` tasks implement a
simple external gravity wave test case evaluate the time-convergence of
time-stepping schemes in the simplest possible model configuration.

Note that this is *not* a shallow water test case.
While the standard, non-linear shallow water thickness equation 
has been left alone, all tendencies in the  momentum equation have been turned
off, save the pressure gradient term. The resulting equations are given by
$$
\begin{align}
    &\partial_t \mathbf{u} = -g \nabla h \\
    &\partial_t h + \nabla \cdot (h\mathbf{u}) = 0 \,.
\end{align}
$$

In particular, this task is used to  test the convergence of local 
time-stepping schemes (`LTS` and `FB_LTS`) that employ a operator splitting
in which tendency terms other than those above are advanced with
a first-order error. As a result, this task helps to show that these local
time-stepping schemes are achieving the correct theoretical order of
convergence is said splitting was not used.

To calculate errors, the task runs the case once at a small time-step
to generate a reference solution. The result of the `analysis` step of each
task is a plot like the following showing convergence
as a function of the cell size and/or the time step:

```{image} images/external_graivty_wave_convergence.png
:align: center
:width: 500 px
```

## supported models

These tasks currently only support MPAS-Ocean.

(ocean-external-gravity-wave-mesh)=
## mesh

Two global mesh variants are tested, quasi-uniform (QU) and icosohydral. In 
addition, the tests can be set up to use either local or global time-stepping
methods. Thus, there are 4 variants of the task:
```
ocean/spherical/icos/external_gravity_wave_global_time_step/convergence_time
ocean/spherical/icos/external_gravity_wave_local_time_step/convergence_time
ocean/spherical/qu/external_gravity_wave_global_time_step/convergence_time
ocean/spherical/qu/external_gravity_wave_local_time_step/convergence_time
```
The default resolutions used in the task depends on the mesh type.

For the `icos` mesh type, the default is 60, as determined
by the following config option. See {ref}`dev-ocean-convergence` for more
details.

```cfg
# config options for spherical convergence tests
[spherical_convergence]

# The base resolution for the icosahedral mesh to which the refinement
# factors are applied
icos_base_resolution = 60.
```

For the `qu` mesh type, it is 120 km as
determined by the following config option:

```cfg
# config options for spherical convergence tests
[spherical_convergence]

# The base resolution for the quasi-uniform mesh to which the refinement
# factors are applied
qu_base_resolution = 120.

# a list of quasi-uniform mesh resolutions (km) to test
qu_refinement_factors = 0.5, 0.75, 1., 1.25, 1.5, 1.75, 2.
```

To alter the resolutions used in the convergence tasks, you will need to create
your own config file (or add a `spherical_convergence` section to a config file
if you're already using one).  If you specify a different resolution
before setting up `external_graivty_wave`, steps will be generated with
the requested resolution (if you alter `icos_resolutions` or `qu_resolutions`
in the task's config file in the work directory, nothing will happen).
For `icos` meshes, make sure you use a resolution close to those listed in
{ref}`dev-spherical-meshes`. Each resolution will be rounded to the nearest
allowed icosahedral resolution.

The `base_mesh` steps are shared with other tasks so they are not housed in
the `external_gravity_wave` work directory. Instead, they are in work
directories like:

```
ocean/spherical/icos/base_mesh/60km
ocean/spherical/qu/base_mesh/60km
```

(ocean-external-gravity-wave-vertical)=
## vertical grid

For this task, only a single vertical level may be used. The bottom depth
is constant and the results should be insensitive to the choice of
`bottom_depth`.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 1

# Depth of the bottom of the ocean
bottom_depth = 1000.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

## initial conditions

The fluid velocity is initialized to zero, and the layer thickness is given as
a simple Gaussian bump

$$
h = e^{-100 \left( \left(\phi - \phi_0\right)^2 + \left(\theta - \theta_0\right)^2 \right)}
$$

where $\phi$ is latitude, $\theta$ is longitude, $\phi_0 = 0$, and
$\theta_0 = \pi / 2$. Here, $\phi_0$ and $\theta_0$ can be set by `lat_center`
and `lon_center` as config options.

## forcing

This case run with all momentum equation terms disabled save the pressure
gradient term.

(ocean-external-graivty-wave-time-step)=
## time step and run duration

With any given time-stepping scheme, the time step for forward integration is
determined by multiplying the resolution by a config option, `rk4_dt_per_km`,
so that coarser meshes have longer time steps. You can alter this before setup
(in a user config file) or before running the task (in the config file in
the work directory).

```cfg
# config options for convergence tests
[convergence_forward]

# time integrator: {'split_explicit', 'RK4'}
time_integrator = RK4

# RK4 time step per resolution (s/km), since dt is proportional to resolution
rk4_dt_per_km = 3.0
```

The `convergence_eval_time`, `run_duration` and `output_interval` are set to
2 days:

```cfg
# config options for convergence forward steps
[convergence_forward]

# Run duration in hours
run_duration = 48.

# Output interval in hours
output_interval = ${convergence_forward:run_duration}
```

## config options

The primary `external_graivty_wave` config options are:

```cfg
# options for external gravity wave convergence test case
[external_gravity_wave]

# the constant temperature of the domain
temperature = 15.0

# the constant salinity of the domain
salinity = 35.0

# the central latitude (rad) of the gaussian bump
lat_center = 0.0

# the central longitude (rad) of the gaussian bump
lon_center = 1.57079633
```

Additionally, for the `global` and `local` time-stepping variants of this task,
the user can configure the time-integrator used. For the `global` variant:

```cfg
# config options for convergence forward steps
[convergence_forward]

# time integrator
#  either: {'RK4'}
#  mpas-ocean: {'split_explicit'}
#  omega: {'Forward-Backward', 'RungeKutta2'}
time_integrator = RK4
```

For the `local` variant:

```cfg
# config options for convergence forward steps
[convergence_forward]

# local time integrator
#  mpas-ocean: {'LTS, FB_LTS'}
#  omega: None
time_integrator = FB_LTS
```

(ocean-external-graivty-wave-cores)=
## cores

The target and minimum number of cores are determined by `goal_cells_per_core`
and `max_cells_per_core` from the `ocean` section of the config file,
respectively. This ensures that the number of cells per core is roughly
constant across the different resolutions in the convergence study.
