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

The task dynamically rebuilds `init` and `forward` steps in `configure()` so
user-supplied `horiz_resolutions` and `vert_resolutions` in config files are
reflected in the work directory setup.

### reference

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.reference.Reference`
defines a step that builds a high-fidelity reference HPGA solution in
`reference_solution.nc`.

It computes pseudo-height and geometric-height profiles on a refined reference
grid, evaluates TEOS-10 specific volume, and computes HPGA at the center
column using a 4th-order finite-difference stencil.

### init

The class {py:class}`polaris.tasks.ocean.horiz_press_grad.init.Init`
defines one step per `(horiz_res, vert_res)` pair.

Each `init` step:

- builds and culls a planar two-cell mesh,
- sets up z-tilde vertical coordinates and profile fields,
- iteratively adjusts pseudo-bottom depth to match target geometric
  water-column thickness, and
- writes `culled_mesh.nc` and `initial_state.nc`.

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
