# MISOMIP Analysis

Creation date: 2026/11/01

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

E3SM runs the ISOMIP+ experiments Ocean0–4 and the MISOMIP1 experiments
IceOcean1r and IceOcean1ra with MPAS-Ocean coupled to MALI, from inputs
Polaris builds ([MISOMIP inputs design](misomip_e3sm_init.md)). Polaris
also runs MPAS-Ocean alone on the same inputs. Section and equation
numbers refer to the protocol
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)).

This design adds analysis of those runs:

- **diagnostics** of melt and its drivers, the cavity's circulation and
  water masses, the thin film and the ice sheet's geometry;
- **conservation** of the melt exchanged between the models;
- **comparisons** of E3SM with the standalone run on the same inputs,
  across experiments and resolutions, and with
  [Yung et al. (2026)](https://doi.org/10.5194/tc-20-2053-2026) and
  [Cornford et al. (2020)](https://doi.org/10.5194/tc-14-2283-2020).

The analysis is for the developers of the coupling, not for the protocol.
It works on the models' own meshes and plots with `mosaic`. Results are not
submitted to MISOMIP. The diagnostics live in the `ocean`, `landice`,
`e3sm` and `viz` frameworks, so they serve any MPAS-Ocean run with
ice-shelf cavities and any MALI run ([D8](#decisions)). Compass's ISOMIP+
steps and MPAS-Analysis's ice-shelf tasks are references for the
algorithms, not sources of code.

It follows the [ocean analysis design](ocean_analysis.md) where that
applies, but adds its own code for finding E3SM and standalone MPAS files.

Success means a published comparison of E3SM's 4 km Ocean0 with the
standalone run over their first month, with the coupler's budgets, in which
each difference can be located.

## Requirements

### Requirement: The analysis reads runs it did not set up

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Polaris analyzes an E3SM case of a MISOMIP experiment and a standalone
MPAS-Ocean run on the same inputs. Where their output lives comes from the
case and the run themselves, with configured overrides.

### Requirement: The runs are diagnosed

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

For each run, as time series and as maps or sections, Polaris computes:

- the total melt flux and the mean melt rate over the floating ice base,
  and the thermal driving, haline driving and friction velocity;
- the barotropic and overturning streamfunctions, temperature and salinity
  in sections and at the seafloor, and the ocean's volume and mean
  temperature and salinity;
- with a thin film, its extent and the open ocean's sea-surface height;
- in a coupled run, MALI's floating ice that the ocean treats as grounded
  next to the grounding line, and the melt missed there;
- from MALI's output, the grounding line, the volume above flotation, the
  grounded area and the ice volume.

Plots are published in a gallery. The data behind each plot is kept in a
netCDF file, which can be published with it.

### Requirement: Exchanged fluxes are checked for conservation

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Polaris reports whether the coupler's budgets close for the meltwater and
heat exchanged between the ocean and MALI. In IceOcean1r and IceOcean1ra,
it also compares the melt the ocean sends with the melt MALI applies, each
from its own model's output.

### Requirement: Runs are compared with each other

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Polaris compares E3SM with the standalone run on the same inputs, the
experiments with each other at one resolution, and each experiment at 4
and 2 km.

### Requirement: Runs are compared with published results

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Ocean0–2 are compared with the models of Yung et al. (2026). IceOcean1r and
IceOcean1ra are compared with Cornford et al. (2020) and with MALI's
standalone Ice1r and Ice1ra.

### Requirement: The protocol's fields can be written

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

On request, Polaris writes the protocol's ocean fields (Sect. 3.3) on its
2 km by 5 m output grid.

### Requirement: E3SM runs report their performance

Date last modified: 2026/11/04

Contributors: Xylar Asay-Davis, Claude

Polaris reports each E3SM run's throughput over model time, the share of
each model in its run time, its cost and its memory, so that a long run
shows whether it slows down or grows.

## Algorithm Design

### Algorithm Design: The analysis reads runs it did not set up

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

An **E3SM run** is given by its case directory ([D2](#decisions)). The
case's XML gives the run and archive directories, the compset (and so
MALI's mode) and both models' initial conditions, which hold the meshes,
the initial geometry and MALI's bed. The run's streams files give each
stream's files, found in the archive or the run directory. A **standalone
run** is given by its forward step's work directory, read the same way.
Both write monthly means ([D3](#decisions)) and daily global statistics,
which only the first-month comparison uses. IceOcean1ra continues from
IceOcean1r's restart and has no initial conditions of its own, so it reads
IceOcean1r's.

Each run contributes its monthly means in a configured range of years,
and its steps are keyed by the months it has, so analyzing more of a run
adds steps rather than replacing them, as in the ocean analysis. Maps
and sections average the period's last 6 months for Ocean0, as the
protocol's tuning does (Sect. 3.2.1), and its last 12 otherwise.

### Algorithm Design: The runs are diagnosed

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

**Melt.** With $F$ the land-ice freshwater flux per unit cell area, $f$
the floating fraction, $A$ the cell area and $\rho_{fw} = 1000$ kg m⁻³,
the total melt flux is $\sum F A$ and the mean melt rate
$\sum F A / (\rho_{fw} \sum f A)$, since partly floating cells melt only
over their floating fraction. $f$ comes from the initial condition in
Ocean0–2 and from the monthly means where the geometry moves
([D7](#decisions)). The thermal and haline driving are boundary-layer less
interface values (Sect. 3.3), averaged with the friction velocity weighted
by $f A$. As in the protocol's tuning (Sect. 3.2.1, Eq. 37), the mean melt
rate is also taken where the draft is deeper than 300 m, and, as in Yung
et al. (2026), in 20 m bins of draft.

**Circulation and water masses.**

- The barotropic streamfunction is `mpas_tools`', with the outer boundary
  at zero.
- The overturning streamfunction in $x$–$z$ accumulates from the top the
  exact transport across lines of constant $x$
  (`polaris.ocean.overturning`), with each layer's transport spread over
  fixed bins of $z$ by overlap.
- Each streamfunction's strength is its range under the ice. Both use
  monthly means of velocity and thickness, whose product differs a little
  from the mean transport.
- The open ocean is the region between the ice front and the restoring
  region, $x \ge 790$ km, leaving out the strips along the side walls
  west of the ice front. The strongest gyre there is the barotropic
  streamfunction of largest magnitude, with its sign.
- Sections along $y = 40$ km and $x = 520$ km use `mpas_tools`' transects,
  drawn with the draft and bed; top and bottom values use
  `polaris.ocean.vertical`.
- Mean temperature is $\sum h T A / \sum h A$, likewise salinity, and the
  volume is $\sum h A$.

**Thin film.** The dry area is the area under grounded ice whose column is
within twice the minimum thickness of its active layers, read from the
run's namelist. The open-ocean SSH is its mean where there is no land ice.

**Open-ocean SSH.** With no difference in pressure at the seafloor from
the restoring region, a column's SSH relative to the restoring region's
mean, $\eta_r$, would be
$\eta - \eta_r = \sum_k (\rho_r(k) - \rho(k))\, h(k) / \rho_0$, where
$\rho_r(k)$ is the restoring region's mean in-situ density in layer $k$
and $\rho_0$ is the run's `config_density0`. Each month gives the means
over the open ocean of the SSH above $\eta_r$, of this height and of the
residual between them. The residual is the excess pressure at the
seafloor, as a height of water. Gyres in the open ocean raise or lower it
by their geostrophic bottom pressure, so it is read beside the strength
of the strongest gyre and beside the geostrophic height of the flow near
the seafloor, $\eta_g = f \psi_b / (g\, \Delta z)$, where $\psi_b$ is
the streamfunction of the flow in a slab of thickness $\Delta z$ (100 m by
default) above the seafloor. The mean of $\eta_g$ over the open ocean,
relative to its mean over the restoring region, is the gyres' share. The
residual less it is a uniform offset from the restoring region, which
closed gyres cannot make, since $\psi_b$ is zero on every wall.
Ageostrophic flow near the seafloor and the choice of slab make the split
good to about 0.1–0.2 cm.

**Grounding-line band.** A band cell is one where MALI's floating fraction,
as the ocean receives it, exceeds the coupling's minimum but the ocean's
own floating fraction is zero, so the ocean holds the column at the film.
Each month gives the band's share of MALI's floating area,
$\sum_{band} f_g A / \sum f_g A$, and an estimate of the melt missed,
$\sum_{band} f_g A\, m_n / \sum m A$, where $f_g$ is MALI's floating
fraction, $m$ the melt flux per cell area and $m_n$ the melt flux per
floating area of the nearest melting cell. Cells next to the grounding line
melt less than their neighbors, so the estimate is likely an upper bound.
Subgrid wetting and drying is expected to make the band hold water and
melt.

**Ice sheet.** From MALI's thickness $H$ and the static bed $b$,
$h_{af} = H + (\rho_{sw}/\rho_i) \min(b, 0)$. The volume above flotation is
$\sum \max(h_{af}, 0) A$, and the grounded area sums $A$ where there is
ice and $h_{af} > 0$. The grounding line is the set of points between
grounded and floating cells where $h_{af}$, interpolated linearly, is zero:
the [MISMIP+ diagnostics](mismip_plus.md) with the densities as arguments.
Ocean maps draw MALI's grounding line over the edge of the ocean's floating
region, and map glc's remapped floating fraction against the ocean's where
E3SM writes it.

**Publishing.** Each step that plots writes a netCDF file beside each plot
and a manifest fragment describing both. A final step copies the plots into
a gallery, and the netCDF files only when asked, as the ocean analysis
does.

### Algorithm Design: Exchanged fluxes are checked for conservation

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

**Coupler budgets.** With `BUDGETS=TRUE`, the coupler's log holds the net
water and heat budgets for each month, each year and the run so far. The
exchange between the ocean and MALI is the `wpolar` and `hpolar` row, in
the ocean's and glc's columns. Polaris reads every table into a time series
and reports each column and their sum. The values are global means printed
to 8 decimals. For a melt of 50 Gt yr⁻¹ in this domain, the water budget
should print near $3\times10^{-3}$ in its units of $10^{-6}$ kg m⁻² s⁻¹,
about 6 significant figures. The first case with budgets confirms what the
check can resolve. At an initial start, the driver skips the ocean's first
coupling interval, but the coupler still books the ocean's initial export
for it in the ocean's column, and glc never receives it. The budgets that contain the start are
marked and reported apart from the closure.

**Each model's own output** ([D6](#decisions)). In IceOcean1r and
IceOcean1ra, the net flux the ocean sends, $\sum (F + F_{fr} - F_{ns}) A$,
is compared with the melt MALI applies, from MALI's global statistics at
every time step. $F_{fr}$ is the frazil flux under the land ice, and
$F_{ns}$ the flux the ocean keeps where MALI floats less than the
coupling's minimum. MALI's step over each glc coupling interval applies
the coupler's average of what the ocean sent over the same interval, as
the first coupled run shows. So each of the ocean's months, and each day
where it writes daily means, is compared with the same period in MALI.
Without $F_{ns}$ in the ocean's output, the cells it sends from are estimated from the mean
floating fraction MALI gives it, and the comparison is labeled as an
estimate. A period that contains the initial start, or that MALI's steps
do not yet cover, is reported apart.

### Algorithm Design: Runs are compared with each other

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

- **E3SM against standalone.** The runs share a mesh, so they are compared
  cell by cell. Time series are overlaid, daily over the first month and
  monthly after. Each time-mean field's difference is mapped with
  `mosaic`, and a table lists its area-weighted RMS and largest value.
- **Across experiments.** Time series at one resolution are overlaid.
- **Across resolutions.** Time series at 4 and 2 km are overlaid. Maps and
  sections are drawn side by side on each mesh, with one color scale and
  no remapping.

### Algorithm Design: Runs are compared with published results

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

**Yung et al. (2026)** ([D5](#decisions)). Every model's COM Ocean0–2
submission, in monthly means on the protocol's grid, is downloaded. Melt,
temperature and salinity series are plotted over the ensemble's range, with
each model as a thin line and MPAS-Ocean's 2019 entry marked. Maps of melt
and its drivers, melt against draft and the streamfunctions' strengths are
shown beside the ensemble's. Runs without the COM physics, including every
E3SM run, are labeled as such.

**Cornford et al. (2020).** The grounding line on the centerline, volume
above flotation and grounded area of IceOcean1r and IceOcean1ra are
plotted with the Cornford et al. (2020) Ice1r and Ice1ra entries and with
MALI's standalone runs, against the years since each experiment started.
Volume above flotation and grounded area come from each MALI run's global
statistics. MALI writes history only at the end of a step, so a
standalone run for the first years forces its steps to end on each month,
and is labeled as such. The primary standalone reference is built from the
coupled run's MALI source. Runs with another MALI version are secondary
lines.

**MISOMIP1's results.** A paper on MISOMIP1's results (Seroussi et al., in
preparation) will serve IceOcean1r and IceOcean1ra as Yung et al. (2026)
serves Ocean0–2. Comparing with it is follow-up work, once its data are
available.

**The centerline transect.** An animation of the x–z section along the
channel's centerline shows the two models evolving together: the bed,
MALI's ice with its draft and grounding line, and the ocean beneath it,
with its thermal driving or temperature and its velocity. It needs daily
MALI thickness and daily ocean means of the tracers and velocity, which
the IceOcean cases write once their year-long runs are set up. Building it
is planned work, once such a run exists.

### Algorithm Design: The protocol's fields can be written

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The protocol's grid gets latitude and longitude from the MISOMIP meshes'
projection, and a SCRIP file. Fields are remapped conservatively from the
ocean's SCRIP file. Those under the ice are normalized by the remapped
floating fraction, the others by the remapped ocean fraction. Sections are
averaged over each 5 m bin by overlap with each layer, and the overturning
streamfunction is computed directly on the protocol's $x$ and $z$. Names
and units are the protocol's.

### Algorithm Design: E3SM runs report their performance

Date last modified: 2026/11/04

Contributors: Xylar Asay-Davis, Claude

Each job of a run, or segment, leaves CIME's timing summary and timer
statistics, a coupler log and, with memory profiling, the driver's memory
profile. All carry the segment's LID.

- Throughput is the simulated years per day of each segment, from its
  summary, and of each model day, from the coupler's daily wall-clock
  stamps.
- Each segment's run time splits into the ocean's time integration, its
  analysis members and the rest of the ocean; MALI's finite-element grid
  build, the rest of its velocity solve and the rest of MALI; and the
  coupler and driver, the rest of the total. The coupler's communication
  overlaps the models' run times, so it is not a part of its own.
- Cost is the summary's processor hours per simulated year. Start-up and
  finishing times come from the summary, and queue waits from Slurm.
- Memory is the coupler's root task's, from its log, and its node's, from
  the profile. Each segment starts new processes, so each is its own line,
  and growth within a segment is told apart from growth over the run.

## Implementation

### Implementation: The analysis reads runs it did not set up

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The tasks are in a new `e3sm/analysis` component ([D1](#decisions)):

```none
e3sm/analysis/<mesh_name>/misomip/<experiment>     one experiment
    e3sm/diagnostics_<months>, e3sm/plots_<months> shared steps
    standalone/diagnostics_<months>, standalone/plots_<months>
    comparison_<months>
    e3sm/conservation_<months>
    published_<months>
    protocol_fields_<months>                       only if enabled
    publish
e3sm/analysis/<mesh_name>/misomip/experiments      all experiments
e3sm/analysis/misomip/resolutions/<experiment>     4 and 2 km
e3sm/analysis/misomip/yung2026/<experiment>        shared download
```

`<months>` names the months a run has, such as `0001-01_0020-12`, joined
for steps that read two runs.

Each run is a config option, and steps are added only for configured runs:

```cfg
[misomip_analysis_misomip-o4km-li1km]
ocean0_e3sm_case = /home/<user>/e3sm_cases/misomip/<case>
ocean0_standalone = <work dir>/ocean/planar/misomip/misomip-o4km-li1km/ocean0/forward
```

As in the ocean analysis tasks, `configure()` rebuilds the steps once the
user's config is read.

`polaris/e3sm/analysis/case.py` reads a case's XML without CIME, expanding
references to other case variables, and finds a stream's files.
`polaris/streams.py`, which reads streams files from packages, is extended
to read a run's streams file from a path and to find the files a stream's
filename template matches, with the date in each name.

### Implementation: The runs are diagnosed

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

- `polaris/ocean/ice_shelf/diagnostics.py` (new): melt, driving and the
  thin film, on MPAS-Ocean's names with or without the
  `timeMonthly_avg_` prefix.
- `polaris/ocean/overturning.py`: spreading layer transport over bins of
  $z$.
- `polaris/landice/`: a public module of the ice-sheet diagnostics, made
  on the MISMIP+ branch, whose own diagnostics become thin wrappers.
- `polaris/viz/planar.py`: side-by-side and difference panels, and lines
  along mask boundaries for grounding lines and ice fronts.
  `polaris/viz/time_series.py` (new): overlaid series with an ensemble
  range.
- `polaris/analysis/`: the ocean analysis's manifest methods and `Publish`
  step, as a mixin and a step any component can use, moved in a separate
  change from main ([D9](#decisions)). Each MISOMIP task ends with a
  `publish` step that copies its plots, and with `copy_netcdf` their data,
  into `[misomip_analysis] output_path`.

### Implementation: Exchanged fluxes are checked for conservation

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

`polaris/e3sm/analysis/budgets.py` parses the budget tables of a coupler
log, compressed or not, into a dataset over period, row and component,
converted to kg s⁻¹ and W with E3SM's Earth radius. The MISOMIP cases set
`BUDGETS=TRUE` ([MISOMIP inputs design](misomip_e3sm_init.md)). IceOcean's
cases add the flux the ocean keeps to its monthly means and write its daily
means of the fluxes exchanged with MALI. MALI's global statistics, written
every time step, hold the melt it applies.

### Implementation: Runs are compared with each other

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

A `comparison` step per experiment, and the `experiments` and
`resolutions` tasks, read the diagnostics steps' files, never the model
output.

### Implementation: Runs are compared with published results

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The `yung2026` step downloads each model's public files from the Open
Science Framework, by the identifiers in the paper's Table 3, into the
ocean database. A README beside them gives the paper's citation, each
registration's identifier and its license. Where a model gives several
Ocean0 runs, the step takes the one tuned to the protocol's target. For
IceOcean, the `published`
step reaches the MISMIP+ tasks' download of Cornford et al. (2020) and
their Ice1r and Ice1ra output through public accessors. Until those
exist, `[misomip_analysis_mismip_plus]` names the work directories of a
`cornford2020` step and of the forward steps.

### Implementation: The protocol's fields can be written

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

`[misomip_analysis] write_protocol_fields = False` by default. When true,
each experiment gets a `protocol_fields` step, and each mesh gets the map to
the protocol's grid as a `MappingFileStep`.

### Implementation: E3SM runs report their performance

Date last modified: 2026/11/04

Contributors: Xylar Asay-Davis, Claude

`polaris/e3sm/analysis/performance.py` parses the timing summary, the
timer statistics, the coupler's stamps and memory records, the memory
profile and `sacct`'s accounting ([D8](#decisions)).
The MISOMIP tasks' `performance` step, added for every E3SM run, links each
segment's files at setup and plots them. Where `sacct` is missing, queue
waits and Slurm's memory are left out.

## Testing

### Testing and Validation

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

- Unit tests read a case's XML and a streams file copied from the first
  E3SM runs, parse budget tables from a coupler log, check melt totals and
  means on a small planar mesh against hand computation, and check that
  spreading transport over bins of $z$ conserves it.
- On the existing 4 km Ocean0 and Ocean3 runs, the monthly-mean melt
  flux matches the mean of the daily statistics, the overturning is near
  zero at the seafloor, and Ocean3's grounding line from MALI's history
  matches the data-mode input's.
- E3SM's 4 km Ocean0 runs for a month with budgets and is compared with the
  standalone run on the same inputs. Each difference is traced to the
  coupler or to a recorded configuration difference, and the budgets'
  residual is reported. Ocean0–2 then run at 4 and 2 km, for lengths agreed
  once the first month's cost is known.
- The comparison with Yung et al. (2026) is developed against short runs.
  Twenty-year standalone COM runs are not part of this work.
- With protocol fields on, 4 km Ocean0's remapped total melt flux matches
  the native one to the map's area error.
- Unit tests parse a timing summary, timer statistics, coupler logs and a
  memory profile with the formats of the first coupled year's segments,
  and check that the parts of a segment's run time add up to its total.
- No task joins a suite, since each needs a run's output.

## Decisions

### D1: The tasks are in a new `e3sm/analysis` component

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The tasks read both models' and the coupler's output, so they belong to
neither `ocean` nor `landice`. The component mirrors `e3sm/init`.

Rejected: steps in the `e3sm/init` tasks, which build inputs; and `ocean`
tasks, which must not import from `e3sm` or read the coupler's log.

### D2: Runs are found from their own description

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The user gives the case or work directory. The case's XML and the run's
streams files say where each stream's files are.

Rejected: a filename template per stream in the config, which can be
mistyped and fails late, as "no files found".

### D3: Standalone runs write monthly means

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The standalone forward writes `timeSeriesStatsMonthly` with the fields of
E3SM's monthly means, so one code path reads both runs. The protocol also
asks for monthly means.

Rejected: comparing E3SM's monthly means with daily snapshots, which makes
every comparison depend on sampling.

### D4: The analysis works on the models' meshes

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Diagnostics and maps are on the models' own meshes. The protocol's fields
on its grid are optional.

Rejected: the protocol's grid as the analysis's product, which interpolates
every run before anyone looks at it.

### D5: Published comparisons use every COM model

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Every model's COM Ocean0–2 submission is plotted. E3SM runs, which use
E3SM's physics, are plotted against them and labeled as not COM, as
context rather than validation.

### D6: Model-side conservation only where MALI evolves

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The melt the ocean sends is compared with the melt MALI applies only in
IceOcean1r and IceOcean1ra. Ocean0–4 rely on the coupler's budgets.

Rejected: the coupler's history times model areas, which repeats the
coupler's own view, since the area corrections are applied on import;
MALI's history of flux averages, which MALI resets at each glc coupling;
and a MALI change that records the melt static and data-mode MALI receive.
Those modes do not use it, so an error in MALI's import cannot affect
their runs.

### D7: E3SM's monthly means carry the ocean's geometry

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Where the geometry moves, the land-ice fraction, floating fraction,
pressure and draft come from E3SM's monthly means, through a general
FAnSSIE change that adds them whenever ice-shelf coupling with glc is on.
The draft is `landIceDraftForSsh`, computed from the imported pressure,
since `landIceDraft` stays at the initial condition in coupled runs.

Rejected: a `streams.ocean` in the cases' user mods, which would replace
the file E3SM writes and drift from it.

### D8: General diagnostics live in the frameworks

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

Diagnostics and plotting helpers go in the `ocean`, `landice`, `e3sm` and
`viz` frameworks. The MISOMIP tasks hold only configuration and the steps
that call them.

Rejected: code within the tasks, as in Compass's ISOMIP+ steps.

### D9: Publishing becomes component-neutral in its own change

Date last modified: 2026/11/01

Contributors: Xylar Asay-Davis, Claude

The ocean analysis's manifest methods and `Publish` step move to
`polaris/analysis/` in a change of their own, reviewed separately and
built on the ocean analysis's copying of products into the gallery. This
work builds on it.
