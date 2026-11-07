# Global Ocean Ice-Shelf Cavities

date: 2026/11/07

Contributors: Xylar Asay-Davis, Claude

## Summary

The `realistic_global` initial condition and dynamic adjustment
([global_ocean_init](global_ocean_init.md),
[global_ocean_dynamic_adjustment](global_ocean_dynamic_adjustment.md)) end at
the Antarctic calving front.  This design adds an ocean under Antarctic land
ice, for MPAS-Ocean, as a step toward global meshes for coupled MALI and
MPAS-Ocean runs.

The treatment under the ice follows ISOMIP+ and MISOMIP1
([isomip_plus](isomip_plus.md),
[split_explicit_wetting_drying](split_explicit_wetting_drying.md)) rather
than Compass:

- the land-ice pressure comes from the ice thickness and never changes;
- the sea-surface height (SSH) follows from that pressure;
- columns too thin to hold the ocean become a thin film handled by wetting
  and drying.

Two domains are supported.  Under the `grounding_line` convention, the ocean
extends under floating ice.  Under `bedrock_zero`, it extends under all
Antarctic ice whose bed is below sea level and is connected to the ocean,
with a thin film under grounded ice.  Both share one initialization and
differ only in the domain.

Success is a dynamic adjustment on the qu240km, qu30km, so12to30km and
rrs6to18km meshes, under both conventions, that runs to the end of its
`simulation` stage.  It must stay within the existing stage checks, after an
SSH adjustment whose largest change falls with each iteration.  A by-hand
extension of `simulation` with melting must also run.

Omega has no ice-shelf cavities, so this design is for MPAS-Ocean only.  It
needs MPAS-Ocean from FAnSSIE with split-explicit wetting and drying.

## Open Questions

### Layers in thin columns

MPAS-Ocean's wetting and drying requires every active layer to stay at
least `config_drying_min_cell_height` (5 cm) thick.  Its z-star coordinate
squashes a column in proportion to `restingThickness`.  On the strongly
non-uniform `realistic_global` grids, a thin column's top layers then fall
far below the minimum.  For example, a 3.5 m film under 70 layers of the
`80layerE3SMv1` grid has a top layer of a few millimetres.  ISOMIP+ avoids
this with a nearly uniform grid.

Options:

1. In columns where proportional layers would be thinner than the minimum,
   make the layers uniform: equal resting and initial thicknesses.  z-star
   then keeps them uniform.
2. Raise the film until its thinnest proportional layer reaches the minimum.
   On `80layerE3SMv1` that is tens of metres under thick ice.
3. Use fewer active layers (a smaller `maxLevelCell`) in thin columns.

