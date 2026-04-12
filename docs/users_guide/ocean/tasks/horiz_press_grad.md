(ocean-horiz-press-grad)=

# horizontal pressure gradient

## description

The `horiz_press_grad` tasks in `polaris.tasks.ocean.horiz_press_grad`
exercise Omega's hydrostatic pressure-gradient acceleration (`HPGA`)
for a two-column configuration with prescribed horizontal gradients.

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
## supported models

These tasks currently support Omega only.

## mesh

The mesh is planar with two adjacent ocean cells.  For each resolution in
`horiz_resolutions`, the spacing between the two columns is set by that value
(in km).

## vertical grid

The vertical coordinate is `z-tilde` with a uniform pseudo-height spacing for
each test in `vert_resolutions`.

The `reference` step uses a finer spacing `vert_res` chosen so that every test
spacing is an integer multiple of `2 * vert_res`. This allows reference
interfaces to align with test midpoints for exact subsampling in analysis.

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

