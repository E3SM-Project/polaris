# ISOMIP+ Tasks

date: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

## Summary

Polaris has had ISOMIP+ mesh and topography steps since
[#141](https://github.com/E3SM-Project/polaris/pull/141) in 2023, but
nothing downstream of them. The `ocean/{planar,spherical}/isomip_plus`
tasks build a mesh, remap the input geometry and stop. The draft that
added an initial condition and forcing
([#151](https://github.com/E3SM-Project/polaris/pull/151)) was never
finished.

MPAS-Ocean has already taken part in ISOMIP+
([Yung et al. 2026](https://doi.org/10.5194/tc-20-2053-2026)) through
Compass. Section, table and equation numbers in this design refer to
the ISOMIP+ protocol
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)).
In Polaris, the ISOMIP+ setup is a platform for idealized
ice-shelf-cavity tests:

- the `inception`, `wetting` and `drying` tasks, which scale the Ocean1
  ice load in time to test wetting and drying;
- Ocean3 and Ocean4, with a moving grounding line, planned as E3SM runs
  in which MALI replays the prescribed geometry;
- MISOMIP1, coupling MPAS-Ocean and an active MALI in E3SM.

This work delivers the first stage:

- Ocean0, Ocean1 and Ocean2 run end to end with MPAS-Ocean, on planar
  and spherical meshes;
- the `inception`, `wetting` and `drying` tasks produce an initial
  condition and forcing, including time-varying land-ice forcing and a
  thin film under grounded ice;
- [Planned Extensions](#planned-extensions) states what running the
  wetting and drying tasks, long runs, standard output, Ocean3–4 and
  MISOMIP1 will require.

In every task, the land-ice pressure is the weight of the ice, and the
sea-surface height adjusts to it, as it will when MALI supplies the
pressure ([D13](#decisions)). The tasks need MPAS-Ocean with the
land-ice options of
[E3SM#8047](https://github.com/E3SM-Project/E3SM/pull/8047) and the cap
on land-ice pressure in grounded cells from
[E3SM-Ocean-Discussion#119](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/119).

Omega does not yet support ice-shelf cavities, so it is out of scope.

| Task        | Geometry         | Grounded cells    | Steps in this work           |
|-------------|------------------|-------------------|------------------------------|
| `ocean0`    | Ocean1           | culled            | init, SSH adj., forward, viz |
| `ocean1`    | Ocean1           | culled            | init, SSH adj., forward, viz |
| `ocean2`    | Ocean2           | culled            | init, SSH adj., forward, viz |
| `inception` | Ocean1 × 0, 1, 1 | thin film         | init                         |
| `wetting`   | Ocean1 × 1, 0, 0 | thin film         | init                         |
| `drying`    | Ocean1 × 1, 2, 2 | thin film         | init                         |

The existing `ocean3` and `ocean4` tasks, which only remap their
geometry, are removed ([D8](#decisions)). All other tasks keep the
existing shared mesh and topography steps.

The Compass `isomip_plus` test group is the reference for capability,
not for code. The new steps are built from pieces Compass did not have:

- shared mesh and topography steps ({ref}`dev-shared-steps` and the
  [shared steps design](shared_steps.md));
- conservative remapping of the input geometry;
- the SSH-adjustment framework in `polaris.ocean.ice_shelf`
  ({ref}`dev-ocean-framework-ice-shelf`);
- the staged-file conventions of `OceanIOStep` and `OceanModelStep`
  ({ref}`dev-ocean-model`);
- YAML model config ({ref}`dev-ocean-framework-config`);
- shared EOS and Coriolis config ({ref}`dev-ocean-framework-eos`).

Success means:

- Ocean0–2 run end to end, and the wetting and drying tasks produce
  initial conditions and forcing, on planar and spherical meshes;
- short runs of Ocean0–2 in Compass and Polaris, with the same
  MPAS-Ocean build, are compared;
- every difference between them is attributed to a cause listed under
  [Decisions](#decisions).

## Requirements

### Requirement: Ocean0, Ocean1 and Ocean2 can be run with MPAS-Ocean

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Each experiment is available on planar and spherical meshes at 4, 2
and 1 km resolution. A task produces an initial condition, brings the
ice-shelf pressure into balance with the ocean, and runs the model.

### Requirement: The wetting and drying tasks have an initial condition

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The `inception`, `wetting` and `drying` tasks produce an initial
condition and forcing, including time-varying land-ice forcing, from
which follow-up work can run them.

### Requirement: Geometry follows the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Each task uses the ISOMIP+ input geometry named in the
[Summary](#summary). Floating ice thinner than 100 m is removed
(calved) before the geometry is used.

### Requirement: Grounded cells are culled where they are never used

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Tasks with static geometry contain only the cells that hold ocean.
Tasks with time-varying geometry keep every cell, and cells under
grounded ice hold a thin film. All tasks use wetting and drying.

### Requirement: Initial conditions and forcing follow the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

| Task                             | Initial T, S | Restoring T, S |
|----------------------------------|--------------|----------------|
| `ocean0`                         | WARM         | WARM           |
| `ocean1`                         | COLD         | WARM           |
| `ocean2`                         | WARM         | COLD           |
| `inception`, `wetting`, `drying` | WARM         | WARM           |

The ocean starts at rest. Temperature and salinity are restored within
10 km of the northern boundary. The domain is an f-plane at 75°S.

### Requirement: Ice-shelf pressure is balanced before the forward run

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

The Ocean0–2 forward runs start from a state in which the pressure from
the ice shelf and the sea-surface height are in approximate dynamic
balance. The pressure is the weight of the ice; the sea-surface height
adjusts to it.

### Requirement: Output supports regression testing and inspection

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The Ocean0–2 forward runs write the ocean state and the land-ice
fluxes, and both can be compared with a baseline. Plots show the
initial geometry, vertical grid, temperature and salinity, and the melt
at the end of the forward run.

### Requirement: Differences from Compass are documented

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Where Polaris and Compass make different choices, this design records
the choice and its expected effect. The comparison in
[Testing](#testing) attributes each observed difference to one of them.

## Algorithm Design

### Algorithm Design: Ocean0, Ocean1 and Ocean2 can be run with MPAS-Ocean

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Each task runs the existing shared mesh and topography steps, then:

1. `init` builds the initial condition and the forcing on the task's
   cells;
2. ten SSH-adjustment iterations balance the ice-shelf pressure;
3. `forward` runs the model with melt fluxes and restoring;
4. `viz` plots the initial condition and the forward output.

The physics follows the COM configuration (Table 4 of the protocol) as
Compass sets it up for MPAS-Ocean:

- linear EOS with $\rho_{ref} = 1027.51$ kg m⁻³, $T_{ref} = -1$ °C,
  $S_{ref} = 34.2$ PSU, $\alpha = 0.03836$ kg m⁻³ °C⁻¹ and
  $\beta = 0.8059$ kg m⁻³ PSU⁻¹;
- three-equation melt with Jenkins heat and salt transfer coefficients
  0.0194 and 0.0194/35, $u_{tidal} = 0.01$ m s⁻¹, and a 10 m boundary
  layer;
- implicit top and bottom drag with coefficient $2.5\times10^{-3}$
  ([D12](#decisions));
- vertical viscosity and diffusivity $10^{-3}$ and $5\times10^{-5}$
  m² s⁻¹, convective values 0.1 m² s⁻¹, no shear mixing;
- horizontal Laplacian viscosity and diffusivity 6.0 and 1.0 m² s⁻¹;
- wetting and drying, with a minimum layer thickness of $10^{-3}$ m
  ([D11](#decisions));
- RK4 time stepping with $\Delta t = 6$ s per km, since MPAS-Ocean
  supports wetting and drying only with RK4;
- 36 uniform z-star levels over 720 m, at least 3 levels per column,
  no partial cells.

The cavity freezing point uses the MPAS-Ocean default coefficients, as
in Compass ([D6](#decisions)).

### Algorithm Design: The wetting and drying tasks have an initial condition

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The existing `TopoScale` step produces the geometry records: the Ocean1
geometry with pressure and draft scaled by the factors in the
[Summary](#summary), at yearly intervals. The fractions are not scaled,
so the melting area stays fixed, as in Compass.

`init` builds the initial condition from the first record. It writes
every record, on the task's cells, as land-ice forcing: pressure,
draft, land-ice fraction and floating fraction, each with its date.
MPAS-Ocean interpolates these fields linearly between records.

### Algorithm Design: Geometry follows the ISOMIP+ protocol

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

Calving is applied to one snapshot of the 1 km input geometry at a
time, before remapping. Where the floating fraction exceeds 0.1 and
the ice is thinner than $H_{calve} = 100$ m, the ice thickness, draft,
surface and floating fraction are set to zero and the cell becomes open
ocean.

```{admonition} Rationale
The protocol (Sect. 3.1.2) requires calving as part of setting up the
topography, and the input files are not calved. About 10 % of the
floating cells in the Ocean1 and Ocean2 input geometry are thinner than
100 m. The 0.1 floating-fraction threshold is the one Compass uses. A
function that calves one snapshot can also serve the Ocean3–4 geometry
([Planned Extensions](#planned-extensions)).
```

The calved geometry is remapped conservatively onto the shared culled
mesh by the existing steps ([D1](#decisions)). The ice-shelf pressure
is $p = \rho_i g H$ with $\rho_i = 918$ kg m⁻³. The initial SSH is the
draft of floating ice at that pressure, with
$\rho_{sw} = 1028$ kg m⁻³, limited to be no deeper than the bed
([D13](#decisions)).

Among the task's cells:

- `landIceMask` is 1 where the land-ice fraction exceeds 0.5, and the
  land-ice fractions are zero elsewhere;
- the SSH-adjustment mask, which selects the cells whose SSH change is
  logged, is 1 where the land-ice fraction exceeds 0.01;
- the bottom depth is deepened where needed so the water column is at
  least $1.1\times10^{-2}$ m thick, or $10^{-3}$ m in thin-film tasks.

These thresholds are Compass's.

### Algorithm Design: Grounded cells are culled where they are never used

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

- **Static geometry (`ocean0`–`ocean2`):** a cell is kept if its
  floating plus open-ocean fraction is at least `min_ocean_fraction`
  (0.5), the rule Compass uses to cull its mesh. Grounded cells are
  never used, so all of them are culled.
- **Scaled geometry (`inception`, `wetting`, `drying`):** every cell of
  the shared mesh is kept. Cells where the draft at the land-ice
  pressure reaches the bed are grounded and hold a thin film whose
  temperature is the freezing point at the land-ice pressure and the
  local salinity.

```{admonition} Rationale
MPAS-Ocean cannot activate a column during a run, so a cell that holds
ocean at any time must be active from the start. The input domain is
entirely below sea level, so keeping the grounded cells of the static
geometry would add 27–34 % more cells. For the scaled geometry, a rule
based on the draft misclassifies grounded cells, whose draft in the
input can sit up to 2.5 m above the bed, so every cell is kept.
```

### Algorithm Design: Initial conditions and forcing follow the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Initial and restoring profiles are linear in depth:

$$
T(z) = T_0 + (T_{bot} - T_0)\,\frac{z}{z_{b}}, \qquad
S(z) = S_0 + (S_{bot} - S_0)\,\frac{z}{z_{b}},
$$

evaluated at layer midpoints, with $z_b = -720$ m.

| Profile | $T_0$ (°C) | $T_{bot}$ (°C) | $S_0$ (PSU) | $S_{bot}$ (PSU) |
|---------|------------|----------------|-------------|-----------------|
| WARM    | −1.9       | 1.0            | 33.8        | 34.7            |
| COLD    | −1.9       | −1.9           | 33.8        | 34.55           |

The restoring rate is

$$
\gamma(x) = \gamma_0 \max\left(0, \frac{x - x_{r0}}{x_{r1} - x_{r0}}\right),
$$

with $\gamma_0 = 1/(10\ \mathrm{days})$, $x_{r0} = 790$ km and
$x_{r1} = 800$ km, using the ISOMIP+ $x$ coordinate on both planar and
spherical meshes.

Evaporation at 200 m yr⁻¹ over the restoring region offsets the
meltwater input. It removes salt and heat at the surface restoring
values $S_0$ and $T_0$, following Eqs. (34)–(36) of the protocol.

The Coriolis parameter is constant, $f = -1.409\times10^{-4}$ s⁻¹.

### Algorithm Design: Ice-shelf pressure is balanced before the forward run

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

The existing framework algorithm is used in the mode that adjusts SSH.
Each of ten iterations runs the model for one hour with melt fluxes
off. The SSH in every cell is then replaced by its value at the end of
the run, and the layers are stretched to match. The land-ice pressure
does not change ([D13](#decisions)). Compass's `adjust_ssh` changes
the pressure instead.

### Algorithm Design: Output supports regression testing and inspection

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The forward run lasts one hour by default, as in Compass's
`performance` step. Output is written at the end of the run.

Horizontal plots use the ISOMIP+ $x$ and $y$ coordinates, so planar and
spherical plots are directly comparable. Transects are at
$y = 40$ km.

### Algorithm Design: Differences from Compass are documented

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Each entry in [Decisions](#decisions) states its expected effect on the
comparison. The comparison isolates model configuration from geometry
by running the Polaris forward step on Compass's initial condition
([Testing](#testing)).

## Implementation

### Implementation: Ocean0, Ocean1 and Ocean2 can be run with MPAS-Ocean

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The task tree for one resolution is:

```
ocean/planar/isomip_plus/2km/
├── base_mesh/                       (shared, existing)
├── topo/                            (shared, existing)
│   ├── map_base/  remap_base/  cull_mesh/  map_culled/
│   ├── remap_culled/{ocean1,ocean2}/
│   └── scale/{inception,wetting,drying}/
└── z-star/
    ├── ocean0/
    │   ├── isomip_plus.cfg
    │   ├── init/
    │   ├── ssh_adjustment/{ssh_forward,ssh_adjust}_{0..9}/
    │   ├── forward/
    │   └── viz/
    ├── ocean1/  ocean2/              (same steps as ocean0)
    └── inception/  wetting/  drying/
        ├── isomip_plus.cfg
        └── init/
```

The spherical tree is the same under `ocean/spherical/isomip_plus`.

`add_isomip_plus_tasks()` no longer creates the `ocean3` and `ocean4`
tasks or their `remap_culled` steps. `TopoRemap` keeps its Ocean3 and
Ocean4 input files and its handling of time records.

`IsomipPlusTest` becomes a subclass of
`polaris.ocean.ice_shelf.IceShelfTask`. Its `thin_film` attribute is
set for the scaled tasks. It adds `init` to every task, and the
SSH-adjustment, `forward` and `viz` steps only to `ocean0`–`ocean2`.

`add_isomip_plus_tasks()` creates one shared config per task, as
`add_ice_shelf_2d_tasks()` does, from:

- the existing `isomip_plus_topo.cfg`;
- `polaris.ocean.eos` `linear.cfg`;
- `polaris.ocean.ice_shelf` `ssh_adjustment.cfg` and `freeze.cfg`;
- a rewritten `isomip_plus.cfg` with the vertical grid, Coriolis, EOS
  values, profiles, restoring, thresholds, SSH-adjustment time steps
  and forward options.

New steps in `polaris/tasks/ocean/isomip_plus/`:

- `init.py`: `Init(OceanIOStep)`;
- `ssh_forward.py`: `SshForward`, a subclass of the framework step that
  supplies the cell count and the shared physics YAML;
- `forward.py`: `Forward(OceanModelStep)`;
- `viz.py`: `Viz(OceanIOStep)`.

Model config lives in two YAML files. `physics.yaml` is shared by the
SSH-adjustment and forward runs; `SshForward` passes it to the
framework as its package YAML. `forward.yaml` adds the run duration,
restoring, melt and streams. The EOS options come from the `[ocean]`
section through `update_eos=True`, not from YAML.

Both model steps estimate their cell count from the resolution and an
ocean area of 30,000 km², the figure Compass uses.

### Implementation: The wetting and drying tasks have an initial condition

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

For tasks with a `Time` dimension in their topography, `Init` writes
`land_ice_forcing.nc` with `xtime`, `landIcePressureForcing`,
`landIceDraftForcing`, `landIceFractionForcing` and
`landIceFloatingFractionForcing`. The #151 draft's
`_write_time_varying_forcing()` is the starting point. The existing
`TopoScale` output already carries the records and their dates.

### Implementation: Geometry follows the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

A new module, `polaris/tasks/ocean/isomip_plus/topo/calving.py`,
provides a public function that calves one snapshot of the input
geometry. `TopoRemap._preprocess()` calls it on each record, with the
threshold from a new `min_ice_thickness` option in
`[isomip_plus_topo]`. The mesh cull is unaffected, because it depends
only on bedrock.

The land-ice pressure and draft helpers and the freezing-point helper
from #151 move to `polaris/ocean/ice_shelf/pressure.py` and
`freeze.py`, using `get_constant()`. `freeze.cfg` holds MPAS-Ocean's
default coefficients. `ice_shelf_2d` drops its private copy of
`_compute_land_ice_pressure_from_draft()` in favor of the shared one.

### Implementation: Grounded cells are culled where they are never used

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

`Init.run()`:

1. reads the shared culled mesh and the task's remapped or scaled
   topography;
2. for static geometry, removes the cells that are less than half
   floating ice or open ocean with `mpas_tools.mesh.cull`, carrying the
   topography fields over with `cull_dataset()`;
3. writes the task's mesh, with Coriolis added by
   `add_coriolis_to_dataset()`, and its graph file;
4. computes masks, fractions, SSH, pressure and bottom depth from the
   first record, and the thin-film mask where the task has a thin film.

The thin-film minimum column thickness and the seawater density used
to compute the draft from the pressure are options in `[isomip_plus]`.
The draft comes from a new shared helper,
`compute_land_ice_draft_from_pressure()`.

### Implementation: Initial conditions and forcing follow the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

`Init.run()` continues:

5. calls `init_vertical_coord()`;
6. evaluates the initial profile at `zMid`, sets the freezing point in
   thin-film cells, and sets zero velocity;
7. writes `mesh.nc`, `vert_coord.nc` and `init.nc` with the
   `OceanIOStep` writers, registered with
   `add_output_files_for_ocean_model_input()`;
8. writes `forcing.nc` with the restoring values and rates,
   `evaporationFlux`, `seaIceSalinityFlux` and `seaIceHeatFlux`.

The WARM and COLD profiles are config options in `[isomip_plus]`. Each
task selects them by name in code, not by overriding the options.

### Implementation: Ice-shelf pressure is balanced before the forward run

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

The task calls `setup_ssh_adjustment_steps()` with the init step's
mesh, graph and initial condition. `[ssh_adjustment]` overrides set
`adjust_variable = ssh`, and `time_integrator = RK4` and
`rk4_dt_per_km = 6` to match the forward run. The init step writes the
SSH-adjustment mask under the name in `mask_variable`.

No task used the framework's SSH mode before. `update_layer_thickness()`,
which it calls, now accepts the vertical coordinate as
`init_vertical_coord()` writes it, with one-based level indices.

### Implementation: Output supports regression testing and inspection

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

`Forward` reads the last SSH-adjustment output as its initial condition
and links `forcing.nc` as the `forcing_data` stream. It writes:

- `output.nc`, validated on `temperature`, `salinity`,
  `layerThickness` and `normalVelocity`;
- `land_ice_fluxes.nc`, validated on the 19 variables Compass compares
  in that file;
- global statistics.

`[isomip_plus_forward]` holds `run_duration` and `rk4_dt_per_km`.
`physics.yaml` turns on wetting and drying with Compass's thin-film
settings and sets the top drag coefficient.

`Viz` plots the fields #151 plotted for the initial condition. For the
forward output it adds melt rate, thermal driving, friction velocity,
and top and bottom temperature and salinity. It uses `plot_horiz_field()`
and the `mpas_tools` transect functions, with the ISOMIP+ coordinates
substituted for `xCell`, `yCell`, `xVertex` and `yVertex`.

New documentation:

- a user's guide page from `docs/users_guide/ocean/tasks/template.md`;
- a developer's guide page;
- `api.md` entries for the new classes and helpers.

`framework_pr` already lists `ocean/planar/isomip_plus/4km/z-star/ocean0`
for its remapping coverage. That entry now runs the full task. No other
suite changes.

### Implementation: Differences from Compass are documented

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

No code. The comparison scripts are not committed.

## Testing

### Testing and Validation: Ocean0, Ocean1 and Ocean2 can be run with MPAS-Ocean

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Set up and run the 18 Ocean0–2 tasks (3 experiments, 3 resolutions, 2
mesh types) with MPAS-Ocean. Record wall-clock times in the pull
request's Testing comment.

### Testing and Validation: The wetting and drying tasks have an initial condition

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Set up and run the 18 `inception`, `wetting` and `drying` tasks. Check
that `land_ice_forcing.nc` has 3 records and that its first record
matches `init.nc`.

### Testing and Validation: Geometry follows the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Unit tests cover calving on a synthetic input grid and the pressure and
freezing-point helpers. The `viz` plots show no ice thinner than 100 m
and a calving front at $x \approx 640$ km.

### Testing and Validation: Grounded cells are culled where they are never used

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

For static geometry, recompute the keep mask from the remapped
topography and check that the init mesh contains exactly those cells.
For scaled geometry, check that all cells are kept and that
thin-film cells have the minimum column thickness and the
freezing-point temperature.

### Testing and Validation: Initial conditions and forcing follow the ISOMIP+ protocol

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Check the bottom temperature in `init.nc` against the table in the
requirement: 1.0 °C for WARM, −1.9 °C for COLD. Check that the
restoring rate is zero south of 790 km and $1/(10\ \mathrm{days})$ at
800 km.

### Testing and Validation: Ice-shelf pressure is balanced before the forward run

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The maximum SSH change logged by each `ssh_adjust` step decreases over
the iterations, as it does in Compass.

### Testing and Validation: Output supports regression testing and inspection

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Run the 4 km planar Ocean0–2 tasks twice against a baseline and confirm
they pass. Inspect the plots.

### Testing and Validation: Differences from Compass are documented

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

Compass and Polaris use the same MPAS-Ocean build, and Compass's
ISOMIP+ namelist sets the same top drag coefficient. Compass's
namelists use the land-ice options that E3SM#8047 replaced, so the
build predates E3SM#8047, and the Polaris tasks are run before their
switch to the new options. The comparison is
at 2 km on the planar mesh for Ocean0, Ocean1 and Ocean2. Compass's
`thin_film_Ocean0`, which uses wetting and drying, is the counterpart
of `ocean0`; its standard Ocean0–2 do not use it
([D11](#decisions)). The comparison has three stages:

1. **Model config.** Compare the generated namelists and streams. Every
   difference is either removed or listed in [Decisions](#decisions).
2. **Forward run on a common initial condition.** Run the Polaris
   model config on Compass's adjusted initial condition, forcing and
   graph partition. Output should match Compass's `performance` step
   bit for bit.
3. **Whole task.** Compare the initial conditions, SSH-adjustment
   convergence, and the melt diagnostics after one hour and after one
   month: ocean area and volume, ice-shelf area, mean melt rate, total
   melt flux, mean thermal driving and mean friction velocity.

Each difference in stage 3 is attributed to one of D1–D4, D11 or D13.
Stage 3 is repeated for the spherical 2 km tasks.

## Planned Extensions

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

This section is not part of this work. It records what each extension
will need, so that the steps above can serve it.

**Running the wetting and drying tasks.**

- SSH adjustment, `forward` and `viz` steps for these tasks, reusing
  the Ocean0–2 steps.
- MPAS-Ocean's time-varying land-ice forcing
  (`config_use_time_varying_land_ice_forcing`) reading
  `land_ice_forcing.nc`.

**Split-explicit wetting and drying.** RK4 at 6 s per km takes 20
times as many steps as the split-explicit scheme at 120 s per km. Work
on split-explicit wetting and drying (Carolyn Begeman's
`alt-wetting-drying-se` branch) is not yet in E3SM. If it is needed,
Polaris will build MPAS-Ocean from an `ocn-glc/fanssie-coupling` branch
that also includes E3SM#8047.

**Long runs.** Ocean0 runs for 1 year and Ocean1–2 for 20. They need:

- forward runs in segments with restarts;
- the evaporation flux updated between segments from the mean SSH in
  the restoring region, as Compass's `simulation` step does;
- monthly-mean output.

At 2 km, 20 years is about 53 million RK4 steps at 12 s, so long runs
depend on split-explicit wetting and drying.

**Standard output.** Barotropic and overturning streamfunctions and the
MISOMIP fields on the 2 km output grid, as in Compass's
`streamfunction` and `misomip` steps.

**Ocean3–4 in E3SM.** MPAS-Ocean runs coupled in E3SM, with MALI in
data mode replaying the Ocean3 or Ocean4 geometry through the coupler.
This does not use MPAS-Ocean's standalone land-ice forcing, and needs a
separate Polaris setup that builds:

- a playback file for MALI from the 101 yearly records of the input
  geometry, calved as the protocol requires (interpolated in time, then
  calved, so the calving front moves rather than thins);
- an MPAS-Ocean initial condition that keeps every cell that holds
  ocean in any record, with a thin film where it is grounded, from the
  Ocean3 or Ocean4 geometry remapped by `TopoRemap`;
- E3SM input files on the spherical ISOMIP+ mesh: initial state,
  forcing, graph partitions, and SCRIP files with and without the
  land-ice mask, as in Compass's `files_for_e3sm`.

The runs use E3SM's existing wetting and drying configuration and run
outside Polaris, like other E3SM cases. Each run is 100 years. At 2 km
with a 12 s thin-film time step, that is about 260 million steps, so
the thin-film time step decides whether these runs are affordable.

**MISOMIP1.** The same E3SM configuration with an active MALI running
MISMIP+, coupled to MPAS-Ocean.

**Other variants.** The `z-star` level of the task path leaves room for
sigma-coordinate variants, which Compass had for its thin-film tests.
Omega can be added once it supports cavities.

## Decisions

### D1: Geometry comes from conservative remapping

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The existing Polaris steps remap the input geometry conservatively,
with destination cells expanded by a factor of 2 for smoothing, and
renormalize by the fraction of bedrock below sea level. Compass applies
a Gaussian filter weighted by ocean fraction on the input grid, then
interpolates bilinearly.

*Effect:* small differences in ice draft and bathymetry, largest at the
calving front, the grounding line and the side walls.

### D2: The meshes differ

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The Polaris planar mesh covers the domain plus an 80 km buffer and is
culled where bedrock is above sea level. Compass builds a periodic mesh
of $n_x \times n_y$ cells, then culls it. Cell centers do not coincide.

*Effect:* comparisons are of domain statistics and plots, not of
cell-by-cell values.

### D3: Each task culls the cells it will never use

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The shared culled mesh keeps every cell over bedrock below sea level,
so one mesh and one set of mapping files serve all tasks. For static
geometry, each task's `init` step then removes the grounded cells.
Tasks with time-varying geometry keep every cell. The #151 draft
instead kept grounded cells as inactive columns with
`maxLevelCell = 0`, which suits neither static nor time-varying
geometry.

*Effect:* for Ocean0–2, the ocean cells match Compass's selection rule,
so only the geometry differences of D1 and D2 remain.

### D4: Pressure comes from ice thickness

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

Polaris computes $p = \rho_i g H$ with $\rho_i = 918$ kg m⁻³. Compass
computes $p = -\rho_{sw} g z_d$ with $\rho_{sw} = 1026$ kg m⁻³, except
in its thin-film tasks. The protocol allows either.

*Effect:* about 0.2 % more pressure under floating ice in Polaris than
in Compass's initial condition. SSH adjustment does not remove it
([D13](#decisions)).

In cells that are partly grounded, the remapped weight of the grounded
ice can exceed what floats at the remapped draft. At 1 km, and at 2 km
on the spherical mesh, the excess is larger than the water column in a
few cells. Without wetting and drying, those runs produced NaN within a
few steps at any time step. Computing the pressure from the draft, as
Compass does, removed the failures, but wetting and drying handles the
excess as a thin film and keeps the pressure physical
([D11](#decisions)). Polaris does nothing to relieve the excess
([D13](#decisions)).

### D5: Forcing is written by the init step

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The #151 draft had a separate `forcing` step. The restoring profiles
need the vertical coordinate that `init` computes, and no other step
reuses the forcing, so `init` writes it, including the time-varying
land-ice forcing.

### D6: The freezing point uses MPAS-Ocean's default coefficients

Date last modified: 2026/09/29

Contributors: Xylar Asay-Davis, Claude

The cavity freezing point uses MPAS-Ocean's default coefficients, as
Compass does, both in the model and for thin-film initial temperatures.
They differ from the COM liquidus in Table 4 of the protocol.

The shared helper selects the formulation by ocean model. Omega uses
TEOS-10 for its freezing temperature, and the helper raises an error for
Omega until it supports ice-shelf cavities.

### D7: The forward run is short

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The default forward run is one hour, and `run_duration` can be raised
by config. Long runs and standard output are
[Planned Extensions](#planned-extensions).

### D8: Wetting and drying tasks stay; Ocean3–4 tasks are removed

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The `inception`, `wetting` and `drying` tasks and the `TopoScale` step
stay, and the three tasks gain an `init` step. Running them is
follow-up work.

The `ocean3` and `ocean4` tasks and their topography steps are
removed. Ocean3–4 will be E3SM runs driven by MALI in data mode, which
need a different Polaris setup
([Planned Extensions](#planned-extensions)). A standalone MPAS-Ocean
version would use a different forcing path and would not serve as a
reference for the coupled runs. `TopoRemap` keeps its support for the
Ocean3 and Ocean4 geometry, which that setup needs to find the cells
that ever hold ocean.

### D9: Omega is not supported

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The tasks are documented as MPAS-Ocean only and are not added to Omega
suites. Using the `OceanIOStep` writers keeps the files in the form
Omega will need once it supports cavities.

### D10: Profiles follow the protocol and Compass

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

The #151 draft gave Ocean2, `wetting` and `drying` a COLD initial
condition, and `wetting` and `drying` COLD restoring. The protocol gives
Ocean2 a WARM initial condition. The scaled tasks use the Ocean0
profiles, as Compass's wetting and drying tests do.

### D11: All model runs use wetting and drying

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Wetting and drying is part of the reason for implementing ISOMIP+ in
Polaris rather than porting Compass's tasks. It lets the pressure come
from the weight of the ice even where cells are partly grounded
([D4](#decisions)), and the scaled tasks need it for their thin film.
MPAS-Ocean supports wetting and drying only with RK4, so the runs use
Compass's thin-film settings and a time step of 6 s per km.

*Effect:* Polaris's `ocean0` corresponds to Compass's
`thin_film_Ocean0` rather than its `Ocean0`. Compass's standard
Ocean0–2 use split-explicit time stepping without wetting and drying,
so they differ from the Polaris tasks in their time stepping and their
thin-layer treatment.

### D12: The top drag coefficient follows COM

Date last modified: 2026/09/28

Contributors: Xylar Asay-Davis, Claude

Compass turned on implicit top drag but left its coefficient at the
MPAS-Ocean default of $10^{-3}$. The Polaris tasks set it to the COM
value of $2.5\times10^{-3}$, and Compass's ISOMIP+ namelist is updated
to match.

### D13: Pressure is prescribed; SSH is adjusted

Date last modified: 2026/10/07

Contributors: Xylar Asay-Davis, Claude

Every task keeps the land-ice pressure from the ice thickness
([D4](#decisions)), and Polaris never changes it. The initial SSH is
the draft of floating ice at that pressure, with
$\rho_{sw} = 1028$ kg m⁻³, limited by the bed. SSH adjustment moves
SSH, not the pressure. The only change to the pressure is the cap in
grounded cells that MPAS-Ocean applies with
[E3SM-Ocean-Discussion#119](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/119).

This replaces the first version of this design, in which SSH
adjustment changed the pressure, as Compass does. `ice_shelf_2d` and
the framework default still adjust the pressure.

```{admonition} Rationale
The goal is MALI coupling, in which the ice sheet supplies the pressure
and the ocean's SSH responds. There, SSH is not known in advance and
the pressure cannot be adjusted.
```

*Effect:*

- In fully floating and open-ocean cells, the initial SSH is within
  0.5 m of the remapped draft (1.4 m in 1 km Ocean2), since the input
  geometry floats at 1028 kg m⁻³. The largest SSH change in the first
  adjustment iteration is 0.3–1.0 m, compared with 5–22 m when the
  pressure was adjusted.
- In partly grounded cells along the grounding line (57–327 per task),
  the initial SSH is deeper than the remapped draft, by up to 5–20 m
  depending on the task. Pressure adjustment used to absorb this.
- In a few cells, the pressure exceeds floatation even at the bed, by
  up to 5.2 m of ice: 9–12 cells in 1 km Ocean0 and Ocean1, 2–3 in
  1 km Ocean2, and 1 in spherical 2 and 4 km Ocean0 and Ocean1. These
  cells start at the bed with the minimum column. Without #119's cap,
  SSH adjustment does not settle next to them in 1 km Ocean2. On the
  planar mesh, the largest SSH change grows to 5.3 m. With the cap, it
  ends at 0.1 m.
- Compass adjusts the pressure, so the two differ in how the pressure
  and SSH are balanced, not only in the initial pressure.
