(ocean-horiz-press-grad)=

# horizontal pressure gradient

## description

The `horiz_press_grad` tasks in `polaris.tasks.ocean.horiz_press_grad`
exercise Omega's hydrostatic pressure-gradient acceleration (`HPGA`)
for a two-column configuration with prescribed horizontal gradients.

The analysis uses two different baselines, each with a different purpose:

- a high-fidelity offline reference solution that is used as the main
  accuracy target, and
- a Python-computed two-column HPGA diagnostic from the `init` step that is
  used as a consistency check against Omega.

Each task includes:

- a high-fidelity `reference` solution for HPGA,
- an `init` step at each horizontal/vertical resolution pair,
- a single-time-step `forward` run at each horizontal resolution, and
- an `analysis` step comparing Omega output with both the reference and
  Python-initialized HPGA.

The tasks currently provided are:

```
ocean/horiz_press_grad/salinity_gradient
ocean/horiz_press_grad/temperature_gradient
ocean/horiz_press_grad/ztilde_gradient
```

```{image} images/horiz_press_grad_salin_grad.png
:align: center
:width: 600 px
```

The point of these tasks is not only to verify that Omega can reproduce the
same discrete answer as the Python initialization, but also to measure how the
two-column discretization converges toward a more accurate non-local
approximation of the continuous hydrostatic pressure-gradient force.

## supported models

These tasks currently support Omega only.

## mesh

The mesh is planar with two adjacent ocean cells.  For each resolution in
`horiz_resolutions`, the spacing between the two columns is set by that value
(in km).

The HPGA diagnostic is evaluated on the single internal horizontal edge that
connects the two columns, at each layer midpoint.  In this page, `x` denotes
the along-layer horizontal direction used by Omega's horizontal gradient
operator.  In the idealized two-column planar geometry, this direction follows
the line joining the two cell centers.  It is therefore related to the shared
edge normal, but it is not intended to define a separate exact geometric
edge-normal coordinate.

## vertical grid

The vertical coordinate is `z-tilde` with a uniform pseudo-height spacing for
each test in `vert_resolutions`.

The meaning of the along-layer `x` direction depends on the task variant.  In
the `salinity_gradient` and `temperature_gradient` tests, the `z-tilde`
interfaces are level, so pressure surfaces are also horizontally level except
where they intersect the bathymetry.  In the `ztilde_gradient` test, the
prescribed `z-tilde` gradient tilts the layers, so the pressure surfaces are
sloped and the along-layer direction follows those sloping layers.

The `reference` step uses a finer spacing `vert_res` chosen so that every test
spacing is an integer multiple of `2 * vert_res`. This allows reference
interfaces to align with test midpoints for exact subsampling in analysis.

## reference solution

The `reference` step constructs a high-fidelity numerical approximation to the
HPGA before any Omega run is performed.  This reference is not an exact
analytic solution.  Instead, it is a deliberately more accurate offline
calculation based on more columns and a much finer vertical grid than the
two-column test itself.

The reference starts from the Omega pseudo-height coordinate `z-tilde`, with

$$
p = -\rho_0 g \tilde z,
$$

and converts to geometric height `z` by integrating the hydrostatic relation

$$
\frac{\partial z}{\partial \tilde z} = \rho_0\,\nu\left(S_A, \Theta, p\right),
$$

where $\nu$ is specific volume from the TEOS-10 equation of state, $S_A$ is
Absolute Salinity, and $\Theta$ is Conservative Temperature.

For each reference column, the configured `z_tilde`, `temperature`, and
`salinity` node values are first reconstructed from the prescribed midpoint
values and horizontal gradients.  The vertical profiles are then evaluated as
functions of `z-tilde` and integrated upward from the seafloor to obtain
geometric height, specific volume, salinity and temperature on the refined
reference grid.

The reference uses five columns at

$$
x = \Delta x_{\mathrm{ref}}\,[-1.5, -0.5, 0, 0.5, 1.5],
$$

where $\Delta x_{\mathrm{ref}} =$ `reference_horiz_res`, 250 m by default.
After constructing Montgomery potential,

$$
M = \alpha p + gz = g\left(z - \rho_0 \alpha \tilde z\right),
$$

the reference HPGA is formed with the same sign convention used in the task
diagnostics,

$$
\mathrm{HPGA}_{\mathrm{ref}} = -\frac{\partial M}{\partial x}
+ p\frac{\partial \alpha}{\partial x}.
$$

The horizontal derivatives at the center column are approximated with the
4th-order centered stencil

$$
\frac{\partial f}{\partial x}(0) \approx
\frac{f\left(-\tfrac{3}{2}\Delta x\right)
- 27 f\left(-\tfrac{1}{2}\Delta x\right)
+ 27 f\left(\tfrac{1}{2}\Delta x\right)
- f\left(\tfrac{3}{2}\Delta x\right)}{24\Delta x}.
$$

