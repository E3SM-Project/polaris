(design-ocean-analysis)=

# Ocean Analysis in Polaris

date: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

```{note}
This is an umbrella design document.  It records the long-term goals and the
shared vocabulary for ocean analysis in Polaris, and it points to the more
detailed design documents that describe individual pieces of that capability.
Most sections below are deliberately sketches that will be filled in as each
piece is designed.  The one piece that is designed in detail today is the
initial set of Omega analysis capabilities described in
{ref}`design-ocean-analysis-initial`.
```

## Summary

Polaris can build meshes, create initial conditions, run Omega and MPAS-Ocean,
and visualize the output of the tasks it runs.  What it cannot do today is
analyze a simulation it did not run.  For MPAS-Ocean and MPAS-Seaice, that role
is filled by MPAS-Analysis, which is driven by zppy as part of the standard
E3SM post-processing workflow.  Omega has no equivalent.

The capability designed in this family of documents is a general-purpose
analysis capability in Polaris: given a completed Omega (or MPAS-Ocean)
simulation and a config file describing it, Polaris produces a set of
diagnostic plots and the intermediate data products behind them.  The
long-term goal is that this capability grows to cover the ocean analysis that
E3SM developers rely on today, and that it is ultimately driven by zppy in the
same way MPAS-Analysis is.

The near-term goal is much narrower and is driven by a concrete commitment: the
E3SM Ocean Team has offered to deliver a first set of analysis capabilities for
Omega's initial coupled runs by September 15, 2026.  That deliverable is
designed in {ref}`design-ocean-analysis-initial`.

Success for this umbrella design is that the near-term deliverable is built on
foundations that the longer-term capability can reuse rather than replace:
shared depth-selection and integration kernels, a suite that can be pointed at
an arbitrary simulation, plots that always come with the data behind them, and
a clean separation between what Omega computes in situ and what Polaris
computes offline.

## Background

### What Polaris does today

Polaris has a number of visualization steps, but each of them is tied to a task
that produced the data it plots.  `Viz` and `StatsAnalysis` in the
`realistic_global` tasks read output from a `forward` step in the same task.
The `customizable_viz` task is the closest thing to a general-purpose analysis
tool: it takes a mesh file and a data file as config options and plots
horizontal fields and transects from them.  It is limited to a single file, a
single time index, and a single vertical level, and it has no notion of
climatologies, time series, or integrated quantities.

The framework pieces that a broader analysis capability needs are, however,
largely in place: shared steps (see [Shared steps](shared_steps.md)), config
files supplied by the user at setup time, the Omega/MPAS-Ocean name mapping
in `polaris.ocean.model`, spherical plotting in `polaris.viz`, remapping
infrastructure in `polaris.remap`, and vertical-coordinate helpers in
`polaris.ocean.vertical`.

### What MPAS-Analysis does today

MPAS-Analysis provides roughly a hundred analysis tasks for MPAS-Ocean and
MPAS-Seaice: climatology maps compared against observational climatologies,
regional and global time series, transects, Hovmoller diagrams, transports,
overturning circulation, and more.  It has its own task/subtask framework, its
own parallel-execution model, its own caching scheme for climatologies and
region masks, and its own HTML-gallery generation.

### Why this is not a port of MPAS-Analysis

Analysis capabilities in Polaris are intended to be written from scratch with
Polaris and Omega in mind, using MPAS-Analysis as a scientific reference for
what each diagnostic means, rather than as a source of code.  The reasons:

- **Framework duplication.**  MPAS-Analysis's task, subtask, and parallelism
  machinery predates and duplicates Polaris's task, step, and suite machinery.
  Porting the tasks means porting or shimming that machinery too.
