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

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Polaris shall be able to analyze a completed Omega or MPAS-Ocean simulation
that it did not set up or run.  All information about the simulation --- where
its output lives, which mesh it used, which period to analyze, and which fields
to analyze --- shall come from a config file the user supplies at setup time.
Setting up and running the analysis shall not require a model build.

**Wherever the simulation already describes itself, Polaris shall read that
description rather than ask the user to restate it.**  A completed Omega run
has a configuration file that names its mesh, its output streams and the
file-name templates and reduction periods of each, so the intended default is
that the user points at that file and Polaris derives what it can.  Config
options naming individual file-name templates remain, as overrides and for
simulations whose configuration is unavailable or in another form, but they are
not what a user should have to fill in.

The reason is not brevity.  Anything the user restates is something they can
restate wrongly, and a mis-typed file-name template fails as "no files found"
long after setup, which is among the least informative ways for this analysis
to go wrong.  Reading the simulation's own configuration also means the
analysis cannot silently disagree with it about what was written.

This is the principle MPAS-Analysis already works on, locating output by
reading the MPAS-Ocean and MPAS-Seaice streams files rather than asking the
user where each file lives.  The experience there is the argument for it: a
known-good pattern with a decade of use, not an invention of this design.  What
differs is only the file being read, Omega's configuration in place of a
streams file.

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

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

The analysis shall present its results in a form that a reviewer can browse
without a filesystem tour, and shall record enough provenance that any plot can
be traced back to the simulation, the date range, the code version, and the
config options that produced it.

By principle 1, presentation is the job of the staging tree and not of the work
tree, and by principle 2 the two are connected by a manifest rather than by a
shared directory structure.  Concretely:

- **Every step writes a manifest fragment** alongside its outputs, naming each
  product it made and the facets that identify it: file, field, season,
  elevation, date range, region, group, and title.
- **A collector publishes and indexes.**  A cheap step gathers the fragments,
  publishes each product into the staging tree, and generates the index over
  it.  Because it works from the fragments rather than from directory
  structure, re-chunking the work does not disturb the output.
- **The staging tree is shallow, with descriptive filenames, plus a generated
  index.**  A gallery is generated, not navigated, and a shallow tree is easier
  to archive, to serve, and to diff between two analyses.  This follows
  MPAS-Analysis, where the experience is good.
- **Products are published by symlink** from the step that owns them, so that
  each file has exactly one owner and Polaris's output checking continues to
  work.  The staging tree is a view, not a second source of truth.

Provenance has a second job beyond presentation, introduced by principle 7: it
is what makes an inherited cache safe to inherit.  Phase 1 ships a minimal
version --- the identity of the simulation, the config options that govern the
product, and a hand-maintained version for the kernel that produced it, carried
in each cache record and refused when it does not match.  A content-addressed
scheme covering the full dependency graph is deferred; see the deferred items
below.

*Details of the index itself to be added*, including how much of
MPAS-Analysis's component/group/gallery structure to adopt.  Polaris already
records provenance for a setup in `polaris/provenance.py`.

### Requirement: pruning and archiving

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Analysis produces far more bytes than it publishes, and repeated analysis of a
growing simulation produces them again.  Polaris shall provide a way to reduce
an analysis directory to what is worth keeping, without the user having to work
out by hand which files those are.

Two distinct operations, which should not be conflated:

- **Prune to the published set.**  Keep the plots and data products that were
  published, and discard the intermediates behind them --- climatologies,
  accumulator caches, and the step directories that held them.  This is the
  operation for an analysis that is finished and wants to be archived or
  handed on: what survives is a self-contained, browsable result.
- **De-duplicate intermediates.**  Keep the analysis re-runnable, but stop
  storing the same array more than once.  Repeated analyses over overlapping
  ranges are the main source: two climatologies covering different ranges share
  no files, but every year they have in common has been read and reduced twice,
  and each range's accumulator cache repeats the months it inherited.  This is
  the operation for an analysis that is still in use on a filesystem with a
  quota.

