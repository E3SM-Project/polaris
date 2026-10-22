# Mixed-Layer Eddies Task

Creation date: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds a planar ocean task, `mixed_layer_eddies`, in which a
mixed-layer front spins down through mixed-layer instability. It
reproduces the ice-free (c = 0) experiment of
[Shrestha & Manucharyan (2022)](https://doi.org/10.1175/JPO-D-21-0024.1)
(SM22). SM22 normalize the eddy overturning by the scaling of
[Fox-Kemper, Ferrari & Hallberg (2008)](https://doi.org/10.1175/2007JPO3792.1)
(FFH08), so the same run tests that scaling.

The task validates Omega's submesoscale eddy parameterization and its
MPAS-Ocean counterpart (`config_submesoscale_*`). An eddy-resolving
500 m run is the reference. Coarse runs at 8 and 16 km run with the
parameterization off and on. The task fills the testing plan in §5 of
Omega's
[submesoscale eddies design](https://github.com/E3SM-Project/Omega/blob/develop/components/omega/doc/design/SubmesoscaleEddies.md).
Omega is the primary model; MPAS-Ocean is supported for comparison.
The overturning diagnostic becomes a mesh-agnostic framework helper,
which other planar tasks such as ISOMIP+ can use.

The starting point is Carolyn Begeman's Compass draft, `arctic_channel`
(`cbegeman/compass:add_arctic_test`). It has SM22's geometry and
initial condition, but this design keeps only those (see D7
under Decisions).

Success has three parts:

- the parameterization computes what its formula says (implementation
  verification);
- the resolved run reproduces SM22's ice-free overturning (test
  validation);
- the parameterized coarse runs restratify like the resolved run
  (parameterization validation).

The first two say whether the code and the test are correct, and each
has a pass/fail check. The third is a longer-term scientific question,
so it is reported but not checked (D13).

## Open questions

- Whether C_e should be tuned so the coarse runs release as much
  potential energy as the resolved run. The comparison reports that
  ratio as the target for such tuning.

## Requirements

### Requirement: An ice-free mixed-layer front spins down in a doubly periodic domain

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The task shall reproduce SM22's ice-free configuration: a doubly
periodic, flat-bottomed f-plane domain, 300 km × 200 km × 152 m, with
f = 1.4 × 10⁻⁴ s⁻¹ and a salinity-only linear equation of state. The
initial state is at rest. It has a 30 m mixed layer carrying two
opposing sinusoidal salinity fronts over the ITP77 Arctic profile. There
is no surface forcing.

### Requirement: Omega runs on its native coordinate, and MPAS-Ocean runs for comparison

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Every task shall run with Omega on the p-star vertical coordinate and
with MPAS-Ocean on z-star, from the same initial state.

### Requirement: An eddy-resolving reference run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

A 500 m run shall resolve mixed-layer instability for 15 days without
the parameterization.

### Requirement: Coarse runs with the parameterization off and on

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

Runs at 8 and 16 km, too coarse to permit mixed-layer instability,
shall each run with the parameterization off and on with E3SM's coupled
defaults. Both models shall use the same parameter values.

### Requirement: The eddy overturning is diagnosed consistently with the models' discrete transports

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The cross-front overturning stream function Ψ(y, z) shall be computed
from edge-normal transports, the quantities the models' continuity
equations use. This applies to both the resolved eddy overturning and
the parameterized one.

The computation shall be exact on any planar MPAS mesh, and other tasks
shall be able to use it.

### Requirement: The parameterization's implementation is verified

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

A coarse run with the parameterization on shall produce the stream
function that the FK11 formula gives for the run's own state. A
mismatch fails the task.

### Requirement: The test reproduces the published ice-free overturning

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

In the resolved run, the normalized overturning |Ψ⁺| in the frontal
zone, averaged over days 5–7, shall be close to 1, as in SM22. A value
outside the tolerance fails the task.

### Requirement: Coarse runs are compared with the resolved run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The restratification of each coarse run shall be reported relative to
the resolved run. It does not fail the task.

## Algorithm Design

### Algorithm Design: An ice-free mixed-layer front spins down in a doubly periodic domain

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The density follows SM22 (their eq. 5 and published `gendata.m`):

$$
\rho(y, z) = Z_S(z)\left[\Delta\rho_y Y_S(y) - \Delta\rho_z\right]
  + \rho_{ITP}(z),
$$

$$
Z_S(z) = \tfrac{1}{2}\left[1 + \tanh\left(\frac{z + H_m}{\Delta h}\right)\right],
\qquad
Y_S(y) = \sin\left(\frac{2\pi (y - L_y/2)}{L_y}\right),
$$

with $H_m = 30$ m, $\Delta h = 5$ m, $\Delta\rho_y = 3$ kg m⁻³ and
$\Delta\rho_z = \Delta\rho_y/2$. $L_y$ is the mesh's periodic length,
not the nominal 200 km, so the front is periodic. The front at
$y = L_y/2$ is analyzed. The other front, at $y = 0$, closes the
periodic domain.

- **EOS:** $\rho = \rho_0[1 + \beta(S - S_0)]$, with
  $\rho_0 = 1027.5$ kg m⁻³, $S_0 = 34$ and $\beta = 10^{-3}$. Salinity
  is $S = S_0 + (\rho - \rho_0)/(\rho_0 \beta)$. Temperature is
  constant.
- **Background profile:** $\rho_{ITP}$ comes from the ITP77 salinity
  profile. Above $z = -H_m$ it is held at its value at $z = -H_m$.
- **Noise:** salinity noise, uniform in ±0.01 and drawn from a fixed
  seed, seeds the instability.
- **Initial flow:** velocity is zero and the surface is flat. The front
  first undergoes Rossby adjustment, which takes about 2 days in SM22.
  See D5.
- **Vertical mixing:** constant background diffusivity and viscosity of
  10⁻⁵ m² s⁻¹, plus convective and LMD94 shear mixing. KPP is off. SM22
  used KPP, but without surface forcing only its interior shear mixing
  acts.
- **Horizontal viscosity:** constant del2 and del4, scaled with
  resolution. SM22 used Smagorinsky viscosity, which Omega does not
  have.
- **Bottom drag:** quadratic, with C_d = 2 × 10⁻³ (SM22).

> **Rationale.** The Stone (1970) fastest-growing wavelength is about
> 6.5 km and the e-folding time is about 9.5 h (SM22, at Ri ≈ 1). At
> 500 m the wavelength spans 13 cells, comparable to FFH08's
> Δx = L_s/10. At 8 km it is shorter than a cell, so mixed-layer
> instability cannot develop on the coarse grids. At 2 and 4 km it
> does (D11).

### Algorithm Design: Omega runs on its native coordinate, and MPAS-Ocean runs for comparison

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The initial state uses the [p-star initialization](pstar_init.md). The
target is a 152 m geometric bottom and the surface pressure is zero.
The vertical grid has 64 uniform pseudo-height levels, about 2.4 m
each. As in the overflow p-star trees, MPAS-Ocean runs z-star from the
converged geometric thicknesses. With a salinity-only linear EOS, pseudo
and geometric thicknesses differ by under 0.5%.

### Algorithm Design: An eddy-resolving reference run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The 500 m mesh has 600 × 462 cells, about 277,000 in all, which is
comparable to EC30to60. A 15-day run needs about 2 × 10⁴ time steps.
The run has three segments, each continuing from the restart the one
before writes: a spin-up to day 5, SM22's diagnosis window over days
5–7 and an extension to day 15. All write daily snapshots of the full
state; the window also writes 3-hourly snapshots of `normalVelocity`,
layer thickness and salinity.

### Algorithm Design: Coarse runs with the parameterization off and on

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The coarse runs use the same initial condition, run for 15 days, and
write daily output. Their parameterization settings are:

| setting | Enable | C_e  | τ (s)  | L_f,min | Δs_max |
|---------|--------|------|--------|---------|--------|
| `off`   | false  | —    | —      | —       | —      |
| `on`    | true   | 0.08 | 172800 | 1 km    | 100 km |

The `on` row is E3SM's coupled MPAS-Ocean default (in
`namelist_defaults_mpaso.xml`) and is also Omega's default. Both grid
lengths are below Δs_max, so Δs is the edge's `dcEdge`. Here
τ⁻¹ ≪ f, so √(f² + τ⁻²) ≈ |f|.

> **Rationale.** The coarse grids still resolve the 200 km front, but
> the scheme multiplies Ψ by Δs/L_f. That is a factor of several here,
> because L_f ≈ 1–1.4 km. The `on` setting shows what E3SM would
> actually do (D12).

### Algorithm Design: The eddy overturning is diagnosed consistently with the models' discrete transports

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

A line $y = y_0$ is represented by the set $B(y_0)$ of edges whose two
cells lie on opposite sides of it. Edges on a domain boundary are
excluded, as are edges across a periodic seam, whose cells are more than
half a period apart. Let edge $e$ have cells $c_1, c_2$
(`cellsOnEdge`). Then $s_e = +1$ if $y_{c_1} < y_0 \le y_{c_2}$ and
$-1$ for the reverse, because MPAS normal velocity is positive from
$c_1$ to $c_2$. The along-front mean stream function at interface $k$
is

$$
\Psi(y_0, z_k) = \frac{1}{L_x} \sum_{e \in B(y_0)} s_e \, d_e
  \sum_{k' < k} u_{e,k'} \, h_{e,k'},
$$

so $\Psi = 0$ at the surface and $\bar v = -\partial \Psi/\partial z$.
Here $d_e$ is `dvEdge` and $h_e$ is the flux thickness on the edge. For
Omega that is the pseudo-thickness, which makes the transport a mass
transport. $L_x$ is the mesh's `x_period`.

The sum is the exact discrete transport from the cells south of $y_0$
to those north of it, on any mesh. On the planar hex mesh, $B(y_0)$ is
the zigzag between two rows of cells. On other meshes it is a staircase
within about one cell of $y_0$.

Along-line means of edge quantities use the weights
$w_e = d_e |\Delta y_e| / \delta_e$, where $\delta_e$ is `dcEdge`. On a
Voronoi mesh the edge normal is parallel to the segment joining its
cell centers, so $w_e$ is the edge's length projected onto x. The
weights sum to $L_x$.

- **Parameterized Ψ:** take $u_e$ as the eddy velocity (`EddyVelocity`
  in Omega, `normalMLEvelocity` in MPAS-Ocean). This is exactly the
  transport the scheme adds.
- **Resolved Ψ:** use SM22's thickness-weighted isopycnal stream
  function (their §2c):
  - bin each edge-layer transport $s_e d_e u_e h_e$ by edge salinity,
    which measures density under this EOS;
  - average over days 5–7 and map each salinity surface to its mean
    depth;
  - take the eddy part as this residual overturning minus the
    Eulerian-mean overturning at the same depth (Abernathey et al.
    2011), the integrated form of $\overline{vh} - \bar v \bar h$.
- **Normalization:**

$$
\Psi^+ = \frac{\Psi}{C_e H^2 \, \overline{\partial_y b} \, \mu(z) / |f|},
\qquad
\mu(z) = \max\left\{0, \left[1 - \left(\tfrac{2z}{H} + 1\right)^2\right]
  \left[1 + \tfrac{5}{21}\left(\tfrac{2z}{H} + 1\right)^2\right]\right\},
$$

where $\overline{\partial_y b}$ is the mixed-layer, x- and time-averaged
buoyancy gradient. It is computed from differences of area-weighted
means over y-bands about one cell wide, across the frontal zone
$|y - L_y/2| < L_y/8$ (SM22's 75–125 km). $C_e = 0.08$ and $H = H_m$.

> **Rationale.** Cell-reconstructed velocities smooth the field and do
> not close the discrete volume budget. Edge sums do, and need no
> interpolation. They also assume no mesh structure: they use only
> `cellsOnEdge`, `yCell`, `dvEdge` and `dcEdge`. FFH08's
> Held–Schneider form, $\overline{w'b'}/\bar b_y$, needs an Eulerian
> $w$. Under z-star or p-star the models provide only velocities across
> moving surfaces. Binning by salinity needs only horizontal
> transports. See D8.

### Algorithm Design: The parameterization's implementation is verified

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The parameterized Ψ on each frontal-zone edge is recovered from the
eddy velocity in the last (day-15) output of each coarse `on` run. It
is compared, edge by edge, with the FK11 formula evaluated from the
same output as the models discretize it:

- the model's own mixed-layer depth (`DenMixLayerDepth` or `dThreshMLD`)
  and N² (`BruntVaisalaFreqSq` or `BruntVaisalaFreqTop`);
- thickness-weighted means over interfaces, from the surface to the top
  of the first layer below the mixed-layer depth. MPAS-Ocean writes that
  layer's index (`indMLD`). For Omega, it is found from the mixed-layer
  depth, measured from the sea surface;
- each model's conventions: H on edges is the minimum of the two cells'
  in Omega and the mean in MPAS-Ocean.

Only edges whose output mixed-layer depth lies within the deepest layer
with nonzero eddy velocity are compared. Elsewhere the output depth is
not the one the eddy velocity used: in Omega the two come from
different stages of a time step, and where the mixed layer is nearly
neutral the diagnosed depth jumps by layers between them. The check
fails if fewer than half the edges qualify or the relative error on
them exceeds 15%.

> **Rationale.** The final runs give errors of 1–5% on 92–100% of
> edges in Omega and about 1% on all edges in MPAS-Ocean. While the
> mixed layer restratifies (days 1–7), Omega's output depth often
> differs from the one its eddy velocity used, so fewer edges qualify
> and errors reach 20% at 16 km. MPAS-Ocean clamps its mixed-layer depth
> to a layer midpoint in places, and its output layer depths differ
> slightly from those it used, so the layer index cannot be recovered
> from the depth; hence `indMLD`. Errors from a sign, a factor, a wrong
> frontal width or C_e of 0.06 instead of 0.08 are larger.

### Algorithm Design: The test reproduces the published ice-free overturning

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The check is that |Ψ⁺| at mid-mixed-layer, from the resolved run, lies
in [0.5, 2]. FFH08 fit C_e = 0.06 to balanced runs and 0.08 to all
runs, so the window allows for that spread and for the start from rest.

### Algorithm Design: Coarse runs are compared with the resolved run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

The comparison uses potential energy per unit area,
$PE = \int \rho g z \, dV / A$, and the mixed-layer mean N² in the
frontal zone. These are among the measures in Omega's design (§5).
Rossby adjustment releases potential energy in every run, so the
comparison uses the release after it,
$\Delta PE = PE(\text{day } 2) - PE(\text{day } 15)$, relative to the
resolved run. The ratios are written to a table and plotted, with no
thresholds (D13). A ratio near 1 for the `on` runs is the target for
tuning C_e.

## Implementation

### Implementation: An ice-free mixed-layer front spins down in a doubly periodic domain

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

New package `polaris/tasks/ocean/mixed_layer_eddies/`:

- `mixed_layer_eddies.cfg`: domain, front, EOS, Coriolis
  (`[coriolis] type = constant`), vertical grid, run duration and
  check tolerances.
- `itp77.csv`: the ITP77 profile, packaged with its provenance. It is
  about 150 rows at 1 dbar spacing to 153 dbar, from the Compass
  database file `mixed_layer_restrat/itp77.csv`.
- `init.py`: `Init(PStarInitStep)` builds a doubly periodic
  `make_planar_hex_mesh` (`nonperiodic_x=False`, `nonperiodic_y=False`)
  and implements `init_tracers()` with the density above.

The linear EOS uses `eos_linear_alpha = 0`, `eos_linear_beta =` ρ₀β,
and a reference density giving ρ₀ at S₀. Omega's linear EOS rejects a
nonzero `Sref`.

```
ocean/planar/mixed_layer_eddies/
├── 500m/{init, spinup, eddies, extended}           (shared steps)
├── 8km/, 16km/{init, forward_off, forward_on}      (shared steps)
├── resolved       (task: 500m steps + analysis)
├── coarse         (task: coarse steps + verify)
└── comparison     (task: all shared steps + analysis)
```

### Implementation: Omega runs on its native coordinate, and MPAS-Ocean runs for comparison

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

`polaris/ocean/model/mpaso_to_omega.yaml` gains two mappings:

- the options: `submesoscale_eddy_parameterization` →
  `Submeso: {Enable, Tau, Ce, LfMin, DsMax}`;
- the variables: `normalMLEvelocity` → `EddyVelocity` and
  `dThreshMLD` → `DenMixLayerDepth`.

The config file sets `coord_type = p-star`. The step writes both models'
initial files, as the overflow `PStarInit` does.

### Implementation: An eddy-resolving reference run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

`forward.py` and `forward.yaml` follow `baroclinic_channel`, with
`dt_per_km` and `btr_dt_per_km` options. One `Forward` class runs a
segment: `full` for the coarse runs, and `spinup`, `eddies` and
`extended` for the resolved run. Both models split the resolved run,
because MPAS-Ocean streams cannot limit output to a time window and
Polaris builds a task's steps before it knows the model. Restarts go to
a shared `restarts` directory, and each segment's restart alarm is
anchored at its start time. The 3-hourly output is about 12 GB.

### Implementation: Coarse runs with the parameterization off and on

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

One `Forward` class takes the setting name and applies the table above
through the mapped MPAS-Ocean options. All values are set explicitly,
because the MPAS-Ocean Registry default C_e (0.06) differs from E3SM's.

### Implementation: The eddy overturning is diagnosed consistently with the models' discrete transports

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

A new framework module, `polaris/ocean/overturning.py`, works on any
planar MPAS mesh, for lines of constant x or y:

- `get_line_edges(ds_mesh, coord, value)` returns the edges crossing
  the line, with their signs and along-line weights;
- `compute_line_transport(ds_mesh, line, normal_velocity,
  layer_thickness)` returns the signed transport per edge and layer,
  using the centered flux thickness that is the default in both models;
- `compute_overturning(transport)` sums along the line and accumulates
  from the surface to give Ψ at interfaces;
- `bin_line_transport(transport, tracer, bins)` returns the per-edge
  transport and thickness in tracer classes, for density-class
  overturning.

It is a dependency-light leaf module and takes arrays, not model
output. The task's `diagnostics.py` builds on it: it computes the
salinity-binned eddy decomposition, the y-band means and Ψ⁺. It reads
output through the Polaris variable mapping, so one code path serves
both models.

### Implementation: The parameterization's implementation is verified

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

`coarse/verify.py` is an analysis step in the `coarse` task. It
evaluates the FK11 formula from each coarse run's last output and
fails the task if the relative error or the fraction of qualifying
edges is outside the configured limits. Runs with the parameterization
on also write N² for this check.

### Implementation: The test reproduces the published ice-free overturning

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

`resolved/analysis.py` computes Ψ and Ψ⁺ and plots them: Ψ⁺ against
μ(z), as in FFH08 Fig. 10 and SM22 Fig. 8. It fails the task if |Ψ⁺|
falls outside the window.

### Implementation: Coarse runs are compared with the resolved run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

`comparison/analysis.py` plots PE(t), the frontal-zone N²(t) and the
final surface salinity for all five runs. It writes the release ratios
to a table and has no check.

The planned commits are:

1. Add this design document.
2. Map the submesoscale options and variables between MPAS-Ocean and
   Omega.
3. Add the `polaris.ocean.overturning` framework module and its unit
   tests.
4. Add the ITP77 profile, config and `Init` step.
5. Add the forward steps and the three tasks.
6. Add the task's diagnostics and the three analysis steps.
7. Add unit tests for the task.
8. Add the User's and Developer's Guide pages, including the
   framework module.

## Testing

### Testing and Validation: An ice-free mixed-layer front spins down in a doubly periodic domain

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Unit tests check the analytic density and salinity, the periodicity of
$Y_S$ on the mesh, and that the noise is reproducible. Manual runs
check that the resolved run's eddies emerge by about day 3, with
wavelengths near 6.5 km.

### Testing and Validation: Omega runs on its native coordinate, and MPAS-Ocean runs for comparison

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Run `coarse` with both models. A unit test covers the new option and
variable mappings.

### Testing and Validation: An eddy-resolving reference run

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Run `resolved` once with each model as a job on a compute node, after
the time step and viscosity are set on `coarse`.

### Testing and Validation: Coarse runs with the parameterization off and on

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Check in the generated `omega.yml` and `namelist.ocean` that the
settings match the table.

### Testing and Validation: The eddy overturning is diagnosed consistently with the models' discrete transports

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Unit tests in `tests/ocean/test_overturning.py` use small planar hex
meshes. Lines of constant y give the row zigzag, and lines of constant
x give staircases. On both kinds of line:

- a uniform flow must give exactly its velocity times the line length;
- a prescribed Ψ, converted to edge velocities, must be recovered to
  round-off;
- the weights must sum to the line length.

Periodic and non-periodic meshes check that seam and boundary edges
are excluded.

### Testing and Validation: The parameterization's implementation is verified

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Confirm that the check fails when C_e is perturbed by 20% in one model
run but not in the analysis.

### Testing and Validation: The test reproduces the published ice-free overturning

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Compare the Ψ⁺ profiles with SM22 Fig. 8 and the Ψ⁺ time series with
SM22 Fig. 2.

### Testing and Validation: Coarse runs are compared with the resolved run

Date last modified: 2026/10/20

Contributors: Xylar Asay-Davis, Claude

Report the release ratios on the PR, with a one-off sweep of C_e
(0.04 and 0.06) at 8 and 16 km in both models. None of the tasks is
added to a suite. `coarse` is the candidate if one is ever wanted.

## Decisions

### D1: A separate task, not a `baroclinic_channel` variant

Xylar, 2026/10/19. The two share only a periodic planar mesh. The
domain, initial condition, forcing and diagnostics all differ.

### D2: Ice-free only; ice-covered runs are future work

Xylar, 2026/10/19. SM22's ice runs need ice–ocean drag. Omega has no
top drag, and no open PR adds it. They also need an ice-aware
parameterization. For MPAS-Ocean that is
[E3SM#8520](https://github.com/E3SM-Project/E3SM/pull/8520), which is
open; Omega has none. SM22's free-drifting ice becomes nearly immobile
above c ≈ 0.68. A stationary, concentration-weighted ice lid with
quadratic drag would therefore capture the regime where Ψ drops about
fourfold. That is a natural follow-up once Omega has top drag.

### D3: SM22's configuration, with FFH08 through its scaling

Xylar, 2026/10/19. A single configuration keeps the cost to one
resolved run. An FFH08-style mid-latitude configuration is a possible
follow-up. It would have f ≈ 7.3 × 10⁻⁵ s⁻¹, a temperature front and
a 50–200 m mixed layer.

### D4: Doubly periodic, not a channel

Xylar, 2026/10/19. SM22 is doubly periodic. A wall-bounded channel, as
in the Compass draft and FFH08, adds sidewall effects that FFH08 had to
exclude from their diagnosis window. It also needs culling, and it fits
a sinusoidal front poorly.

### D5: Start from rest

SM22's text says the front starts in geostrophic balance. Their
published configuration, however, reads only salinity. Its initial U,
V and SSH files are commented out, and they describe a 2-day
adjustment. FFH08 found balanced and unbalanced starts follow the same
scaling.

### D6: 64 uniform levels

This replaces SM22's 68 stretched levels, which range from 0.2 to
20 m. New Omega grids use a multiple of 16 levels. About 2.4 m spacing
is close to SM22's maximum of 2 m in the mixed layer.

### D7: The Compass draft is a reference, not a port

Several parts of the draft are not carried over:

- its `hydro`/`nonhydro` split, which needs a nonhydrostatic
  MPAS-Ocean fork;
- the solitary-wave `[visualize]` options;
- its stream-function scripts.

Its initial condition also has bugs, which this design avoids:

- `fVertex` is zero;
- the thermal-wind velocity is too weak by a factor of 2;
- the SSH sign is inverted;
- the EOS it uses does not match the model's;
- the sine period does not match the domain.

### D8: A mesh-agnostic stream function from edge transports

Xylar, 2026/10/19. Xylar asked whether Ψ should be computed with
TRiSK-consistent numerics; edge transports are those numerics.

- **Mesh-agnostic, not row sums.** A first draft summed the zigzag
  between rows of the planar hex mesh, which would break on any other
  mesh. Xylar preferred a mesh-agnostic form the framework can share.
  It gives identical answers on hex meshes.
- **A second user.** ISOMIP+'s overturning stream function, across
  lines of constant x, can use the same helper.
- **Alternatives rejected.** Cell reconstructions and FFH08's
  $\overline{w'b'}$ form were rejected for the reasons in the
  diagnostic's rationale.

### D9: E3SM coupled defaults, set explicitly

Xylar, 2026/10/19. The `on` setting uses E3SM's coupled values. These
equal Omega's defaults, but not MPAS-Ocean's Registry default, whose
C_e is 0.06.

### D10: Full 300 km domain

Xylar, 2026/10/19. Shrinking L_x to 100 km would cut the resolved
run's cost by a factor of about 3. The full domain keeps comparisons
with SM22's figures direct. The task runs on demand.

### D11: Coarse runs at 8 and 16 km

Xylar, 2026/10/20, after review by Luke Van Roekel and Carolyn Begeman.
The first runs included 2 and 4 km. At 2 km the instability is resolved
and at 4 km it is permitted, so the runs restratified with the
parameterization off, releasing 0.89 and 0.65 times the resolved run's
potential energy. The parameterization is meant for grids that cannot
permit the eddies, and 8 and 16 km are both below Δs_max.

### D12: Off and on, with no FFH08-like setting

Xylar, 2026/10/20. A third setting set L_f,min = Δs_max = 2 km to hold
Δs/L_f at 1. That does not ensure it: L_f is diagnosed larger once
NH/|f| exceeds L_f,min. E3SM has never been run that way, so the
setting was dropped and `on` means E3SM's coupled defaults.

### D13: The comparison is report-only

Xylar, 2026/10/20. Only the formula check (`coarse`) and |Ψ⁺|
(`resolved`) fail a task. The potential-energy ratio measures how well
the scheme, with a given C_e, matches the resolved restratification. It
is a target for tuning, not a test of correctness.

### D14: 15-day runs

Xylar, 2026/10/20. Luke Van Roekel noted that mixed-layer eddies take
about 10 days to reach finite amplitude, so 7 days is too short to
compare restratification. The diagnosis window stays at days 5–7 to
match SM22.
