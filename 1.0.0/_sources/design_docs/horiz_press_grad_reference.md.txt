# Reworked HPG Reference Solution

Creation date: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

## Background: the horizontal pressure gradient and its reference solution

Omega is a non-Boussinesq, hydrostatic ocean model whose prognostic vertical
coordinate is **pseudo-height**, $\tilde{z} = -p / (\rho_0 g)$, where $p$ is sea
gauge pressure, $\rho_0$ is a reference seawater density (`RhoSw`), and $g$ is
gravitational acceleration. The `ocean/horiz_press_grad` task family in Polaris
exists to verify the convergence of Omega's horizontal pressure-gradient (HPG)
operator against a high-fidelity reference solution, as called for in the Omega
[pressure gradient design document](https://github.com/E3SM-Project/Omega)
(`PGrad.md`, "Test: Spatial convergence to exact solution").

The continuous horizontal pressure-gradient force (HPGF) per unit mass that
Omega's momentum tendency must reproduce is, from the
[Omega V1 governing equations](https://github.com/E3SM-Project/Omega)
(`OmegaV1GoverningEqns.md`),

$$
\mathbf{a}_\text{PGF} = -\left(\alpha\,\nabla p + \nabla \Phi\right),
$$

where $\alpha = 1/\rho$ is specific volume, $\Phi = g z$ is the geopotential
(neglecting tidal and self-attraction-and-loading terms), and $\nabla$ is the
**along-layer** horizontal gradient. Using the hydrostatic relation, Omega
rewrites this through the Montgomery potential $M = \alpha p + g z$ as

$$
\mathbf{a}_\text{PGF} = -\nabla M + p\,\nabla \alpha,
$$

and discretizes it with a centered scheme in which $\alpha$ is held constant
within each layer, the Montgomery gradient is evaluated at layer interfaces and
averaged to the layer midpoint, and the along-layer gradient is a two-cell
finite difference across the edge.

### The two-column task and its comparisons

Each `horiz_press_grad` task variant (`salinity_gradient`,
`temperature_gradient`, `ztilde_gradient`) builds a two-column mesh at a set of
paired horizontal and vertical resolutions. Per resolution:

- An `Init` step (a `PStarInitStep`, see the
  [p-star initialization design](pstar_init)) builds the p-star coordinate and
  the initial conservative temperature (CT) and absolute salinity (SA) from
  piecewise pseudo-height profiles, and computes a Polaris HPGA from a two-cell
  finite difference of the Montgomery potential.
- A `Forward` step runs Omega for a **single time step** and writes Omega's
  `NormalVelocityTend`, which is just the HPGA.
- An `Analysis` step performs two comparisons:
  1. **`omega_vs_reference`** — Omega's HPGA against the high-fidelity reference
     solution, fit to a power law to measure the convergence rate.
  2. **`omega_vs_python`** — Omega's HPGA against the Polaris/Python HPGA from
     `Init`, a code-correctness check that the two implementations of the
     *same discrete scheme* agree to a tight tolerance.

Because each forward run is a single step with no coordinate motion, the
forward layer pseudo-heights and geometric heights are identical to those in
`Init`; the `omega_vs_python` comparison therefore needs no special handling.

### The current reference solution and why it must be reworked

The current `Reference` step (`reference.py`) builds five columns at
$x = \Delta x_\text{ref}\,[-1.5,-0.5,0,0.5,1.5]$, integrates the hydrostatic
relation upward from each seafloor to obtain geometric height $z(\tilde z)$,
forms $M$, and takes a **4th-order finite difference across columns** to obtain
$\partial M/\partial x$ and $\partial \alpha/\partial x$ at the center column,
giving HPGA $= -\partial M/\partial x + p\,\partial\alpha/\partial x$. It writes
the result on a vertical grid deliberately refined (via a greatest-common-
divisor construction) so that every test grid's layer midpoints land exactly on
reference grid points. `Analysis` then samples the reference by **exact z̃
matching** with no interpolation.

This design has two structural weaknesses:

1. **Grid-alignment fragility.** Exact-match sampling only works when the
   reference and test pseudo-heights coincide. As soon as a nonzero
   `SurfacePressure` is applied, the p-star coordinate stretches and squashes
   the column in proportion to the pressure thickness, and partial bottom cells
   produce interfaces that no longer align across vertical resolutions. The
   reference must instead be queryable at *arbitrary* pseudo-height with no loss
   of accuracy.
2. **Breakdown near bathymetry.** The cross-column finite-difference stencil
   requires every neighboring column to be valid at a given $\tilde z$. Near the
   seafloor, collocation points in some columns fall below their own bathymetry
   and the stencil cannot be formed, so those layers are masked out. The
   accuracy is also only as good as the stencil and the matched grid, which is
   insufficient for assessing the higher-than-second-order HPG operators planned
   for Omega.

## Summary

This design replaces the multi-column, finite-difference reference solution
with a **single-column, analytic** reference computed at the edge between the
two columns ($x = 0$). The new capability:

- Evaluates the exact continuous HPGF directly via a chain-rule / Leibniz
  expansion of the along-pseudo-height gradient, using TEOS-10 specific-volume
  derivatives. Because the continuous HPGF is coordinate-invariant, this single
  central-column expression is exact in the horizontal — there is no
  finite-difference truncation and no dependence on neighboring columns, so the
  near-bathymetry breakdown disappears and the reference is fidelity-limited only
  by a smooth one-dimensional quadrature.
- Is a callable function of $\tilde z$, so it can be sampled at exactly the
  pseudo-heights a test produces, eliminating the grid-alignment requirement.
- Supports fully general horizontal variation of every prescribed input.
- Is consumed directly by `Analysis` through a shared evaluator module; the
  separate `Reference` step is removed.

The accuracy assessment compares Omega's along-layer HPGA to the reference using
a **layer-averaged** target: for each model layer, the reference is averaged over
that layer's pseudo-height extent at the edge. This compares like with like (a
layer mean against a layer mean) so that legitimate layer tilt and finite layer
thickness are accounted for in the target rather than charged as discretization
error.

The primary challenges are (a) formulating the continuous reference correctly so
that the along-layer computation is judged on its own merits, (b) differentiating
the prescribed profiles with respect to the horizontal coordinate at fixed
pseudo-height — including the case where the profile node pseudo-heights
themselves tilt — and (c) integrating the resulting expression to high accuracy
in the vertical. The design is **successful** if the reference can be evaluated
at any pseudo-height without loss of accuracy, remains valid throughout the water
column including immediately above the bathymetry, is accurate enough to serve a
beyond-second-order HPG operator, supports general horizontal input variation,
and reproduces (with re-tuned thresholds) the convergence behavior the existing
regression tests check.

## Requirements

### Requirement: The reference HPGA can be evaluated at an arbitrary pseudo-height without loss of accuracy

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference solution shall be evaluable at any pseudo-height within the water
column produced by a test, to high accuracy, without requiring that the
reference and test vertical grids coincide. This must hold when a nonzero
sea-surface pressure stretches or squashes the p-star column and when partial
bottom cells misalign layer interfaces across resolutions.

### Requirement: The reference is valid throughout the water column, including immediately above the bathymetry

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference shall remain valid and accurate for every pseudo-height from the
free surface down to the seafloor of the column at the edge between the two test
columns. It shall not break down or require masking in the layers nearest the
bathymetry.

### Requirement: The reference is accurate enough to assess HPG operators beyond second order

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference shall be of sufficient fidelity that, when an HPG operator more
accurate than the current second-order centered scheme is introduced in Omega,
the reference error does not limit the measured convergence. In particular, the
reference shall not introduce a fixed-order horizontal truncation error of its
own.

### Requirement: The reference supports general horizontal variation of the prescribed inputs

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference shall correctly represent horizontal variation of every prescribed
input that the task permits: the geometric sea-surface height, the geometric
seafloor depth, the seafloor pseudo-height, and the temperature and salinity
profile node values **and** node pseudo-heights. No input variation supported by
the task configuration may be assumed to be horizontally uniform.

### Requirement: The accuracy assessment evaluates the along-layer scheme on its own merits

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The comparison between the model's along-layer HPGA and the reference shall
measure only the genuine discretization error of the along-layer scheme. It
shall not attribute legitimate, physically correct effects of tilted layers or
of finite layer thickness to discretization error. The reference shall represent
the exact continuous pressure-gradient force that the along-layer scheme
converges to as both horizontal and vertical resolution are refined.

### Requirement: The capability integrates with the existing two-column task without a separate precompute step

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference shall be available to the `Analysis` step on demand at the
pseudo-heights each test produces, without a separate precomputed reference
artifact and without changing the structure of the `Init`/`Forward`/`Analysis`
workflow or the two comparisons (`omega_vs_reference` and `omega_vs_python`).

## Algorithm Design

### Algorithm Design: The continuous, coordinate-invariant reference and the cancellation of layer-slant terms

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference is the **exact continuous** pressure-gradient acceleration that
Omega's discrete operator must converge to. The key fact that makes a
single central-column evaluation correct is that this acceleration is
**independent of the vertical coordinate** used to evaluate the horizontal
gradients.

Write the horizontal gradients along a general layer label $\sigma$ (constant
along a model coordinate surface). Pseudo-height is, by definition, a rescaled
pressure, $p = -\rho_0 g\,\tilde z$, so along constant $\tilde z$ the pressure is
constant. Using the hydrostatic relation $\partial z/\partial \tilde z =
\rho_0 \alpha$, the along-$\sigma$ gradients of pressure and geometric height are

$$
\nabla_\sigma p &= -\rho_0 g\,\left.\partial_x \tilde z\right|_\sigma, \\
\nabla_\sigma z &= \left.\partial_x z\right|_{\tilde z}
                  + \rho_0 \alpha\,\left.\partial_x \tilde z\right|_\sigma .
$$

Substituting into $\mathbf{a}_\text{PGF} = -(\alpha\,\nabla_\sigma p +
g\,\nabla_\sigma z)$, the two terms proportional to the coordinate slope
$\left.\partial_x\tilde z\right|_\sigma$ carry the **same** $\alpha$ at the same
point and cancel exactly:

$$
\mathbf{a}_\text{PGF} = -g\,\left.\frac{\partial z}{\partial x}\right|_{\tilde z}.
$$

This is the standard statement that the pressure-gradient force does not depend
on the coordinate used to compute it. Consequences for the design:

- The reference is $-g\,\partial_x z|_{\tilde z}$, evaluated at the edge ($x=0$).
  It can be computed entirely at constant $\tilde z$, which is the convenient
  frame, **without approximation**, even when the model layers slant (as in
  `ztilde_gradient`) or bend near the bathymetry (partial cells).
- The cancellation holds only for the **total** acceleration. Omega's discrete
  pieces $\nabla M$ and $p\,\nabla\alpha$ are individually coordinate-dependent
  and large; the design never compares those pieces to the reference, only the
  total. The residual between Omega's along-layer total and the continuous total
  is therefore the genuine discretization error of the along-layer scheme —
  including the classic slant-induced pressure-gradient error that the future
  high-order operator is intended to reduce.

### Algorithm Design: Single-column chain-rule / Leibniz expression for the reference

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

Geometric height as a function of pseudo-height in a single column is obtained by
integrating the hydrostatic relation from the surface:

$$
z(\tilde z; x) = \eta(x) + \rho_0 \int_{\tilde z_s(x)}^{\tilde z}
    \alpha\bigl(S_A(\tilde z', x),\,\Theta(\tilde z', x),\,p(\tilde z')\bigr)
    \, d\tilde z' ,
$$

where $\eta(x)$ is the geometric sea-surface height, $\tilde z_s(x)$ is the
surface pseudo-height ($\tilde z_s = -p_s/(\rho_0 g)$, zero only when the surface
pressure $p_s$ is zero), and $p(\tilde z') = -\rho_0 g\,\tilde z'$ depends only on
$\tilde z'$ (not on $x$). The integral runs downward, so for $\tilde z < \tilde
z_s$ it is negative and $z < \eta$, as required. The reference is **anchored at
the surface** rather than the seafloor because that is the boundary the model
honours: `Init`/Omega build the p-star column from the prescribed sea-surface
height and surface pressure, so the HPGA vanishes at the surface (for zero
surface slope) and grows downward. Anchoring elsewhere — e.g. at the configured
seafloor pseudo-height, which is a coordinate buffer below the deepest valid
layer rather than a honoured geometric boundary — would reconstruct a different
$z(\tilde z)$ and miss the model by a constant offset.

Differentiating with respect to $x$ at fixed $\tilde z$, the lower integration
limit depends on $x$, so the Leibniz rule contributes a boundary term:

$$
\left.\frac{\partial z}{\partial x}\right|_{\tilde z} =
   \eta'(x)
   - \rho_0\,\alpha(\tilde z_s)\,\tilde z_s'(x)
   + \rho_0 \int_{\tilde z_s}^{\tilde z}
        \left.\frac{\partial \alpha}{\partial x}\right|_{\tilde z'} d\tilde z' .
$$

Because $p$ is fixed along constant $\tilde z'$, the integrand involves only the
horizontal variation of the thermohaline state through the TEOS-10 specific
volume:

$$
\left.\frac{\partial \alpha}{\partial x}\right|_{\tilde z'} =
   \alpha_{S_A}\,\left.\frac{\partial S_A}{\partial x}\right|_{\tilde z'}
 + \alpha_{\Theta}\,\left.\frac{\partial \Theta}{\partial x}\right|_{\tilde z'},
$$

where $\alpha_{S_A} = \partial \alpha / \partial S_A$ and
$\alpha_{\Theta} = \partial \alpha / \partial \Theta$ are the first derivatives of
specific volume from the equation of state, evaluated at the central column's
$(S_A, \Theta, p)$. The reference acceleration is then

$$
a(\tilde z) = -g\left.\frac{\partial z}{\partial x}\right|_{\tilde z} =
   -g\left[\,\eta' - \rho_0\,\alpha(\tilde z_s)\,\tilde z_s'
   + \rho_0 \int_{\tilde z_s}^{\tilde z}
   \left(\alpha_{S_A}\,\partial_x S_A + \alpha_{\Theta}\,\partial_x \Theta\right)
   d\tilde z'\right].
$$

Notable properties:

- **No geometric-height integration is required for the HPGA.** Everything is
  expressed through the prescribed profiles $S_A(\tilde z'), \Theta(\tilde z')$
  and the analytic pressure $p(\tilde z') = -\rho_0 g\,\tilde z'$ at the central
  column, plus the input slopes $\eta'$ and $\tilde z_s'$. The only quadrature is
  the smooth one-dimensional integral of $\partial_x\alpha$. (A geometric-height
  integration may still be performed for optional diagnostics.)
- **Single column, valid to the seafloor.** The expression is evaluated only at
  $x = 0$ and is well defined for every $\tilde z \in [\tilde z_b(0), \tilde
  z_s(0)]$. Integrating from the surface loses none of this validity — it reaches
  every pseudo-height down to and immediately above the bathymetry — and it never
  references neighboring columns, so it cannot break down above the bathymetry.
- **Exact in the horizontal.** The horizontal gradient is analytic; there is no
  $\Delta x$ truncation, satisfying the beyond-second-order fidelity requirement.

The boundary term uses $\tilde z_s(0) = $ the surface pseudo-height (the
shallowest `z_tilde` node) and $\alpha(\tilde z_s)$ evaluated from the profiles
at $\tilde z_s(0)$. The slopes $\eta'$ (from `geom_ssh_grad`) and $\tilde z_s'$
(from the surface `z_tilde_grad` node) are read from the configuration gradients
(converted from per-km to per-m and projected onto the edge normal). They are
kept **fully general**: a nonzero sea-surface height or surface pressure makes
$\eta'$ and/or $\tilde z_s'$ (and $\tilde z_s$ itself) nonzero, and the formula
already accounts for them. A regression test that exercises a nonzero surface
pressure is deferred to a follow-up PR; the present tasks all use zero surface
slope and pressure.

### Algorithm Design: Horizontal derivatives of the prescribed profiles at fixed pseudo-height

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The factors $\partial_x S_A|_{\tilde z'}$ and $\partial_x \Theta|_{\tilde z'}$
are the horizontal gradients of the prescribed profiles at fixed pseudo-height.
The profiles are defined by node values and node pseudo-heights, each of which
varies linearly in $x$ (configuration `*_mid` plus `*_grad`$\cdot x$), and a
monotone PCHIP interpolant in pseudo-height (the same interpolant `Init` uses, so
the reference and the test describe the same physical state).

The profile value at fixed $\tilde z'$ depends on $x$ through both the node
values and, in the general case (`z_tilde_grad` $\neq 0$), the node
pseudo-heights. Because PCHIP is nonlinear in its node data, the horizontal
derivative is obtained by **differencing the analytic input profiles**: the
interpolant is constructed at $x = \pm\varepsilon$ from the exactly known linear
node functions and evaluated at $\tilde z'$, and a centered difference is taken,

$$
\left.\frac{\partial S_A}{\partial x}\right|_{\tilde z'} \approx
   \frac{S_A(\tilde z'; +\varepsilon) - S_A(\tilde z'; -\varepsilon)}
        {2\varepsilon},
$$

and similarly for $\Theta$. Since the nodes are exactly linear in $x$ and the
interpolant is smooth in $x$, this is accurate to round-off for a suitably chosen
$\varepsilon$ (optionally refined by Richardson extrapolation). This single
construction handles all task variants uniformly, including tilted node
pseudo-heights, satisfying the general-input requirement.

The specific-volume derivatives $\alpha_{S_A}$ and $\alpha_{\Theta}$ are obtained from the
equation of state at the central column's $(S_A(\tilde z'), \Theta(\tilde z'),
p(\tilde z'))$ — concretely, from `gsw.specvol_first_derivatives` for TEOS-10.

### Algorithm Design: Building the reference profile and the layer-averaged comparison

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

The reference is needed as a layer mean over each model layer. Define the
cumulative integral

$$
I(\tilde z) = \int_{\tilde z_s}^{\tilde z}
   \left(\alpha_{S_A}\,\partial_x S_A + \alpha_{\Theta}\,\partial_x \Theta\right)
   d\tilde z', \qquad
a(\tilde z) = -g\left[\,\eta' - \rho_0\,\alpha(\tilde z_s)\,\tilde z_s'
   + \rho_0\,I(\tilde z)\right].
$$

The integrand is smooth, so $I(\tilde z)$ — and therefore $a(\tilde z)$ — is
evaluated with a high-order quadrature (the existing Gauss–Legendre / adaptive
machinery; see Implementation). $a(\tilde z)$ is thus available as an accurate
callable of pseudo-height.

For the comparison, each model layer $k$ spans, at the edge, the pseudo-height
interval $[\tilde z^{\text{bot}}_{k}, \tilde z^{\text{top}}_{k}]$, where the edge
interfaces are the average of the two cells' interface pseudo-heights (the edge
lies midway between the columns; for linearly varying inputs this average equals
the central-column value). The reference target for layer $k$ is the **layer
mean**

$$
\overline{a}_k = \frac{1}{\tilde z^{\text{top}}_k - \tilde z^{\text{bot}}_k}
   \int_{\tilde z^{\text{bot}}_k}^{\tilde z^{\text{top}}_k}
   a(\tilde z)\, d\tilde z ,
$$

evaluated by high-order quadrature within the layer. This compares the model's
layer-mean acceleration to the true layer-mean acceleration, so finite layer
thickness and layer tilt are folded into the target rather than counted as error
(satisfying the "on its own merits" requirement). As both resolutions refine,
$\overline{a}_k \to a(\tilde z_k)$ and the residual is the scheme's genuine
discretization error.

The model layer interfaces are taken from the test output (identical between
`Init` and `Forward`), so the reference is sampled at exactly the test's
pseudo-heights and the partial-cell bottom geometry is honored automatically. As
in the current analysis, the single deepest valid model layer (which abuts the
bathymetry) is excluded from the error metric.

The sign/orientation of $a$ must match the edge-normal convention used by the
model output: the horizontal coordinate $x$ increases from the first to the
second cell on the internal edge. `Analysis` determines that orientation from
the mesh cell positions and applies it consistently to the input slopes and the
reference acceleration.

### Algorithm Design: Removal of the separate reference step

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

Because the reference is an inexpensive callable evaluated at the test's
pseudo-heights, it does not need to be precomputed by a dedicated step. The
`Reference` step is removed. `Analysis` constructs the reference evaluator from
the configuration (which fully determines the central column) and evaluates the
layer-averaged target per resolution. The greatest-common-divisor reference
grid, the five-column construction, the cross-column finite-difference stencil,
and the exact-match sampling are all retired.

## Implementation

### Implementation: shared reference evaluator module

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

Replace the `Reference` *step* in `polaris/tasks/ocean/horiz_press_grad/reference.py`
with a `Reference` *evaluator module* in the same package (the file name may
remain `reference.py`; it no longer defines a `Step` subclass). The evaluator
encapsulates the central column and exposes the reference as a function of
pseudo-height.

```python
class ReferenceColumn:
    """
    High-fidelity continuous HPGA reference at the edge (x = 0) between the
    two columns, evaluated analytically via the chain-rule / Leibniz
    expansion of the along-pseudo-height gradient.
    """

    def __init__(self, config, x_sign=1.0):
        # x_sign carries the edge-normal orientation (+1 if x increases from
        # cell0 to cell1, -1 otherwise) so the reference matches the model
        # output convention.
        ...
        # Cache, at x = 0:
        #   - PCHIP interpolants for SA(z_tilde), CT(z_tilde)
        #   - the surface pseudo-height z_tilde_s (shallowest z_tilde node),
        #     the sea-surface-height slope eta' and the surface pseudo-height
        #     slope z_tilde_s' (per-metre, * x_sign); kept general so nonzero
        #     SSH / surface pressure need no further change
        #   - alpha(z_tilde_s) for the boundary term

    def specvol(self, z_tilde):
        """alpha = EOS(SA(z_tilde), CT(z_tilde), p = -RhoSw*g*z_tilde)."""

    def dalpha_dx(self, z_tilde):
        """
        alpha_SA * dSA/dx + alpha_CT * dCT/dx at fixed z_tilde, with alpha_*
        from gsw.specvol_first_derivatives and dSA/dx, dCT/dx from analytic-input
        differencing of the profiles (handles tilted nodes).
        """

    def hpga(self, z_tilde):
        """
        a(z_tilde) = -g [ eta' - RhoSw*alpha(z_tilde_s)*z_tilde_s'
                          + RhoSw * I(z_tilde) ],
        with I(z_tilde) the cumulative integral of dalpha_dx from the surface
        z_tilde_s. Vectorized over a 1-D array of target pseudo-heights.
        """

    def layer_mean_hpga(self, z_tilde_interfaces):
        """
        Given edge layer interface pseudo-heights (length nLayers+1), return
        the per-layer mean of a(z_tilde) over each [z_top, z_bot] interval by
        high-order quadrature.
        """
```

Reuse existing utilities rather than reimplementing them:

- `get_array_from_mid_grad(config, name, x)` and `get_pchip_interpolator(...)`
  from `column.py` for node arrays and profile interpolants. Pass an array of
  the single point `x = [0.0]` (plus `x = ±epsilon` for the differencing).
- `compute_specvol` from `polaris.ocean.eos` (TEOS-10 path) for $\alpha$, and
  `gsw.specvol_first_derivatives(SA, CT, p_dbar)` for $\alpha_{S_A}, \alpha_{\Theta}$
  (note `gsw` takes pressure in dbar = Pa $\times 10^{-4}$).
- The fixed-step Gauss–Legendre and adaptive-Simpson quadrature helpers already
  present in `reference.py` (`_gauss_composite`, `_fixed_quadrature`,
  `_adaptive_simpson`) for both $I(\tilde z)$ and the layer-mean integral. The
  quadrature method remains configurable via `reference_quadrature_method`
  (default `gauss4`).
- `Gravity` and `RhoSw` from `polaris.ocean.vertical.ztilde`.

Recommended evaluation strategy for `hpga`/`layer_mean_hpga`: build
$a(\tilde z)$ on a fine internal pseudo-height grid spanning $[\tilde z_b(0), 0]$
by cumulative high-order quadrature of the integrand, then integrate $a$ over
each model layer with the same quadrature using a few sub-samples per layer (the
sub-sampling fineness can reuse `reference_quadrature_method`'s panel count).
Choose the internal grid fine enough that its contribution to the error is far
below the HPGA errors being measured; alternatively evaluate $I$ on demand at the
layer quadrature points to avoid any interpolation. Either approach must keep the
reference fidelity well beyond the model's.

`epsilon` for the profile differencing should be a small fraction of the column
extent (e.g. relative to `reference_horiz_res` if retained for this purpose, or a
fixed small value such as $10^{-3}$ km); document the choice and optionally apply
Richardson extrapolation.

### Implementation: Analysis consumes the reference directly

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

In `analysis.py`:

- Remove the `reference` dependency, the `reference_solution.nc` input, and
  `_sample_reference_without_interpolation`.
- In `setup`, drop the reference-step input wiring; keep the per-resolution
  `init`, `forward`, `culled_mesh`, and `vert_coord` inputs.
- In `run`, construct a single `ReferenceColumn` from `self.config` (its
  orientation `x_sign` is derived once from the mesh, see below). Then for each
  resolution:
  1. Identify the internal edge and its two cells with the existing
     `_get_internal_edge`.
  2. Determine `x_sign` from the cells' `xCell` (sign of `xCell[cell1] -
     xCell[cell0]`), so the reference gradient matches the model edge-normal
     convention. The current Python HPGA in `Init`
     (`_compute_montgomery_and_hpga`) uses `x = horiz_res*[-0.5, 0.5]` for cells
     `[0, 1]`; the new orientation logic must reproduce the same sign the
     existing `omega_vs_python` comparison relies on.
  3. Read the **edge** layer-interface pseudo-heights as the average of the two
     cells' `ZTildeInterface` from the forward output (equivalently `Init`).
  4. Compute `ref_layer_mean = reference.layer_mean_hpga(edge_interfaces)`.
  5. Restrict to valid layers via `maxLevelCell` (shallowest of the two cells,
     as today) and drop the deepest valid layer (abuts bathymetry).
  6. RMS-difference Omega's `NormalVelocityTend` at the edge against
     `ref_layer_mean`; accumulate per resolution.
- The power-law fit, threshold checks, plots, and `omega_vs_python` comparison
  are unchanged in structure. Optionally overlay the reference layer-mean profile
  on a diagnostic plot at the finest resolution.

### Implementation: task wiring and configuration

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

- `task.py`: remove the `Reference` step creation and its entry in the
  `Analysis` dependencies dict (`{'init': ..., 'forward': ...}` only).
- `horiz_press_grad.cfg`: remove `reference_horiz_res` (no neighboring columns).
  Keep `reference_quadrature_method` for the one-dimensional integral and the
  layer mean. Retain the `omega_vs_reference_*` threshold and convergence-rate
  options; their values will likely need re-tuning now that the reference is
  exact in the horizontal (see Testing).
- Delete the now-unused machinery in the old `reference.py`: the five-column
  setup, `_get_reference_vert_res` and `_fraction_gcd`, the 4th-order stencil
  (`_compute_4th_order_gradient`, `_check_gradient`), the per-column
  geometric-height integration used for the cross-column difference, and the
  `reference_solution.nc` output. Keep and relocate the quadrature helpers used
  by `ReferenceColumn`.

### Implementation: orientation and consistency safeguards

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

- The reference must use the same $+x$ orientation as `Init`/`Forward`. Derive it
  from `xCell` and assert that the resulting sign reproduces the existing
  `omega_vs_python` agreement at the coarsest resolution as a guard against a
  flipped gradient.
- The edge surface pseudo-height (average of the two cells' surface
  pseudo-heights) equals $\tilde z_s(0)$ for linearly varying inputs; assert this
  equality to a tolerance to catch configuration or averaging mistakes.
- Keep the EOS path restricted to TEOS-10 (as the task already requires Omega),
  and guard `dalpha_dx` against requesting `specvol_first_derivatives` outside
  gsw's valid range.

## Testing

### Testing and Validation: arbitrary-pseudo-height evaluation and near-bathymetry validity

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

Add unit tests for `ReferenceColumn` (e.g.
`tests/ocean/horiz_press_grad/test_reference.py`):

- **Constant-density column.** With a configuration giving spatially constant
  $\alpha$ (so $\partial_x\alpha = 0$), `hpga` must equal the closed form
  $-g[\eta' - \rho_0\alpha\,\tilde z_s']$ at every pseudo-height, to round-off,
  for several arbitrary $\tilde z$ including values that fall between any plausible
  grid points. (With a nonzero surface pseudo-height slope $\tilde z_s'$, evaluate
  the boundary term at the surface, where the integral is exactly zero.)
- **Zero horizontal variation.** With all input gradients zero, `hpga` must be
  identically zero (no spurious pressure-gradient signal) for arbitrary
  $\tilde z$, including immediately above the seafloor.
- **Independence from sampling.** Evaluate `hpga` on two unrelated pseudo-height
  sets (one of which deliberately does not align with any uniform grid) and on a
  shifted set emulating a nonzero surface pressure; values at coincident
  pseudo-heights must agree to round-off, demonstrating freedom from grid
  alignment.

### Testing and Validation: fidelity beyond second order

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

- **Brute-force gradient cross-check.** For a $\tilde z$ comfortably above the
  seafloor, compare `ReferenceColumn.hpga` to a high-accuracy finite-difference
  estimate formed by fully integrating $z(\tilde z; x)$ at $x = \pm\delta$ and
  differencing at constant $\tilde z$, for a sequence of shrinking $\delta$. The
  analytic value must agree with the Richardson-extrapolated finite difference to
  many digits, confirming the chain-rule/Leibniz implementation and that the
  reference carries no fixed-order horizontal truncation error.
- **Quadrature convergence.** Confirm that refining the quadrature panel count
  changes `hpga` by amounts decreasing at the expected high order and that the
  result is converged well below the model HPGA error levels.

### Testing and Validation: general horizontal input variation

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

- **Tilted nodes.** With `z_tilde_grad` $\neq 0$ (tilted profile node
  pseudo-heights), verify `dalpha_dx` against an independent finite difference of
  $\alpha$ in $x$ at fixed $\tilde z$, confirming the analytic-input differencing
  handles moving nodes.
- **Each gradient in isolation.** Exercise nonzero `salinity_grad`,
  `temperature_grad`, `geom_ssh_grad`, and the surface `z_tilde_grad` node
  one at a time and confirm the corresponding boundary or integrand contribution
  appears with the correct sign and magnitude. The surface boundary terms
  (`geom_ssh_grad`, surface `z_tilde_grad`) are kept general so a follow-up
  nonzero-surface-pressure test needs no further changes.

### Testing and Validation: layer-averaged comparison and regression behavior

Date last modified: 2026/06/14

Contributors: Xylar Asay-Davis, Claude

- **Layer-mean correctness.** For a known smooth $a(\tilde z)$, verify
  `layer_mean_hpga` returns the analytic layer averages, and that for vanishing
  layer thickness it approaches the pointwise value.
- **Regression suite.** Run all three task variants (`salinity_gradient`,
  `temperature_gradient`, `ztilde_gradient`) in the `omega_pr` suite. Confirm the
  `omega_vs_python` comparison still passes at its tight tolerance (unchanged
  scheme), and that `omega_vs_reference` produces a convergence slope in the
  expected range. Because the reference is now exact in the horizontal,
  re-tune `omega_vs_reference_convergence_rate_min/max`,
  `omega_vs_reference_high_res_rms_threshold`, and
  `omega_vs_reference_convergence_fit_max_resolution` to the observed behavior;
  document the updated values and the resolution at which curvature in the
  convergence plot appears.
- **Tilted-layer case.** Pay particular attention to `ztilde_gradient`, whose
  slanted layers exercise the slant-induced pressure-gradient error; confirm the
  layer-averaged comparison yields a clean convergence rather than a spurious
  floor from charging layer tilt as error.
