# Discrete Hydrostatic Consistency in `horiz_press_grad`

Creation date: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

## Summary

The Omega design document for the higher-order horizontal pressure gradient
(`components/omega/doc/design/PGradHighOrder.md`, §2.3 and §3.7) requires
**discrete hydrostatic consistency**: for horizontally uniform conservative
temperature and absolute salinity, with coordinate surfaces tilted arbitrarily
between adjacent columns, the scheme must return exactly zero horizontal
pressure-gradient acceleration (HPGA), to machine precision, with no background
reference state. Its §5.2 makes that a gating test and names the Polaris
two-column task as one of the places it should be exercised.

This design adds two variants to the `ocean/horiz_press_grad` task family that
measure that property, together with the reference-free analysis they need. The
new capability is:

- Two **exact resting states** in which the true HPGA is identically zero, so
  the model's HPGA *is* the error and no reference solution is required:
  `hydrostatic_consistency` (tilted coordinate, flat sea floor) and
  `bathymetry_step` (flat coordinate, stepped sea floor).
- A **tilt scan**: at fixed resolution, the tilt is swept over roughly three
  decades and the exponent $q$ in $\lVert\text{HPGA}\rVert \sim
  (\text{tilt})^{q}$ is measured. The exponent, not a single pass/fail, is the
  discriminating output.
- A **reference-free analysis step**, `RestingAnalysis`, which compares against
  zero rather than against `ReferenceColumn`, retains the Omega-vs-Polaris
  consistency check, and guards the resting-state premise itself.

The primary challenge is not the numerics but the **severity of the
configuration**. The existing `ztilde_gradient` variant is already structurally
a resting state with a tilted coordinate, and the centered scheme passes it with
an RMS HPGA of $\sim 7\times10^{-12}$ m s$^{-2}$ — six orders of magnitude below
the $\sim 3\times10^{-6}$ m s$^{-2}$ bottom-layer error seen in realistic global
Omega runs. A new variant that inherits that configuration would pass trivially
and measure nothing. The design is **successful** if the centered scheme is
driven to an RMS HPGA of at least $10^{-6}$ m s$^{-2}$ somewhere in the sweep
(the *sensitivity gate*), if the measured tilt exponent is stable and
interpretable, and if the resulting diagnostic is ready to be pointed at the
`FiniteVolume` scheme when it exists.

### Two stages, and a note on the word "phase"

This design was written and first implemented before Omega's `FiniteVolume`
scheme existed, and extended once it did. The two Polaris stages are named
rather than numbered, because `PGradHighOrder.md` uses **Phase 1** and **Phase
2** for the scheme's *order* — Phase 1 being `HorzOrder: 2` with a linear
vertical reconstruction, Phase 2 order 4 with PPM — and two independent pairs of
ordinals in one document is a reliable source of confusion.

| stage | what it delivered |
| --- | --- |
| **the calibration stage** | the two resting-state variants, the reference-free analysis, and the `Centered` baseline measured in Omega: tilt exponent $q = 1.000$, sensitivity gate passing by 21–23× |
| **the rollout stage** | scheme selection and the §5.1 gates set from a `Centered`-versus-`FiniteVolume` comparison |

Everything here concerns Omega Phase 1. "Phase" below always means the Omega
sense.

The calibration stage's output is what makes the rollout readable: with the
centered exponent measured at 1.000 to five digits, a `FiniteVolume`
measurement is read against a known-good value rather than against an
expectation.

### What the rollout stage adds

- **A scheme axis.** Each variant runs both `Centered` and `FiniteVolume` over
  one shared initial condition, so the two are compared at an identical state.
- **A second Python kernel to compare against.** `init.py` writes
  `HPGAFiniteVolume` alongside `HPGA`, and each analysis step compares Omega
  against whichever matches the scheme that produced its output.

The two variants deliberately isolate two different mechanisms, which the
sizing work below showed are **not** the same mechanism:

| | `hydrostatic_consistency` | `bathymetry_step` |
| --- | --- | --- |
| what tilts | the p-star reference grid, via `z_tilde_bot_grad` | nothing; only the sea floor moves |
| where the error lives | every layer, growing with depth | the deepest layer valid in both columns, only |
| behaviour vs. the swept parameter | a clean power law | a staircase, set by where `maxLevelCell` changes |
| what it represents | thin, steeply sloped layers in a general ALE coordinate | the bottom partial cell at a bathymetry step |