Pruning shall be safe to the extent that it can be: it shall report what it
would remove before removing it, and removing the intermediates shall never
remove something that cannot be recomputed from the simulation output.

Two things Phase 1 does are what make this implementable later, and neither is
an accident:

- **The manifest is the definition of "published".**  Pruning to the published
  set is a set difference between what the merged manifest names and what is on
  disk, rather than a heuristic over file names.  This is the second reason the
  manifest is in Phase 1 rather than deferred with the gallery.
- **Products are published by symlink from the step that owns them**, so every
  file has exactly one owner and pruning never has to decide which of two
  copies is canonical.  The gridded accumulator caches already symlink
  inherited months forward for the same reason, which is why they are the one
  intermediate that does not duplicate across ranges.

*Details to be added.*  Open questions include whether pruning is a Polaris
command or a step, and whether an analysis pruned to its published set should
remain something `polaris serial` can be pointed at without confusion.

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

Date last modified: 2026/08/25

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
- **The largest source of concurrency is deliberately *inside* a step, not
  across steps.**  An earlier draft decomposed the expensive passes over the
  simulation record into one shared step per simulation year, and treated those
  forty-odd independent non-MPI steps as the prize for task parallelism Phase
  2.  They are now a single seeded accumulator per product, whose remaining
  months are spread over a process pool within the step.  This is a
  deliberate trade in favor of a capability that exists today, and it follows
  principle 3: steps are for caching and selection, and parallelism inside a
  step is the cheaper way to get concurrency.  The consequence for task
  parallelism is that analysis needs it less than this document previously
  claimed, and what it stands to gain is the coarse overlap of independent
  products described in the first bullet.

*Further details to be added* once the analysis workload has been profiled and
task parallelism is available to measure against.

### Requirement: scalability and restartability

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

The analysis shall handle multi-decade simulations on high-resolution meshes
within the resources of a single compute node where possible, and shall be able
to extend an existing analysis with additional simulation years without
recomputing what it has already computed.

Phase 1 establishes the pattern the rest of the capability should follow:
**every expensive computation over the simulation record is a seeded
accumulator**, as described under the organizing principles above.  One step
per product, keyed by what the user asked for, inherits whatever earlier runs
of the same product already computed, does only the difference, and writes a
complete result for its own key.  Extending an analysis from twenty years to
forty therefore costs twenty years of work.

An earlier draft got this by giving each simulation year its own shared step
and letting Polaris's step-completion behavior do the reuse.  That worked, but
it paid a step's overhead --- a directory, a pickle, a config copy, a log file
--- for a chunk no user ever asked for, and it made the completion marker the
only cache-validity check there was, so a changed kernel or a changed constant
would have been inherited silently.  An accumulator is both cheaper and safer:
see principles 6 and 7 above.

Two further properties come with the pattern rather than being added to it.  A
partially written cache in a step's own directory is a valid starting point for
a retry, which is most of what restartability asks for.  And because the
accumulator's remaining work is a set of independent units inside a single
step, it can be spread across cores with a process pool now, rather than
waiting on concurrency across steps.

Phase 1 also streams over monthly files rather than loading a whole record at
once.

*Remaining details to be added*, in particular how analysis is chunked across
compute nodes.  Overlapping independent products is covered by the
task-parallelism requirement above.

## Algorithm Design

### Algorithm Design: organizing principles

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Analysis is a combinatorial workload: products multiply over fields, seasons,
elevations, date ranges, and --- later --- regions and observational
references.  How that work is divided into steps and directories is the
decision most likely to be regretted, because it is cheap to get wrong early
and expensive to change once results have been archived and linked to.  The
principles below govern that division.  Individual design documents in this
family apply them; they do not re-litigate them.

Three questions are easy to conflate, and most of the confusion in an early
draft of {ref}`design-ocean-analysis-initial` came from answering all three
with one mechanism:

1. **What is a step?**  The unit of caching, selection, and scheduling.
2. **What is a directory level?**  The unit of navigation.
3. **What is a product?**  The unit a human archives, browses, and cites.

#### 1. Two trees, two audiences

The **work tree** is machine-facing.  One goes there to debug a step, not to
look at results, so it should be shallow, uniform, and predictable.

The **staging tree** is human-facing.  It is where plots and their netCDF files
are published, where results from repeated analyses accumulate, and what a web
interface serves.

Neither is compromised for the other.  In particular, the work tree does not
need to be browsable, and the staging tree does not need to mirror how the work
was chunked.

#### 2. Products are described by a manifest, not by their path

Each step writes, alongside its outputs, a small manifest fragment describing
every product it made: file, field, season, elevation, date range, region,
group, and title.  A cheap final step collects the fragments, publishes into
the staging tree, and generates the index.

This is the connective tissue between the two trees, and it is what allows the
work to be re-chunked later without breaking output paths, links, or the
gallery.  A path is a poor place to store metadata: it has one dimension and
the metadata has six.

#### 3. The step is the unit of load balancing; in-step parallelism fills in below it

Two kinds of concurrency are available and they are not interchangeable.

**Across steps.**  Polaris's task parallelism schedules whole steps, and only
whole steps, so a step is the smallest thing that can be sent to another node.
This is the concurrency that scales past one node.

**Inside a step.**  A step can run a process pool over its own work.  This
costs no inodes, needs no framework support, and is available today, but it is
confined to the node the step is running on.

The temptation is to reach for the second, because it is free and it is here
now.  Resist it past a point: **a step that absorbs the whole workload into an
internal pool is not task-parallel at all, however parallel it is inside.**
That is exactly MPAS-Analysis's ceiling --- it parallelizes with
`multiprocessing.Process`, which cannot span nodes, and that ceiling is a known
choke point at the resolutions Omega targets.  Rebuilding it in Polaris would
defeat the purpose of task parallelism.

The rule that follows:

> Decompose a workload into enough steps that the scheduler has something to
> balance, and use an in-step pool only for what is left below that
> granularity.

**Phase 1 uses neither.**  It runs serially, because task parallelism will not
exist by its deadline and it does not need to be fast --- it needs to handle
many decades of high-resolution output without falling over, which streaming
bounded amounts of data achieves on its own.  What matters is that both forms
of concurrency can be added afterwards *without invalidating anything already
computed*: splitting a product into more steps is safe because inheritance is
decided by content rather than by path (principle 6), and adding a pool inside
a step changes nothing a step produces.  Designing for concurrency and shipping
without it are compatible here, and Phase 1 takes that option deliberately
rather than by omission.

"Enough to balance" is a property of the machine, not of the science, so where
a workload divides freely it should divide into a **configurable** number of
steps rather than a number derived from the data.  A count fixed by config also
keeps principle 9's step budget from growing with the length of a simulation.

So "how fine should steps be?" has two answers that must both be satisfied:
fine enough that the scheduler can balance them, and no finer than the axes
along which we need independent invalidation (principle 4).  Where those pull
in different directions, the load-balancing floor wins, because a cache that is
coarser than ideal costs a recomputation while a step that is coarser than
ideal costs a node.

The properties a step must have to be *eligible* for concurrent scheduling ---
no process-global state, no dependence on the working directory, temporary
files in its own work directory, logging through its own logger, declared
resources, and internal parallelism sized from those resources rather than from
the machine --- are set out in
[Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md).  Analysis
steps are written to them from the start.

#### 4. Decompose along the axes a user edits between runs

| Axis | Edited between runs? | A step axis? |
| --- | --- | --- |
| Date range | yes, constantly | yes |
| Years available, as a run is extended | yes | yes, but see principle 6 |
| Field or plot list | yes; analysts iterate on it | yes, by field *group* |
| Season, elevation | rarely, and bounded | no --- loop inside a step |
| Region, observational reference | rarely, and multiplies | no --- loop inside a step |
| Colormaps and other styling | yes, but should be cheap | no --- a replot option |

