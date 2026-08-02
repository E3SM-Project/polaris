(dev-ocean-horiz-press-grad)=

# horiz_press_grad

The {py:class}`polaris.tasks.ocean.horiz_press_grad.task.HorizPressGradTask`
provides two-column Omega tests for pressure-gradient-acceleration (`HPGA`)
accuracy and convergence across horizontal and vertical resolutions.

The task family includes four such variants:

- `salinity_gradient`
- `temperature_gradient`
- `ztilde_gradient`
- `surface_pressure_gradient`

{py:class}`polaris.tasks.ocean.horiz_press_grad.resting_state_task.HorizPressGradRestingStateTask`
provides two further variants that are exact resting states, in which the true
HPGA is identically zero and no reference solution is used:

- `hydrostatic_consistency`
- `bathymetry_step`

## framework

The config options for these tests are described in
{ref}`ocean-horiz-press-grad` in the User's Guide.

The User's Guide is also place to go for the mathematical formulation,
the reference-solution definition, and the algorithmic interpretation of the
two task baselines.  This page focuses on how that workflow is implemented in
the code.

The task dynamically rebuilds `init` and `forward` steps in `configure()` so
user-supplied `horiz_resolutions` and `vert_resolutions` in config files are
reflected in the work directory setup.

### metrics

{py:mod}`polaris.tasks.ocean.horiz_press_grad.metrics` is a dependency-light
leaf module (numpy and xarray only) holding the pieces both analysis steps
need: `get_internal_edge()`, `rms()`, `power_law_fit()`,
`write_metric_dataset()`, `format_value_list()` and
`format_value_error_pairs()`.  It exists so the two step modules can share them
without importing private names from one another.

### the finite-volume pressure gradient

Four leaf modules implement the `FiniteVolume` scheme of the
`PGradHighOrder.md` design, as the Python counterpart of Omega's
`PressureGradFiniteVolume`.  They are written from that design rather than from
the C++, so that the Omega-vs-Polaris comparison in `analysis` compares two
independent implementations.

{py:mod}`polaris.tasks.ocean.horiz_press_grad.edge` holds the two-column edge
operator, `edge_delta()` and `edge_mean()`.  It has no dependencies inside the
package so the modules below can share it without importing one another.

{py:mod}`polaris.tasks.ocean.horiz_press_grad.eos_expansion` gives the four
Taylor coefficients of the equation of state from one `gsw` evaluation per cell
per layer, averages them and the reference state to the edge, and evaluates the
resulting shared profile.  Note that `gsw.specvol_first_derivatives()` takes
pressure in dbar but returns the pressure derivative per Pa; the tests assert
this rather than trusting it.

{py:mod}`polaris.tasks.ocean.horiz_press_grad.reconstruction` builds the
mean-preserving linear reconstruction of temperature and salinity in pressure.
The slope is a centred difference of the layer means against *mid-layer
pressure*, which is what makes it exact on a non-uniform grid.

{py:mod}`polaris.tasks.ocean.horiz_press_grad.finite_volume` assembles the
scheme.  The essential piece is `delta_specvol_at_pressure()`, which
differences the integrand at **matched pressure** rather than at matched layer
index: for each quadrature point, `layer_containing_pressure()` finds the layer
of *each column* that contains that pressure.  Under tilt those are not the
same layer -- at 50 m/km and 64 m layers the two columns' layer `k` do not
overlap in pressure at all -- and getting this wrong silently turns the scheme
into a different one.  `column_scan()` then accumulates the fixed-pressure
height difference along the column from `anchor_difference()`, and
`finite_volume_hpga()` forms the layer mean and the tendency.

**The scan anchors at the sea floor**, per design §3.7.4, at the deepest
interface valid in both columns.  This is not a conditioning preference:
`VertCoord` builds geometric height upward from a prescribed bathymetry by
accumulating over each column's *own* layers, so two columns partitioned
differently by a tilt derive sea-surface heights that differ at
$O(\tilde h^2)$, and a surface anchor would feed that straight into the answer.
Note that §3.5.1 of the design still describes a surface anchor; §3.7.4 is
later, gives the argument, and is what Omega implements.

One consequence is worth knowing before reading the tests.  A Polaris initial
condition pins the *sea surface* and lets the bottom pressure absorb the same
$O(\tilde h^2)$ discrepancy, which is the opposite end from `VertCoord`.  So on
these states the sea-floor anchor is **not** zero even on
`hydrostatic_consistency_linear`: the two columns reach slightly different
bottom pressures at the same depth, and at a common pressure their heights
genuinely differ.  The scheme is right to report it.  What the tests assert on
the exact set is therefore that the scan stays *flat* -- every increment zero
to round-off -- and that the assembled tendency is the anchor and nothing
else, which holds to a part in $10^7$ across the sweep.  The
`anchor_at_surface` guard switches ends so the gap can be measured rather than
assumed.