## Requirements

### Requirement: The test configuration is an exact resting state

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Each new variant shall be a configuration whose true, continuous HPGA is
identically zero at every point in the water column, so that the model's
computed HPGA is entirely error and no reference solution is needed. The
resting-state property shall be a consequence of the configuration
(horizontally uniform conservative temperature and absolute salinity specified
as functions of pseudo-height, with no surface-pressure gradient), not an
approximation.

### Requirement: The geometry under test is verified, not assumed

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

The analysis shall confirm at run time that the geometry actually built is the
geometry the configuration asked for, and shall fail loudly if it is not. A
sweep whose swept parameter has been silently altered by the vertical-grid
construction reports an error level for a configuration that was never tested,
in either direction — too large or too small.

### Requirement: The test reaches the severity at which the centered scheme fails

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

At its most severe configuration, the sweep shall drive the existing centered
scheme to an RMS HPGA of at least $10^{-6}$ m s$^{-2}$ — the order of the
bottom-layer HPGA error observed in realistic global Omega runs with a uniform
temperature and salinity state. A sweep that does not reach this level is not
exercising the failure mode the higher-order scheme is meant to fix, and any
conclusion drawn from it about the new scheme would be unsupported.

### Requirement: The measurement discriminates between mechanisms, not just pass and fail

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

The analysis shall report the exponent $q$ in $\lVert\text{HPGA}\rVert \sim
(\text{tilt})^{q}$, restricted to the portion of the sweep where the result is
well above the round-off floor, in addition to absolute error levels. A single
pass/fail number cannot distinguish "the scheme represents specific volume as
piecewise constant in pressure" from "the scheme has a higher-order residual"
from "the scheme is exact", and those are the outcomes the test exists to
separate.

### Requirement: The deepest layer valid in both columns is measured, not discarded

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

The error metric shall include the deepest layer that is valid in both columns
bounding the edge. That layer is the bottom partial cell, and it is where the
pressure-gradient error concentrates; excluding it removes the signal these
tests exist to measure.

This applies to the **reference-based `Analysis` step as well as** to the new
resting-state analysis. `Analysis` currently drops that layer, which is a
leftover from the previous five-column finite-difference reference whose
stencil could not be formed where a neighbouring column's collocation point
fell below its own bathymetry. The reference is now a single analytic column at
the edge, documented as valid to the seafloor, so the exclusion no longer has a
basis. Fixing it is in scope here because it is the same decision, and because
leaving the two analysis steps disagreeing about which layers count would be
incoherent.

### Requirement: The existing variants and their pass criteria are untouched

Date last modified: 2026/08/02

Contributors: Xylar Asay-Davis, Claude

The four existing variants (`salinity_gradient`, `surface_pressure_gradient`,
`temperature_gradient`, `ztilde_gradient`), the `ReferenceColumn` evaluator, and
the convergence-rate and reference thresholds in `horiz_press_grad.cfg` shall
behave exactly as they do today. The new capability shall not change their step
names, work directories, or results.

**Amended for the rollout stage.** This requirement held for the calibration
stage and is deliberately relaxed by the rollout, in two respects:

- the scheme axis puts a scheme label in every forward step's directory, so the
  step names *do* change and the recorded centered baselines have to be
  regenerated. This is the cost of running both schemes over one shared `Init`
  rather than duplicating the initial condition per scheme;
- the convergence bands become per-variant and per-scheme. A single band cannot
  serve four variants whose measured centered rates are 1.6, 1.8, 2.0 and 1.1.

What the rollout does **not** change is the four variants' *results* under
`Centered`, or the meaning of `HPGA`. Any change there is a regression.

### Requirement: The cross-implementation check compares the same algorithm

Date last modified: 2026/08/02

Contributors: Xylar Asay-Davis, Claude

`omega_vs_polaris_rms_threshold` is the only check in the family that compares
Omega's arithmetic against an independent implementation of the same scheme, and
it is worth exactly as much as the claim that the two sides *are* the same
algorithm. Where the Python kernel makes a discretization choice that Omega
makes differently — the quadrature rule and its order, which end of the column
the scan is anchored at, how the reconstruction is closed at the ends of a
column, how the edge-shared expansion point is formed — the check stops
measuring implementation disagreement and starts measuring the gap between two
different algorithms, which is not distinguishable from a bug in either.

