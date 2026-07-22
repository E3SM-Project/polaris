# EOS and Vertical-Coordinate Variants of the Overflow Tasks

date: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

## Summary

The overflow task family currently supports only the linear equation of
state (EOS) with the z-star vertical coordinate. Instabilities have been
observed in realistic-global tests, which use the p-star vertical
coordinate together with a nonlinear EOS (TEOS-10 in Omega). This work
adds variants of all overflow tasks that mirror that configuration in a
small, idealized, fast-running setting, so that the two new ingredients
(nonlinear EOS and p-star coordinate) can be varied independently:

|               | z-star init                         | p-star init              |
|---------------|-------------------------------------|--------------------------|
| linear EOS    | existing tasks (baselines preserved)| coordinate discriminator |
| nonlinear EOS | not included                        | mirrors realistic-global |

The nonlinear EOS is TEOS-10 for Omega and Jackett-McDougall (`jm`) for
MPAS-Ocean.

The result is three task trees under `ocean/planar/overflow/`, each with
its own shared config file and its own shared `init` step. Paths have
two levels below `overflow` — the EOS type, then the vertical
coordinate — for symmetry and so more combinations can be added later:

```
ocean/planar/overflow/
├── linear/
│   ├── zstar/      # existing tasks: z-star + linear EOS (answers unchanged)
│   │   ├── init                                  (shared step)
│   │   ├── smoke_test_horiz_adv_order_{2,3,4}
│   │   ├── smoke_test_horiz_adv_order_{2,3,4}_del4
│   │   └── rpe
│   └── pstar/      # p-star init + linear EOS
│       └── (same tasks)
└── nonlinear/
    └── pstar/      # p-star init + TEOS-10 (Omega) / jm (MPAS-Ocean)
        └── (same tasks)
```

This is 21 tasks total (7 per tree). The `linear/zstar` tree is the
current set of tasks with only the path changed; its answers must not
change. Since the goal is debugging, the full matrix makes it possible
to bisect where problems enter. The smoke tests are the primary
debugging vehicle. The RPE tasks are included in the new trees for
completeness but are too expensive to run routinely; if supporting them
under p-star or the nonlinear EOS proves difficult, they can be
deferred without blocking the rest of this work.

Success means: the `linear/zstar` tree is bit-for-bit with the current
tasks, the two new trees set up and run their smoke tests with both
models, and the shared framework pieces (a TEOS-10 EOS config and a
p-star state-conversion module) are reusable by the realistic-global
initialization work.

## Requirements

### Requirement: A shared mechanism for selecting a nonlinear EOS

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Tasks must be able to select a nonlinear EOS via a shared config file,
in the same way `polaris.ocean.eos` `linear.cfg` and `constant.cfg`
select the linear and constant EOS today. The forward step must
translate this selection into valid model config options for both Omega
(TEOS-10) and MPAS-Ocean (Jackett-McDougall, the closest available
nonlinear EOS), without requiring the linear-EOS options to be defined.

### Requirement: Overflow initial conditions on the p-star coordinate

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

The overflow initial condition (tanh shelf bathymetry, a block of cold
water on the shelf, constant salinity, quiescent velocity, zero surface
pressure) must be producible on the p-star vertical coordinate, with
output files compatible with the existing overflow `Forward`, `Viz`,
and RPE `Analysis` steps (same filenames and required variables).

### Requirement: Model-specific tracer and state conversions are shared framework code

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

The conversions from a converged p-star state to model input files —
layer thickness from geometric interfaces, quiescent velocity, density
from specific volume, and conversion of conservative temperature /
absolute salinity to MPAS-Ocean's potential temperature / practical
salinity — must live in a shared, dependency-light framework module so
that both the overflow p-star init and the realistic-global
initialization (on the `add-realistic-ocean-init` branch) can use them.

### Requirement: Existing overflow answers are preserved

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

The existing z-star + linear-EOS tasks move to
`ocean/planar/overflow/linear/zstar/` with no answer changes. Test
suites that reference the old paths must be updated.

## Algorithm Design

### Algorithm Design: A shared mechanism for selecting a nonlinear EOS

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

No new algorithms. Omega's `Eos.cpp` accepts `teos10`, `teos-10`, and
`TEOS-10` for `EosType`, so the Polaris `eos_type = teos-10` value
passes through unchanged. MPAS-Ocean has no TEOS-10 option; its
Jackett-McDougall EOS (`config_eos_type = jm`) is used as a documented
approximation. Polaris-side (Python) density calculations use TEOS-10
via the `gsw` package for both models; the initial-condition density is
diagnostic only (neither model reads it), so the TEOS-10-vs-`jm`
mismatch for MPAS-Ocean is acceptable.