The field axis is chunked by *group* rather than by variable: things computed
together belong in one step.  Zonal and meridional velocity share a vector
reconstruction, so they share a step.

The bottom two rows matter more than they look.  Regions and observational
references multiply against fields and seasons, so a rule that survives later
phases cannot put them on a step axis.  One step per plot is never the answer.

#### 5. Directory levels must earn their keep, and name things rather than mechanisms

A level is justified by one of two things: enough siblings that clutter is
real, or a name someone would actually navigate by.  A level that fails both is
noise, and every level makes reaching a given depth harder.

The corollary is the more useful half: **if a level's best name describes how
the work was chunked rather than what it holds, the level is wrong.**  A
directory called `years/`, or `offline_metrics/`, is a bucket named after a
mechanism.  The fix is not a better bucket name; it is to make the thing inside
a product with a name of its own, or to remove the level.

#### 6. Steps cache what the user asked for; files cache what the computation needed

Polaris's caching primitive is a completion marker in a step's work directory,
so the only way to get incremental reuse from the framework alone is to create
a directory per unit of reuse.  That is right when the unit is something a user
asked for --- a date range, a field group.  It is wrong when the unit is an
internal chunk of a divisible computation, such as a simulation year: it pays a
step's overhead, a pickle, a config copy, and a log file for a chunk no user
ever named.

For those, use a **seeded accumulator**: one step, still keyed by what the user
asked for, which

- at setup, searches for cache files written by earlier runs of the same
  product, works out which of them cover part of what is being asked for, and
  declares them as ordinary inputs;
- at run, computes only the difference between what is asked for and what it
  inherited, and writes a complete cache for its own key.

This needs no framework change and no manipulation of completion markers.  The
step is still keyed by the user's request, so a new request is a new directory
that has never run, and Polaris's ordinary skip-if-complete behavior is
untouched.  The seed is a declared input, so provenance and input checking work
normally and nothing reaches into another step's directory undeclared.  Every
file remains owned by the step that wrote it.

A partially written cache in the step's own directory is a valid starting point
for a retry, so restartability comes with the pattern rather than being added
to it.

**An accumulator may be more than one step**, and usually should be, by
principle 3.  Splitting one into shards that each cover a slice of the request
costs nothing here, because inheritance is decided by *content* rather than by
path: a shard asks which units it needs and which of them some earlier run
already produced, and neither question refers to how that earlier run was
divided.  A cheap merge step assembles the shards' results.  This is the
property that distinguishes an accumulator from a chunk keyed by its path ---
chunking the latter restricts what can be reused, while chunking the former is
purely a decision about load balancing and can be changed at any time, even
between two runs over the same record.

The pattern applies wherever we own the reduction kernel, and nowhere else.
`ncclimo` has no incremental mode, so a climatology is recomputed in full for
each new date range.

#### 7. Discovery is scoped by construction and validated by content

Principle 6 has software hunting for data on disk, which is worth being
uncomfortable about.  The discomfort is resolved by separating two jobs that a
path is often asked to do at once:

> **The path establishes the search scope.  The content establishes
> admissibility.**

The scope is only ever what construction guarantees: sibling directories of the
same product, written by the same step class with the same outputs, differing
only in the key.  It is never widened to arbitrary locations on disk.

Nothing, however, is trusted because of where it sits.  "Same location"
guarantees less than it appears to: work-directory paths do not encode which
simulation was analyzed, so the same directory re-used against a different
simulation would otherwise cross-contaminate silently, as would a changed
constant or a changed elevation range.  Every cache record therefore carries a
provenance stamp --- the identity of the simulation, the config options that
govern the product, and a version for the kernel that produced it --- and a
record whose stamp does not match what is being asked for is not inherited.  It
is recomputed, without ceremony.