Every such choice shall therefore be reconciled against `PGradHighOrder.md`
before the check is run in anger, and each resolution recorded with its
provenance. Two constraints on how:

1. **The design is the source, not the C++.** The Python kernel was written from
   `PGradHighOrder.md` precisely so that this comparison has content. Reading
   the Omega implementation to settle a question of *intent* the design leaves
   open is legitimate; transcribing it is not, because a Python kernel derived
   from the C++ would compare an implementation against itself.
2. **Reconcile up front rather than by bisection.** The check produces one
   scalar per resolution. It can report that the two sides disagree; it cannot
   report which of several choices disagrees, and several of them first bite in
   the same configurations.

Where a reconciliation finds that the *Python* follows the design and Omega does
not, it stops being a Polaris change and is handed back rather than papered over
by adjusting the Python to match.

## Algorithm Design

### Algorithm Design: Why these configurations are exact resting states

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Omega's vertical coordinate is pseudo-height $\tilde z = -p/(\rho_0 g)$, so
pressure is an exactly linear function of $\tilde z$ and a surface of constant
$\tilde z$ is a surface of constant $p$. `Init` interpolates conservative
temperature $\Theta$ and absolute salinity $S_A$ against $\tilde z$ from
piecewise profiles whose node values and node pseudo-heights are set by
`*_mid` and `*_grad` configuration options. Setting every `*_grad` to zero makes
$\Theta$ and $S_A$ **the same functions of $\tilde z$, and therefore of $p$, in
both columns**. Specific volume is then a function of pressure alone,

$$
\alpha = \alpha\bigl(\Theta(p), S_A(p), p\bigr) \equiv \alpha(p),
$$

isobars are level surfaces, and the true HPGA is identically zero everywhere in
the fluid — for **any** sea-floor shape and **any** tilt of the coordinate
surfaces. This is what makes both variants valid resting states, and it is the
discrete analogue of the property §3.7 of the Omega design asserts.

Two configuration choices are therefore forced:

- `temperature_grad`, `salinity_grad` and `z_tilde_grad` are all zero (inherited
  from the base `horiz_press_grad.cfg`), and `surface_pressure_grad` is zero, so
  the sea surface is flat.
- The deepest profile node lies below the deepest reference-grid interface in
  *either* column, so the PCHIP interpolant is never asked to extrapolate when
  the tilt makes one column's reference grid deeper than the other's.

### Algorithm Design: What actually tilts the coordinate in a p-star column

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

This is the design's central finding, and it determined the shape of both
variants.

`init_pstar_vertical_coord` builds each column by clipping a reference 1-D grid
at that column's `BottomPressure`. In `Init`, the reference grid for column $i$
is uniform over $[0, -\tilde z^{\text{bot}}_i]$ with a level count fixed by the
mid-column value, so `z_tilde_bot_grad` **stretches** one column's reference
grid relative to the other's. The cross-edge offset of interface $k$ then grows
linearly with depth,

$$
\Delta \tilde z_k \;=\; \frac{k}{N}\,
   \bigl(\tilde z^{\text{bot}}_1 - \tilde z^{\text{bot}}_0\bigr),
$$

which is the tilted-coordinate configuration §3.7 describes. **This is the only
mechanism in the two-column task that tilts interior coordinate surfaces.**

A sea-floor step does *not* tilt them. With `z_tilde_bot_grad = 0` both columns
share one reference grid, and moving the sea floor changes only where that grid
is clipped. Every interior interface sits at an identical pseudo-height — and
hence an identical pressure — in both columns, so the cross-edge pressure
difference is exactly zero above the bottom. Offline replication of the Polaris
`Init` arithmetic confirms this: with a sea-floor gradient of 10–200 m km$^{-1}$
and a flat coordinate, the RMS HPGA over the interior layers is
$\sim 10^{-15}$ m s$^{-2}$ (round-off), while the deepest layer valid in both
columns carries $2\times10^{-6}$ to $8\times10^{-5}$ m s$^{-2}$.

Two consequences follow:

1. `bathymetry_step` is a test of the **bottom partial cell**, not of interior
   layer tilt, and its whole signal is in the one layer the reference-based
   analysis discards. Hence the requirement to include that layer.