Recommended: option 1.  The choice affects
[Thin columns are a wet film](#requirement-thin-columns-are-a-wet-film) and
its implementation.

### Pressure gradient at film edges

`realistic_global` runs MPAS-Ocean with `Jacobian_from_TS`, as E3SM does.
ISOMIP+ uses `pressure_and_zmid`, and `Jacobian_from_TS` is known to
misbehave next to thin films.  The first runs keep `Jacobian_from_TS`; a
switch is one config option if the film edges need it.

### Thin films without a cull

Treating every too-thin column as film, under both conventions, is the
starting assumption.  It differs from the ISOMIP+ tasks without a film,
which remove such columns.  See [Decisions](#decisions).

## Requirements

### Requirement: Cavities are enabled by the domain convention alone

The `[spherical_mesh] antarctic_boundary_convention` config option selects
the domain.  `calving_front`, the default, gives today's ocean.
`grounding_line` and `bedrock_zero` give an ocean under land ice.  No other
option is needed.

### Requirement: The ocean and sea ice share one domain

### Requirement: The land-ice load is fixed by the ice thickness

The land-ice pressure is the weight of the ice.  Once set, it does not
change during initialization, SSH adjustment or the forward runs.

### Requirement: The sea surface follows the land-ice load

SSH is the draft of ice floating with the land-ice pressure, wherever that
leaves a column thick enough to hold the ocean.

### Requirement: Thin columns are a wet film

A column that the land-ice load would leave thinner than the
wetting-and-drying minimum in each layer is kept as a film at that minimum.
The film starts fresh, at the freezing point.  Every layer of every column
holds at least the minimum thickness.

### Requirement: The SSH is adjusted to the land-ice load before the dynamic adjustment

### Requirement: There is no surface forcing under land ice

### Requirement: Forward runs carry the land-ice load, with melting optional

The dynamic adjustment applies the land-ice pressure without land-ice
fluxes.  A run continuing from it may turn melting on.

### Requirement: Four base meshes match the unified meshes' ocean resolutions

qu240km, qu30km, so12to30km and rrs6to18km share their ocean settings and
dynamic-adjustment schedules with u-oi240-lr240, u-oi30-lr10,
u-oi-so12to30-lr10 and u-oi6to18-lr12p5.

### Requirement: Unsupported combinations fail at setup

Requesting cavities with Omega is an error at setup.

## Algorithm Design

### Algorithm Design: Cavities are enabled by the domain convention alone

Cavities are on when the convention is not `calving_front`.  The e3sm/init
cull already builds the ocean domain from the convention, so the ocean
steps need only read it.

### Algorithm Design: The ocean and sea ice share one domain

The domain is the cull step's ocean, which already includes land ice under
`grounding_line` and `bedrock_zero`.  Nothing is culled again downstream.

### Algorithm Design: The land-ice load is fixed by the ice thickness

$$
p_{li} = \rho_i g H_i
$$

with $H_i$ the remapped ice thickness, applied in every cell of the land-ice
mask, grounded or floating.

### Algorithm Design: The sea surface follows the land-ice load

$$
\eta_0 = -\frac{p_{li}}{\rho_{sw} g}
$$

the draft of ice floating with that load, from the same reference density
ISOMIP+ uses.  The p-star initialization
([pstar_init](pstar_init.md)) takes $p_{li}$ as its surface pressure and
$\eta$ as its prescribed SSH, and balances each column with the TEOS-10
equation of state.

### Algorithm Design: Thin columns are a wet film

With $N$ active layers and minimum layer thickness $h_{min}$:

$$
\eta = \max\left(\eta_0, z_b + N h_{min}\right)
$$

Cells where $\eta > \eta_0$ form the film and are marked with
`thinFilmMask`.  Their load exceeds what the column supports, which
MPAS-Ocean's grounded-pressure cap handles.  Film water starts with zero
salinity at the freezing point.  How the film's layers are laid out is open:
see [Layers in thin columns](#layers-in-thin-columns).

### Algorithm Design: The SSH is adjusted to the land-ice load before the dynamic adjustment

The SSH adjustment iterates the following, as in ISOMIP+:

1. Run MPAS-Ocean briefly with the land-ice pressure and no fluxes.
2. Take its final SSH, holding the pressure fixed.
3. Rebuild the initial condition with that SSH.

### Algorithm Design: There is no surface forcing under land ice

Wind stress is zero wherever `landIceMask` is set.

### Algorithm Design: Forward runs carry the land-ice load, with melting optional

Land-ice fluxes are `off` with `config_use_land_ice_pressure`, in FAnSSIE's
form, during the SSH and dynamic adjustments.  Melting is `active`.
Wetting and drying is on, with the thin-film options ISOMIP+ uses.  It
exists in MPAS-Ocean's `split_explicit` and `RK4` integrators but not in
`split_explicit_ab2`, so runs with cavities use `split_explicit`.

### Algorithm Design: Four base meshes match the unified meshes' ocean resolutions

Each base mesh names its unified twin.  It takes the twin's per-mesh
options and schedule, then any options of its own.

## Implementation

### Implementation: Cavities are enabled by the domain convention alone

A helper reads `[spherical_mesh] antarctic_boundary_convention` from a
`realistic_global` config and reports whether cavities are on.  The init and
dynamic-adjustment configs get the convention from the base-mesh config, as
the cull config does.

### Implementation: The ocean and sea ice share one domain

`CullMaskStep` runs `bedrock_zero` through its masks and consistency checks.
The parts that assume all land ice in the ocean floats are fixed.
`CullTopoStep` carries the land-ice mask onto the culled ocean mesh.

### Implementation: The land-ice load is fixed by the ice thickness

`RealisticPStarInitStep` uses
`polaris.ocean.ice_shelf.compute_land_ice_pressure_from_thickness()`.  The
initial state writes `landIcePressure`, `landIceDraft`, `landIceMask`,
`landIceFraction`, `landIceFloatingMask` and `landIceFloatingFraction`.  The
floating fields come from the grounded fraction.

MPAS-Ocean's z-star requires `restingThickness` to sum to `bottomDepth`,
the thickness at zero SSH.  The initial state therefore writes

$$
h_{rest,k} = h_k \frac{H}{H + \eta}
$$

where $H$ is `bottomDepth`.  Columns with $\eta = 0$ are unchanged.

### Implementation: The sea surface follows the land-ice load

`RealisticPStarInitStep.run()` passes the land-ice pressure and $\eta$ to
`run_pstar_init()`.  The depth clamp and the hole filling work on the loaded
column.

### Implementation: Thin columns are a wet film

The film layer thickness is a `[realistic_global_init]
thin_film_layer_thickness` option, named as in ISOMIP+, which must match
`config_drying_min_cell_height`.  The freezing point comes from
`polaris.ocean.ice_shelf.compute_freezing_temperature()`.

### Implementation: The SSH is adjusted to the land-ice load before the dynamic adjustment

Shared steps after `initial_state` alternate an SSH forward, with the shared
wetting-and-drying options, and a step that reruns the p-star initialization
at the new SSH.  The dynamic adjustment's first stage starts from the last
one.  `[ssh_adjustment]` sets the iteration count and run length.

### Implementation: There is no surface forcing under land ice

`ForcingStep` reads the land-ice mask on the culled mesh and zeroes the wind
stress there.

### Implementation: Forward runs carry the land-ice load, with melting optional

ISOMIP+'s wetting-and-drying options move to `polaris.ocean.ice_shelf`,
with `add_wetting_drying_yaml_files()` to add them, used by both ISOMIP+
and `realistic_global`.  With cavities on, the `realistic_global` forward
and SSH-adjustment runs add those options, implicit top drag and a
per-stage land-ice flux mode.
A new `[realistic_global_forward] mpaso_cavity_time_integrator` option,
`split_explicit` by default, replaces `mpaso_time_integrator`.

### Implementation: Four base meshes match the unified meshes' ocean resolutions

A table in `polaris.tasks.ocean.realistic_global.mesh_configs` maps each base
mesh to its unified twin.  The config and schedule loaders add the twin's
files, then the base mesh's own config if it has one.  The copies of the
u-oi240-lr240 options in qu240km.cfg and icos240km.cfg, and the test that
keeps them in sync, are removed.

### Implementation: Unsupported combinations fail at setup

The `realistic_global` init and dynamic-adjustment tasks raise an error in
`configure()` when cavities are on and `[ocean] model` is `omega`.

## Testing

### Testing and Validation: Cavities are enabled by the domain convention alone

Unit tests of the helper for each convention.  A qu240km dynamic adjustment
without cavities matches a `main` baseline.

### Testing and Validation: The ocean and sea ice share one domain

Unit tests of the cull masks under `bedrock_zero` on synthetic topography.
The qu240km cull under both conventions passes its consistency checks.

### Testing and Validation: The land-ice load is fixed by the ice thickness

Unit tests of the land-ice fields and resting thicknesses from synthetic
columns.  `landIcePressure` is unchanged from the initial state to the end
of the dynamic adjustment.

### Testing and Validation: The sea surface follows the land-ice load

Unit tests of the prescribed SSH.  In the qu240km initial state, SSH matches
the draft outside the film.

### Testing and Validation: Thin columns are a wet film

Unit tests of the film minimum and film tracers.  No layer is thinner than
the minimum in the qu240km initial state under `bedrock_zero`.

### Testing and Validation: The SSH is adjusted to the land-ice load before the dynamic adjustment

The largest SSH change falls with each iteration on qu240km.

### Testing and Validation: There is no surface forcing under land ice

A unit test of the masked wind stress.

### Testing and Validation: Forward runs carry the land-ice load, with melting optional

Dynamic adjustments on the four meshes run to the end of `simulation`
within their stage checks.  A by-hand extension with `active` melting runs
on so12to30km.

### Testing and Validation: Four base meshes match the unified meshes' ocean resolutions

Unit tests that a base mesh's config holds its twin's options and its own,
with its own taking precedence.

### Testing and Validation: Unsupported combinations fail at setup

A unit test of the Omega error.

## Decisions

- **Thin columns are kept as film, not removed (starting assumption).**  The
  ISOMIP+ tasks without a film remove too-thin columns.  Keeping them makes
  `grounding_line` and `bedrock_zero` differ only in the domain.  Removal
  would also need the layer count in the cull step, before the vertical grid
  exists.
- **The bed is not lowered and the load is not reduced.**  Compass's
  global_ocean init lowered the bed under thin columns.  Reducing the load
  where SSH is raised was also considered.  Both make the ocean disagree
  with the ice geometry that MALI will supply when coupled.
- **MPAS-Ocean comes from FAnSSIE, not E3SM-Project.**  FAnSSIE renames the
  land-ice flux modes and adds the grounded-pressure cap and wetting and
  drying.  ISOMIP+, MISOMIP and `ice_shelf_2d` already use its form.
- **Split-explicit, not `split_explicit_ab2`.**  Only `split_explicit` and
  `RK4` have wetting and drying.