The module also retains `centered_shift()` and `centered_shift_accumulated()`.
These are no longer on the computational path; they are kept as diagnostics,
because `hpga_from_shift(centered_shift(ds), dx)` reproduces the centered
scheme's `HPGA` exactly and is the cheapest available regression test of it.

`finite_volume_hpga()` accepts a `guards` argument holding verification-only
switches, each deliberately breaking one rule of the design.  They exist to
confirm the test suite can detect a broken implementation; they are not
supported settings.

The Gauss-Legendre rule these integrals use comes from the `quadrature_points`
config option, which is the *same* option that fills in Omega's
`PressureGrad:QuadraturePoints`.  That is deliberate and is not a convenience.
`omega_vs_polaris_rms_threshold` is the only check in this task family that
tests Omega's arithmetic against an independent implementation, and it is a
check on the implementations only if both integrate with the same rule; two
sides quadrating differently are two algorithms, and their disagreement would
not be distinguishable from a bug in either.  Exactness itself does not depend
on the rule -- on the exact set the integrand is zero at every point, so any
rule integrates it to zero -- which is exactly why a mismatch here would show
up only off the exact set, where it is hardest to attribute.

### reference

The class
{py:class}`polaris.tasks.ocean.horiz_press_grad.reference.ReferenceColumn`
is not a `Step` but a lightweight callable evaluator.  It is instantiated
inside `Analysis.run()` (once per task, using the config and the mesh-derived
`x_sign`), and computes the HPGA reference analytically without writing any
intermediate file.

`ReferenceColumn.__init__()` reads the quadrature settings
(`reference_quadrature_method`, `reference_quadrature_subdivisions`,
`reference_horiz_eps_km`) and the geometry / profile parameters from config.
It builds `_ClampedInterp` PCHIP interpolants for Absolute Salinity and
Conservative Temperature at $x = 0$ and $x = \pm\varepsilon$ (six interpolants
in all), which are used later for centred finite-differencing.

The public methods are `specvol(z_tilde)` (specific volume at $x = 0$) and
`dalpha_dx(z_tilde)` (the fixed-$\tilde z$ x-gradient of specific volume), plus
the two used by `Analysis`:

- `hpga(z_tilde)` — evaluates $a(\tilde z)$ pointwise at the edge $x = 0$
  via the chain-rule / Leibniz integral, anchored at the surface (the boundary
  the model honours).  It accumulates the cumulative integral
  $I(\tilde z) = \int_{\tilde z_s}^{\tilde z} \bigl(\alpha_{S_A} \partial_x
  S_A + \alpha_{\Theta} \partial_x \Theta\bigr)\,d\tilde z'$ using
  `_fixed_quadrature` on a sorted unique node set, then interpolates back onto
  the requested $\tilde z$ values.  The surface boundary term
  ($\eta'$ and $\tilde z_s'$) is kept general so nonzero sea-surface height and
  surface pressure are supported.
- `layer_mean_hpga(z_tilde_interfaces)` — layer-averages `hpga()` over the
  model's actual pseudo-height layer bounds using 4-point Gauss–Legendre
  quadrature with `reference_quadrature_subdivisions` sub-panels per layer.
  This is what `Analysis` calls to form the reference target per layer.

The private class `_ClampedInterp` wraps
{py:func}`~polaris.tasks.ocean.horiz_press_grad.column.get_pchip_interpolator`
with constant extrapolation at the node bounds.

The quadrature primitives (`_fixed_quadrature`, `_gauss_composite`) support
midpoint, trapezoid, Simpson, `gauss2`, and `gauss4` methods and are shared
between the cumulative integral and the layer averaging.

### init

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.init.Init`
defines one step per `(horiz_res, vert_res)` pair.  It inherits from both
{py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep` and
{py:class}`polaris.ocean.model.OceanIOStep`.

Each `init` step:

- builds and culls a planar two-cell mesh,
- delegates the p-star iterative initialization to
  {py:meth}`~polaris.ocean.vertical.pstar_init.PStarInitStep.run_pstar_init()`,
  which adjusts ``BottomPressure`` until the recovered geometric water-column
  thickness matches the prescribed sea-surface and seafloor geometry, and
