# MISMIP+

Creation date: 2026/10/29

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Polaris's `landice` component gains MISMIP+
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016),
Sect. 2): a 1 km MALI mesh, a spin-up to a steady state whose grounding
line crosses the centerline at 450 ± 10 km, and the Ice0, Ice1 and Ice2
experiments. E3SM's runs of the coupled MISOMIP1 experiment IceOcean1r
start MALI from the steady state. The E3SM inputs built in `e3sm/init`,
such as MALI's initial conditions and the SCRIP files and maps between MALI
and MPAS-Ocean, start from the mesh and the steady state. The analysis of
the E3SM runs reuses the diagnostics. Results are compared with
[Cornford et al. (2020)](https://doi.org/10.5194/tc-14-2283-2020), whose
submitted output is public
([Zenodo](https://doi.org/10.5281/zenodo.3611936)), MALI's own 500 m entry
among it.

The work starts from existing spin-ups. Trevor Hillebrand ran Compass's
MISMIP+ spin-up on Perlmutter at 16 to 1 km, with first-order velocities,
Weertman friction, the protocol's rate factor and densities 918 and
1028 kg m⁻³. With FCT thickness advection, the converged states are:

| Resolution | Years  | Centerline grounding line | Volume above flotation |
|------------|--------|---------------------------|------------------------|
| 8 km       | 20,000 | 405.1 km                  | 3.03 × 10¹³ m³         |
| 4 km       | 20,000 | 447.0 km                  | 3.56 × 10¹³ m³         |
| 2 km       | 16,250 | 457.6 km                  | 3.70 × 10¹³ m³         |
| 1 km       | 15,250 | 455.1 km                  | 3.66 × 10¹³ m³         |

Over its last 1,250 years, the 1 km grounding line moved 0.01 km and the
volume above flotation changed by 1.6 × 10⁻⁴. Compass's pre-spun 2 km file,
whose grounding line is at 423–425 km, predates these runs. MALI's 2017
MISMIP+ entry, with the same law and rate factor at 500 m, started from a
grounding line at 434.6 km.

Success means:

- a 1 km steady state with its centerline grounding line at 450 ± 10 km,
  converged by the criteria below and available to other tasks without
  rerunning the spin-up;
- Ice0 and Ice1r, and the optional experiments in scope, run from it, and
  their grounding line, volume above flotation and grounded area are
  compared with Cornford et al. (2020);
- the mesh is a shared step that the E3SM inputs extend with latitude,
  longitude and SCRIP files.

## Requirements

### Requirement: MISMIP+ follows the protocol

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Polaris sets up MISMIP+ as Sect. 2.1 specifies, on a MALI mesh that
resolves the grounding line, except for the departures under
[Decisions](#decisions).

### Requirement: MALI reaches the protocol's steady state

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Polaris spins MALI up until the grounding line and the volume above
flotation stop changing, and checks that the grounding line crosses the
centerline at 450 ± 10 km. Other tasks can start from the steady state
without repeating the spin-up.

### Requirement: Polaris runs the MISMIP+ experiments

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Polaris runs Ice0 and Ice1r from the steady state, and the optional
experiments in scope ([D10](#decisions)).

### Requirement: Polaris reports the MISMIP+ diagnostics

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

For each run, Polaris reports the grounding line, volume above flotation,
grounded area and ice volume every 10 years, and compares them with
Cornford et al. (2020). Other components can compute the same diagnostics
from MALI output.

## Algorithm Design

### Algorithm Design: MISMIP+ follows the protocol

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The mesh is Compass's uniform planar hexagonal mesh at a nominal 1 km
([D1](#decisions)). Its cell spacing, 982.7 m, puts rows of cell centers
exactly on $y = 0$ and $y = 80$ km. MALI's first-order solver works on the
triangulation of cell centers, so its domain ends at those rows. The
boundary cells' areas, and the lengths of the edges between them, are
halved. Cells span $x = 0$ to 640 km plus a two-cell gutter. Coordinates are
the protocol's, unshifted. The mesh has 62,035 cells and 10 layers with
Glimmer spacing.

The E3SM inputs' SCRIP files inherit two constraints from the mesh. The
SCRIP polygons of the cells on $y = 0$ and $y = 80$ km are trimmed to the
domain, so their map areas equal their halved model areas. Gutter cells
stay whole; they hold no ice, and the ocean's domain covers them.

The physics:

- the bed from Eqs. 1–4;
- ice removed beyond $x = 640$ km: `config_apply_calving_mask = .true.`
  with `calvingMask` set to 1 where $x > 640$ km, and
  `config_restore_calving_front` and `config_remove_small_islands`
  `.false.`. The spin-up removes no other ice, with `config_calving` set to
  `'none'` and `config_remove_icebergs` to `.false.`. The experiments also
  calve floating ice thinner than 10 m, and icebergs
  ([D13](#decisions)). MALI counts the removed ice in `calvingThickness`;
- accumulation of 0.3 m a⁻¹;
- the power law, Eq. 6, with $m = 3$ and the protocol's $\beta^2$, as
  MALI's Weertman law with uniform $\mu$ and an effective pressure of 1
  ([D5](#decisions));
- Glen's law with $n = 3$ and $A = 2.0\times10^{-17}$ Pa⁻³ a⁻¹
  ([D7](#decisions));
- ice and ocean densities of 918 and 1028 kg m⁻³, and gravity of
  9.80616 m s⁻² ([D6](#decisions));
- free slip on $y = 0$ and $y = 80$ km through MALI's Dirichlet mask;
- MALI's first-order velocity solver with its grounding-line
  parameterization, FCT thickness advection and third-order Runge–Kutta
  time stepping, with an adaptive time step ([D3](#decisions)).

### Algorithm Design: MALI reaches the protocol's steady state

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

The spin-up starts from either a 100 m slab, as in the protocol's
preliminary experiments, or the thickness of an existing state on the same
mesh. The 1 km steady state starts from Trevor Hillebrand's state at year
15,250 ([D4](#decisions)).

The spin-up runs for a given number of years. It is converged when, over
its last 1,000 years, the centerline grounding line has moved less than
0.5 km and the volume above flotation has changed by less than 5 × 10⁻⁴ of
itself. If it has not converged, the user lengthens it and continues it
from its latest restart ([D12](#decisions)).

A converged state whose centerline grounding line lies outside
450 ± 10 km fails the step, which reports the position. The user then
changes $A$ and reruns from the current state ([D7](#decisions)).

```{admonition} Rationale
Over 100 years, the criteria allow drifts of about 0.05 km and 5 × 10⁻⁵ in
Ice0, small beside the tens of kilometers of retreat in Ice1r. MALI's 2017
Ice0 drifted 0.3 km and 1.8 × 10⁻⁴.
```

### Algorithm Design: Polaris runs the MISMIP+ experiments

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

| Experiment | Starts from  | Years | Sub-shelf melt                          |
|------------|--------------|-------|-----------------------------------------|
| Ice0       | steady state | 100   | none                                    |
| Ice1r      | steady state | 100   | Eq. 17                                  |
| Ice1ra     | end of Ice1r | 100   | none                                    |
| Ice1rr     | end of Ice1r | 900   | Eq. 17                                  |
| Ice2r      | steady state | 100   | 100 m a⁻¹ of ice where $x > 480$ km     |
| Ice2ra     | end of Ice2r | 100   | none                                    |
| Ice2rr     | end of Ice2r | 900   | as Ice2r                                |

MALI implements both melt rates. Its `mismip` option is Eq. 17 with the
protocol's $\Omega$, $z_0$ and $H_{c0}$. Its `constant` option applies a
heat flux beyond an $x$ limit, and the flux is chosen to melt 100 m a⁻¹ of
ice. Ice1ra and Ice2ra end at $t = 200$ a, the protocol's minimum.

### Algorithm Design: Polaris reports the MISMIP+ diagnostics

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Polaris computes the diagnostics from thickness $H$ and bed $b$ in MALI's
output, with the thickness above flotation

$$
h_{af} = H + \frac{\rho_{sw}}{\rho_i} \min(b, 0).
$$

The volume above flotation is $\sum_i \max(h_{af}, 0) A_i$ over cells of area
$A_i$. The grounded area sums $A_i$ over cells with ice and $h_{af} > 0$. The
grounding line is the zero contour of $h_{af}$, and its centerline position
is interpolated linearly along the row of cells at $y = 40$ km
([D8](#decisions)).

Plots show the time series against every Cornford et al. (2020) entry for
the same experiment, with the Weertman entries and MALI's 2017 entry
marked, and the grounding line at $t = 0$, 100 and 200 a.

## Implementation

### Implementation: MISMIP+ follows the protocol

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

`polaris/landice/mismip_plus/` holds what other components reuse, and
imports nothing from `polaris.tasks`:

- `mesh.py`: the mesh's parameters, its construction and the halving of
  boundary areas, ported from Compass;
- `geometry.py`: the bed (Eqs. 1–4) and the protocol's constants;
- `diagnostics.py`: the diagnostics above, from any dataset with thickness,
  bed and MALI's mesh variables.

The shared mesh step is `mesh/planar/mismip_plus/1km/mesh` in the `mesh`
component ([D2](#decisions)). It builds the culled planar mesh, converts it
with `polaris/landice/mesh.py` and writes the graph file.
`get_mismip_plus_mesh_steps()` in `polaris/tasks/mesh/planar/mismip_plus/`
returns it, as `get_base_mesh_steps()` does for base meshes.

The landice tasks are:

```none
landice/mismip_plus/1km/init             (shared step)
landice/mismip_plus/1km/spin_up          (task)
landice/mismip_plus/1km/spin_up/run      (shared step)
landice/mismip_plus/1km/spin_up/spin_up  (shared step, cached by default)
landice/mismip_plus/1km/ice0             (task)
landice/mismip_plus/1km/ice1r            (task)
landice/mismip_plus/1km/ice1ra           (task)
landice/mismip_plus/1km/ice1rr           (task)
landice/mismip_plus/1km/ice2r            (task)
landice/mismip_plus/1km/ice2ra           (task)
landice/mismip_plus/1km/ice2rr           (task)
```

`init` adds the bed, the slab, the accumulation, the friction fields, the
calving mask and the Dirichlet mask to the mesh. $A$ from the config file
sets `config_default_flowParamA`, and the Albany input leaves out
`Glen's Law A`, so Albany takes MALI's value.

### Implementation: MALI reaches the protocol's steady state

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The `run` step is a `MaliModelStep` that runs MALI for `run_years`. MALI
writes a restart every 250 years and its output every 50 years. When the
step is rerun, for example after a job reaches its wall-clock limit or with
a larger `run_years`, it continues from its latest restart and adds to its
output.

The `spin_up` step checks convergence over the last `convergence_years`
from the output in the `run` step's directory, and fails if the spin-up
has not converged or its grounding line is outside 450 ± 10 km.

```cfg
[mismip_plus_spin_up]
# the state to start from: slab, or a MALI file on the same mesh whose
# thickness is used
initial_state = slab
run_years = 20000
convergence_years = 1000
gl_tolerance = 0.5
vaf_tolerance = 5e-4
```

A starting file's cell coordinates must match the mesh's within 1 m.

The step's output, `steady_state.nc`, is MALI's restart at convergence,
with global attributes for $A$, the densities, gravity, the Albany input,
the final grounding line, volume above flotation and grounded area, and the
spin-up's length. A time series of the diagnostics every 50 years goes
alongside it. The step has `default_cached = True`, and the `spin_up` task
lists it in `free_running_steps`, so only that task runs it
([D9](#decisions)). The experiment tasks include the `mesh`, `init` and
`run` steps, which Polaris leaves out when the steady state is cached.
`get_mismip_plus_steady_state_steps()` returns these shared steps and the
config, for the experiment tasks and for the E3SM inputs. The `spin_up`
task's `viz` step plots thickness, speed, the grounding line, the time
series and MALI's global statistics.

### Implementation: Polaris runs the MISMIP+ experiments

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Each experiment has a shared `forward` step, named for the experiment.
Ice1ra and Ice1rr include Ice1r's, and Ice2ra and Ice2rr include Ice2r's,
and restart from its end. The step makes its graph file from the steady
state, so it does not need the mesh step. Every task ends with an
`analysis` step that computes the diagnostics every 10 years and plots them
and MALI's global statistics, with the preceding experiment's series where
there is one. A shared step downloads the Cornford et al. (2020) supplement
from Zenodo and unpacks it.

No task joins `mali_pr` or `fanssie_pr` ([D11](#decisions)). A `mismip_plus`
suite lists Ice0, Ice1r, Ice1ra, Ice2r and Ice2ra, with the steady state
cached.

### Implementation: Polaris reports the MISMIP+ diagnostics

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

`polaris/landice/mismip_plus/diagnostics.py` provides the diagnostics as
functions of an `xarray.Dataset`, so that the analysis of the E3SM runs
can apply them to MALI's history files from E3SM.

## Testing

### Testing and Validation: MISMIP+ follows the protocol

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Unit tests check the bed against the protocol's values, the mesh's cell
count, boundary rows and halved areas, and the diagnostics on a synthetic
state. The 1 km mesh's cell coordinates match Trevor Hillebrand's to
round-off.

### Testing and Validation: MALI reaches the protocol's steady state

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

The 1 km spin-up runs on Chrysalis with MALI built from MALI-Dev, starting
from Trevor Hillebrand's state, and converges with its grounding line at
450 ± 10 km. The Testing comment shows the grounding line, volume above
flotation and grounded area over his spin-up and Polaris's continuation.

### Testing and Validation: Polaris runs the MISMIP+ experiments

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Ice0, Ice1r, Ice1ra, Ice2r and Ice2ra run at 1 km. Ice0 drifts no more
than the convergence criteria allow. Ice0 also runs with MALI built from
FAnSSIE, the E3SM development branch for ocean–ice-sheet coupling that the
E3SM runs use, and stays at the steady state.

### Testing and Validation: Polaris reports the MISMIP+ diagnostics

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

The plots compare the retreat and recovery with the Cornford et al. (2020)
ensemble and with MALI's 2017 entry, and the Testing comment discusses
where they differ.

## Decisions

### D1: A uniform 1 km mesh

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

MALI runs MISMIP+ on a uniform 1 km mesh.

```{admonition} Rationale
Trevor Hillebrand's 1 and 2 km steady states lie within 2.5 km of each
other, and a 1 km state already meets the protocol's target. MISOMIP1's 2 km
ocean needs MALI to be at least as fine.
```

Rejected:

- a mesh refined near the grounding line. The refined band must cover
  Ice1r's tens of kilometers of retreat, its cell centers would not lie on
  the domain's walls, and it would need a new spin-up;
- 2 km, which is coarser than MISOMIP1 needs.

### D2: The mesh is a shared step of the mesh component

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The mesh is built by `mesh/planar/mismip_plus/1km/mesh`, in the protocol's
coordinates.

*Effect:* the E3SM inputs add latitude, longitude and SCRIP files in new
steps downstream of `mesh`, leaving its output unchanged, so the cached
steady state stays valid. They also write latitude and longitude into
MALI's initial condition for E3SM. MALI's forward code never reads them on
a planar mesh, so the spin-up does not depend on them.

Rejected: a step in the landice tasks, which the E3SM inputs would then
have to move; and building their projection and maps now, which MISMIP+
does not need.

### D3: FCT thickness advection

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

MALI advects thickness with FCT and third-order Runge–Kutta.

Rejected: first-order upwinding with forward Euler, Compass's default,
which is less accurate. Trevor Hillebrand's 1 km run with it converged at
446.5 km.

### D4: The 1 km spin-up starts from Trevor Hillebrand's state

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The 1 km spin-up starts from the thickness of Trevor Hillebrand's 1 km FCT
state at year 15,250, and continues with Polaris's MALI build until it
meets the convergence criteria. The slab stays the default start.

Rejected:

- starting from the slab, which took his run over 15,000 years and several
  hundred Perlmutter node-hours;
- adopting his state without a Polaris run. It came from a MALI build of
  April 2026 that no longer exists.

### D5: Weertman friction only

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

MISMIP+ uses the power law, Eq. 6.

```{admonition} Rationale
Realistic simulations are not yet ready for a Coulomb law, so the power law
is the stepping stone toward them.
```

Rejected for now: a regularized Coulomb law (Eqs. 7 or 11). It needs its
own spin-up, and the parameters of Albany's law must first be related to
the protocol's. In the protocol's BISICLES tests (Sect. 2.2), Ice1r
retreated far more slowly with the power law than with the Coulomb-limited
laws, and MISOMIP1 inherits that.

### D6: E3SM's gravity and the protocol's densities

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

MALI uses the protocol's densities, 918 and 1028 kg m⁻³, and MPAS's gravity,
9.80616 m s⁻², which MALI also passes to Albany. This follows the MISOMIP
design's choice of E3SM's constants over the protocol's 9.81 m s⁻².

### D7: The rate factor is a config option, tuned by hand

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

$A$ is one config option that sets MALI's namelist, from which Albany
takes it. If the converged grounding line is outside the target, the user
changes $A$.

Rejected: tuning $A$ automatically, which costs thousands of model years
per iteration. The protocol's value already meets the target at 1 km.

### D8: Diagnostics from the flotation criterion

Date last modified: 2026/10/29

Contributors: Xylar Asay-Davis, Claude

Polaris computes the diagnostics from thickness and bed, not from MALI's
global statistics.

```{admonition} Rationale
MALI-Dev's `develop` counts the floating fringe next to grounded ice as
grounded in its global statistics since 2026-09-27. Computing from the
flotation criterion keeps the diagnostics comparable across MALI versions
and with Cornford et al. (2020), and applies unchanged to E3SM's output.
```

### D9: The steady state is a cached step output

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The steady state is the cached output of the `spin_up` step, uploaded with
`polaris cache`. The experiment tasks and the E3SM inputs read it from the
cache.

Rejected: a file placed by hand in the landice database. It would carry no
link to the step that made it, and regenerating it would bypass the
mechanism Polaris has for this.

### D10: The experiments in scope

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

All seven experiments are tasks, since they differ only in their start,
length and melt. Ice0, Ice1r, Ice1ra, Ice2r and Ice2ra are run for testing.
Ice1rr and Ice2rr, at 900 years each, are not.

### D11: No suite membership

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

No MISMIP+ task joins `mali_pr` or `fanssie_pr`. The shortest experiment
takes hours on several nodes, and the `dome` tasks already test the
first-order solver there.

Cheaper MISMIP+ regression tests could join `mali_pr` in later work.

### D12: The spin-up runs for a set length

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The spin-up's `run` step runs MALI for a set number of years, and the
`spin_up` step checks convergence over the last 1,000 of them. To continue
an unconverged spin-up, the user raises `run_years` and reruns the `run`
step, which continues from its latest restart. Restarts come every 250
years, as in Compass, and the `spin_up` step reads output written every 50
years.

```{admonition} Rationale
Polaris lets a step launch only its one command, so a step cannot loop over
MALI runs, checking convergence between them.
```

Rejected: a chain of segment steps, set up for the longest spin-up, whose
`run` steps launch nothing once an earlier segment has converged. It would
set up dozens of steps that seldom run.

### D13: The experiments calve thin floating ice and icebergs

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Every experiment calves floating ice thinner than 10 m, with
`config_calving = 'thickness_threshold'`, and removes floating ice cut off
from the grounded ice, with `config_remove_icebergs`. The spin-up does
neither.

```{admonition} Rationale
Without them, Ice2r's velocity solve fails in its fourth year. Its melting
leaves a thin film of floating ice beyond 480 km, but calving the film
alone does not prevent the failure. MALI removes icebergs because they can
keep its velocity solve from converging, and with both options, Ice2r runs
to its end. Ice0, Ice1r and Ice1ra are bit-for-bit unchanged. 10 m is
MALI's default `config_dynamic_thickness`, the smallest threshold it
allows.
```

Rejected: shorter time steps, as in Compass's 2017 runs, with a CFL
fraction of 0.25 rather than 0.8. They were not tried, since they would
more than triple the cost of every experiment.
