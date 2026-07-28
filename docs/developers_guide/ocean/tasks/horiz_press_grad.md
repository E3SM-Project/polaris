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
defines one model step per horizontal resolution.

It runs Omega from the corresponding `init` output and writes `output.nc`
(with `NormalVelocityTend` validation), using options from `forward.yaml`.

### analysis

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.analysis.Analysis`
compares each `forward` result with:

- the analytic reference solution (built from `ReferenceColumn`), and
- the Python-computed HPGA from `init.nc`.

The step writes:

- `omega_vs_reference.nc` and `omega_vs_reference.png`
- `omega_vs_python.nc` and `omega_vs_python.png`

and enforces regression criteria from `[horiz_press_grad]`, including:

- allowed convergence-slope range for Omega-vs-reference,
- high-resolution RMS threshold for Omega-vs-reference, and
- RMS threshold for Omega-vs-Python consistency.

Implementation-wise, `Analysis.run()` iterates over configured horizontal
resolutions.  For each resolution it:

1. reads `init_r*.nc`, `culled_mesh_r*.nc`, `vert_coord_r*.nc`, and
   `output_r*.nc`;
2. identifies the single internal edge via `_get_internal_edge()` and derives
   the forward pseudo-heights via `_get_forward_z_tilde_edge_mid()`;
3. constructs a `ReferenceColumn` with the mesh-derived `x_sign` and calls
   `ref.layer_mean_hpga()` on the edge interface pseudo-heights from
   `init.nc`, dropping the deepest valid layer (which abuts bathymetry);
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
  `init_4km_256m_tilt0p5`.  When it is not given, the existing
  `init_<res>` / `forward_<res>` naming is used, so the four gradient variants
  keep their work directories.
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
   the deepest layer valid in both columns — `Analysis` drops that layer, but
   it is the bottom partial cell and carries the entire `bathymetry_step`
   signal;
3. takes the RMS of Omega's `NormalVelocityTend` at that edge over those
   layers.  The truth is zero, so this is the error, not a difference from a
   reference;
4. does the same for the Polaris-side `HPGA` from `init.nc` and RMS-differences
   the two.

It then groups the sweep by resolution pair, fits the tilt exponent within each
group over the points at or below `tilt_fit_max` when `tilt_fit` is set, writes
`resting_state.nc` and `resting_state.png`, and applies four checks:

- `_check_resting_state()` — the two columns' sea-surface heights must agree to
  `resting_state_max_ssh_diff`.  A larger difference means the vertical-grid
  construction moved the sea floor off the requested bathymetry, so the
  measured HPGA is real physics rather than error;
- `_check_omega_vs_polaris()` — the retained `omega_vs_polaris_rms_threshold`
  consistency check, which is independent of the resting-state property;
- `_check_sensitivity()` — the largest RMS anywhere in the sweep must reach
  `resting_state_sensitivity_min_rms`, or the sweep is not exercising the
  failure mode and must be redesigned;
- `_check_max_rms()` — the consistency gate, skipped while
  `resting_state_max_rms` is `none`.