This reconstruction is non-local: it uses four surrounding columns to evaluate
the gradient at the central column.  It is therefore not the same as a local
reconstruction based only on the two test cells or on local derivatives such
as `dT/dx` and `dS/dx` at the edge midpoint.  That kind of local reference may
be worth exploring in the future, especially when these tasks are extended to
support higher-order HPGA formulations, but it is not what is used today.

## python HPGA in the `init` step

The `init` step computes a second HPGA estimate directly from the initialized
two-column state.  This calculation is intentionally much closer to the
discrete Omega formulation than the high-fidelity reference is.

First, the step constructs the two-cell mesh and the test vertical grid for the
requested `(horiz_res, vert_res)` pair.  Because the geometric water-column
thickness depends on the equation of state through the mapping from
`z-tilde` to `z`, the step iteratively rescales the pseudo-bottom depth so that
the resulting geometric water-column thickness matches the prescribed
sea-surface and bottom geometry.

Once the initialized state is available, the Python diagnostic computes the
same thermodynamic quantities used by Omega: pressure, specific volume,
geometric height, and Montgomery potential.  It then forms a two-column finite
difference,

$$
\frac{\partial M}{\partial x} \approx \frac{M_R - M_L}{\Delta x},
\qquad
\frac{\partial \alpha}{\partial x} \approx
\frac{\alpha_R - \alpha_L}{\Delta x},
$$

with edge pressure

$$
p_{\mathrm{edge}} = \frac{p_L + p_R}{2},
$$

and writes the corresponding diagnostic

$$
\mathrm{HPGA}_{\mathrm{python}} = -\frac{\partial M}{\partial x}
+ p_{\mathrm{edge}}\frac{\partial \alpha}{\partial x}
$$

to `initial_state.nc`.

This Python HPGA is not the main reference solution.  Instead, it checks
whether Omega's one-step tendency matches the expected two-column discrete
calculation from the initialized state.

(ocean-horiz-press-grad-config)=
## config options

Shared options are in section `[horiz_press_grad]`:

```cfg
# resolutions in km (distance between the two columns)
horiz_resolutions = [4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5]

# vertical resolution in m for each two-column setup
vert_resolutions = [4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5]

# geometric sea-surface and sea-floor midpoint values and x-gradients
geom_ssh_mid = 0.0
geom_ssh_grad = 0.0
geom_z_bot_mid = -500.0
geom_z_bot_grad = 0.0

# pseudo-height bottom midpoint and x-gradient
z_tilde_bot_mid = -576.0
z_tilde_bot_grad = 0.0

# midpoint and gradient node values for piecewise profiles
z_tilde_mid = [0.0, -48.0, -144.0, -288.0, -576.0]
z_tilde_grad = [0.0, 0.0, 0.0, 0.0, 0.0]

temperature_mid = [22.0, 20.0, 14.0, 8.0, 5.0]
temperature_grad = [0.0, 0.0, 0.0, 0.0, 0.0]

salinity_mid = [35.6, 35.4, 35.0, 34.8, 34.75]
salinity_grad = [0.0, 0.0, 0.0, 0.0, 0.0]

# reference settings
reference_quadrature_method = gauss4
reference_horiz_res = 0.25
```

The three task variants specialize one horizontal gradient field:

- `salinity_gradient`: nonzero `salinity_grad`
- `temperature_gradient`: nonzero `temperature_grad`
- `ztilde_gradient`: nonzero `z_tilde_bot_grad`

## time step and run duration

The `forward` step performs one model time step and outputs pressure-gradient
diagnostics used in the analysis.

## analysis

The `analysis` step computes and plots:

- Omega RMS error versus reference (`omega_vs_reference.png`), including a
  power-law fit and convergence slope, and
- Omega RMS difference versus Python initialization (`omega_vs_python.png`).

The corresponding tabulated data are written to
`omega_vs_reference.nc` and `omega_vs_python.nc`.

For the Omega-versus-reference comparison, the reference is sampled onto the
test vertical locations without interpolation.  This is why the refined
reference spacing is chosen so that the reference interfaces align exactly with
test midpoints and interfaces.  The comparison only uses layers that are valid
in both the reference and the Omega solution.

For the Omega-versus-Python comparison, the analysis uses the HPGA written by
the `init` step in `initial_state.nc`, so this second metric should be read as
an implementation-consistency check rather than as an accuracy measure against
the high-fidelity reference.

Implementation details for the `reference`, `init`, and `analysis` steps are
described in {ref}`dev-ocean-horiz-press-grad`.