2. Its error is **not** a power law in the sea-floor gradient. The signal is set
   by how the two columns' `maxLevelCell` and clipped bottom thicknesses relate,
   which changes in steps. Fitting an exponent to it would be meaningless, so
   the fit is configurable and is disabled for that variant.

### Algorithm Design: The tilt scan and the exponent

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Because the exact answer is zero there is nothing to converge *to*, so the
discriminating measurement is not a convergence rate against a reference but a
scan of the tilt at fixed resolution. For `hydrostatic_consistency` the swept
parameter is `z_tilde_bot_grad`; the analysis fits

$$
\log_{10} \lVert \text{HPGA} \rVert_{\text{RMS}}
   \;=\; q \, \log_{10} (\text{tilt}) + \text{const}
$$

over the points below `tilt_fit_max`, and reports $q$. The readings are:

| measured $q$ | reading |
| --- | --- |
| $q \approx 1$ | $\alpha$ is effectively piecewise constant in pressure — no better than the centered scheme |
| $q \approx 2$ | consistent with a residual set by the per-cell Taylor expansion point of `PGradHighOrder.md` §3.3 |
| round-off, independent of tilt | consistent with §3.7 holding as written |

An exponent that is neither, or one that drifts across the sweep, is a real
possible outcome and would say the mechanism is not one of the three above.

Restricting the fit to `tilt_fit_max` matters for two reasons: at small tilt the
error approaches the round-off floor and flattens the fit, and at large tilt the
two columns' `maxLevelCell` values begin to differ, which adds a staircase
component. This mirrors the existing
`omega_vs_reference_convergence_fit_max_resolution` option.

The scan is meaningful **immediately**, against the existing `Centered` scheme
and before any new Omega code exists. Offline replication of the Polaris
arithmetic gives $q = 1.00$ for the centered scheme, which is the expected
reading for a scheme that holds $\alpha$ constant within a layer, and which
calibrates the diagnostic.

### Algorithm Design: Sizing the sweep so that it is severe enough

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

The existing variants use a 500 m water column resolved at 0.5–4 m, which is
between one and three orders of magnitude finer than the ~250 m layers in the
deep ocean of a realistic global run. Offline replication of the Polaris `Init`
arithmetic (which reproduces the recorded $7\times10^{-12}$ m s$^{-2}$ for the
existing `ztilde_gradient` to within 4%) gives, at a fixed coordinate tilt of
5 m km$^{-1}$:

| layer thickness | RMS HPGA (centered) |
| --- | --- |
| 256 m | $1.6\times10^{-6}$ |
| 128 m | $5.0\times10^{-7}$ |
| 64 m | $9.6\times10^{-8}$ |
| 16 m | $6.4\times10^{-9}$ |

i.e. roughly second order in layer thickness, and only the coarsest rows are
near the target severity. The new variants therefore use a **deep, coarsely
resolved column**: a sea floor at $-3500$ m, a reference pseudo-bottom at
$-4096$ m, and 16, 32 or 64 levels (256, 128 or 64 m). The level counts are
multiples of 16, which Omega prefers.

The gap between the sea floor and the reference pseudo-bottom is deliberate.
The p-star iteration converges to a pseudo-bottom depth slightly greater than
the geometric water-column thickness (because in-situ density exceeds $\rho_0$
at depth), and the reference grid must extend below it in *both* columns. The
576 m of head room here permits tilts up to a few hundred m km$^{-1}$; without
it the shallower column's reference grid runs out, the p-star iteration
diverges, and the reported HPGA jumps to $O(1)$ m s$^{-2}$ — a failure mode the
`Init` guard below is designed to catch.

A further measured result shapes the sweep: at a fixed tilt *gradient*, the RMS
HPGA is **independent of horizontal resolution** to five digits (1.5570e-06 at
8, 4, 2 and 1 km). The offset and the cell spacing scale together, so the
difference quotient is unchanged. The horizontal sweep is therefore reduced to
two resolutions — enough to confirm the same independence holds in Omega, which
has not been checked — rather than the seven the existing variants use.

### Algorithm Design: The bathymetry guard

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

The swept tilt has to be the geometry actually under test. The analysis
therefore checks

$$
\max_i \lvert \texttt{bottomDepth}_i - \texttt{bottomDepthRequested}_i \rvert
   \;<\; \texttt{resting\_state\_max\_bathy\_error}