- writes `culled_mesh.nc`, `vert_coord.nc`, and `init.nc`.

The class implements the two extension points required by `PStarInitStep`:

- `init_tracers()` reconstructs conservative temperature and absolute salinity
  at p-star layer midpoints by calling the private helper `_interpolate_t_s()`,
  which applies a PCHIP interpolator to the piecewise pseudo-height profiles
  defined in the configuration.
- `_build_pstar_coord_ds()` overrides the base-class default to call
  {py:func}`~polaris.ocean.vertical.pstar.init_pstar_vertical_coord()` per
  column, allowing each column to have a different reference pseudo-depth set
  by ``z_tilde_bot`` in the configuration.

After the iteration converges, `Init.run()` appends the Python-side HPGA
diagnostic via the private helper `_compute_montgomery_and_hpga()`.

`init.nc` stores both the fields needed by Omega and the offline diagnostics
later used in analysis, including `pressure`, `SpecVol`, `Density`,
`GeomZMid`, `GeomZInterface`, `MontgomeryMid`, `MontgomeryInter`, `HPGA`,
`dMdxMid`, `dalphadxMid`, `PEdgeMid`, and `dSAdxMid`.  `vert_coord.nc`
holds the p-star coordinate variables written for Omega.

### forward

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.forward.Forward`
defines one model step per horizontal resolution **and per pressure-gradient
scheme**, named `forward_<res>_<scheme>`.

It runs Omega from the corresponding `init` output and writes `output.nc`
(with `NormalVelocityTend` validation), using options from `forward.yaml`.
`forward.yaml` is a Jinja2 template whose `PressureGrad` block is filled in per
step from the `scheme` argument and the `quadrature_points` config option.

The schemes are listed by the `pressure_grad_types` config option and named in
the module-level `SCHEMES` dict, which maps the config spelling to Omega's
`PressureGradType`.  `SCHEME_HPGA` maps each to the field in `init.nc` that is
its Polaris counterpart, which is what the analysis steps compare Omega
against.

Two things about this axis are worth stating, because both were decided
against plausible alternatives:

- **Both schemes share one `Init` step.**  `Init` is scheme-independent -- it
  writes `HPGA` and `HPGAFiniteVolume` from the same state -- so duplicating it
  per scheme would cost run time and, worse, would leave the comparison open to
  the objection that the two schemes ran on different initial conditions.  The
  cost is that the scheme label is in every forward step's directory, so
  baselines recorded before the axis existed do not carry over.
- **There is no "centered limit" of the finite-volume scheme.**  The two are
  separate implementations and no setting reduces one to the other, so this is
  a choice between schemes rather than a parameter of one.  Omega treats an
  unrecognized `PressureGradType` as fatal rather than falling back to
  `Centered`, so a typo aborts the run instead of producing centered answers
  that read as a pass.

### analysis

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.analysis.Analysis`
compares each `forward` result with:

- the analytic reference solution (built from `ReferenceColumn`), which is a
  property of the state and so is shared by both schemes, and
- the Python-computed HPGA from `init.nc` **for the matching scheme**:
  `HPGA` for `centered`, `HPGAFiniteVolume` for `finite_volume`.  Comparing
  Omega's finite-volume output against the centered `HPGA` would measure the
  difference between two schemes and report it as an implementation
  disagreement.

The step writes:

- `omega_vs_reference.nc` and `omega_vs_reference.png`
- `omega_vs_python.nc` and `omega_vs_python.png`

Both files carry one series per scheme, as variables suffixed with the scheme
name, and both plots draw the schemes on one panel -- the comparison between
them at the same resolution is the measurement, so separating them would hide
it.

The step enforces regression criteria from `[horiz_press_grad]`, applied per
scheme:

- allowed convergence-slope range for Omega-vs-reference,
- high-resolution RMS threshold for Omega-vs-reference, and
- RMS threshold for Omega-vs-Python consistency.

Implementation-wise, `Analysis.run()` iterates over configured horizontal
resolutions and, within each, over schemes.  For each resolution it:

1. reads `init_r*.nc`, `culled_mesh_r*.nc`, `vert_coord_r*.nc`, and
   `output_r*_<scheme>.nc`;
2. identifies the single internal edge via `_get_internal_edge()` and derives
   the forward pseudo-heights via `_get_forward_z_tilde_edge_mid()`;