- **Model conventions.**  MPAS-Analysis is built around MPAS-Ocean's output
  conventions --- `xtime`, `timeSeriesStatsMonthly_avg_*`, and the analysis
  members that produce them --- not merely around MPAS-Ocean's variable names.
  Polaris also uses MPAS-Ocean variable and dimension names as its internal
  standard, but it reaches them by translating Omega's names on read, so the
  rest of the code is unaware of the difference.  Omega's output differs from
  MPAS-Ocean's in time metadata, in the in-situ analysis that produces it, in
  its pseudo-thickness vertical coordinate, and in the fact that it carries
  TEOS-10 conservative temperature and absolute salinity.
- **Division of labor.**  Omega's Analysis module computes diagnostics in situ
  (see below).  Several diagnostics that MPAS-Analysis computes offline from
  high-volume output will instead be read directly from Omega output, which
  changes the shape of the analysis code substantially.
- **Accumulated scope.**  A large fraction of MPAS-Analysis exists to support
  observational comparisons and regional diagnostics that are not needed in the
  first delivery, and that we would want to redesign rather than reproduce.

The intent is not to replace MPAS-Analysis.  MPAS-Seaice analysis continues to
be delivered through zppy's MPAS-Analysis, and MPAS-Ocean analysis will
continue to be available there for as long as it is useful.

### Division of labor with Omega's in-situ Analysis module

Omega's Analysis module computes diagnostics during the simulation and writes
them to output streams, with both temporal reduction (e.g. monthly means) and
instantaneous snapshots.  The initial delivery provides a `GlobalStats` group,
and a meridional overturning circulation (MOC) group is in development.  Omega
requires that analysis output be usable by Polaris for post-processing.

The dividing line we assume throughout this family of documents is:

- **In Omega** belong diagnostics that require the model state at every time
  step, or that would require writing prohibitively large volumes of output to
  compute offline: global statistics, mixed-layer depth, overturning
  streamfunctions, eddy statistics, and other quantities that are nonlinear in
  the instantaneous state.
- **In Polaris** belong diagnostics that can be computed from monthly means
  without loss: climatologies, depth slices, depth integrals of linear
  quantities, area integrals, time series assembled from per-period reductions,
  observational comparison, and everything to do with plotting.

Where a diagnostic could go either way, the initial preference is to compute it
in Polaris, because Polaris code is faster to write and change, and to migrate
it into Omega later if the required output volume or the loss of accuracy from
working with monthly means becomes a problem.

## Roadmap

| Phase | Target | Content |
| --- | --- | --- |
| 1 | September 15, 2026 | Climatology maps, ocean heat content, global-stats time series, MOC plot; run manually.  See {ref}`design-ocean-analysis-initial`. |
| 2 | End of CY2026 | A more complete zppy/MPAS-Analysis-style workflow for Omega, including observational comparison, integration with zppy, and concurrent execution of independent analysis under Polaris task parallelism. |
| 3 | Beyond | Regional analysis, transports and transects, run-to-run comparison, and parity with the ocean tasks E3SM developers rely on today. |

Phase 1 explicitly does not include integration with zppy.  During Phase 1, the
analysis of Omega output is run by hand and made available to the coupled group
within several days of each simulation period completing.

## Requirements

### Requirement: analysis of simulations Polaris did not run

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall be able to analyze a completed Omega or MPAS-Ocean simulation
that it did not set up or run.  All information about the simulation --- where
its output lives, which mesh it used, which period to analyze, and which fields
to analyze --- shall come from a config file the user supplies at setup time.
Setting up and running the analysis shall not require a model build.

This requirement is met in Phase 1; see the `analysis-suite` requirement in
{ref}`design-ocean-analysis-initial`.

### Requirement: plots are always accompanied by their data

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Every plot the analysis produces shall be accompanied by a netCDF file
containing the data that were plotted.  Intermediate data products that are
expensive to recompute shall be written to netCDF so that later steps, later
runs, and other tools can use them without repeating the computation.

This requirement is met in Phase 1; see the `data-products` requirement in
{ref}`design-ocean-analysis-initial`.