$$

at every point in the sweep and fails otherwise, with `Init` writing the
requested bathymetry alongside the achieved one.

The thing this guards against is partial-cell snapping. `min_pc_fraction`
forbids bottom cells thinner than a set fraction of a layer, so the achievable
pseudo-bottom depths are quantized and a requested bathymetry can fall in a gap
between them; `_snap_partial_cells` then moves the sea floor to the nearest
representable depth.

That does **not** break the resting state. Since `run_pstar_init` anchors the
geometric column at the prescribed sea surface, `ssh` is exact by construction,
the sea surface stays level, and the state remains exactly at rest. What breaks
is the *meaning of the sweep*. This matters most for `bathymetry_step`, where
the swept parameter is the sea floor itself: offline replication shows that at
a nominal gradient of 100 m km$^{-1}$ over 4 km, snapping moves both columns to
the same representable depth, so a nominal 400 m step becomes no step, and the
measured RMS HPGA falls to $4\times10^{-16}$ m s$^{-2}$ — which would read as a
spectacular pass rather than a test that had stopped testing anything.

A guard on `ssh` would be useless here, and was: an earlier version of this
design checked $\lvert \eta_1 - \eta_0 \rvert$, which is identically zero once
the column is surface-anchored and therefore can never fire.

Both new variants set `partial_cell_type = None`, which leaves the requested
bathymetry untouched. This does **not** cost partial-cell coverage: in a p-star
column the reference grid is clipped at the pseudo-bottom depth regardless, so
the deepest layer is a partial cell either way. The option controls only
whether the topography is snapped. The guard remains in place so that anyone
who later enables snapping finds out immediately.

> **Historical note.** Before `run_pstar_init` anchored the column at the
> prescribed sea surface, the same snapping surfaced as a spurious *sea-surface*
> tilt — up to 12 m between adjacent columns in this configuration, producing an
> apparent "error" of $3\times10^{-2}$ m s$^{-2}$ that was entirely real
> barotropic physics. That is fixed in the framework (see the p-star
> partial-cell work), and this branch is rebased onto that fix.

## Implementation

### Implementation: shared metric helpers

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

`analysis.py` holds several private helpers that the new analysis needs
verbatim: locating the internal edge, RMS over finite values, the log-log power
law fit, and the netCDF writer. Rather than importing private names across
step modules, move them to a new dependency-light leaf module
`polaris/tasks/ocean/horiz_press_grad/metrics.py` with public names
(`get_internal_edge`, `rms`, `power_law_fit`, `write_metric_dataset`,
`format_value_list`, `format_value_error_pairs`) and have `analysis.py` import
them. This commit is a pure refactor with no behaviour change.

### Implementation: including the bottom layer in the reference-based analysis

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

In `analysis.py`, take one more interface and one more layer:

```python
# was: [: max_level_index + 1]  and  hpga_forward[:max_level_index]
z_tilde_inter_for_ref = z_tilde_inter_edge[: max_level_index + 2]
hpga_ref_diff = hpga_forward[: max_level_index + 1] - ref_layer_mean
```

This is safe with respect to interface masking: `ZTildeInterface` is valid for
indices `0 .. maxLevelCell` in each column and `max_level_index` is
`min(maxLevelCell) - 1`, so interfaces `0 .. max_level_index + 1` are finite in
both columns by construction. The `omega_vs_python` comparison in the same
function already used `[: max_level_index + 1]`, so after this change the two
comparisons agree about which layers count.

**Measured effect.** Running the real `Init` arithmetic and the real
`ReferenceColumn` against a synthetic two-cell mesh (only mesh generation
bypassed), with the Polaris HPGA standing in for Omega's tendency:

| variant | fitted slope | RMS at 0.5 km |
| --- | --- | --- |
| `salinity_gradient` | 1.787 → 1.799 | 2.600e-07 → 2.601e-07 |
| `surface_pressure_gradient` | 2.014 → 2.012 | 1.137e-11 → 1.136e-11 |
| `temperature_gradient` | 1.625 → 1.625 | 2.770e-07 → 2.770e-07 |
| `ztilde_gradient` | 2.003 → 1.119 | 6.779e-12 → 4.954e-11 |

