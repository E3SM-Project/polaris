# MISOMIP Experiments in E3SM

Creation date: 2026/10/16

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

This document plans running the ISOMIP+ ocean experiments (Ocean0–4) and
the MISOMIP1 coupled experiments (IceOcean1r and IceOcean1ra) in E3SM.
MPAS-Ocean and MALI exchange melt and geometry through the coupler.
Polaris builds the meshes and every input the runs need, gains a landice
component to spin up MISMIP+, and analyzes the output. E3SM runs the
simulations. The E3SM code comes from one shared development branch of
FAnSSIE, the Framework for Antarctic System Science in E3SM, which Polaris
pins as a submodule. This document calls the branch FAnSSIE. Section, table
and equation numbers refer to the protocol
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)).

The experiments are a step toward realistic coupling of MPAS-Ocean and
MALI in Antarctica. They rehearse, on a problem whose behavior is well
understood, what realistic runs will need. The results will not be
submitted to MISOMIP, so the protocol is followed where it helps
comparison with published results, not for its own sake.

The work divides into twelve packages, each with its own design document or
E3SM pull request ([work packages](#implementation-work-packages)). This
document records what was established before designing, the requirements
and principles the packages share, and the order in which they land.

The configuration serves two purposes:

- **A test of geometry coupling.**
  [E3SM#8887](https://github.com/E3SM-Project/E3SM/pull/8887) couples
  ice-shelf melt between MPAS-Ocean and MALI and can import MALI's geometry
  into the ocean. Import is off by default because no ocean initial
  condition matches a MALI geometry. Here, the ocean's initial condition is
  built from MALI's geometry through the coupler's own map, so import can
  be on even when MALI is static. The two models' meshes are independent,
  so partly grounded ocean cells appear at the grounding line, as they will
  in realistic runs. A coarse version is cheap enough to serve as a quick
  test of coupling changes.
- **A test of the thin film in coupled runs.** Every experiment keeps a
  thin film of water under grounded ice and uses wetting and drying,
  including Ocean0–2, whose geometry does not change.

| Experiment  | MALI       | Initial T, S | Restoring | Years | Ice geometry      |
|-------------|------------|--------------|-----------|-------|-------------------|
| Ocean0      | static     | WARM         | WARM      | 1     | Ocean1 input      |
| Ocean1      | static     | COLD         | WARM      | 20    | Ocean1 input      |
| Ocean2      | static     | WARM         | COLD      | 20    | Ocean2 input      |
| Ocean3      | data       | WARM         | WARM      | 100   | Ocean3 input      |
| Ocean4      | data       | COLD         | COLD      | 100   | Ocean4 input      |
| IceOcean1r  | prognostic | COLD         | WARM      | 100   | MALI steady state |
| IceOcean1ra | prognostic | from 1r      | COLD      | 100   | from IceOcean1r   |

The input geometry comes from BISICLES's MISMIP+ runs
([Cornford and Asay-Davis 2016](https://doi.org/10.5880/PIK.2016.002)).
The Ocean3 and Ocean4 inputs hold 101 yearly snapshots.

Success means:

- Ocean0–4, IceOcean1r and IceOcean1ra complete in E3SM at 2 km with
  geometry import on;
- at the first coupling step, the geometry the ocean imports equals its
  initial condition to round-off;
- the coupler budgets close for the exchanged melt;
- Polaris diagnoses melt, grounding-line position, volume above flotation
  and conservation from E3SM's history files;
- a 4 km Ocean0 serves as a quick test of changes on FAnSSIE.

## What we established

These findings are from 2026-10-16. Items marked *(inferred)* come from
reading code, not from runs.

### Coupling in E3SM#8887

- MPAS-Ocean sends MALI its net melt per unit floating area and its
  ice–ocean interface temperature. MALI sends its ice pressure, its
  floating, grounded and below-sea-level masks, and its basal conductive
  flux. The coupling is MCT only; the MOAB driver aborts if it is
  requested.
- MALI's pressure is $\rho_i g H$ wherever the bed is at or below sea
  level, grounded ice included. MPAS-Ocean divides each imported field by
  the remapped below-sea-level mask.
- Geometry import is off by default. With SOwISC12to30E3r4 and ais4to20 it
  produced NaNs within one coupling interval. In about 50 partly grounded
  cells, MALI's pressure put the ice base below the seafloor or left less
  than the initial condition's 10 m water column.
- With no atmosphere, the coupler keeps the ocean's model areas, while
  glc's areas come from the glc-to-ocean map. Conservation then needs the
  map's ocean areas to equal the ocean's model areas.
- E3SM's gravity is 9.80616 m s⁻². Polaris's constants use 9.80665.

### Idealized cases in E3SM

- E3SM has no idealized MPAS-Ocean or MALI configuration. MALI-only
  compsets with stub partners exist and are tested.
- Both drivers abort when a prognostic ocean has no atmosphere. With that
  check removed, the coupler would still compute atmosphere–ocean fluxes
  from a zero atmosphere *(inferred: non-finite)*.
- A user grid file and case variables can supply new grids, maps and
  compsets without editing E3SM's XML. Neither MPAS driver reads a domain
  file.
- The `buildnml` scripts of MPAS-Ocean and MALI pick initial conditions
  from hard-coded grid lists, so an unknown grid fails.
- On a planar mesh, MPAS-Ocean reads `sphere_radius` only for its coupler
  areas and for features these runs leave off: GM, Redi, self-attraction
  and loading, scaled freshwater fluxes and particle tracking. Planar meshes
  have a zero `sphere_radius`, so the coupler areas are not finite unless
  it is set.
- E3SM's MPAS-Ocean namelist omits the `wetting_drying` and
  `tidal_forcing` groups, and its run loop never builds the tidal forcing.
  E3SM never writes the stream that holds the interior-restoring fields.
- MALI's E3SM defaults differ from the protocol. The ice density is
  910 kg m⁻³, and ice removed at the calving front reaches the ocean as
  runoff.

### A moving grounding line

- MALI's data mode reads only thickness. It checks for a new record each
  month and takes the latest one, without interpolation. The one existing
  data-mode file, for ais8to30, holds no thickness, so no E3SM test has run
  a changing thickness. Static and data modes send no conductive flux.
- With wetting and drying, MPAS-Ocean resets its floating mask and
  fraction at every step: 0 where the draft is below the bed, 1 elsewhere.
  Nothing checks for ice, so open-ocean cells become floating and receive
  land-ice fluxes. In Polaris's 2 km Ocean0, after one month with
  MPAS-Ocean from Polaris's E3SM submodule, all 4,336 open-ocean cells were
  floating, and their freshwater flux was 5 % of that under the ice. The
  code is on E3SM master
  ([E3SM#7301](https://github.com/E3SM-Project/E3SM/pull/7301)).
- The same reset overwrites the floating fraction imported from MALI with
  0 or 1. The melt MPAS-Ocean sends MALI is normalized by MALI's own
  remapped fraction, which #8887 keeps separately. The two differ in partly
  floating cells.
- Without the grounded-pressure cap of
  [E3SM-Ocean-Discussion#119](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/119),
  imported pressure under grounded ice puts the draft below the bed.
  Fluxes must also be zeroed where the ice is grounded
  ([E3SM-Ocean-Discussion#141](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/141)).
  #8887 has neither.

### Wetting and drying

- E3SM master supports wetting and drying with RK4 only, apart from local
  time stepping, which E3SM does not use.
- Carolyn Begeman's split-explicit work is the first 43 commits of
  [cbegeman/E3SM:alt-wetting-drying-se](https://github.com/cbegeman/E3SM/tree/alt-wetting-drying-se),
  ending at `abc3b5daee`. The same series is in
  `ocn-add-wetting-drying-se-and-fix-vlr`, bundled with other work. It is
  unreviewed research code, and no pull request exists. Its barotropic
  factor has no land-ice terms. It also replaces master's RK4 wetting
  factor, dropping its ssh-gradient and subgrid branches, and #119 edits
  the first of these. Merging it onto
  [xylar/E3SM:ocn/thin-film-wetting-drying](https://github.com/xylar/E3SM/tree/ocn/thin-film-wetting-drying)
  therefore takes a design decision, not only conflict resolution.
- The RK4 thin-film runs of Polaris's `inception` task took, on Chrysalis
  on 2026-10-07:

  | Mesh        | Cells  | MPI tasks | Time per step |
  |-------------|--------|-----------|---------------|
  | 4 km planar | 2,916  | 8         | 56 ms         |
  | 2 km planar | 11,590 | 36        | 64 ms         |

  At 2 km and 12 s per step on 36 tasks, a year takes about 2 days and 100
  years about 195 days. RK4 suffices for Ocean0 and short tests only.

### Polaris and Compass

- Polaris's standalone ISOMIP+ tasks run Ocean0–2 and three thin-film
  tasks with MPAS-Ocean
  ([#826](https://github.com/E3SM-Project/polaris/pull/826),
  [#844](https://github.com/E3SM-Project/polaris/pull/844)). They need #119
  and [E3SM#8047](https://github.com/E3SM-Project/E3SM/pull/8047), which
  are not in Polaris's E3SM submodule.
- Polaris builds MPAS-Ocean from one E3SM checkout per work directory,
  `e3sm_submodules/E3SM-Project` by default. `ice_shelf_2d` runs in
  `mpaso_pr`, `mpaso_nightly` and `framework_pr`.
- The spherical ISOMIP+ meshes are JIGSAW meshes. Their projection is true
  at 75°S, but the domain lies at 65–72°S, so lengths are scaled by 1.008
  to 1.032.
- Polaris has no landice component.
  [#501](https://github.com/E3SM-Project/polaris/pull/501) removed Albany
  from the deployment, and the `MALI-Dev` submodule, from 2024-10-31, is
  unused.
- Unmerged Polaris tasks stage SCRIP files, initial conditions and graph
  partitions for realistic E3SM meshes, but no coupler maps and nothing
  for MALI.
- Compass's MISMIP+ spin-up runs MALI's first-order velocity solver, which
  needs Albany, for 20,000 years from a 100 m slab in one job. Its
  pre-spun 2 km state puts the centerline grounding line at 423–425 km,
  outside the protocol's 450 ± 10 km.
- Compass's ocean `misomip` step computes the COM standard output from
  monthly means. No landice code in Compass relates to MISOMIP1.

## Requirements

### Requirement: The experiments run in E3SM

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Ocean0–4, IceOcean1r and IceOcean1ra run in E3SM with MPAS-Ocean and MALI
as the only active components. MALI is static in Ocean0–2, replays the
prescribed geometry in Ocean3–4, and evolves in IceOcean1r and
IceOcean1ra.

### Requirement: Imported geometry matches the ocean's initial condition

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

At the first coupling step, the land-ice pressure, land-ice fraction and
floating fraction that MPAS-Ocean imports from MALI equal those in its
initial condition, to round-off.

### Requirement: Exchanged fluxes are conserved

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The meltwater and heat one model sends are what the other receives, to
the precision of the coupler budgets.

### Requirement: A thin film lies under all grounded ice

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

In every experiment, each ocean cell under grounded ice holds a thin film
of water, and the ocean uses wetting and drying.

### Requirement: The experiments follow the protocol

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Each experiment follows the protocol, except for the departures listed
under [Decisions](#decisions).

### Requirement: Polaris provides everything the E3SM cases need

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

For ocean resolutions of 4 and 2 km, Polaris produces the meshes, initial
conditions, MALI data-mode files, mapping files, graph partitions and case
configuration for each experiment.

### Requirement: Polaris spins up MISMIP+ with MALI

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Polaris builds and runs MALI. It produces a MISMIP+ steady state whose
grounding line crosses the centerline at 450 ± 10 km.

### Requirement: Polaris analyzes the E3SM runs

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

From E3SM history files, Polaris computes melt, grounding-line position,
volume above flotation and conservation. Its plots compare runs with each
other, with standalone runs and with published results.

### Requirement: Long runs are affordable

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

At 2 km, a 100-year experiment takes about a week of wall-clock time or
less.

### Requirement: A coarse configuration tests the coupling

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

A short 4 km Ocean0 run exercises melt coupling and geometry import, as a
quick test of changes to E3SM's coupling.

### Requirement: The E3SM code comes from one branch

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Polaris's standalone builds and the E3SM cases use E3SM code from one
branch, which Polaris pins. A change can land there before E3SM,
E3SM-Ocean-Discussion or MALI-Dev merges it. Each change on the branch can
be traced to the branch it came from and to its upstream pull request, if
there is one. A Polaris suite regression-tests every change to the branch.

## Algorithm Design: shared principles

Each principle is stated once here and cited by name in the package
designs.

### Principle: independent meshes, one projection

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

MALI and MPAS-Ocean run on separate planar meshes. MALI's resolution is
chosen for the ice dynamics, for example 1 km or finer near the grounding
line. The ocean's is 4 or 2 km. Both meshes take latitude and longitude
from one transverse Mercator projection whose central meridian runs along
the domain's long axis, on a sphere of E3SM's radius. The ocean's E3SM
initial condition sets `sphere_radius` to E3SM's radius, which MPAS-Ocean
uses only for its coupler areas.

```{admonition} Rationale
Across the domain's 80 km width, the projection's scale error is below
$2\times10^{-5}$ and its area error below $4\times10^{-5}$, so planar model
areas and the map's spherical areas differ by no more than that. Fluxes
conserve exactly once both models take their coupler areas from the map
(WP7). [D2](#decisions) and [D13](#decisions) record the alternatives.
```

### Principle: the ocean follows MALI

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The ocean's land-ice fields are what the coupler would deliver from MALI's
initial geometry. Polaris applies the coupler's own glc-to-ocean map $R$
to MALI's initial export, then the normalization MPAS-Ocean applies when
it imports geometry. With $m$ MALI's below-sea-level mask and $\phi_f$ and
$\phi_g$ its floating and grounded masks, the land-ice pressure is

$$
p = \frac{R(m \rho_i g H)}{R(m)},
$$

and the floating and land-ice fractions are $R(m\phi_f)/R(m)$ and
$R(m(\phi_f + \phi_g))/R(m)$, each capped at 1. All three are zero where
$R(m) = 0$. In data mode, the initial condition matches the record MALI
reads at the start.

The constants are E3SM's and the protocol's ([D6](#decisions)):
$\rho_i = 918$ kg m⁻³, $g = 9.80616$ m s⁻², and an ocean density of
1028 kg m⁻³ in both MALI's flotation test and MPAS-Ocean's draft. The
ocean's bed comes from the same source as MALI's, on the ocean's mesh, with
no minimum water column imposed. The thin film and #119's pressure cap
handle cells whose pressure exceeds flotation.

```{admonition} Rationale
Separate remaps of the input for each model would disagree at grounding
lines, which is where the realistic test of #8887 failed. Going through the
coupler's map makes the first import a no-op for any MALI mesh, and it is
how realistic initial conditions will need to be built.
```

### Principle: pressure is prescribed and SSH adjusts

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Polaris never changes the land-ice pressure, as in the standalone tasks
(#826, D13). Before the E3SM run, SSH adjustment with standalone
MPAS-Ocean brings the SSH into balance with the pressure, so the import
stays a no-op.

### Principle: a thin film and an outflow

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Every ocean cell under grounded ice holds a fresh film at MPAS-Ocean's
pressure cap (#844, D17 and D18). The SSH is held at zero in the restoring
region by MPAS-Ocean's tidal forcing, in its direct mode with zero
amplitude (#844, D19). Meltwater and the water the ice displaces leave
there with the local temperature and salinity.

```{admonition} Rationale
E3SM adds meltwater as a volume, and in Ocean3–4 and MISOMIP1 the ice load
also changes. The protocol suggests evaporation to remove the meltwater
but accepts other strategies (Sect. 3.1.8). The outflow handles both, and
#844 found evaporation unstable at the rates a changing load needs.
```

### Principle: E3SM's physics

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The ocean uses E3SM's MPAS-Ocean physics and coefficients, including the
heat and salt transfer coefficients, overridden only where the idealized
domain or wetting and drying requires. The protocol supplies the geometry,
the initial profiles and the restoring. Ocean0–2 also have variants with
the COM physics (Table 4) for comparison with Yung et al. (2026). The
standalone tasks keep the COM physics until WP11 moves them
([D16](#decisions)).

### Principle: stub partners

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The atmosphere, land, sea ice, river and wave components are stubs. With
no atmosphere, the coupler skips the atmosphere–ocean fluxes, so the only
fluxes the ocean receives come from MALI. MALI's calving and face-melt
runoff are kept out of the ocean, since calved ice adds no freshwater in
the protocol (Sects. 3.1.2 and 4).

### Principle: one E3SM branch

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

All E3SM code this work needs comes from FAnSSIE, a long-lived, shared
development branch of the Framework for Antarctic System Science in E3SM,
`fanssie-ocn-glc-coupling` on E3SM-Ocean-Discussion/E3SM, that Polaris pins
as the submodule `e3sm_submodules/FAnSSIE`. Builds of MPAS-Ocean and MALI
for this work point to it explicitly, as they would to any MPAS-Ocean
development branch, and E3SM cases are created from it. Changes land on
FAnSSIE when they work. A ledger on the branch, `FANSSIE.md`, lists each
change, the branch it came from and its upstream pull request, if any.
Moving changes upstream is encouraged but is not a condition for landing
them. Polaris's `fanssie_pr` suite is the standard regression test for
every change to the branch.

```{admonition} Rationale
E3SM and MALI-Dev will not merge these changes at the pace this work
needs; E3SM#8047 has waited since February for master to take non-BFB
changes. Without one branch, Polaris pull requests wait on, or stack onto,
chains of unmerged E3SM pull requests, as #842, #826 and #844 do today.
```

### Principle: a prototype first

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

A throwaway 4 km Ocean0 case answers E3SM's questions before WP6 and WP7
are designed in detail. It uses FAnSSIE, inputs from a prototype script, a
static MALI and RK4. Its findings go into this document and the package
designs; the prototype does not merge.

## Implementation: work packages

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

E3SM code for these packages lands on FAnSSIE. Every package's design
document lives in Polaris, as close to its code as possible: in the
Polaris pull request that implements it, as that branch's first commit. A
package whose code is in E3SM has its design in the Polaris pull request
that first tests or uses it. This document covers WP0 and the plan as a
whole. Task, step and file names are working names.

| Package                   | Code in       | Delivers                                                  | Design lives in                                   |
|---------------------------|---------------|-----------------------------------------------------------|---------------------------------------------------|
| WP0 FAnSSIE               | Polaris, E3SM | the shared development branch and Polaris submodule       | this document; #842 implements it                 |
| WP1 Standalone ISOMIP+    | Polaris, E3SM | Ocean0–2 and thin-film tasks; the floating-mask fix       | `isomip_plus.md`, in #826                         |
| WP2 Split-explicit W&D    | E3SM          | wetting and drying with a thin film in split-explicit     | the PR adding split-explicit thin-film tasks      |
| WP3 Landice component     | Polaris       | component, MALI build, Albany                             | `landice_component.md`                            |
| WP4 MISMIP+               | Polaris       | spin-up, Ice0, Ice1r, optional others                     | `mismip_plus.md`                                  |
| WP5 Meshes and maps       | Polaris       | MALI and ocean meshes, SCRIP files, maps                  | `misomip_meshes.md`                               |
| WP6 E3SM inputs           | Polaris       | initial conditions, data files, partitions, cases         | `misomip_e3sm_inputs.md`                          |
| WP7 Idealized cases       | E3SM          | no atmosphere, coupler areas, namelists, user grids       | WP6's first PR, the first to build E3SM cases     |
| WP8 Moving grounding line | E3SM          | #119 and #141 in coupled runs; fractions; data mode       | the WP6 PR that adds Ocean3–4                     |
| WP9 Analysis              | Polaris       | diagnostics and comparisons                               | `misomip_analysis.md`                             |
| WP10 Subgrid W&D          | E3SM, Polaris | subgrid wetting and drying in partly grounded cells       | the PR that first tests it                        |
| WP11 E3SM's physics       | Polaris, E3SM | E3SM's physics in the ISOMIP+ tasks; COM variants         | `isomip_plus.md`, in the PR that switches physics |

### WP0: The FAnSSIE branch

FAnSSIE starts from E3SM master with the work this plan already depends on:
E3SM#8047 and its fixes,
[E3SM#8661](https://github.com/E3SM-Project/E3SM/pull/8661), E3SM#8887,
and E3SM-Ocean-Discussion#119, #141 and
[#142](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/142).
`xylar/E3SM:ocn/thin-film-wetting-drying` and
`ocn-glc/ice-shelf-melt-coupling` already hold most of them. Pull requests
for this work then target FAnSSIE rather than E3SM-Ocean-Discussion's
master, as Omega's target its `develop` branch.

#842 adds the submodule, so that it can be reviewed and merged without
waiting for E3SM, and #826 and #844 follow it. E3SM-Project stays the
default for every other Polaris build ([D15](#decisions)). No framework
change is needed: a setup that needs FAnSSIE points to the submodule.

#842 also adds a `fanssie_pr` suite. The ice-shelf tasks leave `mpaso_pr`,
`mpaso_nightly` and `framework_pr` for it, since #842 switches them to
options E3SM-Project lacks. Every task that needs FAnSSIE joins
`fanssie_pr`, and every change to FAnSSIE is tested with it against a
baseline from the branch's previous commit.

### WP1: Standalone ISOMIP+

#842, #826 and #844 build MPAS-Ocean from FAnSSIE and merge in that order.
Every later package reuses their initial condition, SSH adjustment, thin
film and forcing.

The floating mask over the open ocean is fixed first, in #142, so that the
reset applies only where there is land ice. The standalone tasks are rerun
with the fix before they merge. The same pull requests drop the JIGSAW
spherical meshes and most of the spherical tasks ([D2](#decisions)).

### WP2: Split-explicit wetting and drying

WP2 starts from `abc3b5daee` merged onto FAnSSIE ([D10](#decisions)).
RK4 keeps master's wetting factor, with #119's changes and its
ssh-gradient and subgrid branches. Carolyn Begeman's factors serve only
the split-explicit scheme. They see grounded ice through #119's limit on
the pressure, as RK4's factor does. WP2 must also:

- fix the known defects, such as a loop over cells that fills an edge
  array, and remove the debugging output;
- make the direct tidal forcing work with the split-explicit scheme;
- find the largest stable time step with a thin film.

Polaris adds split-explicit variants of the thin-film tasks and Ocean0 to
test it. The work lands on FAnSSIE, and an upstream pull request can
follow when it is ready.

### WP3: Landice component

A `landice` component joins `ocean` and `seaice`, with its framework in
`polaris/landice/`, its tasks in `polaris/tasks/landice/`, a MALI model
step, a MALI build from FAnSSIE and a landice database area. Its design
decides how Albany returns: through Polaris's deployment hooks, as
Compass's `--with-albany` does, or by linking an existing installation.

Static and data-mode initial conditions need only MALI's mesh conversion,
not a MALI build, so WP6 can start before Albany is back.

### WP4: MISMIP+

Tasks `landice/mismip_plus/<resolution>/...` port Compass's spin-up onto
WP5's MALI meshes:

- the bed (Eqs. 1–4), a 100 m slab, Weertman friction, and the densities
  918 and 1028 kg m⁻³;
- a spin-up in restartable segments that stops when the grounding line and
  ice volume converge;
- the rate factor $A$ tuned so the grounding line crosses the centerline
  at $450 \pm 10$ km;
- Ice0 and Ice1r, and optionally Ice1ra, Ice1rr, Ice2r, Ice2ra and Ice2rr;
- the MISMIP+ output: grounding line, volume above flotation and grounded
  area.

The steady state is MALI's initial condition for IceOcean1r.

### WP5: Meshes and maps

Shared steps in the `mesh` component build:

- MALI's planar meshes, at a resolution chosen for the ice, covering the
  ISOMIP+ box for Ocean0–4 and the MISMIP+ domain for MISOMIP1;
- the ocean's planar mesh at 4 and 2 km, which the standalone tasks also
  use;
- latitude and longitude for both from the projection, and SCRIP files;
- conservative maps between the ocean and each MALI mesh in both
  directions, in the variants E3SM's coupler expects, and the runoff map.

If the prototype finds that E3SM needs a spherical ocean, the ocean mesh
is mapped onto the sphere with the same projection ([D2](#decisions)).

### WP6: E3SM inputs

Tasks `e3sm/misomip/<resolution>/<experiment>` build:

- MALI initial conditions: static and data-mode ones from the protocol
  input, remapped to MALI's cells and calved, and prognostic ones from
  WP4;
- data-mode files for Ocean3–4 ([D7](#decisions));
- MPAS-Ocean initial conditions that follow MALI through WP5's map, with
  the thin film, profiles, restoring and outflow forcing, after SSH
  adjustment;
- graph partitions for both models at the planned task counts;
- the case configuration: a grid file and a user-mods directory with
  namelists, streams and XML changes ([D12](#decisions)).

The files are staged in an inputdata-style tree, as the realistic
component inputs are. A standalone forward run on the same inputs serves
the comparison in WP9.

### WP7: Idealized cases in E3SM

These changes land on FAnSSIE. None is specific to ISOMIP+, so they can go
upstream when E3SM wants them:

- a prognostic ocean without an atmosphere: relax the driver check and
  skip the atmosphere–ocean fluxes ([D4](#decisions));
- the ocean's coupler areas from the glc-to-ocean map when there is no
  atmosphere, as glc's already are;
- the `wetting_drying` and `tidal_forcing` namelist groups, with the tidal
  forcing built every step;
- initial conditions, data-mode files and graph partitions named by case
  variables, so `buildnml` accepts grids it does not list;
- a switch that keeps MALI's calving and face-melt runoff out of the
  ocean.

Everything specific to the experiments comes from Polaris's user-mods
directory ([D12](#decisions)): namelists, the streams for interior
restoring, the tidal mask and MALI's data mode, and the XML changes.
Compsets are given by long name. The grid files are staged on inputdata,
whether or not E3SM's code on master uses them.

### WP8: A moving grounding line

On FAnSSIE:

- make #119's pressure cap safe for threaded runs;
- use one ocean density in #119's cap, MPAS-Ocean's draft and MALI's
  flotation test;
- reconcile the floating fraction that wetting and drying sets to 0 or 1
  with the fractional one imported from MALI, including the normalization
  of the melt sent back;
- run MALI's data mode with a changing thickness, and check that its masks
  and pressure agree at each export, since MALI reads a new record after
  its time step but before it exports *(inferred)*;
- confirm that the floating mask follows the imported geometry, so newly
  floating cells melt and newly grounded ones stop.

The notes on #8887 name wetting-and-drying runs as the next project after
melt coupling. This package is that project.

### WP9: Analysis

Analysis tasks read E3SM history files from a configured run directory and
compute:

- melt rates and fluxes, grounding-line position, volume above flotation
  and grounded area;
- conservation from the coupler budgets;
- plots comparing E3SM with standalone Polaris on the same inputs, across
  experiments, and with published results: Yung et al. (2026) for Ocean0–2
  and [Cornford et al. (2020)](https://doi.org/10.5194/tc-14-2283-2020)
  for MISMIP+.

Compass's `misomip` and streamfunction steps can be ported where they
help. The protocol's file format is not a goal.

### WP10: Subgrid wetting and drying

MPAS-Ocean's subgrid wetting and drying
([E3SM#6288](https://github.com/E3SM-Project/E3SM/pull/6288),
[E3SM#8608](https://github.com/E3SM-Project/E3SM/pull/8608)) corrects
partly wet cells using lookup tables built in init mode from fine-scale
topography. It supports one layer, RK4, standalone runs and a free surface
over static topography. WP10 extends it to partly grounded cells under ice
shelves, with RK4 and static geometry first. Its own design settles the
details.

### WP11: E3SM's physics

The standalone ISOMIP+ tasks move to E3SM's physics
([principle](#algorithm-design-shared-principles)), including
`Jacobian_from_TS` for the pressure gradient and E3SM's land-ice flux
coefficients. Ocean0–2 keep COM variants. The equation of state is `jm`,
evaluated at each layer's actual depth, which needs an MPAS-Ocean change on
FAnSSIE ([D17](#decisions)). The design amends `isomip_plus.md` in the pull
request that makes the change.

### Order

| Stage | Experiments            | Needs                                                |
|-------|------------------------|------------------------------------------------------|
| A     | 4 km Ocean0, prototype | WP0                                                  |
| B     | Ocean0–2               | WP0, WP1, WP5, WP6, WP7, WP9, WP11; WP2 for Ocean1–2 |
| C     | Ocean3–4               | stage B, WP2, WP8                                    |
| D     | IceOcean1r, 1ra        | stage C, WP3, WP4                                    |

WP2, WP3, WP4 and WP11 can proceed alongside stages A–C: WP2 needs only
WP0 and WP1, WP3 needs nothing, WP4 needs WP3 and WP5, and WP11 needs only
WP1. WP10 follows WP2, and no stage needs it.

FAnSSIE starts from these pull requests, whose states are as of
2026-10-16:

| Pull request               | State                                           |
|----------------------------|-------------------------------------------------|
| E3SM#8047                  | draft; waits for master to take non-BFB changes |
| E3SM#8661                  | approved, open                                  |
| E3SM#8887                  | draft                                           |
| E3SM-Ocean-Discussion#119  | draft                                           |
| E3SM-Ocean-Discussion#141  | open                                            |
| E3SM-Ocean-Discussion#142  | open                                            |
| split-explicit W&D (WP2)   | no pull request                                 |

## Testing and Validation

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

Each step builds on the one before it.

1. **Polaris unit tests.** The ocean's land-ice fields equal the coupler's
   map and the import's normalization applied to MALI's initial export.
   Model and map areas agree to $4\times10^{-5}$.
2. **The prototype.** The planar ocean runs in E3SM with its
   `sphere_radius` set. In coupler history, every ocean input except glc's
   is zero. At the first coupling step, the imported fields equal the
   initial condition to round-off. With static MALI, runs with import on
   and off differ only by growth from round-off over 5 days.
3. **E3SM against standalone.** E3SM's Ocean0 and standalone Polaris's
   Ocean0, on the same inputs with RK4 at 4 km, are compared after a
   month. Each difference is traced to the coupler or to a recorded
   configuration difference.
4. **Conservation.** With `BUDGETS=TRUE`, the budgets close for the
   exchanged melt.
5. **Published results.** The COM variants of Ocean0–2 are compared with
   Yung et al. (2026).
6. **Ocean3–4.** The geometry the ocean imports tracks the data-mode file.
   The grounding line moves without failure, the open-ocean SSH stays near
   zero, and no open-ocean cell receives land-ice fluxes. In partly
   floating cells, the melt MALI receives equals the melt the ocean sends.
7. **MISOMIP1.** MALI's grounding-line retreat and volume above flotation
   in IceOcean1r are compared with its own Ice1r, which uses the
   protocol's melt parameterization.
8. **Split-explicit.** At 4 km, split-explicit and RK4 Ocean0 agree
   closely, and a split-explicit 100-year run at 2 km meets the long-run
   requirement.

Every change to FAnSSIE runs `fanssie_pr` against a baseline from the
branch's previous commit. The 4 km Ocean0 case also repeats steps 2 and 4.

## Scope and non-goals

- Omega does not yet support ice-shelf cavities, so it is out of scope.
- IceOcean2r and IceOcean2ra are out of scope ([D9](#decisions)).
- The results are not submitted to MISOMIP, and no publication centers on
  them. The protocol's output files are not produced.
- Matching realistic Antarctic initial conditions, "option B" in the notes
  on #8887, is separate work. It can reuse the principle that the ocean
  follows MALI.
- The MOAB driver is out of scope until it supports ice-shelf coupling.
- Moving changes from FAnSSIE upstream is not a requirement of this work.
  The ledger keeps them from being lost.
- Polaris makes the inputs and the case configuration. People create and
  run the E3SM cases.

## Decisions

### D1: The ocean follows MALI

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The ocean's land-ice fields come from MALI's initial export, remapped by
the coupler's own map. A separate remap of the protocol input for each
model is rejected because it would disagree with MALI at grounding lines.

*Effect:* partly grounded and partly floating ocean cells occur at the
grounding line, as they will in realistic coupling. The comparison with
standalone runs uses the E3SM inputs.

### D2: The ocean runs on the planar mesh in E3SM

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

MPAS-Ocean runs in E3SM on the standalone tasks' planar mesh, with
`sphere_radius` set in its initial condition. No E3SM configuration has
run a planar ocean before, so the prototype checks for assumptions of a
sphere.

Alternatives:

- **The planar mesh mapped onto the sphere.** This is the fallback if the
  prototype finds such an assumption. Its lengths would differ from the
  planar mesh's by less than $2\times10^{-5}$, and the standalone tasks
  would need the mapped mesh too for comparisons.
- **The existing spherical meshes.** Rejected: their projection scales
  lengths by 1.008 to 1.032 across the domain. The open ISOMIP+ pull
  requests drop them, along with most of the spherical tasks.

### D3: Every experiment has a thin film

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Ocean0–2 keep a thin film under grounded ice although their geometry is
static. They test the capability in coupled runs before the grounding line
moves.

### D4: No atmosphere, through a driver change

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The drivers accept a prognostic ocean without an atmosphere and skip the
atmosphere–ocean fluxes. A data atmosphere on the ocean grid, with
MPAS-Ocean's bulk forcing off, is rejected. It needs no driver change, but
it needs data-atmosphere inputs, and the coupler computes fluxes that the
ocean then ignores.

### D5: The MCT driver

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

All runs use the MCT driver, the only one in which #8887 couples ice-shelf
melt.

### D6: E3SM's constants

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The inputs use E3SM's gravity, 9.80616 m s⁻², and its sphere radius,
6,371,229 m, not the values in Polaris's constants. MALI's ice density is
set to the protocol's 918 kg m⁻³, replacing E3SM's 910. MPAS-Ocean uses
MALI's ocean density, 1028 kg m⁻³, wherever it converts pressure to
draft.

```{admonition} Rationale
The import must be a no-op. MALI's coupler areas assume E3SM's radius, and
the ocean's planar areas must use the same one.
```

### D7: Data-mode files hold monthly records

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The protocol interpolates the yearly geometry linearly in time and calves
after interpolating (Sects. 3.1.2 and 3.2.4). MALI's data mode steps from
record to record without interpolation. Polaris therefore writes monthly
records, each interpolated in time and then calved. Yearly records are
rejected because the geometry would move in yearly jumps.

### D8: An outflow, not evaporation

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

Water leaves through the tidal forcing in the restoring region, not
through the protocol's evaporation, as in #844 (D19). See
[the thin-film principle](#algorithm-design-shared-principles).

### D9: IceOcean2 is out of scope

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

IceOcean2r and IceOcean2ra are optional in the protocol. They need MALI to
calve ice thinner than 100 m, and a new spin-up with Ice0 and Ice1 rerun
(Sect. 4.2).

### D10: Split-explicit work starts from Carolyn Begeman's series

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

WP2 starts from `abc3b5daee`, the most recent split-explicit series.
`alt-wetting-drying-se` adds stale copies of #119 and of the thin-film
viscosity work on top of it.
`ocn-add-wetting-drying-se-and-fix-vlr` carries the same series with
vertical-remap and debugging commits.

### D11: Ocean resolutions are 4 and 2 km

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

The ocean uses 2 km for the protocol runs, the COM resolution
(Sect. 3.1.5), and 4 km for development and the quick coupling test.
MALI's resolution is set in the MISMIP+ design ([D13](#decisions)).

### D12: The E3SM configuration lives in Polaris

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

For each experiment, Polaris writes a user-mods directory and a grid file
from the same physics configuration as the standalone tasks. FAnSSIE
carries only the general changes of WP7.

Rejected: compset modifiers, namelist defaults and grid entries in E3SM.
They would split the physics between two repositories, and idealized tests
are not a priority for E3SM integration.

```{admonition} Rationale
One source for the physics keeps the E3SM and standalone runs identical,
so the comparisons in WP9 test the coupling rather than the configuration.
```

### D13: MALI and ocean meshes are independent

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

MALI's mesh is chosen for the ice dynamics and need not share cells with
the ocean's.

Rejected: cutting both meshes from one planar mesh so that their cells
coincide. It would tie MALI's resolution to the ocean's, and MALI may need
finer resolution than the ocean can afford, as BISICLES had through
adaptive refinement in POPSICLES. Every ocean cell would also be wholly
grounded, floating or open, which hides the partly grounded cells that
realistic coupling must handle. A run with MALI on the ocean's mesh
remains available as a diagnostic if remapping is suspected.

### D14: FAnSSIE only gains commits

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

FAnSSIE is a long-lived, shared development branch, like Omega's
`develop`, for the few people doing ocean–ice-sheet coupling work. It
lives on E3SM-Ocean-Discussion/E3SM, a neutral home. Every E3SM change
for this work starts from FAnSSIE and merges into it through a pull
request on E3SM-Ocean-Discussion/E3SM. Small fixes and changes to the
branch's ledger may be committed directly. Upstream pull requests that
the work depends on are merged in as they are, and E3SM master is merged
in from time to time. Nothing on the branch is rewritten, so every commit
Polaris pins stays reachable.

```{admonition} Rationale
A pull request into FAnSSIE from a branch based on E3SM master can carry
changes unrelated to it, which makes it confusing to review.
```

*Effect:* a change made here reaches E3SM by being rebased or
cherry-picked onto master.

Rejected:

- feature branches based on E3SM master, the first version of this
  decision;
- regenerating the branch from master and a list of feature branches, as
  E3SM's `next` is. Its history is cleaner, but each rebuild must be
  tagged so that pinned commits survive, and conflicts are resolved again
  at every rebuild.

### D15: E3SM-Project stays Polaris's default

Date last modified: 2026/10/16

Contributors: Xylar Asay-Davis, Claude

E3SM-Project remains the E3SM source for every Polaris build except those
for ocean–ice-sheet coupling work, which point to FAnSSIE explicitly. The
tasks that need FAnSSIE, including all the ice-shelf tasks, run in
`fanssie_pr` and not in the regular suites.

Rejected: making FAnSSIE the default. FAnSSIE is specialized for coupled
ocean–ice-sheet work, and every suite, nightly CDash runs included, would
then test it rather than E3SM. Also rejected: keeping `ice_shelf_2d` in the
regular suites on its current options. Tasks that work with one source but
not the other would then be hard to tell apart as the two diverge.

### D16: E3SM's physics, not COM's

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The ocean uses E3SM's MPAS-Ocean physics and coefficients, overridden only
where the idealized domain or wetting and drying requires. The experiments
rehearse realistic coupling, so they exercise the physics realistic runs
will use.

Rejected: the COM physics (Table 4) throughout, which the standalone tasks
use today. It would make the E3SM runs override E3SM's defaults with
Laplacian viscosity, constant mixing and a tuned $\Gamma_T$. It stays as a
variant of Ocean0–2, the only experiments with published results to
compare against.

*Effect:* #826 and #844 merge with the COM physics, and WP11 then moves the
standalone tasks to E3SM's physics.

### D17: `jm` at each layer's actual depth

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The ocean uses the `jm` equation of state, evaluated at the pressure of
each layer's actual depth, possibly lagged by a time step, rather than its
reference depth. The change is an MPAS-Ocean option on FAnSSIE, off by
default, so other runs are unchanged.

```{admonition} Rationale
`jm` evaluates each layer at a pressure computed once from
`refBottomDepth`. With z-star, layers under the ice sit far deeper than
their reference depths, so under 700 m of ice the top layers are evaluated
at near-surface pressure. Under floating ice, the actual depth gives the
right pressure, since the ice weighs as much as the water it displaces.
```

Rejected:

- a linear equation of state until Omega supports ice-shelf cavities,
  which has no thermobaricity or cabbeling;
- `wright`, which uses each layer's actual depth but has never worked
  correctly;
- `jm` at reference depths, as on E3SM master.
