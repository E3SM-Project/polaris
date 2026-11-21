# Galewsky Barotropic Jet Tasks

Creation date: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds the barotropically unstable jet of
[Galewsky, Scott & Polvani (2004)](https://doi.org/10.3402/tellusa.v56i5.14436)
(GSP04) as spherical ocean tasks for Omega and MPAS-Ocean. A
mid-latitude zonal jet in gradient-wind balance is perturbed by a small
height bump. Gravity waves radiate within hours, and the jet rolls up
into vortices over six days. The
[corrigendum](https://doi.org/10.1111/j.1600-0870.2006.00192.x)
(GSP06) replaces GSP04's Figs. 2 and 6.

GSP04 §5 prescribes three stages, and each becomes a task:

- `steady_state`: the unperturbed jet, without diffusion, must stay
  steady for several days;
- `adjustment`: the perturbed jet, without diffusion, for 6 h; height and
  divergence are compared with GSP06 Fig. 2 and GSP04 Table 1;
- `unstable`: the perturbed jet, with ∇² diffusion, for 144 h; vorticity
  is compared with GSP06 Fig. 6 and GSP04 Table 1.

The tasks run on icosahedral and quasi-uniform meshes at the resolutions
of the `geostrophic` tasks.

This work is independent of an earlier prototype by Sara Calandrini and
Alice Barthel
([E3SM-Project/polaris#70](https://github.com/E3SM-Project/polaris/pull/70)),
which inspired it.

Success has two parts:

- the steady jet's drift from its initial state decreases as the mesh is
  refined;
- at the finer resolutions, both models reproduce GSP06's height,
  divergence and vorticity fields and GSP04's Table 1 values.

## Open questions

- Whether the quasi-uniform threshold for $h$ is loose enough. It rests
  on meshes from three machines (D12).
- Whether any GSP04 Table 1 comparison becomes a pass/fail check. The
  first implementation reports them only.
- Whether the resolutions inherited from `geostrophic` suit this test
  (D8).
- Which tasks, if any, join the `convergence` or nightly suites. This
  waits for run costs.

## Requirements

### Requirement: Galewsky's balanced jet and perturbation define the initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

The initial state shall be GSP04's zonal jet (eq. 2) with the height in
gradient-wind balance with it (eq. 3) and a global mean depth of 10 km.
Tasks that call for it shall add GSP04's height perturbation (eq. 4).

### Requirement: Both models run every task from the same initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

### Requirement: An unperturbed jet stays steady without diffusion

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Without perturbation or diffusion, the jet's departure from its initial
state after 24 h shall decrease as the mesh is refined.

### Requirement: The early adjustment reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Without diffusion, the perturbed jet's height and divergence at 2, 4 and
6 h shall be comparable with GSP06 Fig. 2, and its 4 h values with
GSP04 Table 1.

### Requirement: The diffusive instability reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

With ∇² diffusion of 1 × 10⁵ m² s⁻¹, the perturbed jet's vorticity at
96, 120 and 144 h shall be comparable with GSP06 Fig. 6, and its 144 h
values with GSP04 Table 1.

### Requirement: Results can be compared across resolutions and meshes

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Each task shall run on a sequence of icosahedral and of quasi-uniform
meshes and present all resolutions together.

## Algorithm Design

### Algorithm Design: Galewsky's balanced jet and perturbation define the initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

The jet is GSP04 eq. 2:

$$
u(\phi) = \frac{u_\mathrm{max}}{e_n}
          \exp\left[\frac{1}{(\phi - \phi_0)(\phi - \phi_1)}\right]
          \quad \text{for } \phi_0 < \phi < \phi_1,
$$

and zero elsewhere, with $u_\mathrm{max} = 80$ m s⁻¹, $\phi_0 = \pi/7$,
$\phi_1 = \pi/2 - \phi_0$ and $e_n = \exp[-4/(\phi_1 - \phi_0)^2]$.
The peak is at 45°N.

The height is GSP04 eq. 3:

$$
g h(\phi) = g h_0 - \int_{-\pi/2}^{\phi} a\, u(\phi')
            \left[f + \frac{\tan\phi'}{a} u(\phi')\right] d\phi'.
$$

The integral is evaluated by cumulative quadrature on a fine latitude
grid and interpolated to cell centres. $h_0$ is chosen so that the
area-weighted global mean of $h$ is 10 km. The range of $h$ is about
9071 to 10158 m.

The velocity comes from the streamfunction

$$
\psi(\phi) = -a \int_{-\pi/2}^{\phi} u(\phi')\, d\phi',
$$

evaluated at vertices. Each edge's normal velocity is the difference of
$\psi$ between its two vertices, divided by `dvEdge`, with the sign set
by the MPAS edge convention. The discrete divergence of this field is
zero to round-off, because each cell's sum of edge fluxes telescopes
around a closed loop (D2).

The perturbation is GSP04 eq. 4:

$$
h'(\lambda, \phi) = \hat{h} \cos\phi\, e^{-(\lambda/\alpha)^2}
                    e^{-[(\phi_2 - \phi)/\beta]^2},
\quad -\pi < \lambda \le \pi,
$$

with $\hat{h} = 120$ m, $\alpha = 1/3$, $\beta = 1/15$ and
$\phi_2 = \pi/4$. It is added to $h$ without rebalancing the velocity.

The radius, gravity and rotation rate are the Polaris constants, not
GSP04's (D3). The ocean is a single layer over a flat bottom at the
mean depth. SSH is $h$ minus that depth.

> **Rationale.** GSP04's jet and eq. 3 height form an exact steady
> solution of the continuous nonlinear shallow-water equations. The
> $u \tan\phi / a$ term is 12% of $f$ at 45°N, so it cannot be dropped
> (D1).

### Algorithm Design: Both models run every task from the same initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Both models use the nonlinear shallow-water terms: thickness flux,
potential-vorticity flux and kinetic-energy gradient. They run one
z-star layer with a constant equation of state, RK4 time stepping, no
bottom drag and no tracer mixing.

The time step is 1 s per km of resolution, so 60 s at 60 km.

Momentum diffusion is ∇² only, with ν = 0 in `steady_state` and
`adjustment` and ν = 1 × 10⁵ m² s⁻¹ in `unstable` (D5). ν does not scale
with cell size in either model. Neither model diffuses thickness.

> **Rationale.** The gravity-wave speed for a 10 km layer is about
> 315 m s⁻¹, against 171 m s⁻¹ in `geostrophic`, which uses 2 s/km. Half
> that time step keeps a similar Courant number. GSP04 used 30 s at
> T341.

### Algorithm Design: An unperturbed jet stays steady without diffusion

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`steady_state` runs the unperturbed jet for 120 h with ν = 0, the
duration GSP04 used for this stage. The analysis computes the
normalized l2 error of $h$ and of normal velocity at 24 h against the
initial state, at every resolution (D11). It fits convergence rates as
`geostrophic` does. Vorticity at 120 h is plotted at each resolution.

> **Rationale.** No initial state is exactly steady on a TRSK C-grid.
> The residual imbalance is truncation error, so the drift should shrink
> with resolution. On icosahedral meshes, grid imprinting can trigger the
> instability without any perturbation
> ([Weller, Thuburn & Cotter, 2012](https://doi.org/10.1175/MWR-D-11-00193.1)).
> GSP04 §5 notes the same for coarse resolutions and asks that the
> resolution be refined until the jet stays steady. A jump in the error
> or non-zonal structure in the vorticity plot shows where that happens.

### Algorithm Design: The early adjustment reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`adjustment` runs the perturbed jet for 6 h with ν = 0, writing output
hourly. It plots, at 2, 4 and 6 h:

- $h$ minus the balanced, unperturbed height, with contours at
  ±4, ±12, ±20, … m;
- divergence, with contours at ±4, ±12, ±20, … × 10⁻⁷ s⁻¹.

The plots cover −180° to 180° longitude and −90° to 90° latitude, as in
GSP06 Fig. 2, with one row of panels per resolution.

At 4 h it reports, for each resolution, the l2 norm, maximum and minimum
of divergence and the maximum and minimum of $h$. GSP04 Table 1 gives
4.0 × 10⁻⁷, 3.7 × 10⁻⁶ and −2.0 × 10⁻⁶ s⁻¹, and 10182 and 9052 m.

> **Rationale.** Table 1 also lists l2(h) = 9778 m. For a field with a
> global mean of 10 km, the l2 norm of GSP04 eq. 6 cannot be less than
> 10 km, so that value is not used.

### Algorithm Design: The diffusive instability reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`unstable` runs the perturbed jet for 144 h with
ν = 1 × 10⁵ m² s⁻¹, writing output every 24 h. It plots relative
vorticity:

- at 96, 120 and 144 h for each resolution, as in GSP06 Fig. 6;
- at 144 h for all resolutions in one figure, as in GSP04 Fig. 8.

Contours are at ±1, ±3, ±5, … × 10⁻⁵ s⁻¹, with negative contours
dashed. The plots cover 10°N to 80°N and 90°E eastward through 360° to
80°E, as in GSP06.

At 144 h it reports, for each resolution, the l2 norm, maximum and
minimum of vorticity. GSP04 Table 1 gives 2.1 × 10⁻⁵, 9.3 × 10⁻⁵ and
−7.3 × 10⁻⁵ s⁻¹.

> **Rationale.** GSP04 chose ν so that the day-6 solution converges near
> T85, a 1.4° transform grid. The 60 and 120 km icosahedral meshes and
> the 90 to 150 km quasi-uniform meshes should therefore approach
> GSP06's solution. The coarser meshes show how the solution degrades.

### Algorithm Design: Results can be compared across resolutions and meshes

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Relative vorticity at vertices and divergence at cells are computed in
Python from the output normal velocity. They use the TRSK circulation
and flux-divergence operators on the MPAS mesh (D7). Global integrals
follow GSP04 eq. 5, weighted by `areaTriangle` for vertex fields and
`areaCell` for cell fields.

Contour plots are drawn directly from vertex or cell locations by
triangulation in longitude–latitude, without remapping (D9).

## Implementation

### Implementation: Galewsky's balanced jet and perturbation define the initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

A new package `polaris/tasks/ocean/galewsky_jet` holds the tasks. A
module of pure functions computes the initial state from latitude,
longitude and mesh arrays:

```python
def jet_velocity(lat, u_max, phi0, phi1): ...
def balanced_height(lat, h_mean, u_max, phi0, phi1, a, g, omega): ...
def height_perturbation(lon, lat, h_hat, alpha, beta, phi2): ...
def normal_velocity(ds_mesh, u_max, phi0, phi1, a): ...
```

The functions are vectorised; there are no per-cell loops. Quadrature
uses `scipy.integrate.cumulative_trapezoid` on about 10⁵ latitudes.

An `Init` step, modelled on `geostrophic`'s, writes the mesh, vertical
coordinate and initial state. A `perturbed` argument chooses whether to
add $h'$. There are two shared init steps per mesh:

- `spherical/<prefix>/galewsky_jet/init/balanced/<mesh>`;
- `spherical/<prefix>/galewsky_jet/init/perturbed/<mesh>`.

The jet and perturbation parameters are config options in a
`[galewsky_jet]` section of `galewsky_jet.cfg`, with GSP04's values.

### Implementation: Both models run every task from the same initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

A `Forward` step subclasses `SphericalConvergenceForward`. A
`forward.yaml` gives the shared settings for both models. MPAS-Ocean
sets `config_hmix_scaleWithMesh: false`, and Omega keeps the
`MeshScalingEnable: false` that `OceanModelStep` already sets.

Each task has a config section, `[galewsky_jet_<task>]`, giving its run
duration, output interval and ν. The forward step reads these in place
of `[convergence_forward]`. `rk4_dt_per_km` is 1.0.

### Implementation: An unperturbed jet stays steady without diffusion

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`steady_state` uses a `ConvergenceAnalysis` subclass like
`geostrophic`'s. The exact solution is the initial state, read from the
init step. Only the `both` refinement (space and time together) is
offered (D10). The evaluation time is `convergence_eval_time` in the
`[convergence]` section (D11). A viz step at each resolution plots
vorticity at 120 h with `plot_global_mpas_field`.

### Implementation: The early adjustment reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`adjustment` has one analysis step that depends on every resolution's
forward step. It writes the figures described above and a table of the
4 h values, with GSP04's values in the final row. The table goes to the
log and to a CSV file.

### Implementation: The diffusive instability reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

`unstable` has the same structure as `adjustment`, with vorticity
figures and a table of the 144 h values.

### Implementation: Results can be compared across resolutions and meshes

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

There are six tasks:

| Task path | Init | ν (m² s⁻¹) | Duration |
|---|---|---|---|
| `ocean/spherical/icos/galewsky_jet/steady_state` | balanced | 0 | 120 h |
| `ocean/spherical/icos/galewsky_jet/adjustment` | perturbed | 0 | 6 h |
| `ocean/spherical/icos/galewsky_jet/unstable` | perturbed | 1 × 10⁵ | 144 h |
| `ocean/spherical/qu/galewsky_jet/steady_state` | balanced | 0 | 120 h |
| `ocean/spherical/qu/galewsky_jet/adjustment` | perturbed | 0 | 6 h |
| `ocean/spherical/qu/galewsky_jet/unstable` | perturbed | 1 × 10⁵ | 144 h |

Resolutions come from `[spherical_convergence]`, as in `geostrophic`:
60, 120, 240 and 480 km for icosahedral meshes and 90, 120, 150 and
180 km for quasi-uniform meshes.

A module of diagnostics holds the vorticity, divergence, global-norm and
contour-plot helpers that `adjustment` and `unstable` share.

A `galewsky_jet` suite lists the six tasks.

Documentation follows the repository's usual pattern:

- a User's Guide page from `docs/users_guide/ocean/tasks/template.md`,
  with figures from the Chrysalis runs;
- a Developer's Guide page;
- `docs/developers_guide/api.md` entries.

## Testing

### Testing and Validation: Galewsky's balanced jet and perturbation define the initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

Unit tests in `tests/ocean/galewsky_jet` check, without a model:

- the jet peaks at 80 m s⁻¹ at 45°N and is zero outside
  $(\phi_0, \phi_1)$;
- the height has a global mean of 10 km and satisfies eq. 3's
  differential form to quadrature accuracy;
- the perturbation peaks at 120 m at (0°, 45°N);
- on a coarse icosahedral mesh, the discrete divergence of the initial
  velocity is zero to round-off, and its reconstructed zonal velocity
  matches eq. 2.

### Testing and Validation: Both models run every task from the same initial state

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

All six tasks run with both models on Chrysalis first. Omega then runs
them on Aurora and pm-gpu.

### Testing and Validation: An unperturbed jet stays steady without diffusion

Date last modified: 2026/11/10

Contributors: Xylar Asay-Davis, Claude

On icosahedral meshes, the thresholds are 1.8 for $h$ and for normal
velocity. On quasi-uniform meshes, they are 0.8 for $h$ and 1.7 for
normal velocity (D12). The vorticity plots show at which resolutions the
jet breaks down.

| Mesh | Machine | Model | $h$ rate | Normal velocity rate |
|---|---|---|---|---|
| icos | Chrysalis | MPAS-Ocean | 2.04 | 1.97 |
| icos | Chrysalis | Omega | 2.03 | 1.97 |
| icos | Aurora | Omega | 2.03 | 1.97 |
| icos | pm-gpu | Omega | 2.03 | 1.97 |
| QU | Chrysalis | MPAS-Ocean | 1.08 | 1.90 |
| QU | Chrysalis | Omega | 1.08 | 1.90 |
| QU | Aurora | Omega | 1.44 | 1.96 |
| QU | pm-gpu | Omega | 1.44 | 1.96 |

### Testing and Validation: The early adjustment reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

The figures are compared by eye with GSP06 Fig. 2 and the table with
GSP04 Table 1.

### Testing and Validation: The diffusive instability reproduces Galewsky's

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

The figures are compared by eye with GSP06 Fig. 6 and GSP04 Fig. 8, and
the table with GSP04 Table 1.

### Testing and Validation: Results can be compared across resolutions and meshes

Date last modified: 2026/11/09

Contributors: Xylar Asay-Davis, Claude

The `pr` suites run against a `main` baseline to confirm that the new
tasks change nothing else.

## Decisions

### D1: Gradient-wind balance, not f-only balance

The height comes from GSP04 eq. 3, including the $u \tan\phi / a$ term.
Balancing the height against $f$ alone, by solving
$-g\nabla^2 h = \nabla\cdot(f \mathbf{u}^\perp)$, was rejected. A 1-D
calculation puts the resulting height error at −13 to +77 m, against a
120 m perturbation. The unbalanced acceleration at 45°N is about
1 × 10⁻³ m s⁻², so the unperturbed jet would adjust from the first time
step.

### D2: Velocity from a vertex streamfunction

Normal velocity is differenced from a streamfunction at vertices. Point
sampling eq. 2 at edges, as `geostrophic` does, was rejected. It leaves
a discrete divergence that radiates gravity waves in `steady_state`.

### D3: Polaris constants, not GSP04's

The radius, gravity and rotation rate come from `get_constant`, as in
`geostrophic` and the spherical meshes. GSP04 used a = 6.37122 × 10⁶ m,
g = 9.80616 m s⁻² and Ω = 7.292 × 10⁻⁵ s⁻¹. The relative differences are
about 10⁻⁴. Balance requires the initial state to use the model's own
constants.

### D4: Three tasks, one per GSP04 stage

GSP04 §5 asks for all three stages, and Table 1 gives reference values
only for the adjustment and diffusive stages. `adjustment` costs about
1/24 of `unstable` and is the only check of the gravity-wave stage.
Omitting it was rejected for that reason. The diffusive and
inviscid perturbed runs cannot share a forward step, since ν differs.

### D5: Diffusion only where GSP04 uses it

`steady_state` and `adjustment` are inviscid and `unstable` uses
ν = 1 × 10⁵ m² s⁻¹, as in GSP04. Diffusing the steady jet was rejected.
A 1-D estimate shows ν alone lowers the jet's peak from 80 to about
67 m s⁻¹ in 6 days, which would hide the truncation error the task
measures.

GSP04 eq. 1 also diffuses $h$, but neither model has thickness
diffusion. The comparison with GSP06 Fig. 6 will show the effect.

### D6: No short regression task

A short run of the balanced jet exercises the same momentum terms as
`realistic_global`, `cosine_bell` and `geostrophic`, which the PR and
nightly suites already cover. The tasks join no existing suite until
their cost is known.

### D7: Diagnostics computed from normal velocity

Vorticity and divergence are computed in Python from the output normal
velocity, by the same code for both models. Using each model's own
diagnostic output was rejected. Polaris maps vorticity between the two
models' output names but not divergence, and any difference between the
models' operators would show up as a difference between the models.

### D8: Resolutions inherited from `geostrophic`

The first implementation uses `geostrophic`'s resolutions. The 480 and
240 km meshes cannot resolve the roll-up. The 60 km mesh may not be
fine enough for an inviscid jet to stay steady. The resolutions will be
revisited after the Chrysalis runs.

### D9: Contour plots on GSP04's longitude–latitude windows

The comparison figures copy GSP06's windows and contour levels so they
can be set beside the paper. Remapping to a regular grid was rejected as
an extra step that adds its own interpolation error. Filled maps from
`plot_global_mpas_field` are used only for the per-resolution
`steady_state` plots.

### D10: Joint space–time refinement only

`steady_state` offers only the `both` refinement. Separate space and
time refinement, as in `geostrophic`, was rejected for a first
implementation; it triples the task count without a new GSP04 check.

### D11: Convergence measured at 24 h, not 120 h

`steady_state` measures convergence at 24 h but runs for 120 h. In
Omega runs, the icosahedral wavenumber-5 imprinting and quasi-uniform
meanders grow to dominate the error by 72–96 h. At 120 h, the
normal-velocity error is 0.89 at 480 km and 0.10 at 60 km on icosahedral
meshes, and the fitted rates are about 1. At 24 h, the rates are about 2
on icosahedral meshes. Evaluating at 120 h was rejected because it
measures when the instability is triggered, not the truncation error.
The 120 h run keeps GSP04's duration, so the vorticity plots still show
when the jet breaks down.

### D12: Separate thresholds for icosahedral and quasi-uniform meshes

`steady_state` has its own pair of thresholds for each mesh type. On
icosahedral meshes, every run gives rates of 2.0 for both fields. On
quasi-uniform meshes, the rate for $h$ was 1.08 on the meshes JIGSAW
generated on Chrysalis and 1.44 on those from Aurora and pm-gpu, for the same
model. A single threshold low enough for quasi-uniform meshes was
rejected because it would not catch a loss of second-order convergence
on icosahedral meshes.