The first three are unaffected. `ztilde_gradient` is the only variant with a
tilted coordinate, so its two columns clip the bottom layer at different
thicknesses; that cell carries `-1.55e-09` m s$^{-2}$ at 0.5 km against an
interior RMS of `6.8e-12`, converges at roughly first order, and pulls the
fitted slope down. That is a real first-order error in the bottom partial cell
which the exclusion was hiding — the same behaviour `hydrostatic_consistency`
measures directly, and what the higher-order scheme exists to fix.

`ztilde_gradient.cfg` therefore takes its own convergence band, provisionally
`[0.9, 1.4]`, marked in the file as requiring re-tuning from the first real
Omega run. The shared `omega_vs_reference_high_res_rms_threshold` of 1e-6 needs
no change.

### Implementation: the reference-free analysis step

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Add `polaris/tasks/ocean/horiz_press_grad/resting_analysis.py` defining
`RestingAnalysis`, a sibling of `Analysis` rather than a mode of it, so the
existing step is untouched. Per sweep point it:

1. locates the internal edge with `get_internal_edge`;
2. takes `maxLevelCell` for the two bounding cells and forms the valid range
   `0 .. min(maxLevelCell) - 1` **inclusive of the deepest common layer**;
3. reads Omega's `NormalVelocityTend` at that edge and takes its RMS over the
   valid layers — the truth is zero, so this is the error;
4. does the same for the Polaris-side `HPGA` from `init.nc`;
5. RMS-differences the two and applies `omega_vs_polaris_rms_threshold`, which
   is retained: it confirms Omega implements the discretization Polaris thinks
   it does, independently of the resting-state property;
6. applies the bathymetry guard, comparing `bottomDepth` from
   `vert_coord.nc` against `bottomDepthRequested` from `init.nc`.

It then groups the sweep by resolution pair, fits `power_law_fit` over the
points with tilt $\le$ `tilt_fit_max` when `tilt_fit` is true, writes
`resting_state.nc` and `resting_state.png` (log-log, one series per resolution
pair), logs the exponents, and applies the gates:

- **sensitivity gate** — the largest RMS over the whole sweep must be at least
  `resting_state_sensitivity_min_rms`; this is a hard prerequisite, and failing
  it means the sweep must be redesigned before anything is concluded from it;
- **consistency gate** — RMS below `resting_state_max_rms`, deliberately
  disabled (`none`) until the rollout stage measures a value to set it from;
- **Omega-vs-Polaris** and **resting-state** checks as above.

### Implementation: the tilt axis and the resting-state task

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

`Init` and `Forward` gain an optional `subdir_suffix`, and `Init` gains optional
`tilt_option` / `tilt`. When a tilt is given, `Init.run` sets that option in its
own config before building the columns, exactly as it already sets
`vertical_grid:vert_levels`. `Init.run` also gains a guard that raises when a
column's reference pseudo-bottom does not extend below its converged
pseudo-bottom depth — the divergence mode described above — with an error
naming the offending column and the head room available.

Task wiring goes in a new module `resting_state_task.py` defining
`HorizPressGradRestingStateTask`, rather than branching `HorizPressGradTask`.
The existing task pairs `horiz_resolutions[i]` with `vert_resolutions[i]` and
keys its step dictionaries by horizontal resolution alone, so it cannot express
the repeated horizontal resolutions the new sweep needs; the new task keys by
the `(horiz_res, vert_res, tilt)` triple. `Init` and `Forward` are reused
unchanged apart from the optional arguments above.

This is a deliberate departure from the working plan, which leaned toward adding
the tilt axis inside `HorizPressGradTask._setup_steps`. Doing so would have
required renaming the existing variants' steps to disambiguate the vertical
resolution, changing their work directories for no benefit to them.

### Implementation: configuration

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

`horiz_press_grad.cfg` gains the resting-state options with inert defaults, so
the four existing variants are unaffected. Which task class a variant uses is
decided by name in `__init__.py`, so no separate "this is a resting state" flag
is needed. The new variant `.cfg` files set the deep column, the coarse
vertical resolutions, and the sweep:

```
# hydrostatic_consistency.cfg (abridged)
geom_z_bot_mid = -3500.0
z_tilde_bot_mid = -4096.0
horiz_resolutions = [4.0, 4.0, 4.0, 1.0]
vert_resolutions = [256.0, 128.0, 64.0, 256.0]
tilt_option = z_tilde_bot_grad
tilt_values = [0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0]
tilt_fit = True
tilt_fit_max = 10.0
```

