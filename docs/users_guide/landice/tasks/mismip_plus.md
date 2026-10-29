(landice-mismip-plus)=

# mismip_plus

The `mismip_plus` tasks run the third Marine Ice Sheet Model Intercomparison
Project, MISMIP+, as
[Asay-Davis et al. (2016)](https://doi.org/10.5194/gmd-9-2471-2016) specify
it in their Sect. 2.  MALI spins up to a steady state whose grounding line
crosses the centerline of a trough near $x = 450$ km, and then runs the
Ice0, Ice1 and Ice2 experiments from it, which melt the ice shelf and let it
recover.  The analysis compares the results with those submitted to MISMIP+
([Cornford et al. 2020](https://doi.org/10.5194/tc-14-2283-2020)).

```none
landice/mismip_plus/1km/spin_up
landice/mismip_plus/1km/ice0
landice/mismip_plus/1km/ice1r
landice/mismip_plus/1km/ice1ra
landice/mismip_plus/1km/ice1rr
landice/mismip_plus/1km/ice2r
landice/mismip_plus/1km/ice2ra
landice/mismip_plus/1km/ice2rr
```

All the tasks use Albany's first-order velocity solver, so they need a
Polaris environment with Albany (see {ref}`dev-landice-albany`).  They are
expensive: the spin-up takes thousands of model years, and each 100-year
experiment takes hours on several nodes.

## mesh

The mesh is a uniform planar hexagonal mesh with a nominal resolution of
1 km.  Its cell spacing, 982.7 m, puts rows of cell centers exactly on the
domain's walls at $y = 0$ and $y = 80$ km.  MALI's first-order solver works
on the triangulation of cell centers, so its domain ends at those rows, and
the areas of the cells on the walls, and the lengths of the edges between
them, are halved.  The cells span $x = 0$ to 640 km, plus a gutter of two
cells.  The mesh has 62,035 cells and 10 vertical levels with the spacing of
Glimmer.

The mesh is made by the shared step `mesh/planar/mismip_plus/1km/mesh` in
the `mesh` component.

## physics

The bed is that of Eqs. 1-4 of Asay-Davis et al. (2016).  Ice accumulates at
0.3 m a⁻¹, and ice beyond $x = 640$ km is removed by MALI's calving mask.
The experiments also calve floating ice thinner than 10 m, and icebergs,
floating ice cut off from the grounded ice, both of which Ice2's melting can
leave behind.  The spin-up removes no other ice.  Basal friction follows the
power law (Eq. 6), with $m = 3$ and $\beta^2 = 3.160 \times 10^6$ Pa m⁻¹ᐟ³
s¹ᐟ³, as MALI's Weertman law with a uniform friction coefficient and an
effective pressure of 1 Pa.  Glen's law has $n = 3$ and a rate factor $A$ set
by a config option.  Ice and seawater have densities of 918 and 1028 kg m⁻³,
and gravity is MALI's 9.80616 m s⁻².  The walls at $y = 0$ and 80 km are
free-slip.

MALI advects thickness with flux-corrected transport and third-order
Runge-Kutta time stepping, with an adaptive time step.

(landice-mismip-plus-spin-up)=

## spin_up

`spin_up` spins MALI up to the steady state, from which the experiments
start.  Its `run` step runs MALI for `run_years`, starting from the state in
`initial_state`.  By default, this is a 100-m slab of ice, from which the
protocol's preliminary experiments took about 20,000 years to reach a steady
state.  It can instead be a MALI file on the same mesh, such as a restart
from an earlier spin-up, whose thickness is used.  MALI writes a restart
every 250 years, and when the `run` step is run again, for example after a
job reaches its wall-clock limit, it continues from its latest restart.
MALI also writes the thickness and the other fields of the experiments'
output to `output.nc` every 50 years.  Every MISMIP+ run writes MALI's
global statistics, such as the ice volume, volume above flotation, grounded
area and the grounding-line and calving fluxes, to `globalStats.nc` every
time step.  A continued run carries on in the same `output.nc` and
`globalStats.nc`.

The `spin_up` step then checks that the spin-up has converged: over its last
`convergence_years`, the grounding line must have moved less than
`gl_tolerance` along the centerline, and the volume above flotation must
have changed by less than `vaf_tolerance` of itself.  The grounding line
must also cross the centerline within 10 km of $x = 450$ km.  If the spin-up
has not converged, increase `run_years` and run `polaris serial` in the
`run` step's directory to continue it.  If the grounding line is too far
from 450 km, change `flow_param_a` and continue the spin-up.

The `spin_up` step writes `steady_state.nc`, MALI's restart at the end of
the spin-up, with global attributes that describe the spin-up and its final
grounding line, volume above flotation and grounded area.  It also writes
`spin_up_diagnostics.nc`, with the diagnostics every 50 years.  The `viz`
step plots the thickness and surface speed of the steady state, the
diagnostics over the spin-up, and MALI's global statistics: the changes in
volume and area in `spin_up_global_stats_volume.png` and the mass fluxes in
`spin_up_global_stats_flux.png`.

The experiment tasks read the steady state from the cache of step outputs,
so they do not run the spin-up.  To run it in an experiment task, set the
task up with `--free_running spin_up`.

## experiments

| Task     | Starts from     | Years | Melt under the ice shelf                    |
|----------|-----------------|-------|---------------------------------------------|
| `ice0`   | steady state    | 100   | none                                        |
| `ice1r`  | steady state    | 100   | Eq. 17 of Asay-Davis et al. (2016)          |
| `ice1ra` | end of `ice1r`  | 100   | none                                        |
| `ice1rr` | end of `ice1r`  | 900   | Eq. 17                                      |
| `ice2r`  | steady state    | 100   | 100 m a⁻¹ of ice where $x > 480$ km         |
| `ice2ra` | end of `ice2r`  | 100   | none                                        |
| `ice2rr` | end of `ice2r`  | 900   | as in `ice2r`                               |

MALI writes the thickness, upper surface, bed, surface and basal speeds and
rate of thickness change every 10 years, and its global statistics every
time step.  The tasks that start from the end of another experiment include
that experiment's `forward` step, which runs first unless it already has.

Each task's `analysis` step computes the ice volume, the volume above
flotation, the grounded area and the position of the grounding line on the
centerline every 10 years, and writes them to `diagnostics.nc`.  It plots
them against those of every MISMIP+ entry for the same experiment, with the
entries that use the power law and MALI's own 2017 entry marked.  It also
plots the grounding line at 0, 100 and 200 years, the thickness and surface
speed at the end of the experiment, and MALI's global statistics, as in the
spin-up.  A shared step downloads the supplement of Cornford et al. (2020)
from [Zenodo](https://doi.org/10.5281/zenodo.3611936).

## diagnostics

The diagnostics are computed from the flotation criterion, not from MALI's
global statistics.  The thickness above flotation is

$$
h_{af} = H + \frac{\rho_{sw}}{\rho_i} \min(b, 0),
$$

where $H$ is the ice thickness and $b$ is the bed elevation.  The volume
above flotation sums $\max(h_{af}, 0)$ times the cell area, and the grounded
area sums the areas of cells with ice and $h_{af} > 0$.  The grounding
line's position on the centerline is interpolated linearly between the cell
centers on $y = 40$ km where $h_{af}$ first falls to zero downstream of the
ice divide.

## config options

```cfg
# config options for MISMIP+ tasks
[mismip_plus]

# the rate factor (Pa^-3 s^-1) in Glen's law, the protocol's
# 2.0e-17 Pa^-3 a^-1.  Change it if the steady state's grounding line misses
# 450 +/- 10 km on the centerline.
flow_param_a = 6.338e-25

# the number of MPI tasks for MALI, and the fewest it may run on.  A job's
# size is the geometric mean of the two.
ntasks = 256
min_tasks = 128


# config options for the MISMIP+ spin-up
[mismip_plus_spin_up]

# the state to start from: slab, for 100 m of ice wherever x < 640 km, or a
# MALI file on the same mesh whose thickness is used
initial_state = slab

# the length of the spin-up in years, a multiple of 250
run_years = 20000

# the spin-up has converged if, over its last convergence_years (a multiple
# of 50), the grounding line has moved less than gl_tolerance (km) along the
# centerline and the volume above flotation has changed by less than
# vaf_tolerance as a fraction of itself
convergence_years = 1000
gl_tolerance = 0.5
vaf_tolerance = 5e-4


# config options for plots of MISMIP+
[mismip_plus_viz]

# the colormaps for ice thickness and surface speed
thickness_cmap = cmo.ice_r
speed_cmap = cmo.speed

# the largest surface speed (m a^-1) in the colormap
speed_max = 1500.0
```

The mesh's config file, `mismip_plus_mesh.cfg`, sets the number of vertical
levels and their spacing:

```cfg
# config options for the MISMIP+ mesh
[mismip_plus_mesh]

# the number of vertical levels in the MALI mesh
levels = 10

# the spacing of the vertical levels: uniform or glimmer
vertical_spacing = glimmer
```

## cores

MALI runs on `ntasks` MPI tasks, 256 by default, and on no fewer than
`min_tasks`.