### Algorithm Design: Overflow initial conditions on the p-star coordinate

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

The p-star initialization uses the fixed-point iteration from the
[p-star init design](pstar_init.md) (`PStarInitStep.run_pstar_init()`)
with zero surface pressure. The overflow tracer profile (cold block on
the shelf, constant salinity) is evaluated at the current p-star layer
midpoints each outer iteration and interpreted as conservative
temperature (CT) and absolute salinity (SA).

Because pseudo-depth is not geometric depth
($dz_{geom} = \nu \, \rho_{sw} \, d\tilde{z}$, with specific volume
$\nu$ and $\rho_{sw} = 1026$ kg m$^{-3}$), the pseudo grid must reach
deeper than the pressure at the deepest geometric bathymetry or the
domain would be artificially truncated. The pseudo-depth needed for the
2000 m geometric bottom is roughly $2000 \, \bar{\rho} / \rho_{sw}$:
~1950 m for the linear EOS (mean density ≈ 998 kg m$^{-3}$ with the
shared `linear.cfg` values) and ~2015 m for TEOS-10 (in-situ density up
to ~1037 kg m$^{-3}$ at depth). The pseudo grid is therefore 2400 m
deep (~19% buffer over the worst case) with 72 uniform levels,
preserving the ~33.3 m layer spacing of the 60-level, 2000 m z-star
grid while making the number of levels a multiple of 16, which is
preferred for Omega performance. This mirrors the buffer used in
`horiz_press_grad` (576 m pseudo bottom for a 500 m geometric bottom).

### Algorithm Design: Model-specific tracer and state conversions are shared framework code

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Omega receives CT and SA directly. For MPAS-Ocean, CT is converted to
potential temperature via `gsw.pt_from_CT` and SA to practical salinity
via `gsw.SP_from_SA`, with pressure from the p-star product. The
`SP_from_SA` conversion needs a nominal longitude/latitude on a planar
mesh; this defaults to (0°, 0°) and is exposed as config options.

Note that the `add-realistic-ocean-init` branch currently uses
`gsw.t_from_CT` (in-situ temperature); MPAS-Ocean expects *potential*
temperature, so the shared helper uses `pt_from_CT` and that branch
picks up the fix when it adopts this module.

## Implementation

### Implementation: A shared mechanism for selecting a nonlinear EOS

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

A new shared config file `polaris/ocean/eos/teos10.cfg` contains only

```ini
[ocean]
eos_type = teos-10
```

(no linear parameters). `OceanModelStep.update_namelist_eos()`, which
currently reads the `eos_linear_*` options unconditionally, is
restructured to branch on `eos_type`:

- `linear` / `constant`: current behavior (read `eos_linear_*`, map
  `constant` → `linear` for MPAS-Ocean, reject nonzero `Tref`/`Sref`
  for Omega).
- `teos-10`: for MPAS-Ocean, set `config_eos_type = jm` and do not
  touch `config_eos_linear_*`; for Omega, pass `teos-10` through
  unchanged. The `eos_linear_*` options are not read at all.

### Implementation: Overflow initial conditions on the p-star coordinate

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

A new `PStarInit(PStarInitStep)` step in
`polaris/tasks/ocean/overflow/pstar_init.py`:

- builds the same planar hex mesh as the existing `Init` step, culls
  it, and adds Coriolis via a mesh helper factored out of `Init.run()`;
  writes `base_mesh.nc`, `culled_mesh.nc`, and `culled_graph.info`;
- computes `geom_z_bot` from the existing tanh shelf profile;
- uses zero surface pressure;
- implements `init_tracers()` as the existing
  cold-block-on-the-shelf profile evaluated at the current p-star layer
  midpoints, interpreted as CT/SA;
- after `run_pstar_init()` converges, uses the shared state-conversion
  helpers to add layer thickness, quiescent velocity, and density,
  converts tracers for MPAS-Ocean, and writes `vert_coord.nc` and
  `init.nc` with the same filenames as the existing `Init` step so
  `Forward`, `Viz`, and `Analysis` need no retargeting.

`add_overflow_tasks()` loops over the three variants:

| subdir                            | EOS cfg      | init step class | coord  |
|-----------------------------------|--------------|-----------------|--------|
| `planar/overflow/linear/zstar`    | `linear.cfg` | `Init`          | z-star |
| `planar/overflow/linear/pstar`    | `linear.cfg` | `PStarInit`     | p-star |
| `planar/overflow/nonlinear/pstar` | `teos10.cfg` | `PStarInit`     | p-star |

Each variant gets its own `PolarisConfigParser` and its own shared init
step, and the same set of smoke-test and RPE tasks as today. A new
`overflow_pstar.cfg` adds the p-star `[vertical_grid]` overrides
(including the 2400 m / 72-level pseudo grid) for the two p-star trees.
The p-star iteration uses the shared `ocean.cfg` defaults
(`pseudothickness_iter_count = 6`,
`water_col_adjust_frac_change_threshold = 1.0e-12`).

`forward.py` / `forward.yaml` are expected to be unchanged:
`update_eos=True` already routes EOS settings through
`update_namelist_eos()`, and `horiz_press_grad` demonstrates that Omega
needs no extra `VertCoord` settings in the forward yaml for p-star (the
coordinate comes from `vert_coord.nc`). MPAS-Ocean runs its usual
coordinate initialized from the converged geometric thicknesses.

In passing, two pieces of cleanup in `overflow.cfg`:

- The `[overflow]` options `eos_linear_beta` and `eos_linear_Sref` are
  dead leftovers from the compass port (the shared `linear.cfg`
  `[ocean]` section is the source of truth) and are deleted.
- `rpe/analysis.py` reads `min_temp` and `max_temp` from
  `[overflow_rpe]`, which never defines them, so the RPE analysis step
  would fail at runtime today. They are added following the
  `baroclinic_channel` precedent, tracking the initial-condition
  temperatures.

### Implementation: Model-specific tracer and state conversions are shared framework code

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

A new dependency-light module `polaris/ocean/vertical/pstar_state.py`
with helpers factored out of `InitialStateStep` on the
`add-realistic-ocean-init` branch:

- `layer_thickness_from_geom_interfaces(ds)` — `restingThickness` and
  `layerThickness` from converged `GeomZInterface`, masked by
  `cellMask`;
- `add_quiescent_normal_velocity(ds, ds_mesh)` — zero
  `normalVelocity`;
- `add_density_from_specvol(ds)` — `Density = 1 / SpecVol` with
  attributes;
- `convert_tracers_to_mpas_ocean(ds, lon, lat)` — CT → potential
  temperature via `gsw.pt_from_CT` and SA → practical salinity via
  `gsw.SP_from_SA`, with pressure from the p-star product.

When `add-realistic-ocean-init` merges, its `InitialStateStep` is
refactored to call these (a follow-up on that branch).

### Implementation: Existing overflow answers are preserved

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

The existing tasks keep their step and task classes; only the task
directory changes from `planar/overflow` to
`planar/overflow/linear/zstar`. The overflow paths in
`polaris/suites/ocean/omega_nightly.txt`, `omega_pr.txt`, and
`mpaso_pr.txt` are updated accordingly; no new suite entries are added
for now.

## Testing

### Testing and Validation: A shared mechanism for selecting a nonlinear EOS

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Unit tests cover `update_namelist_eos()` for all `eos_type` × model
combinations. Manual testing: set up and run the smoke tests from the
`nonlinear/pstar` tree with both models (where builds are available).

### Testing and Validation: Overflow initial conditions on the p-star coordinate

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Manual testing: set up and run the smoke tests from the `linear/pstar`
and `nonlinear/pstar` trees with both models, checking that the
converged bathymetry matches the tanh shelf profile and the runs are
stable. The RPE tasks are validated opportunistically; note that
sorting in-situ density from a nonlinear EOS gives only an approximate
RPE measure (documented in the user's guide).

### Testing and Validation: Model-specific tracer and state conversions are shared framework code

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Unit tests for each helper in `pstar_state.py`, including the
CT/SA → potential-temperature/practical-salinity round trip against
direct `gsw` calls.

### Testing and Validation: Existing overflow answers are preserved

Date last modified: 2026/07/22

Contributors: Xylar Asay-Davis, Claude

Manual testing: compare the `linear/zstar` smoke tests against a
baseline from `main` to confirm answers are unchanged (only the path
moved). The updated suites are exercised by the usual nightly and PR
testing.
