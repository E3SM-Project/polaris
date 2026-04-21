(dev-ocean-horiz-press-grad)=

# horiz_press_grad

The {py:class}`polaris.tasks.ocean.horiz_press_grad.task.HorizPressGradTask`
provides two-column Omega tests for pressure-gradient-acceleration (`HPGA`)
accuracy and convergence across horizontal and vertical resolutions.

The task family includes three variants:

- `salinity_gradient`
- `temperature_gradient`
- `ztilde_gradient`

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

### reference

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.reference.Reference`
defines a step that builds a high-fidelity reference HPGA solution in
`reference_solution.nc`.

In implementation terms, `Reference.run()` does four things:

- determines the refined vertical resolution from the configured test
  resolutions,
- builds the reference columns and their thermodynamic profiles,
- computes the reference diagnostic fields, and
- writes `reference_solution.nc`.

Most of the work is organized through the private helpers
`_get_ssh_z_bot()`, `_get_z_tilde_t_s_nodes()`, `_compute_column()`, and
`_integrate_geometric_height()`.  Together, these routines reconstruct the
column state, convert from pseudo-height to geometric height, and populate the
reference dataset.

`reference_solution.nc` contains both the baseline fields used directly in
analysis and additional diagnostics that are useful when debugging or
inspecting the reference calculation, including `HPGAMid`, `HPGAInter`,
`MontgomeryMid`, `MontgomeryInter`, `dMdxMid`, `dalphadxMid`, `PEdgeMid`, and
the valid-gradient masks.

### init

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.init.Init`
defines one step per `(horiz_res, vert_res)` pair.

Each `init` step:

- builds and culls a planar two-cell mesh,
- sets up z-tilde vertical coordinates and profile fields,
- iteratively adjusts pseudo-bottom depth to match target geometric
  water-column thickness, and
- writes `culled_mesh.nc` and `initial_state.nc`.

The implementation is centered around `Init.run()` and three helpers:

- `_init_z_tilde_vert_coord()` initializes the vertical coordinate for each
  column separately,
- `_interpolate_t_s()` reconstructs temperature and salinity on the test grid,
- `_compute_montgomery_and_hpga()` computes the Python-side HPGA diagnostic and
  related output fields.

`initial_state.nc` stores both the fields needed by Omega and the offline
diagnostics later used in analysis, including `PressureMid`, `SpecVol`,
`Density`, `GeomZMid`, `GeomZInter`, `MontgomeryMid`, `MontgomeryInter`,
`HPGA`, `dMdxMid`, `dalphadxMid`, `PEdgeMid`, and `dSAdxMid`.

### forward

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.forward.Forward`
defines one model step per horizontal resolution.

It runs Omega from the corresponding `init` output and writes `output.nc`
(with `NormalVelocityTend` validation), using options from `forward.yaml`.

### analysis

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.analysis.Analysis`
compares each `forward` result with:

- the high-fidelity reference solution, and
- the Python-computed HPGA from `initial_state.nc`.

The step writes:

- `omega_vs_reference.nc` and `omega_vs_reference.png`
- `omega_vs_python.nc` and `omega_vs_python.png`

and enforces regression criteria from `[horiz_press_grad]`, including:

- allowed convergence-slope range for Omega-vs-reference,
- high-resolution RMS threshold for Omega-vs-reference, and
- RMS threshold for Omega-vs-Python consistency.

Implementation-wise, `Analysis.run()` reads the reference, init, and forward
outputs for each configured horizontal resolution, then uses helper routines
such as `_get_internal_edge()`, `_get_forward_z_tilde_edge_mid()`,
`_sample_reference_without_interpolation()`, `_check_vertical_match()`,
`_rms_error()`, and `_power_law_fit()` to produce the comparison datasets and
plots.

The key code-level distinction is that the reference comparison is built from
`reference_solution.nc`, whereas the implementation-consistency comparison is
built from `initial_state.nc`.  The forward solution always comes from
`output.nc` via `NormalVelocityTend`.