### Requirement: analysis is written against Polaris's naming standard

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Analysis shall be written against MPAS-Ocean variable and dimension names,
which are Polaris's internal standard, and shall rely on
`OceanIOStep.open_model_dataset` to translate Omega's names on read using
`polaris/ocean/model/mpaso_to_omega.yaml`.  Analysis code shall not branch on
which model produced the data in order to choose a field or dimension name; a
step that needs to do so indicates a missing entry in the mapping.  Where a
model does not provide a required field, the analysis shall report that clearly
rather than failing obscurely.

A consequence is that analysis written for Omega also works on MPAS-Ocean
output wherever the two models provide equivalent fields.  That is a useful
property, but it is not a testing strategy: MPAS-Ocean differs from Omega in
time metadata and in which analysis members produce its output, so validating
against MPAS-Ocean would exercise code paths we do not ship.  Validation is
against Omega output as Omega capabilities become available.

### Requirement: comparison with observations

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The analysis shall be able to compare simulated climatologies against
observational climatologies, producing model, observation, and bias maps
together with summary error metrics.

Comparison shall happen **on the MPAS mesh**: observational data sets are
remapped onto the mesh and compared there, rather than the model being remapped
onto a lat-lon comparison grid.  Model output is therefore never interpolated
away from the grid it was computed on, and the error metrics are area-weighted
sums over model cells.

*Remaining details to be added.*  Open topics include: which observational data
sets to support first (WOA23, and the standard MPAS-Analysis suite of SST, SSS,
MLD, and velocity products); where the mapping files and remapped observations
are cached, since remapping observations onto each new mesh is the expensive
part; and how the conservative temperature and absolute salinity that Omega
carries are converted for comparison with observational potential temperature
and practical salinity.

### Requirement: regional analysis, transects, and transports

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The analysis shall support diagnostics restricted to named ocean regions
(basins, marginal seas, Antarctic shelf regions) and along named transects, and
shall support transports through transects.

*Details to be added.*  Open topics include: how region masks are generated and
cached (`geometric_features` and `mpas_tools` today); whether region masks are
computed in Polaris or read from files produced elsewhere; which regional
quantities are computed in Omega in situ versus in Polaris; and how regional
time series relate to the global time series designed in Phase 1.

### Requirement: run-to-run comparison

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The analysis shall be able to compare two simulations against one another,
producing difference maps and overlaid time series, in the way that
MPAS-Analysis compares a run against a control run.

*Details to be added.*

### Requirement: presentation and provenance

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The analysis shall present its results in a form that a reviewer can browse
without a filesystem tour, and shall record enough provenance that any plot can
be traced back to the simulation, the date range, the code version, and the
config options that produced it.

Phase 1 delivers the substrate: a staging tree, keyed by product and date
range, into which every plot and its netCDF are published, separate from the
Polaris work directories where the computation happens.  Results accumulate
there across repeated analyses of different ranges.  See the
`repeated-analysis` requirement in {ref}`design-ocean-analysis-initial`.

*Details of the presentation layer to be added.*  What is missing is the
gallery or index over that tree, comparable to MPAS-Analysis's HTML output.
Polaris already records provenance for a setup in `polaris/provenance.py`.

### Requirement: workflow integration

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Analysis of Omega output shall eventually be launched by zppy as part of the
standard E3SM post-processing workflow, in the same way MPAS-Analysis is today.

*Details to be added.*  In Phase 1 this requirement is explicitly deferred: the
analysis is run by hand by the Ocean Team.  Open topics include what the zppy
interface to Polaris looks like, how the analysis suite is chunked over
simulation years, and how Polaris job scripts interact with zppy's.

### Requirement: concurrent execution of independent analysis

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

An analysis suite is a collection of independent, non-MPI Python steps, which
is precisely the workload that Polaris's task-parallelism work targets.  The
analysis capability shall be able to take advantage of that concurrency as it
becomes available, and shall not be written in ways that make its steps
ineligible for it.