```
# bathymetry_step.cfg (abridged)
geom_z_bot_mid = -3500.0
z_tilde_bot_mid = -4096.0
horiz_resolutions = [4.0, 4.0]
vert_resolutions = [256.0, 128.0]
tilt_option = geom_z_bot_grad
tilt_values = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 200.0]
tilt_fit = False
```

Both set `partial_cell_type = None` in `[vertical_grid]`, for the reason given
under the bathymetry guard above.

`forward.yaml` was unchanged for the calibration stage: every variant ran the
existing `Centered` scheme. The rollout gives it a `PressureGrad` block, filled
in per step — see below.

### Implementation: the scheme axis

Date last modified: 2026/08/02

Contributors: Xylar Asay-Davis, Claude

`Forward` gains a `scheme` argument, and `forward.yaml` a `PressureGrad` block
filled in through `add_yaml_file`'s `template_replacements`:

```yaml
PressureGrad:
   PressureGradType: {{ pressure_grad_type }}
   QuadraturePoints: {{ quadrature_points }}
```

`HorzOrder` and `VerticalReconstruction` are left at their Omega defaults of 2
and `linear`, which are the only Phase 1 values; the Phase 2 values exist as
keys but are rejected with an error, so a configuration written for Phase 2
cannot quietly run as Phase 1. An unrecognized `PressureGradType` is likewise
fatal rather than falling back to `Centered`, so a typo aborts the run instead
of producing centered answers that read as a pass.

Both task classes key their step dictionaries by `(resolution, scheme)` — or
`(horiz_res, vert_res, tilt, scheme)` for the resting-state sweep — and build
one `Forward` per scheme over **one shared `Init`**. `Init` is
scheme-independent: it writes both `HPGA` and `HPGAFiniteVolume` from the same
state, so duplicating it per scheme would cost run time and, worse, would leave
the two schemes' comparison open to the objection that they were run on
different initial conditions.

This is the departure from the calibration stage's structure noted under the
amended requirement above: it changes the existing variants' step directories.
The alternative — a task per `(variant, scheme)` pair — preserves them, but runs
`Init` twice per state and leaves no analysis step that sees both schemes, which
is the comparison the rollout exists to make.

`quadrature_points` is a single config option that drives both this template and
the Python kernel's Gauss order. It is deliberately not two options: the two
sides using different quadrature would make them different algorithms, which is
what the cross-implementation requirement above forbids. Sweeping it for
accuracy remains available and moves both sides together.

## Testing

### Testing and Validation: the sensitivity gate is the prerequisite

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Run both variants with `Centered` and confirm the sensitivity gate passes.
Offline replication of the Polaris arithmetic predicts the centered RMS HPGA
listed below; the first job of the real run is to confirm Omega agrees, via the
retained `omega_vs_polaris_rms_threshold` check.

| variant | configuration | predicted centered RMS |
| --- | --- | --- |
| `hydrostatic_consistency` | 4 km, 256 m, tilt 50 m km$^{-1}$ | $2.1\times10^{-5}$ |
| `hydrostatic_consistency` | 4 km, 64 m, tilt 50 m km$^{-1}$ | $9.8\times10^{-7}$ |
| `bathymetry_step` | 4 km, 256 m, 100 m km$^{-1}$ | $2.3\times10^{-5}$ |
| `bathymetry_step` | 4 km, 128 m, 25 m km$^{-1}$ | $3.8\times10^{-6}$ |

If the gate fails, the sweep is not exercising the failure mode and must be
redesigned before the variants are used to judge any scheme. This is the single
most consequential check in the calibration stage.

### Testing and Validation: the tilt exponent

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

Confirm that `hydrostatic_consistency` returns $q \approx 1$ for `Centered` at
every resolution pair, and that the value is stable when `tilt_fit_max` is
varied. Offline replication gives $q = 0.95$–$1.00$, the droop below 1 coming
from the largest tilts where `maxLevelCell` starts to differ between columns —
which is what `tilt_fit_max` is there to exclude. A centered exponent far from 1
should be understood before the scan is used on the new scheme.

Confirm that `bathymetry_step` produces the expected staircase and that its
interior layers sit at round-off, isolating the signal to the bottom cell.