Three further rules keep this auditable rather than magical:

- **Only a completed step is a candidate.**  A directory without a completion
  marker is never inherited from, which also disposes of the half-written cache.
- **Reuse is loud.**  Every run reports what it inherited and from where, and
  the provenance travels in the output.  An auditable decision is a different
  thing from an invisible one.
- **Explicit mode exists.**  Reuse can be disabled outright, and an additional
  search location can be named, for anyone who wants determinism rather than
  discovery.  Discovery is the default, not the only option.

#### 8. A cache is an intermediate product, so its form follows its consumer

A cache is not a private data structure; it is an intermediate product with a
known consumer, and it should be written in the form that consumer reads.  A
reduced time series consumed whole by a plotting step is one file with an
unlimited time dimension, appended to as the record grows.  A monthly field
consumed by `ncclimo` is monthly files, because that is `ncclimo`'s interface.

Two guardrails bound the space, in place of a target file size, which cannot be
stated without becoming resolution-dependent:

- never more cache files than there are input files;
- never rewrite more than one chunk in order to append one unit.

Beyond that this is deliberately **not a load-bearing decision**.  An
accumulator exists to avoid re-reading gigabytes of three-dimensional monthly
output, and that pass dominates cache I/O in every case we have.  Accumulators
are for reductions, and reductions are small.

#### 9. Size steps for the production case

Any granularity looks absurd at the resolution of a regression test.  Step size
is chosen against a production run --- a multi-decade, high-resolution coupled
simulation --- where a pass over a year of three-dimensional monthly output is
gigabytes and minutes.  A test configuration has few enough years that the
overhead is irrelevant.

The targets, which later phases should hold themselves to:

- a step should do at least tens of seconds of work at production resolution,
  so that Polaris's per-step overhead is a few percent at most;
- a step should do no more than a fraction of the suite's total work, so that
  the scheduler has something to balance --- principle 3's floor, and the
  binding constraint for anything expensive;
- a suite should contain steps numbering in the low hundreds, and should stay
  there as regions and observational comparisons are added.

The middle target is the one most easily lost, because nothing fails when it is
missed: the suite still runs, it just runs on one node.  A product whose cost is
concentrated in a single step should say so explicitly and say why that is
acceptable, rather than leaving it to be discovered.

Polaris's actual per-step overhead --- setup and run of a step that does
nothing --- should be measured once and recorded here, so that this stops being
a matter of judgment.

#### 10. Split computation from plotting only where computation dominates

Writing the data behind a plot is required in all cases; see the
`plots are always accompanied by their data` requirement.  Making the
computation a *separate step* from the plot is a different question, and it
earns its keep only where recomputing is expensive relative to replotting.  For
a map on the native grid, the plotting is the expensive part, so splitting buys
nothing and costs a level and a step.  Where a plot is a cheap rendering of an
expensive reduction, the reduction is an accumulator by principle 6 and the
split has already happened for a better reason.

*Further algorithm designs to be added as individual capabilities are
designed.*  Algorithm designs for the Phase 1 capabilities are in
{ref}`design-ocean-analysis-initial`.

## Implementation

### Implementation: code organization

Date last modified: 2026/08/25

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

Two further pieces are added by Phase 1 and are expected to be reused:

- **Manifest and publication** live in `polaris/tasks/ocean/analysis/`
  alongside the steps in Phase 1, and should move to a component-neutral home
  when a second component wants them.  Steps depend on the manifest writer, not
  on the collector.
- **Accumulator support** --- discovering candidate caches among sibling
  directories, checking provenance stamps, and reporting what was inherited ---
  is a shared helper rather than something each product reimplements, since
  principle 7 is only as good as its least careful implementation.