Task parallelism is designed separately, in the `task_parallelism` family of
design documents --- an umbrella plus one document per phase --- developed on
the task-parallelism branch.  Its Phase 2 enables concurrent execution of
eligible non-MPI steps across a multi-node allocation, with non-MPI steps
eligible by default and step authors marking a step unsafe only when it relies
on shared mutable state, external side effects, or uncontrolled process
launching.  That phase is what analysis stands to gain from, and it lines up
with Phase 2 of this roadmap.

Three consequences for the analysis design:

- **The Phase 1 products already overlap.**  Climatology maps, ocean heat
  content, global stats, and the MOC plot are four independent tasks, so they
  can run concurrently as soon as the capability lands, with no changes to
  them.
- **Two Phase 1 details need checking against the eligibility rules** rather
  than being assumed safe: the climatology step launches `ncclimo`, which
  itself forks up to twelve background processes, and every plotting step
  symlinks its results into a shared staging tree.  Neither looks like a
  problem --- products stage into disjoint directories, and the climatology is
  a shared step so only one instance of it exists --- but "launches
  subprocesses" and "writes into a shared location" are exactly the properties
  the eligibility mechanism is meant to catch.
- **The per-year decomposition is the real prize, and Phase 1 already has
  it.**  Vertically integrated heat content and offline mixed-layer depth are
  computed by one shared step per simulation year, a structure Phase 1 adopts
  for reuse across date ranges rather than for parallelism.  Those steps are
  independent, non-MPI, and numerous --- forty of them for a forty-year record
  --- so they are exactly the workload Phase 2 of task parallelism is built to
  overlap, and they should benefit with no restructuring at all.

*Further details to be added* once the analysis workload has been profiled and
task parallelism is available to measure against.

### Requirement: scalability and restartability

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The analysis shall handle multi-decade simulations on high-resolution meshes
within the resources of a single compute node where possible, and shall be able
to extend an existing analysis with additional simulation years without
recomputing what it has already computed.

Phase 1 establishes the pattern the rest of the capability should follow:
**every expensive computation is decomposed into a per-year product keyed by
the year rather than by the requested date range**, and given its own shared
step, so that it is computed once and reused by every later analysis.  Reuse is
then not a caching mechanism of our own but a consequence of Polaris's ordinary
shared-step and step-completion behavior.  Phase 1 also streams over monthly
files rather than loading a whole record at once.

*Remaining details to be added*, in particular how analysis is chunked across
compute nodes.  Running the per-year products concurrently is covered by the
task-parallelism requirement above.

## Algorithm Design

*To be added as individual capabilities are designed.*  Algorithm designs for
the Phase 1 capabilities are in {ref}`design-ocean-analysis-initial`.

## Implementation

### Implementation: code organization

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The intended organization, established in Phase 1 and expected to hold as the
capability grows:

- **Shared, dependency-light kernels** live in leaf modules under
  `polaris/ocean/` alongside `conservation.py`, `rpe.py`, and
  `surface_pressure.py`, or beside related helpers in an existing subpackage.
  Phase 1 adds `polaris/ocean/vertical/elevation.py` (elevation selection and
  layer-overlap weights) and `polaris/ocean/heat_content.py`.  These are
  ordinary functions on `xarray` objects with no dependence on Polaris steps,
  so they can be unit tested directly and reused by any step.
- **Analysis steps and tasks** live under `polaris/tasks/ocean/analysis/`.
- **Suites** that run analysis live in `polaris/suites/ocean/`, named for the
  model they target, as `omega_analysis` is.
- **Plotting primitives** live in `polaris/viz/`, extended as new plot types
  are needed rather than duplicated inside analysis steps.