3. constructs a `ReferenceColumn` with the mesh-derived `x_sign` and calls
   `ref.layer_mean_hpga()` on the edge interface pseudo-heights from `init.nc`,
   over interfaces `0 .. max_level_index + 1` so that every layer valid in both
   columns is included, down to and including the bottom partial cell.  An
   earlier version dropped that layer because the then-current five-column
   finite-difference reference could not form its stencil there; the analytic
   single-column reference is valid to the seafloor, so it is now kept;
4. checks that Python and Omega pseudo-heights agree with
   `_check_vertical_match()`, then computes the Omega-vs-Python RMS difference
   from `init.nc` HPGA.

The forward solution always comes from `output.nc` via `NormalVelocityTend`.
`rms()` and `power_law_fit()` from `metrics` produce the convergence datasets
and plots.

## the resting-state variants

{py:class}`polaris.tasks.ocean.horiz_press_grad.resting_state_task.HorizPressGradRestingStateTask`
is a sibling of `HorizPressGradTask` rather than a mode of it.  The existing
task pairs each entry of `horiz_resolutions` with one entry of
`vert_resolutions` and keys its step dictionaries by horizontal resolution
alone, so it cannot express the repeated horizontal resolutions the tilt sweep
needs.  The resting-state task keys its steps by the
`(horiz_res, vert_res, tilt)` triple instead, and builds the outer product of
the resolution pairs with `tilt_values`.

`Init` and `Forward` are reused unchanged apart from two optional arguments:

- `subdir_suffix` replaces the horizontal resolution in the step name, so
  repeated horizontal resolutions do not collide.  It is built by
  `sweep_suffix(horiz_res, vert_res, tilt)`, giving names like
  `init_4km_256m_tilt0p5`.  When it is not given, the horizontal resolution is
  used, giving `init_<res>` and `forward_<res>_<scheme>`.
- `tilt_option` and `tilt` (on `Init` only) name a `[horiz_press_grad]` config
  option that `Init.run()` sets in its own config before building the columns,
  in the same way it already sets `vertical_grid:vert_levels`.

`Init.run()` also calls `_check_reference_grid_head_room()` after
`run_pstar_init()`.  The p-star iteration converges to a pseudo-bottom depth
somewhat greater than the geometric water-column thickness, because in-situ
density exceeds `RhoSw` at depth.  If a tilt makes a column's `z_tilde_bot`
shallower than that, the reference grid cannot span the water column, the
iteration diverges, and the resulting HPGA is of order 1 m s$^{-2}$ rather than
the order 1e-5 m s$^{-2}$ being measured.  The guard raises with the head room
available in each column.

### resting_analysis

{py:class}`polaris.tasks.ocean.horiz_press_grad.resting_analysis.RestingAnalysis`
replaces `Analysis` for these variants.  Per sweep point it:

1. locates the internal edge with `get_internal_edge()`;
2. forms the valid layer range `0 .. min(maxLevelCell) - 1`, **inclusive** of
   the deepest layer valid in both columns — the bottom partial cell, which
   carries the entire `bathymetry_step` signal.  `Analysis` includes it too;
3. takes the RMS of Omega's `NormalVelocityTend` at that edge over those
   layers, for each scheme.  The truth is zero, so this is the error, not a
   difference from a reference;
4. does the same for the matching Polaris-side field from `init.nc` --
   `HPGA` or `HPGAFiniteVolume` per `SCHEME_HPGA` -- and RMS-differences the
   two.

It then groups the sweep by resolution pair, fits the tilt exponent within each
group and scheme over the points at or below `tilt_fit_max` when `tilt_fit` is
set, writes `resting_state.nc` and `resting_state.png`, and applies four
checks:

- `_check_bathymetry()` — `bottomDepth` must match the `bottomDepthRequested`
  written by `Init` to within `resting_state_max_bathy_error`.  The p-star
  column is anchored at the prescribed sea surface, so `ssh` is exact by
  construction and cannot reveal a problem; partial-cell snapping instead moves
  the sea floor, which leaves the state at rest but means the swept tilt is no
  longer the geometry under test;
- `_check_omega_vs_polaris()` — the retained `omega_vs_polaris_rms_threshold`
  consistency check, applied per scheme and independent of the resting-state
  property;
- `_check_sensitivity()` — the largest RMS anywhere in the sweep must reach
  `resting_state_sensitivity_min_rms`, or the sweep is not exercising the
  failure mode and must be redesigned.  This is applied to **`centered` only**:
  it asks whether the sweep is severe enough to exercise the failure the
  higher-order scheme exists to fix, so demanding it of `finite_volume` would
  be requiring the new scheme to fail;
- `_check_max_rms()` — the consistency gate, applied per scheme and skipped
  while `resting_state_max_rms` is `none`.
