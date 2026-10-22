# Split-Explicit Wetting and Drying with a Thin Film

Creation date: 2026/10/18

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

This design is WP2 of the
[MISOMIP design](https://github.com/E3SM-Project/polaris/pull/858).
MPAS-Ocean's split-explicit scheme gains wetting and drying with a thin
film under grounded ice. Polaris adds split-explicit variants of the
ISOMIP+ `ocean0`, `inception`, `wetting` and `drying` tasks and of the
drying slope tasks to test it.
The E3SM code lands on FAnSSIE, the shared development branch of the
Framework for Antarctic System Science in E3SM, through a pull request to
`fanssie-ocn-glc-coupling`.

With RK4, a 100-year run at 2 km takes about 195 days on Chrysalis, so
the long MISOMIP experiments need the split-explicit scheme.

The work starts from Carolyn Begeman's unreviewed split-explicit series
and her wetting-and-drying design, which is on Overleaf. Debugging and
changes to the algorithm are expected. They are recorded here and in an
updated copy of her design.

## Requirements

### Requirement: Wetting and drying works with the split-explicit scheme

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

MPAS-Ocean runs the ISOMIP+ Ocean0–2 and thin-film tasks with wetting and
drying, a thin film under grounded ice and the split-explicit scheme.

### Requirement: Other runs are unchanged

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

Runs without a thin film and without direct tidal forcing are
bit-for-bit with FAnSSIE before this work, except split-explicit runs with
wetting and drying.

### Requirement: Split-explicit agrees with RK4

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

On the same inputs, split-explicit and RK4 runs agree closely in melt, sea
surface height and the extent of the thin film.

### Requirement: Displaced water can leave the domain

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

With the split-explicit scheme, the sea surface height is held at zero in
the restoring region, as it is with RK4.

### Requirement: Split-explicit runs restart exactly

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

A split-explicit run with wetting and drying gives the same results
whether or not it restarts partway.

## Algorithm Design

### Algorithm Design: the starting point

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The first 43 commits of `cbegeman/E3SM:alt-wetting-drying-se`, ending at
`abc3b5daee`, are merged onto FAnSSIE. In that series, a barotropic
wetting factor is computed at each barotropic subcycle from the water
column predicted from outgoing fluxes. The baroclinic factor is computed
the same way, at the end of the time step, from the final barotropic
velocity and the edge water column averaged over the subcycles.

### Algorithm Design: RK4 keeps master's factor

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

RK4 keeps master's wetting factor, `ocn_wetting_drying_wettingVelocity`,
with E3SM-Ocean-Discussion/E3SM#119's changes and its ssh-gradient and
subgrid branches. The series' outflux factor,
`ocn_wetting_drying_outflux_barotropic_factor`, serves only the
split-explicit scheme. Its column-wide factor, which only its RK4 path
used, and a barotropic factor that nothing called are removed. A
split-explicit run that requests subgrid
or ssh-gradient wetting and drying stops at initialization. Both schemes
add the rule below that keeps water out from under grounded ice.

```{admonition} Rationale
The series replaces master's RK4 factor and drops the branches that #119
and subgrid wetting and drying use. Keeping master's factor leaves RK4
runs without a thin film bit-for-bit and keeps subgrid wetting and
drying, which supports one layer and RK4 only, available for WP10.
```

### Algorithm Design: grounded ice in the split-explicit factors

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The split-explicit factors see grounded ice through #119's limit on the
land-ice pressure, as RK4's factor does. #119's `sshLandIceAdjustment` is
the sea-surface-height equivalent of the pressure the limit removes. The
factors reduce the predicted water column by it and, when comparing
neighbors' sea surface heights, raise the cell's by it. This is the
land-ice treatment in Carolyn Begeman's design.

```{admonition} Rationale
Without it, a cell under grounded ice looks like any thin column. Its
1 mm film layers open whenever they drift above the minimum thickness,
and at grounding-line cliffs, where the ice base steps 50–90 m between
neighbors and the pressure gradient on those layers is unbalanced, they
reach meters per second. Testing dryness on the actual water column
instead made all three RK4 thin-film tasks and split-explicit SSH
adjustment blow up.
```

### Algorithm Design: water stays out from under grounded ice

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

In both schemes, water flows into a cell under ice heavier than
flotation only where the neighbor's head exceeds the cell's head plus
the excess, that is, where it could lift the ice. A cell's head is its
sea surface height plus the land-ice pressure after #119's limit, in
meters of seawater. The excess is minus `sshLandIceAdjustment`.

```{admonition} Rationale
A cell under ice heavier than flotation looks dry, so water can flow in
but not out. Split-explicit SSH adjustment of the 4 km `wetting` task
trapped 1.2e9 m³ this way, up to 4.9 m deep, in 46 cells, since its
factor opens a dry cell's edges whenever the predicted barotropic
velocity points in. Once the ice thinned, the water drained as a dam
break and the run failed after an hour. With the rule, 7.5e6 m³ is
trapped, about as much as with RK4, which never opens an edge without
flow. With the rule, RK4 traps 25% and 14% less water in the `drying`
and `inception` tasks.
```

### Algorithm Design: the baroclinic factor follows the barotropic one

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

As in RK4 and Carolyn Begeman's design, a dry cell closes edges without
flow as well as outflow edges. The baroclinic factor is also closed
wherever the barotropic factor of the last subcycle is closed.

```{admonition} Rationale
The baroclinic factor is computed from the final barotropic velocity,
which is zero on every edge the subcycles closed, and without the
outflow the subcycles predicted. The series closed only outflow edges,
so all of those edges opened again, and a cell just above the critical
height, closed by its predicted outflow, looked wet. The baroclinic
velocity in the thin layers of such an edge then grew unopposed at a
grounding-line cliff.
```

### Algorithm Design: the factors scale velocities, not forces

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The split-explicit wetting factors scale velocities and the barotropic
thickness flux, never a single force. The velocity tendency and the
barotropic forcing are computed without them. The baroclinic factor
scales the change in the baroclinic velocity over the time step. Each
subcycle's barotropic factor scales the corrected barotropic velocity and
the thickness flux, and the predictor is not limited.

```{admonition} Rationale
Under an ice shelf, the SSH gradient and the land-ice pressure gradient
nearly cancel, and at the ISOMIP+ grounding line each reaches about
0.2 m s⁻². The barotropic subcycles see the first directly and the
second through the barotropic forcing. The series scaled the first by
the subcycle's factor and the second by the baroclinic factor, so wherever
the two differed, one force went unopposed. They differed on most edges
under grounded ice, and in the 4 km `wetting` task the barotropic
velocity at the grounding line reached 27 m s⁻¹ within an hour.
```

### Algorithm Design: direct tidal forcing

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

With the split-explicit scheme, the direct tidal forcing resets the layer
thicknesses, and so the sea surface height, in the forced cells at the
end of each time step, as it does with RK4, in every cell of the block,
halos included. In between, the barotropic pressure gradient sees the
forced cells' actual sea surface height, as RK4's does, rather than the
forced value.

```{admonition} Rationale
FAnSSIE's split-explicit scheme already resets the thicknesses, but only
in the cells that its last barotropic subcycle computed, so halo copies
of forced cells drift from the cells they copy. Its pressure gradient
used the forced value, so nothing opposed flow between two forced cells,
and in the thin-film tasks, currents there grew to 4 m s⁻¹ within hours.
Holding the forced value in the continuity equation as well made the
runs fail sooner.
```

### Algorithm Design: velocity ramp with a thin film

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The ISOMIP+ tasks with a thin film turn on the ramped wetting factor of
O'Dea et al. (2021), `config_zero_drying_velocity_ramp`, in their
SSH-adjustment and forward runs, with either time integrator. Velocities
are ramped down in columns thinner than 0.1 m per layer.

```{admonition} Rationale
Without the ramp, the split-explicit `wetting` task failed when a cell
whose ice had just floated, holding 0.15 m of water, filled from a 99 m
deep neighbor at 15 m s⁻¹. RK4 passes without the ramp, but both schemes
use it so that their results can be compared. Slowing the ice evolution
4 or 10 times, or a baroclinic time step from 24 to 120 s, did not
reliably prevent such failures.
```

### Algorithm Design: SSH adjustment leaves the restoring region free

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

SSH adjustment does not hold the SSH at zero in the restoring region,
although the forward run does. SSH adjustment copies its final SSH
everywhere, so the water it moves out from under the ice leaves the open
ocean about 7.6 cm high in `wetting` and `drying`, which the forward run
then drains.

```{admonition} Rationale
Holding the restoring region during SSH adjustment as well removed the
mismatch but changed either scheme's melt by less than 1%, and it made
SSH adjustment converge worse at the grounding line: at 2 km with
split-explicit, its last change grew from 0.7 to 3.1 cm. With
spatially variable upwind, that made the 2 km split-explicit `wetting`
task fail.
```

### Algorithm Design: defects in the series

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

These are fixed or removed:

- a loop over cells that fills the edge arrays `wettingVelocityFactor`
  and `wettingVelocityBaroclinicCur` in
  `mpas_ocn_time_integration_split.F`;
- the fallback for neighbors beyond `nCellsAll`, marked "check with
  Steven";
- the halo exchange of `effectiveDensityInLandIce`, a field that
  E3SM#8047 removed;
- commented-out and per-step debugging output;
- loops widened from one halo layer to all cells in the diagnostics and
  ALE thickness, unless the factors need them;
- a call to `mpas_timer_start` with an argument it does not take, which
  kept `abc3b5daee` from compiling;
- factors set to 1 only on a cold start, although they are not in the
  restart stream, so a restart zeroed the first step's baroclinic
  velocity;
- a regrouped sum in the baroclinic velocity update, which changes
  rounding;
- an overwrite of the diagnosed `layerThickEdgeFlux` during
  initialization, which differs at the top active level and drops
  upwinding in the first step.

Debugging the ISOMIP+ tasks found this, also fixed: a time-varying
forcing clock that only RK4 advanced, so with the split-explicit scheme
the land-ice load never changed in time, and that restart files recorded
one time step behind the model with either scheme, so restarts with
time-varying forcing were not exact.

### Algorithm Design: exact restart

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

Two factors carry from one time step to the next: the baroclinic factor
and the barotropic factor of the last subcycle, with which the next
barotropic stage starts, as in Carolyn Begeman's design. Both are in the
restart stream. Without wetting and drying, both are 1 at
initialization, so runs without wetting and drying do not need them in
the restart file.

```{admonition} Rationale
The series left the last subcycle's factor in one time level and started
each barotropic stage from the other after the end-of-step swap, so a
step began from the second-to-last subcycle's factor. Neither factor was
in the restart stream.
```

### Algorithm Design: time step

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The largest stable baroclinic and barotropic time steps with a thin film
are found at 4 and 2 km and set as time steps per kilometer. The
split-explicit variants use 30 s per km for the baroclinic step and 6 s
per km for the barotropic one, about 20% below the largest stable steps,
37.5 and 7.5 s per km at both resolutions.

```{admonition} Rationale
At both resolutions, the `wetting` task failed with a baroclinic step of
45 s per km, although `ocean0` ran with 120 s per km at 4 km, and every
task failed with a barotropic step of 10 s per km. The barotropic step
was 1.5 s per km before, and the larger one makes a 2 km step about 37%
cheaper.
```

### Algorithm Design: split-explicit rather than `split_explicit_ab2`

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

Wetting and drying with a thin film stays in MPAS-Ocean's
`split_explicit` scheme rather than moving to `split_explicit_ab2`,
E3SM's default.

```{admonition} Rationale
Without wetting and drying and with centered thickness fluxes, a 30-day
4 km `ocean0` run with `split_explicit_ab2` takes 347 s, against 551 s
with `split_explicit` at the same time steps, and its melt agrees with
RK4's within 0.1%. With upwinding, everywhere or only in thin columns, it
fails within 2 hours, because its barotropic edge thickness combines layer
thicknesses and SSH upwinded in different directions. Moving to it would
need an upwind-consistent barotropic edge thickness, the integrator side
of this work, direct tidal forcing and the wetting factors in its
restart, and then this testing again. The saving of 37% per step does not
justify that in a model that Omega will replace.
```

## Implementation

### Implementation: E3SM

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

The branch `xylar/E3SM:ocn/split-explicit-thin-film` starts at FAnSSIE
`23b25eb360`. Its first commit merges `abc3b5daee`, resolving the
conflicts in `mpas_ocn_wetting_drying.F` by the two designs above and in
`mpas_ocn_time_integration_split.F` by dropping the
`effectiveDensityInLandIce` exchange. Fixes follow as separate commits. A
pull request merges the branch into `fanssie-ocn-glc-coupling`, which adds
a row to the ledger in `FANSSIE.md`.

### Implementation: Polaris

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The ISOMIP+ tasks gain split-explicit variants of `ocean0`, `inception`,
`wetting` and `drying`, such as
`ocean/planar/isomip_plus/4km/z-star/split_explicit/ocean0`. WP11's
physics variants use the same level, as in `.../z-star/com/ocean0`. Each
variant adds its own config file. `split_explicit.cfg` sets
`time_integrator`, `split_dt_per_km` and `btr_dt_per_km` for the forward
run, in `[isomip_plus_forward]`, and for SSH adjustment, in
`[ssh_adjustment]`, so SSH adjustment uses the same scheme as the forward
run. If that makes debugging harder, the variants adjust SSH with RK4
until split-explicit is stable. `Forward` sets the MPAS-Ocean time
integrator from these options. A restart variant,
`.../split_explicit/wetting/with_restart`, follows `ice_shelf_2d`'s: it
reuses its task's init and SSH adjustment and compares a full run with
one that restarts halfway. With a thin film, `Forward` and the SSH
adjustment's `ThinFilmSshForward` add `thin_film_wetting_drying.yaml`,
which turns on the velocity ramp for both time integrators. The 4 km
split-explicit `ocean0`, `wetting` and `wetting/with_restart` join
`fanssie_pr`, and the FAnSSIE submodule moves to the commit that merges
this work.

The drying slope tasks, barotropic and the baroclinic case of O'Dea et al.
(2021), come to Polaris in their own pull request based on `main`,
starting from Carolyn Begeman's port in #192. They need only RK4 wetting
and drying, which E3SM-Project has. This work adds their split-explicit
variants.

## Testing

### Testing and Validation: other runs are unchanged

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

`fanssie_pr` runs with MPAS-Ocean from this work against a baseline with
FAnSSIE's code before this work. The `ice_shelf_2d` tasks and the RK4
ISOMIP+ `ocean0` are bit-for-bit, and the RK4 thin-film tasks change as
intended. Without wetting and drying, a 30-day split-explicit `ocean0`
run is bit-for-bit with FAnSSIE's.

### Testing and Validation: split-explicit agrees with RK4

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The drying slope tasks run with both schemes. Split-explicit matches their
reference solutions about as well as RK4, without grid-scale noise.

Split-explicit and RK4 runs of `ocean0` at 4 km, and of the thin-film
tasks at 4 and 2 km, are compared in melt, sea surface height in the
restoring region, the area of the thin film and the minimum water column.
They share the initial condition, and each adjusts SSH with its own
scheme, so the comparison starts with the adjusted SSH.
A thin-film run with uniform temperature and salinity keeps them uniform.

At 4 km, in `wetting`, `drying` and `inception`, the area of the thin
film agrees within 0.1%, neither scheme thins a column below the minimum,
and both hold SSH at zero in the restoring region. Split-explicit's
time-mean melt is 13%, 10% and 31% lower than RK4's, whose melt varies
three times as much from hour to hour, along with larger velocities near
the ice.

Halving RK4's time step changes its time-mean melt in `wetting` and
`inception` by 2% or less. Split-explicit's rises 5% and 8% between 30
and 12.5 s per km. Extrapolated to a zero time step, split-explicit's
melt is still 9% and 24% below RK4's, so most of the gap is a difference
between the schemes. Split-explicit's time-step error at 30 s per km is
about 7% and 12%. A thin-film run with uniform temperature and salinity,
and no land-ice fluxes, keeps them within 3e-7 °C and 1e-5 PSU over 12
hours with either scheme.

Most of the gap comes from the restoring region. As the ice load changes,
the tasks push 30 Sv into the domain (`wetting`) or out of it (`drying`)
and 38 Sv out of it (`inception`). Split-explicit resets the forced cells
only at the end of each 120 s step, after its subcycles have let their
SSH drift for 240 s, so they take up less of the flux than RK4's, which
are reset every 24 s. Next to the restoring region, split-explicit's SSH
stands 1.6 to 1.8 m from zero in `wetting` and `drying` and 8 to 14 m in
`inception`, against 0.1 to 0.7 m with RK4, and less water moves through
the cavity. In an experiment that also resets the forced cells'
barotropic SSH after every subcycle, split-explicit's melt at 4 km is 7%
and 3% below RK4's in `wetting` and `drying` and varies as much, but
`inception` fails after 20 hours, in flows of 5 m s⁻¹ along steps in the
ice base over the thin film that RK4 survives, and at 2 km `drying` and
`inception` fail too. Holding the forced cells' SSH through the
subcycles instead makes all three tasks fail, from jets along the
restoring region.

SSH adjustment leaves the open ocean 7.6 cm high in `wetting` and
`drying`, which the forward run then drains. Holding the restoring region
at zero during SSH adjustment removes the mismatch but changes either
scheme's melt by less than 1%. With the ice held fixed, all of the melt
gap is under floating ice and in the friction velocity, not the thermal
driving, so the closure of thin columns, layer by layer or column-wide,
is not its cause.

A watch item: at 2 km, the grounding-line cell by the south wall near
(514, 4) km carries the largest SSH-adjustment residual. A small change
to the adjusted state there, from holding the restoring region during
SSH adjustment, made the split-explicit `wetting` task fail within 2
hours, with 12.7 m s⁻¹ on its edges after 1 hour.

Over 30 days, with the upwind thickness fluxes that the ISOMIP+ tasks
use for wetting and drying, `ocean0`'s melt agrees within 3% for the
first 2 days and then diverges: split-explicit's is 40% above RK4's over
the month and 52% above it over days 20 to 30. The melt rates agree near
the grounding line, but downstream of 520 km split-explicit melts 2 to 5
times as much, with friction velocities 1.5 to 4 times RK4's and similar
thermal driving, and its kinetic energy under the ice shelf keeps
growing, to 3 times RK4's, which levels off after 10 days. The divergence
is in FAnSSIE before this work, and it comes from split-explicit's
upwinding. Without wetting and drying, split-explicit runs with and
without this work are bit-for-bit over the month, and with centered
thickness fluxes, split-explicit, `split_explicit_ab2` and RK4 agree
within 0.1%, at about 104 Gt/yr over days 20 to 30, against 96.8 Gt/yr
after a month for Compass's 2 km `Ocean0`, which uses
`split_explicit_ab2` and centered fluxes. Halving either scheme's time
steps, a third outer iteration, a 6 s barotropic step or explicit drag
leaves the divergence with upwind fluxes in place.

With `config_use_spatially_variable_upwind`, which upwinds only where the
column is thinner than 5 to 10 m, in both schemes and with wetting and
drying, split-explicit's `ocean0` melt is 1.1% above RK4's over the month
and 1.6% above it over days 20 to 30, and the thin-film tasks run with
both schemes. Their split-explicit melt
is then 13%, 12% and 37% below RK4's in `wetting`, `drying` and
`inception`, so the gap from the restoring region remains. Blending
split-explicit's own upwind thicknesses the same way changes these
results by 1% or less and makes `inception` fail.

### Testing and Validation: split-explicit runs restart exactly

Date last modified: 2026/10/18

Contributors: Xylar Asay-Davis, Claude

In `.../split_explicit/wetting/with_restart`, a run that restarts halfway
is bit-for-bit with one that does not.

### Testing and Validation: cost of long runs

Date last modified: 2026/10/19

Contributors: Xylar Asay-Davis, Claude

The cost per simulated year at 2 km, at the largest stable time step, is
measured and extrapolated to 100 years.

On Chrysalis, with the time steps above, a split-explicit step of the 2 km
`wetting` task takes 38 ms on 36 MPI tasks, 27 ms on 128 (one node) and
22 ms on 256 (two nodes). A 100-year run would take about 23, 16.5 and
13.6 days, against about 195 days for RK4 on 36 tasks. The 11,590-cell
mesh scales poorly beyond one node, and the thin film limits the
baroclinic step to 37.5 s per km, at which two nodes would take about 11
days.