Analysis asks for something no existing task needed --- the same simulation
analyzed repeatedly over different date ranges, reusing what does not depend on
the range --- but it turns out to need no framework changes to get it.  The
mechanism is the one the cosine bell task family already uses for resolutions:
a task rebuilds its step list in `Task.configure()`, which runs after the
user's config has been merged, so step subdirectories can be keyed by date
range, and expensive per-year work can be a shared step per year created with
`Component.get_or_create_shared_step()`.  Re-running and reuse then both follow
from ordinary step-completion behavior.  Later phases should reach for this
pattern before reaching for new framework capabilities.

### Implementation: items deferred from Phase 1

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Things that Phase 1 knowingly does the simpler way because of its September 15
deadline, recorded here so that they are picked up rather than forgotten.  Each
is explained in context in {ref}`design-ocean-analysis-initial`.

- **Use the TEOS-10 heat capacity for ocean heat content.**  Omega carries
  conservative temperature, for which $\rho_0 c_p^0 \Theta$ with
  $c_p^0 = 3991.86795711963$ J kg⁻¹ K⁻¹ is the *definition* of heat content
  rather than an approximation.  That constant is not in the Physical Constants
  Dictionary, and adding it is not achievable by September 15, so Phase 1 uses
  the PCD's `seawater_specific_heat_capacity_reference` (3996 J kg⁻¹ K⁻¹)
  instead --- a 0.1% systematic offset.  The follow-up is to add $c_p^0$ to the
  PCD and switch to it.
- **Replace the offline mixed-layer depth fallback**, if it is what ships, with
  Omega's in-situ density-threshold diagnostic.  A mixed-layer depth derived
  from monthly-mean profiles cannot represent deep winter mixing events and
  cannot produce a monthly maximum at all.
- **Compute the ocean heat content climatology from per-month integrals**
  rather than from a climatology of conservative temperature, if the neglected
  $\overline{\Theta' h'}$ covariance term proves large enough to matter.
- **Regional overturning**, in particular the Atlantic MOC and the standard
  maximum-AMOC-near-26.5°N metric, which arrives with the regional analysis
  described in the requirements above.

### Implementation: design documents in this family

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

- {ref}`design-ocean-analysis-initial` --- the Phase 1 deliverable: monthly,
  seasonal, and annual climatologies from Omega monthly means; global maps at
  selected elevations; ocean heat content over elevation ranges as maps and as
  a global time series; time series from Omega's `GlobalStats` output; and a
  latitude-elevation plot of the global MOC.

*Additional documents to be added for Phases 2 and 3.*

## Testing

### Testing and Validation: umbrella

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Two testing strategies apply across the whole capability and are established in
Phase 1:

1. **Unit tests on the shared kernels against analytic answers.**  Elevation
   selection, layer-overlap weights, integrals, and averaging are pure
   functions of `xarray` inputs and are tested on small synthetic columns whose
   correct answers can be written down.  These are the parts where a silent
   error would corrupt every plot downstream, they are cheap to test, and an
   analytic answer is a stronger reference than another code's output.
2. **Staged validation against Omega output.**  Each diagnostic is run against
   real Omega output at low resolution as soon as the Omega capability it
   depends on lands, rather than waiting for the full set.  This front-loads
   discovery of mismatches between what the analysis assumes and what Omega
   actually writes, which is where the schedule risk lives.

We do not validate by running the analysis on MPAS-Ocean output.  It would
exercise code paths --- different time metadata, different analysis members ---
that we do not ship for Omega, giving false confidence.  Where the *magnitude*
of a diagnostic needs a sanity check, published MPAS-Analysis results for E3SM
simulations are a reasonable thing to eyeball against, but that is a science
judgment rather than an automated test.

Analysis suites are user-facing and are not intended for the `pr` or `nightly`
suites: they require a completed simulation as input, and their cost is
dominated by that simulation rather than by anything a PR could break.
Regression coverage comes from the unit tests plus, once Omega can write
monthly means, a short end-to-end smoke test on a low-resolution run.