### Testing and Validation: resting-state and consistency checks

Date last modified: 2026/07/28

Contributors: Xylar Asay-Davis, Claude

- **Bathymetry guard.** Confirm it passes for both variants as configured, and
  confirm it *fires* for a deliberately broken configuration — set
  `partial_cell_type = partial` on `bathymetry_step` with a sea-floor gradient
  of 32 m km$^{-1}$, which offline replication shows moves the sea floor
  12.33 m from the request.
- **Zero-tilt sanity.** With the swept parameter set to zero the RMS HPGA must
  be exactly zero (offline replication gives 0.0, not merely round-off), since
  the two columns become identical.
- **Omega-vs-Polaris.** The retained check at `omega_vs_polaris_rms_threshold`
  must pass at every sweep point. Its present value of $10^{-10}$ was tuned for
  errors of order $10^{-7}$; it may need re-tuning for a signal of order
  $10^{-5}$ and should be set from the observed differences.
- **Regression.** Run the four existing variants and confirm their step names
  and work directories are unchanged. Their *results* change, because the
  bottom layer is now included: three are unaffected in practice, while
  `ztilde_gradient`'s convergence slope drops from ~2.0 to ~1.1 and its
  provisional band must be re-tuned from the observed value.

### Testing and Validation: the rollout stage

Date last modified: 2026/08/02

Contributors: Xylar Asay-Davis, Claude

Two corrections to how this section read before Omega's `FiniteVolume` landed,
both from `omega_finite_volume_handoff.md`. The keys are `HorzOrder: 2` and
`VerticalReconstruction: linear`, **not** `ReconstructionOrder` and `constant` —
`constant` truncates the equation-of-state expansion to $\alpha_0$ and would run
the centered scheme under a new name. And there is **no "reduced configuration"
or centered limit** of the new scheme: the two are separate implementations and
no setting reduces one to the other. Phase 1 offers exactly two configurations,
`Centered` and `FiniteVolume` with its defaults.

The Python counterpart also already exists — it was written during the
calibration stage, from the design rather than from the C++ — so what this stage
tests is not whether it can be built but whether it and Omega agree.

**Reconciliation, before anything is run.** Work through every discretization
choice named in the cross-implementation requirement above, record its
resolution and provenance, and give each confirmed mismatch its own fix and its
own test. Two are already confirmed: the Python kernel defaults to a 4-point
Gauss rule where Omega defaults to 2, and it anchors its column scan at the sea
surface where Omega anchors at the sea floor. Neither shows up on the exact set,
where the integrand is zero at every quadrature point; both bite off it, which
is where the §5.1 gates live.

**Gates, set from measurement and not before.** Three points, of which the
first two would otherwise have been got wrong:

- bands are **per variant**, not per scheme alone. The measured `Centered` rates
  are 1.6, 1.8, 2.0 and 1.1 across the four gradient variants, so a single
  "≈ 2 for centered" band fails three of them;
- the accuracy gate is a **ratio at the coarse end**, set from the measured
  advantage — 6.5× at 256 m layers, 2.4× at 64 m, ~400× on stepped bathymetry;
- **do not gate on relative convergence order.** The two schemes converge at
  similar rates on smooth profiles; the advantage is a constant factor that
  *narrows* under refinement, so a gate requiring the new scheme's slope to beat
  the centered one would fail where nothing is wrong.

`resting_state_max_rms` is set from the measured `FiniteVolume` level at a
stated tilt, as an explicit multiple. The **improvement gate** — `FiniteVolume`
RMS below `Centered` RMS at every sweep point — needs no prior measurement and
ships with the analysis change.

**Report absolutes.** $\max\lvert\mathcal{S}\rvert$ behaved unexpectedly under
vertical refinement on the linear variant during the calibration stage, so
absolute residuals and tendencies in m s$^{-2}$ are reported alongside any
ratio, not in place of them.

**The variant to expect surprises from is `bathymetry_step`.** Every Omega-side
measurement of the new scheme so far used equal layer counts in both columns, so
this is where the rule for evaluating a column's reconstruction below its own
floor is first genuinely exercised.

Finally, the result — whichever way it falls — is written back into
`PGradHighOrder.md` as a measured property with its configuration and tilt range
attached. That is an Omega-side commit in a separate repository and is not
folded into the Polaris work.
