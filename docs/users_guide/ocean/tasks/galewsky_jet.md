(ocean-galewsky-jet)=

# galewsky_jet

The `galewsky_jet` tasks implement the barotropically unstable jet of
[Galewsky, Scott & Polvani (2004)](https://doi.org/10.3402/tellusa.v56i5.14436)
(GSP04), with two figures replaced in a
[corrigendum](https://doi.org/10.1111/j.1600-0870.2006.00192.x) (GSP06).
A mid-latitude zonal jet in gradient-wind balance is perturbed by a small
height bump.  Gravity waves radiate from the bump within hours, and the jet
rolls up into vortices over about six days.

GSP04 §5 recommends testing a model in three stages, and each is a task:

- `steady_state`: the unperturbed jet without diffusion for 5 days;
- `adjustment`: the perturbed jet without diffusion for 6 hours;
- `unstable`: the perturbed jet with diffusion for 6 days.

Each task runs on a sequence of icosahedral (`icos`) or quasi-uniform (`qu`)
meshes:

```none
ocean/spherical/icos/galewsky_jet/steady_state
ocean/spherical/icos/galewsky_jet/adjustment
ocean/spherical/icos/galewsky_jet/unstable
ocean/spherical/qu/galewsky_jet/steady_state
ocean/spherical/qu/galewsky_jet/adjustment
ocean/spherical/qu/galewsky_jet/unstable
```

All six are in the `galewsky_jet` suite.

## suppported models

These tasks support both MPAS-Ocean and Omega.

(ocean-galewsky-jet-steady-state)=

## steady_state

### description

Without a perturbation or diffusion, the jet is an exact steady solution of
the continuous shallow-water equations.  No initial state is exactly steady
on the discrete mesh, so the jet drifts by an amount that should shrink as
the mesh is refined.  The drift grows into the jet's instability without
any perturbation.  On icosahedral meshes it takes the form of a wavenumber-5
pattern imprinted by the grid.  The pattern is visible after 5 days even at
60 km, and it begins to break up the jet within 3 days on the coarser
meshes.

The `analysis` step computes the normalized L2 error of the layer thickness
and of the normal velocity after 1 day against the initial state, and fits
convergence rates to them, as in {ref}`ocean-geostrophic`.  The early time
measures the truncation error before the instability grows.  The step
writes `convergence_h.png` and `convergence_normalVelocity.png`.  The task
fails if a rate is below the threshold in the config options.

The run lasts 5 days, as in GSP04, so the `viz` step at each resolution
shows when the jet breaks down.  It plots the relative vorticity after 5
days (`final_vorticity.png`) and its change from the initial state
(`diff_vorticity.png`).

### mesh

See {ref}`ocean-galewsky-jet-mesh`.

### vertical grid

See {ref}`ocean-galewsky-jet-vertical`.

### initial conditions

The balanced jet without the perturbation; see
{ref}`ocean-galewsky-jet-init`.

### forcing

N/A

### time step and run duration

The time step is 1 s per km of resolution (see
{ref}`ocean-galewsky-jet-config`), and the run duration is 120 hours, as in
GSP04.  Output is written every 24 hours.  There is no diffusion.

### config options

See {ref}`ocean-galewsky-jet-config`.

### cores

See {ref}`ocean-galewsky-jet-cores`.

(ocean-galewsky-jet-adjustment)=

## adjustment

### description

The perturbed jet runs for 6 hours without diffusion, covering the
gravity-wave adjustment of GSP06 Fig. 2.  The `analysis` step writes one
figure per resolution, `adjustment_<mesh>.png`, with the height minus the
balanced height and the divergence at 2, 4 and 6 hours.  The longitude and
latitude ranges and the contour levels are those of GSP06 Fig. 2, so the
figures can be compared with it directly.

The step also writes `table1_comparison.csv` and the log, with the l2 norm,
maximum and minimum of divergence and the maximum and minimum of height at
4 hours.  The last row holds the values from GSP04 Table 1.  GSP04 Table 1
also gives l2(h) = 9778 m, which is left out because the l2 norm of a field
with a global mean of 10 km cannot be below 10 km.

The task reports these comparisons but does not pass or fail on them.

### mesh

See {ref}`ocean-galewsky-jet-mesh`.

### vertical grid

See {ref}`ocean-galewsky-jet-vertical`.

### initial conditions

The balanced jet with the perturbation; see {ref}`ocean-galewsky-jet-init`.

### forcing

N/A

### time step and run duration

The time step is 1 s per km of resolution, and the run duration is 6 hours.
Output is written every hour.  There is no diffusion.

### config options

See {ref}`ocean-galewsky-jet-config`.

### cores

See {ref}`ocean-galewsky-jet-cores`.

(ocean-galewsky-jet-unstable)=

## unstable

### description

The perturbed jet runs for 6 days with ∇² momentum diffusion of
1 × 10⁵ m² s⁻¹, as in GSP04.  GSP04 chose that value so that the solution
at day 6 converges at a resolution near T85, a 1.4° transform grid.

The `analysis` step writes one figure per resolution,
`unstable_<mesh>.png`, with the relative vorticity at 96, 120 and 144 hours,
on the longitude and latitude ranges and with the contour levels of GSP06
Fig. 6.  `unstable_all_resolutions.png` shows every resolution at 144 hours,
as in GSP04 Fig. 8.

The step also writes `table1_comparison.csv` and the log, with the l2 norm,
maximum and minimum of relative vorticity at 144 hours, and the values from
GSP04 Table 1 in the last row.  The task reports these comparisons but does
not pass or fail on them.

GSP04 also diffuses the layer thickness, but neither MPAS-Ocean nor Omega
has thickness diffusion.

### mesh

See {ref}`ocean-galewsky-jet-mesh`.

### vertical grid

See {ref}`ocean-galewsky-jet-vertical`.

### initial conditions

The balanced jet with the perturbation; see {ref}`ocean-galewsky-jet-init`.

### forcing

N/A

### time step and run duration

The time step is 1 s per km of resolution, and the run duration is 144 hours.
Output is written every 24 hours.  The viscosity is constant: it does not
scale with cell size in either model.

### config options

See {ref}`ocean-galewsky-jet-config`.

### cores

See {ref}`ocean-galewsky-jet-cores`.

(ocean-galewsky-jet-mesh)=

## mesh

The mesh is global and either icosahedral or quasi-uniform, at the same
resolutions as {ref}`ocean-geostrophic`: 60, 120, 240 and 480 km for
icosahedral meshes and 90, 120, 150 and 180 km for quasi-uniform meshes.
They are set in the `[spherical_convergence]` section; see
{ref}`ocean-cosine-bell-mesh` for these options.

(ocean-galewsky-jet-vertical)=

## vertical grid

The tasks exercise only the shallow-water dynamics, so there is a single
layer over a flat bottom at the 10 km mean depth of the layer.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 1

# Depth of the bottom of the ocean, the global mean of the layer thickness
bottom_depth = 10000.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star
```

(ocean-galewsky-jet-init)=

## initial conditions

The zonal velocity of the jet is (GSP04 eq. 2)

$$
u(\phi) = \frac{u_\mathrm{max}}{e_n}
          \exp\left[\frac{1}{(\phi - \phi_0)(\phi - \phi_1)}\right]
          \quad \text{for } \phi_0 < \phi < \phi_1,
$$

and zero elsewhere, with $u_\mathrm{max} = 80$ m s⁻¹, $\phi_0 = \pi/7$,
$\phi_1 = \pi/2 - \phi_0$ and $e_n = \exp[-4/(\phi_1 - \phi_0)^2]$.

The layer thickness is in gradient-wind balance with the jet (GSP04 eq. 3):

$$
g h(\phi) = g h_0 - \int_{-\pi/2}^{\phi} a\, u(\phi')
            \left[f + \frac{\tan\phi'}{a} u(\phi')\right] d\phi',
$$

with $h_0$ chosen so that the global mean of $h$ is 10 km.  The integral is
computed by quadrature on a fine latitude grid.  The thickness ranges from
about 9071 m north of the jet to 10158 m south of it.

The normal velocity is the difference of the streamfunction
$\psi(\phi) = -a \int_{-\pi/2}^{\phi} u\, d\phi'$ between the two vertices
of each edge, divided by the edge length.  Its discrete divergence is zero to
round-off.

The `adjustment` and `unstable` tasks add the perturbation of GSP04 eq. 4:

$$
h'(\lambda, \phi) = \hat{h} \cos\phi\, e^{-(\lambda/\alpha)^2}
                    e^{-[(\phi_2 - \phi)/\beta]^2},
\quad -\pi < \lambda \le \pi,
$$

with $\hat{h} = 120$ m, $\alpha = 1/3$, $\beta = 1/15$ and
$\phi_2 = \pi/4$.

The Earth's radius, gravity and rotation rate are the Polaris constants,
which differ from those of GSP04 by about 1 part in 10⁴.  The temperature
and salinity are constant.

(ocean-galewsky-jet-config)=

## config options

The jet, the perturbation and the settings of each task are in
`galewsky_jet.cfg`, which the three tasks for a mesh type share:

```cfg
# config options for convergence tests
[convergence]

# Evaluation time for the steady_state convergence analysis (in hours).  By
# 72 hours, grid imprinting begins to break up the jet on the coarser meshes.
convergence_eval_time = 24.0


# config options for convergence forward steps
[convergence_forward]

# time integrator: {'split_explicit', 'RK4'}
time_integrator = RK4

# RK4 time step per resolution (s/km), since dt is proportional to resolution.
# Gravity waves in a 10 km layer travel at about 315 m/s.
rk4_dt_per_km = 1.0


# options for the Galewsky et al. (2004) barotropic jet
[galewsky_jet]

# the peak velocity of the jet (m/s)
u_max = 80.0

# the latitude of the southern edge of the jet (degrees), pi/7 radians
jet_south_lat = 25.714285714285715

# the latitude of the northern edge of the jet (degrees), pi/2 - pi/7 radians
jet_north_lat = 64.28571428571429

# the global mean of the layer thickness (m)
h_mean = 10000.0

# the amplitude of the height perturbation (m)
perturbation_amplitude = 120.0

# the longitudinal width of the perturbation (radians), 1/3
perturbation_lon_width = 0.3333333333333333

# the latitudinal width of the perturbation (radians), 1/15
perturbation_lat_width = 0.06666666666666667

# the latitude of the centre of the perturbation (degrees)
perturbation_lat = 45.0

# the constant temperature of the domain
temperature = 15.0

# the constant salinity of the domain
salinity = 35.0


# options for the steady_state task: the unperturbed jet without diffusion
[galewsky_jet_steady_state]

# run duration (hours)
run_duration = 120.0

# output interval (hours)
output_interval = 24.0

# del2 viscosity (m^2/s), 0 to disable
viscosity = 0.0

# convergence thresholds below which the task fails on icosahedral meshes
convergence_thresh_icos_h = 1.8
convergence_thresh_icos_normalVelocity = 1.8

# convergence thresholds below which the task fails on quasi-uniform meshes.
# The rate for layer thickness depends on the mesh that JIGSAW generates.
convergence_thresh_qu_h = 0.8
convergence_thresh_qu_normalVelocity = 1.7


# options for the adjustment task: the perturbed jet without diffusion
[galewsky_jet_adjustment]

# run duration (hours)
run_duration = 6.0

# output interval (hours)
output_interval = 1.0

# del2 viscosity (m^2/s), 0 to disable
viscosity = 0.0

# times at which to plot height and divergence (hours)
plot_times = 2.0, 4.0, 6.0

# the time at which to compare with Table 1 of Galewsky et al. (2004) (hours)
table_time = 4.0

# contour interval for the height change from the balanced state (m)
h_contour_interval = 8.0

# contour interval for divergence (1/s)
div_contour_interval = 8.0e-7


# options for the unstable task: the perturbed jet with diffusion
[galewsky_jet_unstable]

# run duration (hours)
run_duration = 144.0

# output interval (hours)
output_interval = 24.0

# del2 viscosity (m^2/s), 0 to disable
viscosity = 1.0e5

# times at which to plot vorticity (hours)
plot_times = 96.0, 120.0, 144.0

# the time at which to compare with Table 1 of Galewsky et al. (2004) (hours)
table_time = 144.0

# contour interval for relative vorticity (1/s)
vort_contour_interval = 2.0e-5
```

Each task's plot and table times must be multiples of its output interval.
The `[galewsky_jet_viz_vort]` and `[galewsky_jet_viz_diff_vort]` sections
set the colormaps of the `steady_state` viz plots; see
{ref}`dev-visualization-global`.

(ocean-galewsky-jet-cores)=

## cores

The number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `[ocean]` section of the config file, from an
estimate of the number of cells at each resolution.