Analysis asks for something no existing task needed --- the same simulation
analyzed repeatedly over different date ranges, reusing what does not depend on
the range --- but it turns out to need no framework changes to get it.  The
mechanism is the one the cosine bell task family already uses for resolutions:
a task rebuilds its step list in `Task.configure()`, which runs after the
user's config has been merged, so step subdirectories can be keyed by the date
range the user asked for.  Reuse across ranges is then the seeded accumulator
of principle 6, which needs nothing from the framework beyond the ability to
declare an input discovered at setup time.  Later phases should reach for these
patterns before reaching for new framework capabilities.

#### How this work is divided into branches

Date last modified: 2026/08/29

This capability is built as a series of branches rather than one, and the
division has been settled once here so that each new piece of work does not
reopen it.

**Design documents change only on the design branch.**  Every edit to the
documents in this family lands on `add-analysis-designs`, and never on a
branch that implements one of them.  The design is then one reviewable thing
whose history reads as a design discussion, implementation branches rebase onto
it, and a reviewer is never asked to judge a design change and the code that
assumes it in the same diff.

**Each work item is a branch, and carries everything that item needs to be
complete.**  A branch holds its code, its unit tests, and its User's Guide
documentation.  Documentation is not a separate work item to be swept up at the
end: a capability that ships undocumented is not finished, and the moment its
behavior is fresh is the moment to write it down.

**Within a branch, each piece of code is followed by its tests, and the
documentation comes last.**  This is the order the branches built so far
already follow --- a kernel, then the tests for that kernel, then the step that
uses it, then the tests for the step, then the page that documents the result.
It keeps every commit reviewable on its own and keeps a test from being
attributed to code it did not accompany.

**A branch is cut from the branch it actually depends on.**  Where two items
are independent they branch from the same parent and stay independent rather
than being stacked for convenience; where one needs another, it is cut from it.
Shared infrastructure is therefore cut low, below its consumers, even when the
consumers were written first --- which is why publication branches from the
scaffolding rather than from the products, as described in
{ref}`design-ocean-analysis-initial`.

### Implementation: items deferred from Phase 1

Date last modified: 2026/08/29

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
- **Regional overturning**, in particular the Atlantic MOC and the standard
  maximum-AMOC-near-26.5°N metric, which arrives with the regional analysis
  described in the requirements above.
- **A content-addressed provenance scheme for inherited caches.**  Phase 1
  stamps each cache record with the simulation identity, the config options
  that govern the product, and a hand-maintained kernel version integer, and
  refuses to inherit a record whose stamp does not match.  Bumping that integer
  by hand is the weak link: it is correct only if it is remembered.  The
  follow-up is a stamp derived from the code and configuration themselves,
  covering the full dependency graph of a product, so that correctness does not
  rest on discipline.
- **Measure Polaris's per-step overhead** --- setup and run of a step that does
  nothing --- and record it under the organizing principles, so that the step
  sizing targets in principle 9 rest on a number rather than on judgment.

Phase 1 also ships without concurrency of any kind, and without the presentation
and verification layers designed around it.  These are deferred to Phase 2
rather than dropped, and each is designed above or in
{ref}`design-ocean-analysis-initial` already:

- **Split accumulators into several steps**, so that the scheduler has
  independent pieces to place.  Phase 1's heat content accumulator is a single
  step and is the bulk of a first run, which is the one place Phase 1 knowingly
  misses principle 9.  Splitting it costs nothing in reuse, since inheritance
  is decided by content rather than by path, so months cached by the
  single-step version are inherited unchanged.
- **Process pools inside steps**, for whatever is left below step granularity.
- **Generate a gallery over the staging tree.**  Phase 1 publishes the products
  and the merged manifest, which is everything a generator needs; what is
  missing is the generator.
- **Build the mechanical conformance checks** for the task-parallel
  groundrules.  Phase 1 follows the rules; nothing verifies that it still does.
- **The `analysis_test` task and its suite**, which runs a short Omega
  simulation and analyzes it.  It cannot run until Omega writes monthly means,
  and is the first thing to build once the Phase 1 products are out.

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
