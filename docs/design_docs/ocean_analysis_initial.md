(design-ocean-analysis-initial)=

# Initial Omega Analysis Capabilities

date: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

## Summary

The E3SM Ocean Team has committed to delivering a first set of analysis
capabilities for Omega's initial coupled runs by **September 15, 2026**, as a
stepping stone to a more complete zppy/MPAS-Analysis-style workflow later in
the calendar year.  This document designs that deliverable.  The broader
context is in {ref}`design-ocean-analysis`.

The deliverable is a Polaris suite, `omega_analysis`, that is pointed at a
completed Omega simulation through a user-supplied config file and produces:

1. **Map-view climatologies** (monthly, seasonal, and annual) of sea surface
   temperature, sea surface salinity, zonal and meridional velocity,
   mixed-layer depth, and vertically integrated ocean heat content.  Fields
   with a vertical dimension are plotted at a configurable set of elevations.
2. **Global time series** of the quantities in Omega's `GlobalStats` output.
3. **A global time series of ocean heat content** integrated over configurable
   elevation ranges.
4. **A latitude-elevation plot of the global meridional overturning circulation
   (MOC)** from the MOC diagnostic that Omega computes in situ.

Every plot is accompanied by a netCDF file containing the data plotted, and the
expensive intermediate products (climatologies, reduced monthly heat content)
are written to netCDF as well.

The same simulation can be analyzed repeatedly over different date ranges.
Results accumulate in a range-keyed staging tree, and re-analyzing a new range
inherits the reduced monthly values earlier ranges already computed instead of
recomputing them.

The staging tree is published with a thumbnail for every plot and a generated
gallery over them, as static HTML that a web server serves unchanged.  The
gallery follows MPAS-Analysis's familiar layout, and is designed around the
fact that the portal hosting it throttles: what a page costs to load is a
requirement here, not a detail of presentation.

MPAS-Analysis is the scientific reference for what each of these diagnostics
means, but the implementation is written from scratch with Polaris and Omega in
mind rather than ported.  The reasoning is in {ref}`design-ocean-analysis`.

Four things are deliberately **out of scope** for this deliverable:

- **Analyzing MPAS-Ocean output.**  The analysis locates a simulation's output
  by reading the simulation's own Omega configuration, and MPAS-Ocean describes
  its output with namelists and streams files instead.  Supporting it means
  writing a translator from those into the same form, which is separate work.
  This costs the deliverable nothing, since the design already develops against
  Omega output for the reasons given under `omega-monthly-means`.
- **Integration with zppy.**  For September 15, the analysis is run by hand by
  members of the Ocean Team, who make the results available to the coupled
  group within several days of each simulation period completing.  MPAS-Seaice
  analysis continues to be delivered through zppy's MPAS-Analysis.
- **Comparison with observations.**  When observational comparison arrives, the
  intent is to remap the observations onto the MPAS mesh and compare there, not
  to remap the model onto a comparison grid.  Everything in this document
  therefore stays on the native mesh, and nothing here should be read as a step
  toward interpolating model output to a lat-lon grid.
- **A global MOC time series.**  This was in the original proposal but has been
  dropped: MOC strength integrated globally is not a standard metric.  The
  standard metric --- maximum Atlantic MOC near 26.5°N --- is deferred to a
  later delivery along with the rest of the regional analysis.

The deliverable depends on Omega work that is outside this design: monthly-mean
output of full model fields, including the geometric vertical coordinate, and
a mixed-layer-depth diagnostic.  These are described in the
`omega-monthly-means` requirement below so that the dependencies are explicit,
along with the fallback for mixed-layer depth if it cannot be delivered in
time.

Success is that a member of the Ocean Team can, with a config file and two
Polaris commands, produce the full set of plots above for an Omega coupled run
on a machine where that run's output lives.

### Conventions

Two conventions are used throughout this document and throughout the code it
describes.  Both are Polaris-wide conventions rather than choices made here.

**Names are MPAS-Ocean names.**  MPAS-Ocean variable and dimension names are
Polaris's internal standard.  Analysis code refers to `temperature`,
`salinity`, `zMid`, `zInterface`, `minLevelCell`, `maxLevelCell`,
`bottomDepth`, and `areaCell`, and to the dimensions `nCells`, `nEdges`,
`nVertLevels`, `nVertLevelsP1`, and `Time`, regardless of which model produced
the data.  Omega's names --- `Temperature`, `GeomZMid`, `GeomZInterface`,
`NCells`, `NVertLayers`, and so on --- are translated to the Polaris standard
automatically when a dataset is opened with
`OceanIOStep.open_model_dataset`, using the mapping in
`polaris/ocean/model/mpaso_to_omega.yaml`.  Analysis steps therefore never
branch on the model to get a field name, and config options that name fields
use the MPAS-Ocean names.  Where a field is new to Omega and has no MPAS-Ocean
counterpart --- and is not expected to gain one --- it keeps its Omega name, and
there is no entry to add: a mapping exists to reconcile two spellings of the
same quantity, not to assign names.

**Pseudo-thickness is not translated.**  There is one deliberate exception to
the rule above, and it matters enough to state up front.

Omega is non-Boussinesq and prognoses **pseudo-height**, $\tilde{z}$, a
normalized pressure with units of meters, defined in
[Omega's governing equations](https://github.com/E3SM-Project/Omega/blob/develop/components/omega/doc/design/OmegaV1GoverningEqns.md)
as

$$
\tilde{z} = -\frac{p}{\rho_0 g},
\qquad\text{so that}\qquad
d\tilde{z} = \frac{\rho}{\rho_0} \, dz
$$

with $\rho_0$ a constant reference density used purely as a normalization ---
its presence does not make the model Boussinesq.  `PseudoThickness` is
$\tilde{h} = \Delta \tilde{z}$, in meters, and $\tilde{h} \approx h$ only to
the extent that $\rho \approx \rho_0$.  Two consequences follow, and analysis
code needs both:

- **Reference density times pseudo-thickness equals full density times
  geometric thickness**,

  $$
  \rho_0 \tilde{h} = \rho h = \frac{\Delta p}{g},
  $$

  which is the **mass per unit area** of the layer, exactly, by hydrostatic
  balance.  It needs no equation of state.
- The **geometric** thickness is the derived quantity:
  $h = \rho_0 \, \alpha \, \tilde{h}$, where $\alpha = 1/\rho$ is specific
  volume, so recovering it requires the equation of state.  This is the
  relation Omega uses to build `GeomZInterface` and `GeomZMid`.

MPAS-Ocean's `layerThickness` is the other way around: it is the geometric
thickness $h$, and because MPAS-Ocean is Boussinesq, $\rho_0 h$ is *its* mass
per unit area.  The two variables therefore coincide in what they mean for a
mass-weighted integral and differ in what they mean for a geometric one, so
renaming one to the other would hide exactly the distinction that matters.
`polaris/ocean/model/mpaso_to_omega.yaml` already declines to map them; this
design records why.

Analysis therefore never asks for "the thickness".  It asks for one of two
things by name:

- **Geometric positions and thicknesses** come from `zInterface` and `zMid`,
  which both models write (Omega as `GeomZInterface` and `GeomZMid`) and which
  are translated as usual.  A geometric layer thickness, where one is needed,
  is a difference of interface elevations, not a separate variable --- which is
  also the only way to get it offline, since $\alpha$ is not written.
- **Mass per unit area** comes from the model's own mass-like thickness
  variable --- `PseudoThickness` for Omega, `layerThickness` for MPAS-Ocean ---
  read under its native name and multiplied by $\rho_0$.  A single helper,
  `polaris.ocean.model.get_layer_mass`, returns $\rho_0 \tilde{h}$ for Omega
  and $\rho_0 h$ for MPAS-Ocean, so this is the one place in the analysis code
  that knows which model wrote the file.

This is what makes the heat content integral below a mass integral rather than
a volume integral scaled by a reference density, and it is the same convention
used for evaluating conservation in Omega.

**The vertical coordinate is elevation, positive up.**  All vertical positions
in config options, algorithms, and output are elevations $z$ in meters with
$z = 0$ at the resting sea surface and $z$ increasing upward, so that positions
within the ocean are negative.  A map "at 100 m below the surface" is requested
as `-100.0`, and the ocean heat content range conventionally called "0 to
700 m" is written `top:-700.0` --- `top` being the free surface of each column,
which is what "0 m" means in that phrase, rather than the resting sea surface
at $z = 0$.  This matches `zMid` and `zInterface` as the
models write them and avoids sign flips scattered through the code.  Where the
text uses the word "depth" it is describing a quantity that is positive down,
such as `bottomDepth`, and says so.

**Attributes are the CF ones.**  Omega writes each variable attribute twice:
once in its own capitalized spelling --- `Units`, `Name`, `StdName`,
`Description`, `ValidMin`, `ValidMax` --- and once in the CF spelling ---
`units`, `name`, `standard_name`, `long_name`, `valid_min`, `valid_max`.
Analysis reads **only** the CF form and ignores the capitalized one entirely.

This is not a stylistic preference.  The CF attributes are the ones every tool
in the stack already understands: `xarray` ingests them, uses `units` and
`calendar` to decode times, and writes them back out.  The capitalized
duplicates are understood by nothing, so code that reads them works on files
Omega wrote and fails on every other file --- including one that has merely
been through `xarray`, which moves `units` into `.encoding` on decoding while
leaving `Units` sitting in `.attrs`.  A dependence on the capitalized form is
therefore invisible until it is tested against a file we wrote ourselves,
which is exactly when it is most expensive to find.

`polaris.ocean.model.time.get_days_since_start` has such a dependence today,
in `ds['Time'].Units`.  It predates this design and is used across the ocean
component, so fixing it is framework work rather than analysis work, but no
new analysis code should follow it.

## Requirements

### Requirement: analysis-suite

Date last modified: 2026/08/27

Contributors: Xylar Asay-Davis, Claude

Polaris shall provide a suite that computes all of the analysis in this
document for a single Omega simulation, run standalone or within E3SM.
Analyzing MPAS-Ocean output is out of scope for this deliverable.

The user shall supply a config file that provides:

- the path to the simulation's own Omega configuration file, from which the
  mesh, the vertical coordinate and the output files shall be found without
  the user restating any of them;
- the start and end dates of the climatology;
- the fields for which climatology maps should be produced (if different from
  the defaults);
- the elevations at which climatology maps should be plotted, for fields that
  have a vertical dimension (if different from the defaults);
- the start and end dates of the time series;
- the fields from Omega's global statistics for which time series should be
  plotted (if different from the defaults);
- the elevation ranges over which ocean heat content should be integrated (if
  different from the defaults).

Setting up and running the suite shall not require an Omega or MPAS-Ocean
build, since no model is run.  The suite shall be usable on the machine where
the simulation output resides, without copying that output.

Each analysis product shall be a separate task within the suite, so that a user
can run a single product without running the rest, and the expensive
climatology computation shall be shared between the tasks that need it.

### Requirement: data-products

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Every plot the suite produces shall be accompanied by a netCDF file containing
exactly the data that were plotted, so that the values can be inspected,
compared against other tools, or re-plotted without recomputation.

Every plot and its data shall also be described in a machine-readable manifest
naming the facets that identify it --- at minimum the field, the season, the
vertical reduction, and the date range --- so that a reader or an index can
find a product without knowing how the work was divided into steps.

Intermediate products that are expensive to compute --- climatologies and
reduced monthly ocean heat content in particular --- shall be written to
netCDF, and a step that finds an intermediate product from a previous run shall
be able to reuse it rather than recomputing it.  Reuse shall be conditional on
the product having been computed for the same simulation, by the same kernel,
under the config options that govern it, and shall be reported rather than
silent.

### Requirement: repeated-analysis

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Polaris shall support analyzing the same simulation repeatedly with different
climatology and time-series date ranges.

Analyzing a new range shall not overwrite or remove the results of a range
analyzed earlier, and ranges analyzed at different times shall appear together
in the published output described under `publication` below.

Re-running the analysis with a changed range shall recompute the products that
depend on that range.  It shall not be necessary to delete the work directory
or to pass a flag to force recomputation, and it shall not be possible to
obtain a plot labeled with one range whose contents were computed for another.

Re-running with a changed range shall reuse the intermediate results that do
not depend on the range.  Extending a time series from twenty years to forty
shall cost twenty years of work, not forty.

Re-running with an unchanged range shall recompute nothing by default, and it
shall be possible to ask for the plots to be redrawn --- after a change to
colormaps or other styling --- without recomputing the intermediate results
behind them.

### Requirement: publication

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Results shall be published to a single location that a reader can browse
without knowing anything about Polaris work directories, and that a web server
can serve unchanged.  That location shall carry a generated index over the
results rather than requiring the reader to navigate directories.

The index shall be static HTML, generated from the merged manifest, and shall
require no server-side code, no build step, and no network access of its own,
so that it works equally from a local filesystem and from a web portal.

**Every plot shall have a thumbnail.**  With a few hundred plots, thumbnails
are what let a reader decide which full images to open, and they frequently
answer the question without any full image being opened at all.  A thumbnail
shall be a separate, small, lossy file rather than the full image scaled down
by the browser, which would cost the full image's bytes.

**A page shall stay within what a throttled link can deliver.**  The analysis
is hosted on the LCRC public web portal, which throttles in a way that stalls a
page asking for too much at once, and this is the constraint that the
presentation has to be designed around rather than discovering later.  Three
things shall bound what a page costs: thumbnails shall be small, no page shall
carry the whole result set, and images the reader has not scrolled to shall not
be fetched.  The parameters controlling this shall be config options, since the
binding constraint is a property of the host rather than of the analysis.

**The published output shall not need to be regenerated to be extended.**  The
index shall be derived from the manifest alone, so that facets added later ---
region, observational reference, a second simulation to compare against --- and
richer presentation --- per-product pages carrying provenance and the code that
reproduces a figure, filtering, search --- can be added without changing any
step, any manifest fragment already written, or any published path.  The
broader intent this serves is in {ref}`design-ocean-analysis`.

What this deliverable does *not* owe is a considered visual design.  A gallery
following MPAS-Analysis's familiar layout, and no more, is what Phase 1 ships.

### Requirement: omega-monthly-means

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

*This requirement describes work in Omega, not in Polaris.  It is stated here
because everything else in this document depends on it.*

Omega shall be able to write monthly means of a configurable list of model
fields.  The monthly-mean output shall:

- cover, at minimum, the fields needed by this analysis: conservative
  temperature, absolute salinity, pseudo-thickness, sea surface height,
  reconstructed zonal and meridional velocity at cell centers, and mixed-layer
  depth.  Reconstructed velocities are **required** rather than preferred: the
  machinery to write them exists in Omega, two cell-centered fields are about
  two thirds the size of one edge field, and `normalVelocity` is not itself
  plotted by anything here, so there is no reason for a simulation to write the
  larger field and no reason for Polaris to carry a reconstruction it would
  never use;
- include the **geometric vertical coordinate**, `GeomZMid` and
  `GeomZInterface`, so that Polaris does not have to reconstruct it (see the
  vertical-geometry algorithm design for why it cannot);
- carry CF-compliant time metadata: a `time` coordinate with `units`,
  `calendar` and a `bounds` attribute, and a **`time_bnds` variable holding the
  start and end of the averaging period**.  This is not a formality --- it is
  the specific thing `ncclimo` needs in order to read Omega output at all, and
  it has to hold the right values, not merely be present.  See the
  implementation section, where this is now confirmed against real output
  rather than assumed;
- use a file-name convention that encodes the year and month, or that groups
  whole years into one file, and that is stable across a simulation.

Omega's Analysis module already provides temporal reduction with a configurable
`ReductionPeriod`, including `1Month`, for the `GlobalStats` group.  The work
required is to make the same reduction available for full model fields.

Checkpointing the monthly reduction so that it resumes correctly across a
restart is a longer-term goal and is not required for this deliverable: the
simulations to be analyzed are not expected to restart more often than once a
month, so a reduction period that divides the restart interval is sufficient.

#### Mixed-layer depth

Omega should provide a **mixed-layer depth** diagnostic computed in situ from
the instantaneous state, using a density-threshold criterion, and make it
available for monthly averaging.  This is the scientifically correct source:
mixed-layer depth is a strongly nonlinear function of the temperature and
salinity profiles, so a mixed-layer depth computed from monthly-mean
temperature and salinity is not the monthly mean of the mixed-layer depth.

Whether this can be delivered in Omega by September 15 is a question for the
team rather than something this design can settle.  **If it cannot**, Polaris
shall fall back to computing mixed-layer depth offline from the monthly-mean
conservative temperature and absolute salinity, using the same density
threshold criterion, and shall label the resulting plots to make clear that
they are computed from monthly means.  The fallback is described in the
mixed-layer-depth algorithm design, along with what it does and does not
capture.

### Requirement: climatology

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall compute monthly, seasonal, and annual climatologies from a
simulation's monthly means, over a start and end year given by the user.

The seasons shall include, at minimum, the annual mean (`ANN`) and the four
standard three-month seasons (`DJF`, `MAM`, `JJA`, `SON`), and the user shall
be able to request additional seasons.  The twelve monthly climatologies shall
also be available.

Climatologies shall be computed only for the fields that are needed, so that
the cost of the computation scales with what is being analyzed rather than with
the full contents of the monthly-mean files.

### Requirement: climatology-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Polaris shall produce global maps of climatological fields on the native MPAS
mesh, for each requested field and each requested season.

A field with a vertical dimension has to be reduced to a horizontal map before
it can be plotted, and there is more than one useful way to do that.  Polaris
shall provide a general **vertical reduction** for this purpose, of which the
user shall be able to request any combination:

- **the sea surface** --- the topmost valid layer of each column;
- **a fixed geometric elevation** --- a given elevation $z$ (positive up, so
  negative within the ocean), obtained by linear interpolation in the vertical;
- **a fixed layer index** --- a given vertical index, common to all columns;
- **the seafloor** --- the bottommost valid layer of each column;
- **an integral over an elevation range** --- the mass-weighted integral of the
  field between two elevations, which is how ocean heat content maps are
  produced.

The "topmost" and "bottommost" valid layers shall respect `minLevelCell` and
`maxLevelCell`, so that columns under ice-shelf cavities and columns with
partial bottom cells are handled correctly.  Where a requested elevation falls
outside a column --- below the seafloor, or under land --- the map shall be
masked rather than showing an extrapolated value.

Sea surface temperature and sea surface salinity are obtained by requesting the
sea surface for the temperature and salinity fields; they are not separate
fields.

Where a model does not output reconstructed zonal and meridional velocity,
Polaris shall reconstruct them from the normal velocity on edges.

### Requirement: ocean-heat-content-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Polaris shall compute ocean heat content integrated over elevation ranges from
a climatology of conservative temperature, and shall produce a global map for
each elevation range and each requested season.

This is the elevation-range case of the vertical reduction required above, and
is delivered as a field of the climatology maps rather than as a product of its
own.  A heat content map is a climatology map of a field that happens to be
derived, and separating the two would mean two code paths, two step trees, and
two config conventions for the same operation.

The elevation ranges shall be set by config options.  The defaults shall be the
whole ocean, the surface to $-700$ m, $-700$ m to $-2000$ m, and $-2000$ m to
the seafloor.  A range boundary that falls in the interior of a model layer
shall contribute that layer in proportion to the fraction of the layer within
the range, and a range boundary below the seafloor of a given column shall be
truncated at the seafloor.

### Requirement: global-stats-time-series

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall plot time series of the global statistics that Omega's
`GlobalStats` analysis group writes, over a start and end year given by the
user, for a list of fields given by the user.

Polaris shall ship a config file defining a default list of fields and
statistics, so that a user who has not thought about which quantities to plot
gets a useful set.  A field or statistic in that list that the simulation did
not write shall be **skipped with a message in the log, not treated as an
error**: the defaults describe what we would like to see, and any given
simulation will have written some subset of it.  A field the user has asked for
explicitly is treated the same way, since the user has no more control over
what the completed simulation wrote than we do.

For each field, the plot shall show the global mean together with the global
minimum, maximum, and standard deviation, and shall show the change relative to
the beginning of the time series as well as the absolute values, since drift is
usually what the reader is looking for.  Statistics that are absent are simply
omitted from that field's plot.

The time axis shall be labeled in simulation years.

### Requirement: ocean-heat-content-time-series

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall compute a time series of globally integrated ocean heat content,
over the same elevation ranges as the ocean heat content maps, from each
monthly-mean conservative temperature field over a start and end year given by
the user, and shall plot that time series.

The plot shall show both the absolute heat content and the anomaly relative to
the start of the time series, since the anomaly is the quantity of interest for
drift and for the planetary energy budget while the absolute value is dominated
by the mean state.

The computation shall stream over the monthly files rather than loading the
full record into memory, and shall cache the reduced monthly values so that
extending the time series with additional simulation years does not require
reprocessing the years already covered.

### Requirement: moc-plot

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall produce a latitude-elevation plot of the global meridional
overturning streamfunction from the MOC diagnostic that Omega computes in situ,
averaged over the climatology period.

The plot shall be in Sverdrups, with a diverging color map centered on zero,
contour lines at a configurable interval, and elevation on the vertical axis so
that the sea surface is at the top.

Omega shall provide, alongside the streamfunction, the mean geometric elevation
of each layer interface over the same period, so that the vertical axis is
meaningful.  Polaris shall not reconstruct it.

Polaris shall not compute the MOC itself.  The overturning streamfunction
requires the full three-dimensional velocity field at every time step to be
computed correctly, and Omega computes it in situ for exactly that reason.

### Requirement: regression-test

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Polaris shall provide a regression test that runs a short Omega simulation and
then analyzes its output, so that the analysis capability is exercised
end-to-end by something we run ourselves.

Everything else in this document consumes output from a simulation Polaris did
not run, on a machine where that simulation happens to live.  That is the point
of the capability, and it is also why nothing in it would otherwise be covered
by a suite: a regression that broke the climatology, the vertical reduction, or
the accumulator would be found by a person analyzing a coupled run, which is
the most expensive place to find it.

The test shall run a coarse-resolution Omega forward run configured to write
the monthly-mean output this analysis reads, and shall then run the analysis
products against it.  It shall be a suite of its own rather than an addition to
`omega_pr` or `omega_nightly`, since it costs a forward run and it is blocked
on Omega capabilities that the PR suite must not be blocked on.  Adding it to
`omega_nightly` once it is stable and its cost is known is the expected
follow-up.

The test verifies that the products are produced and are self-consistent, not
that they are scientifically meaningful: a simulation short enough to run in a
test is too short for the diagnostics to say anything.

## Algorithm Design

### Algorithm Design: climatology

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Climatologies are computed with `ncclimo` from the NCO package, which Polaris
already depends on.  `ncclimo` is used rather than an `xarray` implementation
because it is the tool the rest of the E3SM post-processing workflow uses, it
is substantially faster than a naive `xarray` implementation on large files, it
handles the season-weighting conventions correctly, and using it keeps our
climatologies comparable with those produced by zppy.

The monthly climatology for month $m$ is the unweighted mean over the requested
years of the monthly means for that month:

$$
\overline{\phi}_m = \frac{1}{N_{yr}} \sum_{y=y_0}^{y_1} \phi_{y,m}
$$

The seasonal climatology weights each month by the number of days in that
month:

$$
\overline{\phi}_s = \frac{\sum_{m \in s} d_m \overline{\phi}_m}
                         {\sum_{m \in s} d_m}
$$

and the annual mean is the same expression with $s$ running over all twelve
months.  `ncclimo` implements both, using the calendar of the input files.

Two conventions matter and are worth stating explicitly:

- **December handling.**  `DJF` needs a December, and the December that is
  contemporaneous with a given January and February belongs to the previous
  year.  `ncclimo`'s `-a sdd` ("seasonally discontinuous December") option
  takes December from the same year as January and February, which means every
  year in the requested range contributes exactly one December and no data
  outside the range are needed.  This is the convention MPAS-Analysis uses, and
  we adopt it for consistency.
- **Averaging is over the fields written, not over derived quantities.**  A
  climatology of layer thickness and a climatology of temperature are not the
  same as a climatology of their product.  This matters for heat content and is
  discussed under the heat content algorithm below.

### Algorithm Design: repeated-analysis

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

The whole approach rests on separating what depends on the requested range from
what does not:

| Product | Depends on the range? | Cost |
| --- | --- | --- |
| Monthly means (model output) | no | read-only input |
| Reduced monthly ocean heat content | no, keyed by month | expensive |
| Offline monthly mixed-layer depth | no, keyed by month | expensive |
| `ncclimo` climatologies | yes | expensive |
| Climatology and heat content maps | yes | cheap, from the climatology |
| Global stats time series | yes | cheap |
| MOC time average | yes | cheap |

The rows in the middle are the ones that matter.  A given month's vertically
integrated heat content is the same quantity no matter which range asked for
it, so it should be computed once and reused forever, while everything else is
either cheap to redo from those monthly values or is the climatology itself.

Every step is keyed by what the user asked for --- a date range --- and the
expensive range-independent work is made incremental *inside* a step by the
**seeded accumulator** of principle 6 in {ref}`design-ocean-analysis`.  The
accumulator finds the cache files left by earlier runs of the same product,
inherits the months they cover, computes only the rest, and writes a complete
cache for its own range.

An earlier draft of this design instead gave every simulation year its own
shared step at a year-keyed subdirectory, so that reuse fell out of Polaris's
completion markers with no machinery of our own.  That was appealing but wrong
on two counts.  It paid a step's overhead --- a directory, a pickle, a config
copy, a log file --- for a chunk no user ever asked for, and it turned the
directory tree into a bucket named after a mechanism.  Worse, the completion
marker was then the *only* validity check: change the heat content kernel or a
constant and every one of those directories would still report itself complete.
The accumulator is cheaper and, with the provenance stamp described below,
safer.

The steps that remain are **shared steps** in the sense of
[Shared steps](shared_steps.md), created with
`Component.get_or_create_shared_step()` at a subdirectory computed from the
range, so that the climatology for a range is built once no matter how many
products read it.  The implementation section works through the details.

#### How many steps, and how much do they do?

Principle 9 in {ref}`design-ocean-analysis` asks for step counts in the low
hundreds and for steps that do at least tens of seconds of work at production
resolution.  For a typical analysis --- a 60-year record with a 20-year
climatology --- this design produces:

| Steps | Count |
| --- | --- |
| `ncclimo` climatology | 1 |
| Climatology maps, one per field group | 6 |
| Heat content series accumulator | 1 |
| Offline mixed-layer depth, accumulator plus its climatology (fallback only) | 2 |
| Global stats, MOC | 2 |
| **Total** | **12** |

The count is **independent of the length of the record**, which is the property
worth having.  It grows with the number of field groups and products, and --- in
a later phase, when accumulators are split for a scheduler --- with how much
concurrency the machine can use.  Neither is something the length of a
simulation can run away with.  An earlier draft, with one shared step per simulation year, gave
about 130 steps for the same analysis and grew linearly, so a century-long
record would have given about 230.  That was never going to break Polaris --- a
few hundred steps is ordinary, and the existing `ocean` component builds
several hundred across all its tasks --- but the count grew with something the
user has no control over, which is the wrong shape even when the numbers are
small.

Step *size* is the other half.  On a first run the heat content accumulator
reads the whole record, which at 6to18 km over several decades is hours; on a
re-run over an overlapping range it reads only the new months.  A climatology
map step plots the seasons and reductions of one field group, which is seconds
to minutes per plot at production resolution.  Neither is close to the regime
where a step's overhead --- a work directory, a pickle, a config copy, a log
file --- would be a meaningful fraction of its runtime.

Principle 9's other target, that no step be a large fraction of the suite, is
knowingly missed: the heat content accumulator is the bulk of a first run.  That
is acceptable only because Phase 1 is serial, so there is nothing the imbalance
could have been traded against.  It is the first thing to fix when there is a
scheduler, and it is fixed by splitting the accumulator, which costs nothing in
reuse.

The count grows with the number of field groups and, in later phases, with
whatever new products are added --- not with the record, the seasons, the
elevations, or the regions.  That is what principle 4 is protecting: the
dimensions that multiply are loops inside steps, so adding regional analysis
multiplies the *plots* without multiplying the *steps*.

The climatology is the one expensive computation that genuinely depends on the
range, and it is recomputed for each new range.  In principle a climatology
over a new range could be assembled incrementally from per-year seasonal
partial sums, but `ncclimo` has no such mode, and writing our own incremental
climatology to save a rerun is not a trade we should make for this deliverable.
Two ranges' climatologies coexist without special handling, because `ncclimo`
already encodes the range in its output file names
(`<caseid>_<season>_<YYYYMM>_<YYYYMM>_climo.nc`).

### Algorithm Design: climatology-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

#### Vertical geometry

Everything in this document that involves a vertical position needs the
geometric elevation of layer midpoints, $z^{mid}_{k}$, and of layer interfaces,
$z^{int}_{k}$, for each column.  These are read directly from `zMid` and
`zInterface` --- Omega's `GeomZMid` and `GeomZInterface` --- which is why the
`omega-monthly-means` requirement asks for them as monthly-mean output.

Polaris cannot reconstruct them from the monthly means of the other fields.
Omega builds the geometric coordinate by accumulating upward from
$-\mathrm{BottomGeomDepth}$ using layer thicknesses
$h = \rho_0 \, \mathrm{SpecVol} \times \mathrm{PseudoThickness}$, and it does
so the same way regardless of which vertical coordinate the simulation uses ---
the choice of z-star, p-star, or sigma determines how `PseudoThickness` is
initialized and how it evolves, not how geometric elevation is computed from
it.  Reconstructing $z$ offline therefore requires specific volume, which means
evaluating the TEOS-10 equation of state on the monthly-mean state.  That is
not the monthly mean of $\mathrm{SpecVol} \times \mathrm{PseudoThickness}$, so
the reconstruction would introduce an error that has nothing to do with the
diagnostic being computed.  Having Omega write the geometric coordinate removes
the problem entirely, since the monthly mean of $z$ is exactly the mean layer
geometry we want.

Note the direction of the dependence, which is the reason for the conventions
stated at the top of this document: geometric thickness is *derived* from
pseudo-thickness and specific volume, and it is the derived quantity that
cannot be recovered offline.  Mass per unit area, $\rho_0 \tilde{h} = \rho h$,
needs no equation of state at all.  That is why the heat content integral is
written in terms of it and why only quantities that genuinely need the
geometry --- elevation slices, and the partial layers at a heat content range
boundary --- read `zMid` and `zInterface`.

Because the input to the map steps is a climatology, the $z^{mid}_{k}$ they use
is the climatological-mean layer geometry.  This does mean that a $-100$ m map
is a map on the time-mean position of the $-100$ m surface rather than the time
mean of maps on the instantaneous $-100$ m surface.  The difference is small
away from regions with a large seasonal cycle in layer thickness.

#### Elevation selection

Let $f_k$ be the field in a given column, $k_{min}$ = `minLevelCell` and
$k_{max}$ = `maxLevelCell` be the zero-based indices of the topmost and
bottommost valid layers, and let the requested elevation specification be one
of `top`, `bottom`, `k<n>`, or an elevation $z$ in meters (negative within the
ocean).

- `top`: $f = f_{k_{min}}$.
- `bottom`: $f = f_{k_{max}}$.
- `k<n>`: $f = f_n$, masked in columns where $n < k_{min}$ or $n > k_{max}$.
- elevation $z$: find $k_1$, the largest valid index with
  $z^{mid}_{k_1} \ge z$, and interpolate linearly between $k_1$ and $k_1 + 1$:

  $$
  w = \frac{z - z^{mid}_{k_1+1}}{z^{mid}_{k_1} - z^{mid}_{k_1+1}},
  \qquad
  f = w f_{k_1} + (1 - w) f_{k_1+1}
  $$

  If $z$ is above the midpoint of the topmost layer, $f = f_{k_{min}}$; if it
  is below the midpoint of the bottommost layer but above the seafloor,
  $f = f_{k_{max}}$.  If $z < z^{int}_{k_{max}+1}$ --- below the seafloor ---
  or the column is land, the result is masked.

  Clamping rather than masking between the top layer midpoint and the sea
  surface matters in practice: a request for $0$ m or $-5$ m would otherwise be
  masked everywhere, which is not what a user asking for a near-surface map
  intends.

The search for $k_1$ is vectorized over columns as the count of valid layer
midpoints at or above $z$, which avoids a Python loop over cells:

```python
k1 = (z_mid >= z).sum(dim='nVertLevels') - 1
```

with `z_mid` set to `NaN` outside the valid range so invalid layers do not
contribute, followed by a clip into `[k_min, k_max - 1]` and a mask for the
out-of-column cases.

#### Velocity

The map steps plot zonal and meridional velocity at cell centers, read directly
from the monthly means.  Polaris does not reconstruct them, and Phase 1 has no
offline reconstruction path at all.

An earlier draft had one, reconstructing from `normalVelocity` on edges with
the least-squares weights designed in
[Vector Reconstruction](vector_reconstruction.md), so that this product would
not block on Omega work.  It is not needed: the Omega side is in progress in
[Omega #525](https://github.com/E3SM-Project/Omega/pull/525), which adds
velocity-component reconstruction for I/O, so reconstructed velocities become a
required output rather than a preferred one, and a fallback for a case that
will not arise is code we would write, test and maintain for nothing.

That work is still a draft, so this is the one place the design depends on
something not yet landed upstream.  The consequence is contained: until it
does, the mock-up files carry `NormalVelocity` and no components, so the
velocity maps are the one product that reports missing fields and skips, in the
way described under `omega-monthly-means`.  Nothing else waits on it.  Writing
the offline path against that gap would cost more than the wait, and would
leave us maintaining two ways to obtain the same field.

Polaris's reconstruction itself is not going away and is being fixed
independently --- [Polaris #721](https://github.com/E3SM-Project/polaris/pull/721)
corrects vector reconstruction on planar meshes, found while doing the Omega
work.  It stays available for tasks that need it; this analysis simply does not
read edge velocities.

The accuracy question that would otherwise decide this does not arise either.
Reconstruction is linear, so reconstructing from a climatology of normal
velocity gives exactly the climatology of the reconstructed velocity --- doing
it in the model costs nothing in accuracy, and it saves writing and reading an
edge field nothing else here wants.

### Algorithm Design: mixed-layer depth (fallback only)

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

*This algorithm applies only if Omega cannot deliver an in-situ mixed-layer
depth diagnostic in time.  If Omega provides one, mixed-layer depth is an
ordinary monthly-mean field and flows through the climatology and map steps
like any other, and none of this section applies.*

The fallback computes mixed-layer depth from each monthly-mean profile of
conservative temperature and absolute salinity using the same density-threshold
criterion Omega plans to use: the mixed layer extends to the elevation at which
the potential density referenced to $10$ m exceeds the density at $10$ m by
$\Delta \rho = 0.03$ kg m⁻³, with linear interpolation between the bounding
layers.  Density is evaluated with `gsw`, which Polaris already depends on and
which implements the same TEOS-10 formulation Omega uses.

The mixed-layer depth is computed for each month and then averaged over the
climatology period, rather than being computed from the climatology.  Computing
it from the seasonal or annual climatology would be a second, much larger
approximation on top of the one described next.

What this fallback does *not* capture, and what should be said on the plots and
in the netCDF metadata:

- Monthly-mean profiles are smoother than instantaneous profiles.  Averaging
  over a month blends the stratification before, during, and after a mixing
  event, so the mixed-layer depth derived from the mean profile is not the mean
  of the mixed-layer depths.
- The effect is largest exactly where mixed-layer depth matters most: winter
  deep-convection regions, where a few days of deep mixing set the monthly mean
  of the true mixed-layer depth but leave only a muted signature in the
  monthly-mean profile.
- Monthly maximum mixed-layer depth, which MPAS-Analysis reports and which is
  the more useful deep-convection diagnostic, cannot be recovered at all from
  monthly means.

The fallback is therefore adequate for a first look at the seasonal cycle of
the mixed layer in a coupled run and is not adequate as a deep-convection
diagnostic.  Replacing it with Omega's in-situ diagnostic should be the first
follow-up after September 15 if the fallback is what ships.

### Algorithm Design: ocean-heat-content

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

*This algorithm is shared by the heat content maps and the heat content time
series; the two differ in what they integrate over and in what they read, not
in the kernel.*

Ocean heat content per unit area is a *mass*-weighted integral of conservative
temperature.  Over an elevation range $[z_{bot}, z_{top}]$ with
$z_{bot} < z_{top}$, where either boundary may be a fixed elevation, the free
surface, or the seafloor,

$$
Q(z_{bot}, z_{top}) = c_p^0 \int_{z_{bot}}^{z_{top}} \rho \, \Theta \, dz
                    = \rho_0 c_p^0 \int_{\tilde{z}_{bot}}^{\tilde{z}_{top}}
                      \Theta \, d\tilde{z}
                    \approx \rho_0 c_p^0 \sum_k \Theta_k \, \tilde{w}_k
$$

where $\Theta$ is conservative temperature, $\rho$ is in-situ density, and
$\tilde{w}_k$ is the pseudo-thickness of the overlap between layer $k$ and the
requested range.

The middle step is the change of variable $\rho \, dz = \rho_0 \, d\tilde{z}$
from the conventions, and it is an identity, not an approximation: a
mass-weighted integral in $z$ is a plain integral in $\tilde{z}$ scaled by
$\rho_0$.  The final step is the layer quadrature, so the only error is the
usual one of treating $\Theta$ as uniform within a layer.

In particular, the reference density in the discrete sum is **not** a
Boussinesq approximation.  Since $\rho_0 \tilde{h}_k = \rho_k h_k$ is the mass
per unit area of layer $k$ exactly --- for Omega by the definition of
pseudo-height, for MPAS-Ocean because it is Boussinesq --- a range covering
whole layers gives the mass-weighted integral with no reference-density error
at all.  This is the substantive difference from the MPAS-Analysis
formulation, which weights $\Theta$ by a *geometric* thickness and multiplies
by a reference density, and so carries an in-situ-versus-reference density
error of a few tenths of a percent.

The geometric coordinate enters only through the partial layers at the range
boundaries, because the range is specified in $z$ while the integral is in
$\tilde{z}$.

That the range is specified in geometric elevation is a deliberate choice
rather than an oversight.  "Ocean heat content, 0 to 700 m" means 700
*geometric* meters in MPAS-Analysis, in the observational products this
diagnostic is compared against, and in the literature, and the same is true of
a map "at 100 m".  Specifying ranges in pseudo-depth instead would be more
natural for a mass-conserving model --- a fixed $\tilde{z}$ range is a fixed
pressure range and therefore exactly a fixed mass per unit area, which is a
cleaner control volume for a heat budget --- and it would remove the geometric
coordinate from this algorithm entirely.  We do not do it, because it would
silently redefine a number everyone else reports geometrically, for a
difference that is a fraction of a percent in the upper ocean and one to two
percent at abyssal depths.  Config options are documented as geometric
elevations, and the conversion happens here, in one place.

Let

$$
w_k = \max\left(0, \;
      \min\left(z^{int}_{k}, z_{top}\right) -
      \max\left(z^{int}_{k+1}, z_{bot}\right)\right)
$$

be the geometric thickness of the overlap, for layers within
`[minLevelCell, maxLevelCell]` and $w_k = 0$ elsewhere, and let
$h_k = z^{int}_{k} - z^{int}_{k+1}$ be the layer's geometric thickness.  Then

$$
\tilde{w}_k = \frac{w_k}{h_k} \, \tilde{h}_k
$$

is the pseudo-thickness of the overlap, and $\tilde{w}_k = \tilde{h}_k$
whenever the layer lies entirely within the range.

Splitting a layer by a geometric fraction rather than by a pseudo-height
fraction is exact with respect to the model's own discretization, not a further
approximation: within a layer Omega uses a single specific volume
$\alpha_{i,k}$, so $h = \rho_0 \alpha \tilde{h}$ makes $z$ linear in
$\tilde{z}$ across the layer and the two fractions are equal.  For MPAS-Ocean
the question does not arise, since `layerThickness` is the geometric thickness
and $\tilde{w}_k$ reduces to $w_k$.

Where these weights are formed from a *climatology* rather than from a single
month, the ratio $w_k/h_k$ is a ratio of monthly means rather than a mean of
ratios.  This is second order --- it affects only the two boundary layers of a
range, and only through the seasonal cycle of layer thickness --- and it is one
face of the covariance term discussed below.

The $w_k$ expression handles all of the cases the requirement calls for without
special casing: a range boundary in the interior of a layer contributes a
partial thickness; a range extending below the seafloor is truncated because
$z^{int}_{k_{max}+1} = -H$; a `bottom` boundary is expressed as
$z_{bot} = -\infty$; a `top` boundary as $z_{top} = +\infty$, which resolves
per column to the free surface $z^{int}_{k_{min}}$; and a column whose seafloor
lies above $z_{top}$ contributes zero.

Expressing the upper boundary as `top` rather than as $0.0$ matters more than
it looks.  A range written `0.0:-700.0` would exclude the water between the
resting sea surface and the free surface, and would exclude a different amount
of it in each column and in each season.  `top` is what "0 to 700 m" means
everywhere it is reported, and it makes the whole-column range `top:bottom`
cover every valid layer, so that every layer is whole and the geometric
coordinate drops out of that answer entirely.

The globally integrated heat content used for the time series is the
area-weighted sum

$$
Q_{tot} = \sum_i A_i \, Q_i
$$

over cells $i$ with area `areaCell`.

#### Choice of constants

Omega uses TEOS-10, in which conservative temperature is *defined* so that
potential enthalpy is $c_p^0 \Theta$ with the exact constant
$c_p^0 = 3991.86795711963$ J kg⁻¹ K⁻¹.  Using that constant with conservative
temperature is therefore not an approximation but the definition of heat
content.

Polaris's Physical Constants Dictionary provides
`seawater_specific_heat_capacity_reference` = 3996.0 J kg⁻¹ K⁻¹ and
`seawater_density_reference` = 1026.0 kg m⁻³, which are the values
MPAS-Analysis uses.  The specific heat capacity differs from the TEOS-10
constant by 0.1%, which is small compared to other uncertainties but is a
systematic offset in any comparison.

**Decision:** Phase 1 uses the PCD value for $c_p^0$.  The TEOS-10 constant is
not in the PCD today, and adding a constant to it is not something we can
complete by September 15, so using the PCD is what keeps Polaris consistent
with the constants the rest of E3SM is using in the meantime.  It is exposed as
a config option so that a user can experiment with the TEOS-10 value without a
code change.

In the long run we do want $c_p^0$: because Omega carries conservative
temperature, $c_p^0 \Theta$ is potential enthalpy per unit mass by definition,
so the mass-weighted integral above is the heat content rather than an
approximation to it.  Adding $c_p^0$ to the PCD and switching to it is recorded
as a deferred item in {ref}`design-ocean-analysis`.

**$\rho_0$ is not a free parameter.**  Unlike $c_p^0$, the reference density in
the discrete sum is not a modeling choice we are making --- it is the constant
that *defines* pseudo-height in Omega, and the Boussinesq reference density in
MPAS-Ocean.  Using any other value would make $\rho_0 \tilde{h}$ something
other than the layer's mass per unit area.  It must therefore be the same
$\rho_0$ the model used, and it is not exposed as a config option.  Polaris already takes that value from the PCD's
`seawater_density_reference` when it builds Omega's p-star vertical coordinate
in `polaris/ocean/vertical/pstar.py`, so the analysis reads it from the same
place; if Omega's `RhoSw` ever diverges from the PCD value, that is a bug in
Polaris's vertical coordinate before it is a bug in this diagnostic.

The practical consequence of the mass-weighted form, noted above, is that the
in-situ-versus-reference density error in the MPAS-Analysis formulation ---
a few tenths of a percent, nearly uniform, so it biased the absolute heat
content much more than the anomaly --- is gone at no cost, since the model
already writes the mass-like thickness we need.

#### Heat content from a climatology versus from monthly means

The heat content maps are computed from the climatology of $\Theta$ and of the
layer thicknesses, per the requirement.  Because heat content is a product of
those two, this omits the covariance term:

$$
\overline{\Theta \tilde{h}} = \overline{\Theta}\,\overline{\tilde{h}} +
                      \overline{\Theta' \tilde{h}'}
$$

This term is already dropped at every timescale shorter than a month, the
moment the analysis works from monthly means rather than from model time steps.
Neglecting it again from month to season is the same approximation applied over
a longer averaging period, not a new one, so there is little sense in being
scrupulous about the second while accepting the first in silence.

Its size settles the question.  Over a fixed elevation range the term enters
only through the partial layers at the range boundaries and through the free
surface, and for the $0$ to $-700$ m range a seasonal sea surface height of
order $0.1$ m against a near-surface seasonal temperature anomaly of a few
kelvin gives order $10^6$ J m⁻², against a total near $2.9 \times 10^{10}$
J m⁻².  That is order $10^{-4}$ of the signal --- an order-of-magnitude sketch
rather than a bound, but several orders below anything that would change a
conclusion drawn from these maps.  The sub-monthly version is of similar
magnitude and partly cancels, being eddy-driven rather than systematic.

We therefore compute the maps from the climatology and do not plan to revisit
it.  The alternative --- computing per-month vertically integrated maps and
averaging those --- would cost a full pass over the three-dimensional monthly
output for every season plotted, which is a large price for $10^{-4}$.

What this does require is that the climatology include both `PseudoThickness`
and the geometric interfaces: the former sets the mass weight, the latter the
partial-layer fraction at the range boundaries.

The heat content time series does not have the issue at all, because it
integrates each monthly mean separately and averages afterward.

### Algorithm Design: moc-plot

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Omega's MOC analysis group computes the overturning streamfunction on latitude
bins and layer interfaces, in Sverdrups, and writes it with the same
temporal-reduction machinery as `GlobalStats`.  Polaris averages the reductions
over the requested climatology years and plots the result.

Only the **global** streamfunction is plotted.  Omega's MOC group can compute
the streamfunction for named regions, but regional analysis is out of scope for
this deliverable, so no region masks, region names, or region config options
appear here.  Regional overturning --- the Atlantic MOC in particular --- comes
with the rest of the regional analysis in a later delivery, and the plotting
primitive introduced below is written so that it will not need changing then.

Two details need care:

- **The vertical coordinate of the plot.**  The streamfunction lives on layer
  interfaces (`nVertLevelsP1`), which are not at a fixed elevation.  Omega
  shall provide the mean interface elevation alongside the streamfunction; the
  natural way to produce it is a climatology of `GeomZInterface` over the same
  period as the MOC, reduced to a mean per layer interface.  Polaris plots what
  Omega provides and does not reconstruct it: a Polaris-side reconstruction
  would either repeat that averaging on a different period or fall back on
  resting thicknesses, and in both cases the plot's vertical axis would quietly
  disagree with the diagnostic it is labeling.
- **Averaging over the requested period.**  Omega writes per-period reductions
  (e.g. monthly or annual means).  The streamfunction is linear in the
  velocity, so a mean of the reductions weighted by the length of each
  reduction period is the streamfunction of the mean flow over the period.

The exact variable, dimension, and coordinate names in Omega's MOC output must
be confirmed against the implementation before this step is written; see the
open questions.

## Implementation

### Implementation: analysis-suite

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

#### Tasks, steps, and the suite

New tasks live in `polaris/tasks/ocean/analysis/`, added to the ocean component
by `add_analysis_tasks(component)` in `polaris/tasks/ocean/add_tasks.py`.  The
work-directory layout is:

```none
ocean/analysis/
├── climatology/0021-0040/                    (shared: ncclimo)
├── climatology_maps/0021-0040/
│   ├── temperature/ salinity/ velocity/      (one step per field group)
│   ├── ssh/ mixed_layer_depth/
│   └── heat_content/
├── mixed_layer_depth/0021-0040/              (only if computed offline)
│   ├── monthly/                              (accumulator)
│   └── climatology/                          (second ncclimo call)
├── heat_content_series/0001-0060/
├── global_stats/0001-0060/
└── moc/0021-0040/
```

The layout follows one rule --- **`<product>/<period>/[<field group>]`** ---
and the third level exists only for the one product that is chunked.  This is
the work tree, so it is built for predictability and for finding a step's log,
not for browsing; browsing is the staging tree's job.  See principles 1 and 5
in {ref}`design-ocean-analysis`.

Two levels from an earlier draft are gone, and it is worth saying why, since
the reasoning generalizes:

- **`years/`**, which held one shared step per simulation year, is gone because
  those steps are gone --- the expensive per-year work is now a seeded
  accumulator inside a single step.  Renaming the level would not have helped:
  a directory whose best name describes how the work was chunked is a level
  that should not exist.
- **`maps/`, `time_series/`, and `plot/`**, the single-step levels between a
  product and its period, are gone because a level with one child and a name
  that repeats its parent earns nothing and costs a level of depth on every
  path.

Every step is a shared step in the sense of [Shared steps](shared_steps.md),
created at `ocean/analysis`, the highest level at or below which all of the
tasks that use them live.  This matters most for the climatology, which every
field group of `climatology_maps` reads and which therefore runs once no matter
how many of them are run.

Tasks are a thin grouping over these steps and no longer introduce directory
levels of their own: `climatology_maps` is one task with a step per field
group, and `heat_content_series`, `global_stats`, and `moc` are one task with
one step each.  Running a subset is `polaris serial --steps`.

The suite is `polaris/suites/ocean/omega_analysis.txt`, named to match the
existing `omega_pr` and `omega_nightly` suites:

```none
ocean/analysis/climatology_maps
ocean/analysis/heat_content_series
ocean/analysis/global_stats
ocean/analysis/moc
```

A user analyzes a simulation with:

```bash
polaris suite -c ocean -t omega_analysis -w <work_dir> -f analysis.cfg \
    --model omega
polaris serial
```

No `-p`/`--component_path` is given, because no model executable is needed.
The `--model` flag (or an `[ocean] model` option in the config file) tells
Polaris which model's naming conventions to expect on read.

Analyzing two simulations means two work directories.  The simulation name is
not part of the work-directory path, because task subdirectories are fixed when
the component is constructed, before the user's config file has been read.

#### Config options

Defaults ship in `polaris/tasks/ocean/analysis/analysis.cfg` and the user
overrides the ones that describe their simulation.  The sections below are the
proposed starting point:

```ini
[ocean_analysis]

# The absolute path to the simulation's Omega configuration file.  This is the
# analysis' only description of where the simulation's output lives: Polaris
# reads the mesh, the output streams and their file-name templates from it, so
# that none of them have to be restated here.  It is required, since an Omega
# run always has one.  MPAS-Ocean output is not supported; reading it would
# need a translator from its namelists and streams into the same form.
omega_config_filename =

# The absolute path to the directory containing the simulation's output.
# Defaults to the directory containing the Omega configuration file, which is
# what its relative file names are resolved against.
simulation_path =

# A short name for the simulation, used in plot titles and file names
simulation_name = omega

# Where to publish plots, their netCDF files, thumbnails, and the generated
# gallery.  Defaults to <work_dir>/analysis_output.  Point this somewhere
# web-servable if you want to share the results.  The thumbnail options that
# go with it are given under `publication`.
output_path =

# The horizontal mesh file, absolute or relative to simulation_path.  Defaults
# to the mesh the Omega config names.
mesh_filename =

# The vertical-coordinate file (Omega only), absolute or relative to
# simulation_path
vert_coord_filename =


[ocean_analysis_climatology]

# The first and last year of the climatology, inclusive
start_year = 1
end_year = 10

# The seasons to compute, in addition to the 12 monthly climatologies
seasons = ANN, DJF, MAM, JJA, SON

# The seasons to plot; may include the monthly climatologies JAN through DEC
plot_seasons = ANN, DJF, JJA

# The fields for which climatology maps are produced, using MPAS-Ocean
# (Polaris standard) names
fields = temperature, salinity, velocityZonal, velocityMeridional, ssh,
         mixedLayerDepth

# The elevations at which fields with a vertical dimension are plotted.
# Elevations are in m, positive up, so values within the ocean are negative:
#   top      the topmost valid layer of each column (the sea surface)
#   bottom   the bottommost valid layer of each column (the seafloor)
#   <z>      an elevation in m, linearly interpolated
#   k<index> a fixed, zero-based vertical index
elevations = top, -100.0, -500.0, -2000.0, bottom

# Whether to compute mixed-layer depth offline from monthly-mean temperature
# and salinity, for simulations whose output does not include it
compute_mixed_layer_depth = False

# The density threshold used when computing mixed-layer depth offline, in
# kg m-3, relative to a reference elevation of -10 m
mixed_layer_depth_threshold = 0.03


[ocean_analysis_ohc]

# The elevation ranges over which heat content is integrated, given as
# <top>:<bottom> in m, positive up.  "bottom" means the seafloor.  These are
# geometric elevations, matching the convention used by MPAS-Analysis and by
# observational heat content products; the integral itself is mass-weighted.
elevation_ranges = top:-700.0, -700.0:-2000.0, -2000.0:bottom, top:bottom

# The specific heat capacity used to convert conservative temperature to heat
# content.  By default, this comes from the Physical Constants Dictionary.
# The reference density is not a config option; see the algorithm design.
#seawater_specific_heat_capacity = 3996.0


[ocean_analysis_time_series]

# The first and last year of the time series, inclusive
start_year = 1
end_year = 10

# The fields from the model's global statistics output to plot.  Fields the
# simulation did not write are skipped with a message, not an error.
fields = temperature, salinity, normalVelocity, kineticEnergyCell, ssh

# The statistics to plot for each field.  As with fields, missing statistics
# are skipped.
stats = mean, min, max, std


[ocean_analysis_moc]

# The contour interval in Sv
contour_interval = 2.0

# The maximum absolute value of the color map in Sv; the color map is
# symmetric about zero
#max_streamfunction = 30.0
```

Per-field plotting options follow the existing Polaris convention of a section
per field, as in `realistic_global.cfg`:

```ini
[ocean_analysis_map_temperature]
colormap_name = cmo.thermal
norm_type = linear
norm_args = {'vmin': -2., 'vmax': 32.}
```

Sections for the fields we expect to plot ship with defaults; fields without a
section fall back to the defaults in `polaris.viz.get_viz_defaults`.

The section name is not the field name pasted onto a prefix.  Field names are
the models' own and are therefore camel case, while Polaris config sections are
lower case with underscores everywhere else in the codebase, and the sections
this design adds are no exception.  A field's section is
`ocean_analysis_map_<field, in lower case with underscores>`, so
`velocityZonal` gets `[ocean_analysis_map_velocity_zonal]` and
`mixedLayerDepth` gets `[ocean_analysis_map_mixed_layer_depth]`.

That conversion is mechanical, so no step spells a section out.  A small helper
module, `polaris/tasks/ocean/analysis/config_sections.py`, provides
`camel_to_snake(name)` and `map_section(field)`, and every caller goes through
`map_section`, so exactly one place knows the prefix and the spelling rule.  It
is a leaf module with no Polaris imports, for the same reason `sim_files.py` is
one: it can be unit tested on its own, and any step can use it without pulling
in a step.

#### Field and dimension naming

Per the conventions stated in the summary, config options name fields using
MPAS-Ocean names, and analysis code uses MPAS-Ocean variable and dimension
names throughout.  `OceanIOStep.open_model_dataset` performs the translation
from Omega names on read, driven by `polaris/ocean/model/mpaso_to_omega.yaml`,
which already maps the vertical geometry this design depends on:

```yaml
  zMid: GeomZMid
  zInterface: GeomZInterface
```

**The mapping reconciles two spellings; it is not a naming authority.**  An
entry exists when both models write the same quantity under different names,
and only then.  Three cases follow from that, and they cover everything this
design needs:

- **Both models have the field.**  It is mapped, and analysis uses the
  MPAS-Ocean name --- `temperature`, `zMid`, `areaCell`.
- **Only Omega has the field.**  A mixed-layer depth diagnostic, for instance.
  There is nothing to reconcile, so there is no entry and analysis uses the
  Omega name as written.  Inventing an MPAS-Ocean-styled synonym would put a
  name in the codebase that no model ever writes, and the entry recording it
  would be a rename in appearance only.
- **Both models have a similar name for different quantities.**
  `layerThickness` and `PseudoThickness` are the case in point.  There is no
  entry, deliberately, for the reasons given under the conventions.

The practical consequence of the middle case is that Omega's spelling appears
in analysis code, and in the values of config options that name fields, for
fields Omega alone provides, which is a small inconsistency of style and an
accurate one: those fields come from Omega and from nowhere else.  Config
section names are the exception, because they are Polaris' own rather than
either model's: `map_section` converts the field name, so no model's spelling
reaches a section header.  If such a field later gains an MPAS-Ocean
counterpart, or Omega renames it, that is the point at which an entry earns its
keep --- and adding one then is a one-line change, so there is nothing to be
gained by adding it in advance.

No analysis step branches on `config.get('ocean', 'model')` to choose a field
or dimension name, except `get_layer_mass`, which exists precisely to be that
one branch.  Anywhere else, a branch on the model means either that the mapping
is missing an entry, or that a field one model does not have is being read
unconditionally.

#### Locating input files

A small helper module, `polaris/tasks/ocean/analysis/sim_files.py`, expands the
file-name templates over a year range into lists of files and checks that they
exist, reporting the missing years clearly.  It is shared by every step that
reads simulation output.  This is deliberately a separate module rather than a
method on a step, so that it can be unit tested and reused.

Where the templates come from is the point.  The user's input is
`omega_config_filename`, the path to the simulation's own Omega configuration,
and the same module reads the output streams from it: each stream gives a
file-name template, a reduction period and a directory, which is enough to
identify the monthly means, the `GlobalStats` output and the MOC output without
the user restating any of it.  The mesh and the vertical coordinate are read
from the same place.

**The templates are not config options, and the Omega configuration is
required.**  An earlier draft had `monthly_mean_template` and its siblings as
config options overriding what the Omega configuration says, which cannot
work: Polaris config files use `ExtendedInterpolation`, so a bare `$Y` in a
value raises `invalid interpolation syntax` and takes down the whole config
combine, not merely that option.  Escaping it as `$$Y` would work and would be
a trap, since a template pasted out of `omega.yml` would then fail
confusingly.

Removing the override layer rather than escaping it is the better trade in any
case.  An Omega run always writes an `omega.yml`, so there is no case where the
configuration is genuinely unavailable and the fallback would earn its keep;
making it required removes the precedence rules, the reporting of which source
won, and the one path by which a `$` could reach a config value.  What remains
in the config file are plain paths with no templating in them ---
`simulation_path`, `mesh_filename` and `vert_coord_filename` --- for output or
a mesh that has moved since the run.  Each may be absolute or relative to
`simulation_path`, and the step reports which of the two sources each path came
from, so that a surprising file list can be diagnosed without guessing.

**MPAS-Ocean output is therefore not supported, and says so.**  Reading it
needs a translator from its namelists and streams into the form this module
reads, which is separate work and is not in scope here.  This costs the
deliverable nothing: the design already develops against Omega output rather
than MPAS-Ocean output, for the reasons given under `omega-monthly-means`.  A
step set up against a simulation whose `[ocean] model` is `mpas-ocean` reports
that rather than failing obscurely later.

Reading Omega's configuration is done defensively --- a missing stream, a
stream that names no file, and an analysis group that is turned off are told
apart and reported as such --- since its schema is Omega's to change and this
is the one place Polaris depends on its shape rather than on its output.  The
names of an analysis group's output streams have to be reconstructed the way
Omega's analysis manager builds them, as
`<prefix>_<period><TimeStats|Instants><template>`.  A group can write both time
means and snapshots, under different names, and today's simulations write only
snapshots, so neither spelling can be assumed: the time mean is preferred where
there is one.

The pattern is MPAS-Analysis's, which locates MPAS-Ocean and MPAS-Seaice output
by reading their streams files rather than asking the user where each file
lives.  Only the file being read differs.  Worth knowing when the Omega reader
is written, because the failure modes MPAS-Analysis hit there --- a stream
present but empty, a template whose expansion matches nothing, a relative path
resolved against the wrong directory --- are the ones to report clearly rather
than discover in a traceback.

Input files are symlinked into each step's work directory in `setup()` using
`Step.add_input_file`, which gives the usual Polaris provenance and dependency
checking without copying data.

**Where that reporting goes is not settled, and today's answer is temporary.**
It is written to stdout during `setup()`, because a step has no logger until
the run harness attaches one, and it earns its place while the reader is new:
it is how a wrong file list gets diagnosed at the moment.  It cannot stay
there.  Polaris deliberately writes almost nothing during setup, so that what
the user sees is the suite being set up rather than the internals of individual
steps, and ten analysis steps each reporting their inputs dilutes exactly that.
Before the deliverable, this moves into each step's own log at run time, where
`self.logger` exists and where a reader looking into one step's behavior will
go for it, leaving setup with only what it already prints.

#### Every path is explicit

Polaris changes the process working directory into each step's work directory
before running it, so a step may open a bare filename and get the right file.
Analysis steps do not rely on that, per
[Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md): a step
that depends on the process working directory cannot run beside another step in
one process and cannot be sent to a worker on another node at all.

Declaring inputs and outputs by relative name stays exactly as it is --- setup
already resolves those against the step's work directory.  The rule is about
the body of `run()`, and the framework now provides what it needs:
`Step.work_path()`, which joins path components onto the step's own work
directory and returns an absolute path, raising rather than guessing if the
work directory is not set.

Every `open`, `open_model_dataset`, `write_netcdf` and output filename in the
pseudocode below goes through it.  The pseudocode is written that way rather
than being cleaned up later, because this is precisely the habit that is cheap
to adopt while the code is being written and expensive to retrofit once there
are dozens of steps.

Temporary files go in the step's work directory for the same reason, never in
`/tmp` or the base work directory: each step already has a directory of its
own, so writing there is enough to guarantee that two concurrent steps cannot
choose the same temporary path.

#### Declared resources

Every analysis step declares what it needs, so that a scheduler can decide how
many may run at once.  Two quantities matter and they behave differently.

**Cores** are declared as `cpus_per_task` with `ntasks = 1`, since nothing here
is MPI.  The number is whatever parallelism the step will actually start, which
in Phase 1 is one for every step except the climatology, where it is twelve to
match `ncclimo`'s background processes.  Should a step later gain an internal
pool, its size comes from this number and never from `os.cpu_count()`: that is
the whole content of the bounded-process-launching rule, since a step sized to
the machine oversubscribes the node the moment a second step runs beside it.

**Memory** is the quantity that distinguishes analysis from most existing
Polaris steps, because at high resolution a step can need a large fraction of a
node and a scheduler packing by cores alone will oversubscribe it.  What each
step's footprint is set by is known:

- an accumulator holds one month of three-dimensional input at a time, which is
  what keeps its footprint independent of the length of the record --- reading
  a month at a time rather than a year is a resource decision and not only a
  convenience, and it is what lets several decades at 6to18 km be analyzed at
  all;
- a map step holds one season of the climatology for its field group, plus the
  `mosaic` descriptor for the mesh;
- the climatology step's footprint is `ncclimo`'s, not ours;
- the merge and publish steps hold kilobytes.

The *numbers* are deliberately not guessed here.  Sensible values need
measurement at production resolution, which is being gathered separately for
exactly this purpose, and a guessed default that is too large wastes a node
while one that is too small fails late.  What this design commits to is that
each step declares the quantity, and that the declaration is derived from the
list above rather than from a spot measurement of one configuration.

### Implementation: data-products

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Each plotting step writes, alongside each PNG, a netCDF file with the same base
name containing the plotted field, its coordinates, units, and the config
options --- including the date range --- that produced it as global attributes.
Both go in the step's own subdirectory, are described in the step's manifest
fragment, and are published into the staging tree by symlink, as described
under `publication`.

The manifest is what carries the facets that identify a product --- field,
season, vertical reduction, date range, and later region and observational
reference.  Encoding those in the path instead would mean a directory level per
facet, and a path has one dimension where the metadata has six.

The expensive intermediates are:

- the `ncclimo` output in `ocean/analysis/climatology/<range>/`, already a set
  of netCDF files;
- the monthly heat content cache written by the heat content accumulator;
- the equivalent monthly mixed-layer depth cache, if it is computed offline.

The climatology is a range-keyed output of a shared step, so its reuse is
Polaris's ordinary step-completion behavior.  The accumulator caches carry the
provenance stamp that makes them safe to inherit across runs.

### Implementation: repeated-analysis

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Everything this requirement asks for falls out of machinery Polaris already
has, provided the step tree is keyed correctly.  No framework changes are
needed.

#### Steps can be built from the user's config

The `Task` subdirectory is fixed when the component is constructed, before the
`-f` config file is read --- but a task's *steps* are not.  `polaris setup`
merges the user's config into each task's config parser and then calls
`Task.configure()` on every task, and only afterward adds configs to the steps,
explicitly so that steps created during `configure()` are handled.  A task may
therefore discard and rebuild its entire step list from config options that the
user supplied at setup time, with subdirectories derived from those options.

This is not a new pattern.  The cosine bell task family does exactly this: its
`configure()` calls `_setup_steps()` again "in case a user has provided new
resolutions", removing every step and re-adding one per resolution at a
subdirectory named for the resulting mesh.  Shared steps are created at a
computed subdirectory with `Component.get_or_create_shared_step()`, which
returns the existing step if one has already been created at that
subdirectory.

The analysis tasks use the same pattern with date ranges in place of
resolutions.

#### Re-running comes from range-keyed step subdirectories

Every range-dependent step lives at a subdirectory named for the range it
covers: `climatology/0021-0040`, `climatology_maps/0021-0040/temperature`,
`global_stats/0001-0060`.  A setup with a new range therefore
creates *new steps in new directories*, which have never run and so are not
complete, and they run.  A setup with the same range lands on the same
directories, which are complete, and nothing is recomputed.

This is the behavior the requirement asks for, and it needs nothing beyond the
existing rule that a step is complete when `polaris_step_complete.log` exists
in its work directory.  It also makes it structurally impossible to get a plot
labeled with one range whose contents came from another, since the two ranges
never share a directory.

#### Reuse comes from seeded accumulators

The expensive range-independent work --- vertically integrated heat content,
and mixed-layer depth if it is computed offline --- is one step per product,
keyed by the range like everything else, which inherits what earlier runs
already computed.

`polaris/tasks/ocean/analysis/accumulate.py` provides the shared machinery, so
that each product supplies only its kernel and its cache layout:

```python
class Accumulator(OceanIOStep):
    def setup(self):
        # find cache files under sibling range directories of this product,
        # keep those from completed steps whose provenance stamp matches,
        # and add each as an input file.  product_dir is an absolute path
        # resolved at setup, not a path relative to the process cwd
        self.seeds = discover_seeds(self.product_dir, self.stamp())

    def run(self):
        needed = months_in_range(self.start_year, self.end_year)
        have = inherited_months(self.seeds)
        self.logger.info(f'inheriting {len(have)} months, '
                         f'computing {len(needed - have)}')
        for month in sorted(needed - have):
            self.compute_month(month)
        publish(have, needed)
```

#### One step per accumulator in Phase 1

Each accumulator is a single step, and its months are processed one after
another.  Phase 1 runs serially: there is no scheduler to feed by the deadline,
so splitting a product into more steps would add directories, a merge step and
a config option while nothing ran any sooner.

The design this leaves on the table is recorded in principle 3 of
{ref}`design-ocean-analysis`, and it is worth knowing that taking it later
costs nothing here.  Splitting an accumulator into several steps that each
cover a slice of the request is safe *because inheritance is decided by
content*: a shard asks which months it needs and which of them some earlier run
already produced, and neither question refers to how that earlier run was
divided.  So the split can be introduced when there is a scheduler to use it,
and every month cached before then is still inherited.  That is the property a
chunk keyed by its path could never have had, and it is why deferring this is a
deferral rather than a debt.

Four things about this are worth stating explicitly, because they are what make
it acceptable to have software hunting for data on disk.

**The search scope is what construction guarantees, and nothing wider.**  Only
sibling directories of the same product are candidates: the same step class,
with the same outputs, differing only in the range.  Nothing outside the
product's own directory is searched, and no other work directory is ever
consulted.

**Admissibility comes from content, not from location.**  Each cache record
carries a provenance stamp --- the identity of the simulation, the config
options that govern the product, and a version integer for the kernel --- and a
record whose stamp does not match is recomputed rather than inherited.  This
matters because the path guarantees less than it looks like: task
subdirectories do not encode which simulation was analyzed, so the same work
directory pointed at a second simulation would otherwise cross-contaminate in
silence, as would a changed elevation range or a changed constant.

**Only completed steps are candidates.**  A sibling directory without
`polaris_step_complete.log` is skipped, which also disposes of the
half-written cache left by an interrupted run.

**Reuse is reported.**  Each run logs how many months it inherited and from
where, and the provenance travels into the output netCDF.  One config option
provides an explicit mode for anyone who wants determinism instead of
discovery:

```ini
[ocean_analysis]

# Inherit results from earlier analyses of the same simulation in this work
# directory.  Set to False to recompute everything from the monthly means.
reuse_previous = True

```

The pattern applies wherever we own the reduction kernel.  It does not apply to
the climatology, because `ncclimo` has no incremental mode; a climatology is
recomputed in full for each new range.

Extending a time series from twenty years to forty therefore reads twenty years
of monthly means, not forty.  Running a forty-year range and then a twenty-year
sub-range inside it reads nothing at all the second time.  A partially written
cache in the step's own directory is itself a valid starting point on a retry,
which is most of what restartability asks for.

Because the remaining months are independent, they are spread over a process
pool inside the step rather than over steps.  This follows principle 3 in
{ref}`design-ocean-analysis`, and it means the analysis gets its concurrency
from a capability that exists today rather than from task parallelism.

#### Replotting

Re-running with an unchanged range recomputes nothing, which is what the
requirement asks for and is usually what a user wants.  It is not what they
want after changing a colormap.  A config option forces the plotting steps to
run again:

```ini
[ocean_analysis]

# Re-run the plotting steps even when their range is unchanged, to pick up
# changes to colormaps and other plot styling.  Intermediate results --
# climatologies and accumulator caches -- are still reused.
replot = False
```

When it is set, `configure()` removes the completion markers of the steps that
produce plots, and only those, so replotting costs the plotting and nothing
else.  This is why plotting does not need to be split into its own step, per
principle 10: for a map, plotting *is* the expensive part, so a separate step
would buy nothing that this option does not.  MPAS-Analysis replots
unconditionally, which is rarely what is wanted; the default here is not to.

#### Caveats

`polaris setup` rewrites the suite pickle at the root of the work directory, so
the most recently set-up range is the one `polaris serial` will run.  Step
directories from earlier ranges are untouched --- they have their own pickles,
outputs, and completion markers --- so re-running an earlier range means
re-running setup with that range's config, after which everything it needs is
already complete except whatever it is being asked to redo.

Analyzing many ranges accumulates step directories, climatology files, and
accumulator caches.  This is deliberate, since it is what makes re-analyzing an
earlier range nearly free, but it is worth knowing about on a filesystem with a
quota.  The climatology files dominate: an accumulator cache for a reduced
series is kilobytes, while a full set of `ncclimo` output is a copy of the
requested fields for every season.

### Implementation: publication

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

The work tree is built for predictability, not for browsing, so results are
published into a separate staging tree whose root is a config option.  This is
principle 1 in {ref}`design-ocean-analysis`: two trees, two audiences.

#### Where the code lives, and on which branch

Publication is three pieces, and keeping them apart is what lets presentation
change without touching a step:

- the **manifest writer**, which a plotting step calls once per product;
- the **collector**, which merges the fragments, publishes each product, and
  renders its thumbnail;
- the **site generator**, which renders the index from the merged manifest.

None of the three knows anything about the ocean --- the writer takes arbitrary
facets, and the generator renders whatever the manifest holds --- so all three
live in a component-neutral `polaris/analysis/` package beside `polaris/viz/`,
rather than under `polaris/tasks/ocean/analysis/` to be moved when a second
component wants them.  The templates ship as package data named `*.template`,
which `MANIFEST.in` already includes.  `jinja2` and `pillow` are both already
in the environment --- `jinja2` is used by `polaris/streams.py` and `pillow`
arrives with `matplotlib` --- but both become direct dependencies here and are
declared as such in `pyproject.toml`.

Following the branch rules in {ref}`design-ocean-analysis`, this work is a
branch cut from the analysis scaffolding rather than from either arm of
products, because the manifest writer is a dependency of every plotting step
and shared infrastructure is cut below its consumers.  The consequence is
deliberate and is recorded here so that it is not rediscovered: the branches
that add products rebase onto this one, and each gains one commit that emits
its own manifest fragments.

#### Config options

```ini
[ocean_analysis]

# Where to publish plots, their netCDF files, thumbnails, and the generated
# gallery.  Defaults to <work_dir>/analysis_output.  Point this somewhere
# web-servable if you want to share the results.
output_path =

# The width in pixels of the thumbnail generated for each plot.  Thumbnails
# are what make a few hundred plots browsable, and their total size is what
# decides whether a gallery page loads over a throttled link, so this is the
# first thing to reduce if pages are slow to appear.
thumbnail_width = 320

# The image format for thumbnails, jpeg or webp.  webp is roughly a quarter
# smaller at the same quality and every current browser reads it; jpeg is the
# safer default.
thumbnail_format = jpeg

# The compression quality of thumbnails, from 1 to 100.  Above about 80 the
# bytes grow quickly and a thumbnail does not look better.
thumbnail_quality = 75
```

#### Every step writes a manifest fragment

Alongside its outputs, each step writes `manifest.json` describing every
product it made and the facets that identify it:

```json
{"products": [
  {"png": "temperature_ANN_-100m.png",
   "nc": "temperature_ANN_-100m.nc",
   "group": "climatology_maps", "gallery": "temperature",
   "field": "temperature", "season": "ANN", "reduction": "-100m",
   "start_year": 21, "end_year": 40,
   "title": "Potential temperature at 100 m, ANN, years 21-40"}]}
```

Three rules keep this from growing into a format that needs a specification.

**A step fills the facets; the collector fills everything else.**  The
published name and the thumbnail are added by the collector when it publishes,
so a step never has to know the staging tree's layout, and a change to that
layout is a change to one step.

**Only `group` and `gallery` shape the site.**  Every other facet is caption
material today and filter material later.  This is the hinge that makes the
extensibility requirement cheap: adding a `region` facet adds a key to the
fragment and a word to the caption, and changes nothing in the generator.

**Order is meaning, so the collector preserves it.**  Products keep the order
they appear in within a fragment, and fragments are ordered by group and
gallery.  A gallery therefore reads ANN, DJF, MAM, JJA, SON because that is the
order the step plotted them in, and no sort key, season-ordering table, or
comparator has to exist anywhere.

The manifest is what carries the facets that identify a product --- field,
season, vertical reduction, date range, and later region and observational
reference.  Encoding those in the path instead would mean a directory level per
facet, and a path has one dimension where the metadata has six.

#### A `publish` step collects, thumbnails, and generates

One cheap step per suite reads every fragment and, in order: symlinks each
product into the staging tree, renders a thumbnail for each plot, writes the
merged manifest, and generates the site over it.  It works from the fragments
rather than from directory structure, which is what lets the work be re-chunked
later without disturbing output paths, links, or the gallery --- principle 2.
A product whose fragment is present but whose file is missing is reported
rather than silently omitted.

Because it is the only step that knows how results are presented, everything in
the two sections below can change without a single plotting step changing.

#### The staging tree

The staging tree is shallow, with descriptive filenames.  A shallow tree is
easier to archive, to serve, and to diff between two analyses:

```none
<output_path>/
├── index.html                                      (the gallery groups)
├── manifest.json                                   (the merged manifest)
├── galleries/
│   ├── climatology_maps_temperature_0021-0040.html
│   └── …
├── plots/
│   ├── climatology_maps_temperature_ANN_-100m_0021-0040.png
│   ├── climatology_maps_temperature_ANN_-100m_0021-0040.nc
│   ├── climatology_maps_heat_content_ANN_top_to_-700m_0021-0040.png
│   ├── heat_content_series_0001-0060.png
│   └── …
└── thumbnails/
    └── climatology_maps_temperature_ANN_-100m_0021-0040.jpg
```

The filename is the facets in a fixed order, so it sorts usefully, greps
usefully, and cannot collide between two ranges.  Range keys are the
zero-padded start and end years, matching the convention `ncclimo` already uses
in its file names.  This follows MPAS-Analysis, where the experience with a
flat plot directory plus a generated gallery has been good.

**Products are published by symlink** from the step that owns them, so each
file has exactly one owner, Polaris's output checking continues to work, and
the staging tree is a view rather than a second source of truth.  Results from
different ranges coexist because the range is in the filename.

Thumbnails are the exception: they are generated files with no owner upstream,
so they are real files in the staging tree rather than symlinks, and they are
regenerated only when missing or older than the plot they came from.  Adding
one product to an existing analysis therefore costs one thumbnail, not three
hundred.

#### Thumbnails

Each thumbnail is made from the published PNG with `pillow`: the image is
flattened onto white, since the plots are written with an alpha channel and
neither JPEG nor a gallery wants transparency, scaled to `thumbnail_width`
preserving aspect ratio, and written in `thumbnail_format` at
`thumbnail_quality`.

Making them here rather than in the plotting steps is deliberate.  It keeps the
plotting steps ignorant of presentation, it keeps the policy in one place where
changing it re-renders everything consistently, and it means a thumbnail can be
regenerated from what was published without re-running any analysis.

The measured cost, on the three-panel MPAS-Analysis figure used for the
comparison below, is 20 ms per image to decode, scale, and encode.  A default
Phase 1 analysis is on the order of a hundred products, so the whole pass is a
few seconds.  Memory is one image at a time.  The loop is embarrassingly
parallel and is an obvious candidate for principle 3's in-step pool if the
product count ever grows enough to matter; Phase 1 runs it serially with
`cpus_per_task = 1`.

#### The generated site

The site follows MPAS-Analysis's shape, because that is what the Ocean Team
already knows how to navigate:

- a **gallery group** is a section of the landing page: a product group for one
  date range, such as "Climatology maps, years 0021-0040".  The collector
  composes this from the `group` facet and the range rather than the step
  naming it, so a step stays unaware that ranges accumulate side by side.
- a **gallery** is one page of thumbnails within a group, such as the maps of
  potential temperature, and is identified by the `gallery` facet.
- the landing page shows each group with one representative thumbnail per
  gallery --- the gallery's first product, which is deterministic because order
  is preserved --- so the reader chooses a gallery by looking rather than by
  reading names.

Clicking a thumbnail opens the full PNG, with the netCDF linked beside it.
That link target is the one thing that changes when per-product pages arrive.

The pages are rendered from `jinja2` templates with the CSS inlined, so a page
costs one HTML request and its images, and no stylesheet request.  There is no
JavaScript: the site works from `file://`, from `python -m http.server`, and
from the LCRC portal identically, and there is nothing to break when a browser
changes.  Every `<img>` carries `loading="lazy"` so that thumbnails below the
fold are not fetched until they are scrolled to, and explicit `width` and
`height` so that lazy loading does not make the page reflow as images arrive.
Both are plain HTML attributes supported by every current browser.

Every page carries the simulation name, the date ranges, and the Polaris
provenance from `polaris/provenance.py`, so a page found later can be traced
back to what produced it.

#### What a page costs

This is the number the design exists to control, so it is worth writing down
rather than asserting.

The reference is a real MPAS-Analysis result: one page of its ocean output
carries **1641 thumbnails at roughly 46 kB each**, all fetched eagerly, which
is about **75 MB in 1641 requests** before the page settles.  Its thumbnails
are 480 px wide and lightly compressed.  This is the behavior that stalls on a
throttled link.

Against a single global map panel of that figure --- a stand-in for the
single-panel maps this suite produces, since no Polaris analysis has been
published yet --- a thumbnail at the defaults above is **about 13 kB** as JPEG
at 320 px and quality 75, or about 10 kB as WebP.  This should be confirmed on
real output rather than trusted; the point it is making, that the reference's
thumbnails are several times larger than they need to be, is not sensitive to
the exact figure.  With the default field and season lists a climatology-map
gallery holds roughly fifteen products, so a gallery page is a ~10 kB document
plus ~200 kB of thumbnails, of which lazy loading fetches only the visible rows
--- on the order of **100 kB** before the page is usable.  The landing page
carries one thumbnail per gallery, so it is of the same order.

The three levers act independently, which is why all three are used: small
thumbnails cut the bytes per image by a factor of three or four against the
reference, gallery pages cut the images per page by two orders of magnitude,
and lazy loading cuts what is fetched before the page settles to the handful
that are visible.  A single page never asks for a full PNG.

What is *not* known is whether the LCRC portal throttles bytes or requests.
Everything above helps with either, but the remedies differ if requests are the
binding constraint --- a sprite sheet, or thumbnails inlined in the page as
data URIs --- and both are worse in every other way.  Deciding between them
should follow a measurement against the portal rather than a guess; that
measurement is listed under testing below, and the alternatives are recorded
among the deferred items in {ref}`design-ocean-analysis`.

#### Where this is extended

Four extensions are expected, and none requires a step, a fragment, or a
published path to change:

- **New facets** --- region, an observational reference, a second simulation to
  compare against --- are new keys in the fragment and new words in a caption.
  Only a facet that should become a new gallery or group touches the generator.
- **Per-product pages**, carrying the provenance and the code that reproduces a
  figure in the way E3SM-Diags does, are a new template and a changed link
  target.  The manifest already holds everything such a page would show except
  the recipe itself.
- **Filtering and search** across facets are a client-side layer over
  `manifest.json`, which the site already publishes beside the pages for
  exactly this reason.
- **A different visual design** is templates and CSS.


### Implementation: omega-monthly-means

Date last modified: 2026/08/27

Contributors: Xylar Asay-Davis, Claude

This is Omega work and is implemented in the Omega repository, not in Polaris.
What Polaris needs to do:

- name the stream the monthly means are written to.  The file names come from
  the simulation's own Omega configuration, so a change to the stream's file
  name, frequency or directory needs no Polaris change --- but which stream to
  read is Polaris's to say, and the expectation is that monthly means will get
  a stream of their own rather than staying in `History`, which is where the
  mock-up has them.  That is a one-line change here when the stream exists;
- add any new Omega fields, including a mixed-layer depth diagnostic, to
  `polaris/ocean/model/mpaso_to_omega.yaml` once their Omega names are fixed;
- add an Omega YAML fragment that turns on monthly-mean output of the required
  fields, so that a Polaris-run simulation can produce input for its own
  analysis, in the same way `analysis_members.cfg` and `forward.yaml` configure
  `GlobalStats` today.

#### A mock-up already exists to develop against

Development proceeds against Omega output rather than MPAS-Ocean output.
MPAS-Ocean would be a misleading target: its variable and dimension names
differ, its time metadata is not CF compliant, and its monthly means come from
a different analysis member with different conventions, so code that works
against it tells us little about whether it will work against Omega's.

That would have limited early work to the shared kernels, but no longer does.
A one-year QU240 Omega simulation has been run for this purpose on the
`mockup-realistic-global-analysis-run` branch, and a mock-up set of
monthly-averaged files derived from it is staged at

```none
<test_dir>/qu240-one-year-analysis-mockup/monthly_means/ocn.hist.0001-01.nc … 0001-12.nc
```

one month per file, carrying `Temperature`, `Salinity`, `PseudoThickness`,
`GeomZMid`, `GeomZInterface`, `SshCell`, `SpecVol`, `KineticEnergyCell` and
`NormalVelocity`, on dimensions `time`, `NCells`, `NVertLayers`,
`NVertLayersP1` and `NEdges`, with `time` in `seconds since 0000-12-01` on a
`noleap` calendar and `time_bnds` giving each month's bounds.

These files are reached by pointing `simulation_path` at a directory whose
`output/` is a symlink to `monthly_means/`, since the run's own Omega
configuration names `output/` and the mock-up is not what Omega will actually
write.  That is a fixture, deliberately, and not something the analysis has
code for: the mock-up exists to be developed against and then discarded, and
the monthly means are expected to arrive in their own stream in any case.

Every product in this design except mixed-layer depth and the reconstructed
velocity components can be developed and tested against these files today.
They are what the order of work assumes: the steps are built against real Omega
output from the start rather than against synthetic data with a later
integration step.

#### `ncclimo` reads Omega output --- confirmed

The open question about whether `ncclimo` could read Omega monthly means
without the MPAS-specific `-P mpaso` processing type is **settled, and the
answer is yes** --- provided `time_bnds` is present and holds the expected
values.  That was established against the mock-up files above, and it is why
the requirement now names `time_bnds` specifically rather than asking for
"time bounds" in general.

This was the item on the critical path, so it is worth being clear about what
was and was not shown: that `ncclimo` accepts the files and produces
climatologies, at QU240, from a mock-up.  It has not been exercised at high
resolution, over multiple years, or against output Omega's own monthly
reduction wrote rather than a mock-up of it.

The steps are written so that they degrade gracefully: a step whose input
fields are not yet available reports which fields are missing from which file
and skips the affected products, rather than failing the suite.  This is what
makes it possible to run the suite against a partially-capable Omega and get
the products that are ready.

### Implementation: climatology

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

`polaris/tasks/ocean/analysis/climatology.py` defines a `Climatology` step:

```python
class Climatology(OceanIOStep):
    def setup(self):
        # expand the monthly-mean template over [start_year, end_year] and
        # symlink each file into the step's work directory
        # register the expected ncclimo output files as outputs

    def run(self):
        # assemble the list of variables needed by the steps that use this
        # climatology, plus the vertical-geometry variables
        # run ncclimo
```

The `ncclimo` command:

```none
ncclimo --no_stdin -4 --clm_md=mth -a sdd \
    -p <parallel_mode> -j <threads> \
    -v <variables> --seasons=<seasons> \
    -s <start_year> -e <end_year> -o . <input files>
```

Notes on the arguments:

- `-a sdd` selects the seasonally discontinuous December convention discussed
  in the algorithm design.
- `-v` restricts the climatology to the union of the fields requested for maps,
  the fields needed for heat content (`temperature` and the model's mass-like
  thickness), and the vertical geometry (`zMid`, `zInterface`).  Every name on
  that list is a field the model wrote, which is what keeps the mapping back to
  Omega names below well defined.  Building this list is the reason `Climatology` needs
  to know which steps depend on it; the list is assembled from config options
  at runtime rather than passed in by each task, so that the step stays neutral
  with respect to which tasks pulled it in.

  Note that `-v` takes the names as they appear *in the files*, which are Omega
  names, so the step maps its Polaris-standard list back through
  `mpaso_to_omega.yaml` before building the command.  This is the one place in
  the design where the model-specific names are unavoidable, because `ncclimo`
  operates on the files rather than on an opened dataset.
- Omega's monthly means carry CF time metadata, so `ncclimo`'s generic handling
  should apply and the MPAS-specific `-P mpaso` processing type should not be
  needed.  **This needs to be confirmed against real Omega output**; if
  `ncclimo` cannot read Omega files directly, the fallback is either an
  NCO-side change or a small preprocessing pass, and this should be checked as
  soon as Omega can write monthly means because it is on the critical path.
- `-p`/`-j` set the parallel mode and thread count.  `ncclimo` in `bck` mode
  runs up to twelve background processes, one per month, so the step requests
  `cpus_per_task = 12` and `ntasks = 1`.  This is the worked example of bounded
  process launching from
  [Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md): the
  step declares what it will start, and `-j` is set from `cpus_per_task` rather
  than from the size of the machine, so a second step running beside it does
  not find the node oversubscribed.
- `ncclimo`'s scratch space is pointed at the step's own work directory rather
  than being left to `TMPDIR`, so that two climatologies running at once ---
  the model one and the mixed-layer depth one --- cannot collide on a temporary
  path.
- `ncclimo` is launched through Polaris's subprocess helper with the step's
  logger, so its output is captured into the step's log rather than
  interleaving on shared streams with whatever else is running.

The output file names produced by `ncclimo` follow the pattern
`<caseid>_<season>_<YYYYMM>_<YYYYMM>_climo.nc`.  Rather than reconstructing
that pattern, downstream steps locate climatology files by globbing on the
season, which is robust to `ncclimo` naming changes.

### Implementation: climatology-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Two new shared modules carry the reusable logic.

`polaris/ocean/vertical/elevation.py`, a dependency-light leaf module beside
the existing vertical-coordinate helpers, unit tested directly:

```python
def get_z_mid_and_interface(ds):
    """Return zMid and zInterface, raising a clear error if absent."""


def parse_vertical_reduction(spec):
    """Parse 'top', 'bottom', 'k<n>', an elevation in m, or a '<top>:<bottom>'
    elevation range, into a vertical reduction."""


def apply_vertical_reduction(da, reduction, z_mid, z_interface,
                             min_level_cell, max_level_cell):
    """Slice a field with a vertical dimension into a horizontal map.

    Slicing at an elevation, a layer index, the surface or the seafloor are
    the cases of one operation: every one of them picks one layer of each
    column, whatever the field means.
    """


def elevation_range_weights(z_interface, layer_mass, min_level_cell,
                            max_level_cell, z_top, z_bot):
    """Return the per-layer mass per unit area within an elevation range.

    An elevation range also turns ``nVertLevels`` into nothing, but it is a
    weighted integral rather than a slice, and what the weighted sum of a
    field *means* is a property of the diagnostic rather than of the vertical
    coordinate.  So this module supplies the weights and the diagnostic
    supplies the sum, which is what lets one heat content kernel serve both
    the maps and the time series.

    The geometric overlap thickness w_k is computed from ``z_interface`` and
    used only as a fraction of the layer, which is then applied to
    ``layer_mass``.  Passing a layer mass of ``z_interface`` differences
    recovers the purely geometric weights, which is what the elevation-slice
    utilities want.
    """
```

`polaris/ocean/heat_content.py`:

```python
def heat_content(temperature, weights, specific_heat):
    """Vertically integrated heat content per unit area [J m-2]."""
```

`elevation_range_weights` lives with the other elevation utilities rather than
with heat content because it is a property of the vertical coordinate, and it
will be reused by any future vertically integrated diagnostic.  It takes the
layer mass rather than computing it, so that the one place that knows how each
model spells its mass-like thickness stays
`polaris.ocean.model.get_layer_mass`.

#### Chunking: one step per field group

There is one `ClimatologyMaps` step per **field group**, not per field and not
one for all of them.  Per principle 4 in {ref}`design-ocean-analysis`, the
field list is an axis a user edits between runs --- adding a field should cost
that field and not the others --- while seasons and elevations are bounded and
rarely change, so they are loops inside the step.

The unit is a group rather than a variable because things computed together
belong together: zonal and meridional velocity share one vector reconstruction,
and heat content over several elevation ranges shares one set of layer weights.
Splitting those would repeat the expensive part.  The Phase 1 groups are
`temperature`, `salinity`, `velocity`, `ssh`, `mixed_layer_depth`, and
`heat_content`.

Each step loops over seasons, the fields in its group, and the vertical
reductions requested for them:

```python
for season in plot_seasons:
    ds = self.open_model_dataset(self.work_path(climo_filename(season)),
                                 self.config)
    z_mid, z_interface = get_z_mid_and_interface(ds)
    layer_mass = get_layer_mass(ds, self.config)
    for field in self.field_group.fields:
        if field == 'heat_content':
            self._plot_heat_content(ds, season, layer_mass, k_min, k_max)
            continue
        da = ds[field]
        for reduction in self._reductions(da):
            da_map = apply_vertical_reduction(
                da, reduction, z_mid, z_interface, k_min, k_max)
            basename = f'{field}_{season}_{reduction.label}'
            write_netcdf(da_map, self.work_path(f'{basename}.nc'))
            self.manifest.add(da_map, field=field, season=season,
                              reduction=reduction, filename=f'{basename}.nc')
            plot_global_mpas_field(
                da=da_map, out_filename=self.work_path(f'{basename}.png'),
                config=self.config,
                colormap_section=map_section(field),
                mesh_filename=self.work_path('mesh.nc'), ...)
```

Heat content is the one branch in this loop.  Its field is derived rather
than read, and its reduction is an elevation range rather than an elevation,
and a range is weighted rather than sliced, so it takes the weights from
`elevation_range_weights` and the sum from the heat content kernel instead of
going through `apply_vertical_reduction`.  Everything around it --- the
season loop, the netCDF beside each plot, the shared `mosaic` descriptor,
the naming --- is the same.

Output names are `<field>_<season>_<reduction_label>.png` with reduction labels
`top`, `bottom`, `-100m`, `k10`, and `top_to_-700m`, so that the set of files
in the step directory is self-describing.  Range labels use `_to_` rather than
a hyphen because the elevations are themselves negative.

The plots are independent, so a step with many of them spreads them over a
process pool rather than over steps, but Phase 1 does not take it: plots are
drawn one after another.  Building the `mosaic` descriptor is the expensive
part of plotting a global mesh, so it is constructed once per step and shared,
which is where most of the available saving is anyway.

Both framework dependencies this used to have are now met.  `polaris.viz` no
longer assigns `plt.rcParams` from inside a step: `mplstyle_context()` scopes
the style and DPI to a `with` block, and the spherical and planar plotting
functions use matplotlib's object-oriented `Figure` API rather than the
`pyplot` current-figure state.  Both landed with the task-parallel groundrules.
These steps therefore need no workaround and no special pleading --- they call
`polaris.viz` as it now is.

Step authors should follow
[the task parallelism page](../developers_guide/framework/task_parallelism.md)
in the Developer's Guide, which is the practical form of the rules; the design
behind them is
[Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md).

Maps are plotted on the native mesh with the existing
`polaris.viz.plot_global_mpas_field`, which is `mosaic`-based and needs no
remapping.  Native-mesh plotting is not a temporary expedient: it is where
observational comparison is headed too, with observations remapped onto the
MPAS mesh rather than the model remapped onto a comparison grid.

A field the simulation did not write --- zonal velocity from a run configured
without it, for instance --- is reported clearly and its maps are skipped,
rather than failing the whole step.

If `compute_mixed_layer_depth` is set, the task adds an accumulator structured
exactly like the heat content one: its kernel computes a month of
mixed-layer depth with `gsw` as described in the algorithm design.  Its cache
is one gridded file per month, so inherited months are symlinked forward rather
than copied or rewritten --- and, per principle 8 in
{ref}`design-ocean-analysis`, because that is the form its consumer reads.

#### A second climatology

That consumer is `ncclimo`, run a second time over the accumulator's monthly
files.  It is a second instance of the same `Climatology` step class, at
`mixed_layer_depth/<range>/climatology`, taking the accumulator's monthly files
as inputs and a variable list of one.

Doing the seasonal averaging with `ncclimo` rather than ourselves keeps a
single implementation of what a season is.  The seasonally discontinuous
December convention, the length-of-month weighting, and the set of seasons are
then the same for a derived field as for a model field by construction rather
than by test, and there is no second averaging path to keep in step.

The cost is that the usual pattern --- one `ncclimo` call per component, once
and for all, plus perhaps a reference climatology --- does not hold here.  A
derived field arrives in its own files, written by a different step, with a
different variable list, and not until an expensive pass over the record has
finished, so it cannot join the call that covers model output.  This is a
deliberate departure and the only one in the design: a second call, for the one
product Polaris computes rather than reads.

The scheduling consequence is worth being explicit about, since a serial chain
behind an expensive step is what principle 3 warns against.  It is confined to
this product: the main climatology reads model output only and does not wait on
the accumulator, so nothing else is held up by it.  Only the mixed-layer depth
maps sit behind the chain of accumulator, second climatology, and maps --- and
only in the fallback case, which exists precisely because we would rather Omega
computed this diagnostic in situ.

Its outputs carry an attribute recording that they were computed offline from
monthly means, and the step adds a note to the plot titles, so that a reader
cannot mistake them for an in-situ diagnostic.

### Implementation: ocean-heat-content-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Heat content maps are the `heat_content` field group of `ClimatologyMaps`, not
a step of their own.  The group differs from the others in two small ways, both
of which the loop above already accommodates:

- its field is derived rather than read, by
  `heat_content(ds.temperature, weights, cp0)` where `weights` comes from
  `elevation_range_weights`, so the derivation happens inside the reduction
  loop rather than before it, since the weights depend on the range;
- its vertical reductions are the configured elevation ranges rather than the
  configured elevations, and they are read from `[ocean_analysis_ohc]` rather
  than from `[ocean_analysis_climatology]`.

The layer weights $\tilde{w}_k$ do depend on the range, so they are not shared
between ranges --- but everything expensive is.  The climatology of $\Theta$,
of `PseudoThickness` and of `zInterface` is read once per season, and each
range is then a masked weighted sum over levels, which is negligible beside the
read.  Adding an elevation range therefore costs almost nothing, which is why
the ranges are a loop inside this step rather than an axis of decomposition.

This is also why the heat content maps have no dependency on the heat content
accumulator: they are computed from the climatology, like every other map,
while the accumulator exists only for the time series, where the per-month
values *are* the product.  The asymmetry is not an inconsistency --- it is the
difference between wanting a seasonal mean, which the climatology already is,
and wanting a time axis, which only a pass over every month can give.

The result is written to netCDF in J m⁻² and plotted in GJ m⁻² --- a range of
$0$ to $-700$ m at a typical 10 °C is about 29 GJ m⁻², which is a readable
number.  Output names follow the same convention as the rest of the maps,
`heat_content_<season>_<range_label>.png`, for example
`heat_content_ANN_top_to_-700m.png` and
`heat_content_ANN_-2000m_to_bottom.png`.  Plot
titles state the elevation range and the season explicitly, and the netCDF
carries the range as attributes, so that a plot cannot be mistaken for a
different range.

### Implementation: global-stats-time-series

Date last modified: 2026/08/27

Contributors: Xylar Asay-Davis, Claude

Omega's `GlobalStats` group writes variables named
`<Field>_<SpatialStat>_TimeMean<Period>` --- for example
`Temperature_SpatialMean_TimeMean1Month` --- to streams named
`GlobalStats_<Freq>TimeStats`.  The step builds the variable names from the
configured fields and statistics, opens the files for the requested years with
`xr.open_mfdataset`, and concatenates along time.  The existing entries in
`mpaso_to_omega.yaml` already map several of these to Polaris-standard names
(`normalVelocityAvg`, and so on) and are extended as more fields are analyzed.

Before plotting, the step intersects the configured `(field, statistic)` pairs
with what the dataset actually contains, logs one line per missing pair, and
plots the rest.  A field with no surviving statistics is skipped entirely.  The
step fails only if *nothing* it was asked for is present, which is the case
worth interrupting the user for, since it usually means the file-name template
or the year range is wrong rather than that a variable is missing.

The existing `StatsAnalysis` step in
`polaris/tasks/ocean/realistic_global/analysis_members/` already produces
exactly the plot we want, but takes its input from a `forward` step in the same
task.  Rather than duplicating it, the plotting is factored into a function in
`polaris/ocean/analysis_plots.py`:

```python
def plot_global_stats(ds, time, fields, stats, out_dir, title_prefix):
    """Plot absolute and relative-to-start time series with a std envelope."""
```

used by both the existing `StatsAnalysis` step and the new one.  This keeps the
`realistic_global` task's behavior unchanged while avoiding a second copy of
the plotting logic.

The time axis is the simulation year, derived from the decoded CF time
coordinate as the calendar year plus the fraction of the year elapsed, using
the calendar the file declares.

It is worth being explicit about why this is not
`polaris.ocean.model.time.get_days_since_start` divided by the length of a
year, which an earlier draft of this design proposed.  That helper returns
days since the *file's reference date*, which is whatever `units` happens to
say --- `seconds since 0000-12-01` in the QU240 mock-up.  Dividing that by a
year length gives a number that coincides with the simulation year only when
the reference date happens to sit at the start of year zero, so a series over
years 21--40 would be labelled correctly by luck rather than by construction.

Taking the year from the decoded date instead has no such dependence, and it
makes the axis agree with the two other places the same year appears: the `$Y`
in the file names the analysis expanded to find these files, and the range key
in the step's own directory.  Those three have to mean the same year, and this
is what makes them.

### Implementation: ocean-heat-content-time-series

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

This product is one accumulator step, `HeatContentSeries`, keyed by the
requested range.  Its kernel reduces one month to a handful of numbers:

```python
class HeatContentSeries(Accumulator):
    def compute_month(self, filename):
        ds = self.open_model_dataset(self.work_path(filename), self.config)
        _, z_interface = get_z_mid_and_interface(ds)
        layer_mass = get_layer_mass(ds, self.config)
        ohc = []
        for z_top, z_bot in elevation_ranges:
            weights = elevation_range_weights(z_interface, layer_mass,
                                              k_min, k_max, z_top, z_bot)
            column = heat_content(ds.temperature, weights, cp0)
            ohc.append((area_cell * column).sum('nCells'))
        return xr.merge(ohc)
```

The accumulator machinery described under `repeated-analysis` handles the rest:
inheriting the months an earlier range already reduced, reducing the remaining
months one at a time, and writing the cache.

The cache is a single netCDF with an unlimited `Time` dimension, appended to as
months are added, because its consumer is the plotting in this same step, which
reads the whole series.  This is principle 8 in {ref}`design-ocean-analysis`:
the form follows the consumer.  Forty years of four elevation ranges is a few
tens of kilobytes, so there is nothing here worth chunking.

Reading a month at a time is deliberate.  A global three-dimensional
temperature field at 30 km resolution and 80 levels is roughly 150 MB per
month, so a forty-year record is several tens of gigabytes; a month at a time
bounds memory regardless of how long the record is, and it is also what makes
the unit of caching a month.  Only `temperature`, the model's mass-like
thickness variable, `zInterface`, and the vertical-index fields are read.

The plot has two panels: absolute heat content in units of 10²² J, and the
anomaly relative to the first month, with one line per elevation range.  The
concatenated time series is written to `ocean_heat_content_time_series.nc`.

This accumulator is the most expensive part of the suite on a first run, and
nearly free on every run after it.  At 6to18 km over several decades a first run
is hours, which is acceptable for a product that is then incremental forever
after, and it is bounded rather than unbounded because only one month is held
at a time.

Two moves are available if that proves intolerable, in the order we would reach
for them: reduce the months concurrently, either across steps or within one,
which is what principle 3 describes and Phase 1 deliberately leaves out; or
compute the vertical integrals in Omega in situ, which reduces the whole
product to a concatenation.  If mixed-layer depth is also computed offline, its
accumulator makes the same pass over the same monthly files and the two could
share one pass; they are kept separate because merging them would couple two
products for a saving that only matters on a first run.

### Implementation: moc-plot

Date last modified: 2026/08/27

Contributors: Xylar Asay-Davis, Claude

The `moc` step reads Omega's global MOC output over the climatology years,
averages over time weighted by the length of each reduction period, and plots
the result as filled contours with overlaid contour lines against the interface
elevations Omega provides.

The plotting primitive is added to `polaris/viz/` as a general
latitude-elevation contour plot, rather than being written inline in the step,
since regional overturning, zonal means, and meridional heat transport plots
will all want it in a later phase:

```python
def plot_lat_elevation_field(da, lat, z, out_filename, config,
                             colormap_section, contour_interval=None, ...):
```

Elevation on the vertical axis puts the sea surface at the top without
inverting the axis, consistent with the sign convention used everywhere else in
this design.

The step is guarded so that a missing MOC file, or MOC output without interface
elevations, produces a clear message naming the expected file and the Omega
config option that produces it, rather than a traceback --- the MOC capability
is new in Omega and users will encounter simulations that predate it.

### Implementation: regression-test

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

The task is `ocean/analysis_test/QU240`, in
`polaris/tasks/ocean/analysis_test/`, and the suite is
`polaris/suites/ocean/omega_analysis_test.txt` containing only it.

#### What it runs

An init chain and a forward run at QU240, reusing the existing
`realistic_global` QU240 machinery rather than adding another mesh, with an
Omega YAML fragment that turns on monthly-mean output of the fields this
analysis reads.  That fragment is the same one described under
`omega-monthly-means`, which is what makes this test worth having: it exercises
the Omega-side configuration, not just the Polaris-side code.

**One simulated year**, which is the shortest run that exercises the whole
chain.  `ncclimo` needs whole years to form seasonal and annual climatologies,
so a one- or two-month run would cover the accumulator and the maps but would
skip the climatology entirely --- and the climatology is the step with the
most external surface area, since it shells out to NCO and depends on Omega's
time metadata being read correctly by a tool we do not control.  A year at
QU240 is a small forward run, and the analysis over it is seconds.

The analysis products then run over years 1 to 1: the climatology, the
climatology maps for each field group, the heat content series, the global
stats time series, and the MOC plot if the simulation wrote MOC output.

#### How the analysis steps are pointed at it

The analysis steps read a simulation through the file-name templates in
`[ocean_analysis]`, so the task sets those templates to the forward step's
output and creates its own instances of the same step classes at
`ocean/analysis_test/QU240/`.  No step class learns anything about being under
test.

The one addition is ordering: the forward step's monthly-mean outputs are
declared as inputs of the analysis steps, so Polaris runs them in the right
order and reports a missing file as a missing dependency rather than as a
mystery.

#### What it checks

Beyond running without error, the step that closes the task checks the
properties that do not depend on the simulation being long enough to be
meaningful:

- every product named in the merged manifest exists, and every published
  symlink resolves;
- each plot has its netCDF companion, and the netCDF carries the date range
  the plot is labeled with;
- the global heat content time series has twelve months, is finite, and is
  positive for every elevation range;
- the annual-mean climatology of a field equals the mean of its twelve monthly
  climatologies to round-off, which exercises `ncclimo`'s weighting and our
  reading of it;
- a map at the sea surface equals the top valid layer of the same field, which
  exercises the vertical reduction against the climatology rather than against
  synthetic data.

Baseline comparison against a previous run of the same suite is available as it
is for any Polaris task, and is the natural way to catch an unintended change
in a diagnostic's values.

This task is also where the task-parallel conformance checks described under
`analysis-suite` should run when they are built, since it is the only place a
whole analysis suite exists cheaply enough to exercise every step.

#### Dependency on Omega, and when this lands

This task cannot run until Omega can write monthly means of full model fields.
Until then it is set up but its forward step is expected to produce nothing the
analysis can read, which the analysis steps report as missing fields rather
than as failures --- the same degradation described under
`omega-monthly-means`.  It should not go into any shared suite until it passes.

That dependency also places it **after the September 15 deliverable** rather
than within it.  By the time Omega can write what this task needs, the
deliverable itself is due, and the products a scientist is waiting on come
first.  This is a schedule judgment rather than a statement about its value: a
capability that nothing we run exercises is a capability that regresses
quietly, so this is the first thing to build once the products are out.

### Implementation: order of work

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Each entry below is a branch, following the branch rules in
{ref}`design-ocean-analysis`: a coherent, independently reviewable piece of
work carrying its code, its unit tests, and its User's Guide documentation,
leaving the suite working for the products delivered so far.  Design changes
are not among them, since those land on the design branch.

The order is by deliverable priority rather than by dependency depth, which is
why the vertical machinery comes late.  Slicing by layer index needs no
vertical geometry at all, and heat content over the whole column needs only
`minLevelCell` and `maxLevelCell`, so both a map and a heat content drift curve
can be on screen well before elevation interpolation exists.  The standard
$0$--$700$ m, $700$--$2000$ m and $2000$ m--seafloor ranges then enrich a
product that already works rather than gating it.

1. This design document and the umbrella document
   {ref}`design-ocean-analysis`.
2. The `omega_analysis` scaffolding: the `polaris/tasks/ocean/analysis/`
   package, `analysis.cfg`, `sim_files.py` including the reader for the
   simulation's Omega configuration, the range-keyed step subdirectories, the
   tasks with their `configure()` methods, and the `omega_analysis` suite, with
   steps that do nothing yet.  This is where the repeated-analysis structure is
   established, so it lands before anything that depends on it.
3. The `global_stats` time series step, including factoring the shared plotting
   function out of `StatsAnalysis`.  It depends on nothing above it, reads
   Omega's `GlobalStats` output directly, and needs no vertical geometry, so it
   is the earliest point at which the suite produces a plot a scientist wants.
4. The `Climatology` step (`ncclimo`).  Early because it carries the most
   external risk in the design: it shells out to NCO and depends on Omega's
   time metadata being read correctly by a tool we do not control.  Everything
   map-shaped is blocked on it, so we want to find out.
5. The `ClimatologyMaps` step, restricted to fields with no vertical dimension
   and to slicing by layer index.  The first maps on disk, and no vertical
   geometry needed.
6. Publication: the manifest writer, the `publish` step that collects and
   renders thumbnails, and the generated gallery over the staging tree, as
   designed under `publication`.  Its position in this list is a priority
   rather than a dependency: it is cut from item 2 and not from the products,
   because the manifest writer is a dependency of every plotting step.  The
   product branches above it therefore rebase onto it, each gaining one commit
   that emits its own fragments.
7. `polaris/ocean/heat_content.py` and whole-column mass weights, with unit
   tests.
8. The `heat_content` field group of `ClimatologyMaps`, whole column only.
9. The `Accumulator` base class --- seed discovery and provenance stamping ---
   with unit tests, since this is the piece whose failure modes are silent.
10. The `heat_content_series` step built on it, whole column only.  Heat content
    drift is what a coupled run is judged on, which is why it precedes the
    vertical machinery rather than following it.
11. `polaris/ocean/vertical/elevation.py` --- the full vertical reduction:
    interpolation to an elevation, the sea surface, the seafloor, and elevation
    ranges --- with unit tests.  This enriches items 5, 8 and 10, each of which
    already works without it.
12. The `moc` step and the `plot_lat_elevation_field` primitive.
13. The `replot` option.
14. The offline `mixed_layer_depth` accumulator and its climatology, only if
    Omega's in-situ diagnostic will not be ready in time.

User's Guide documentation is not a work item of its own.  Each branch above
brings the page or the section that documents what it added --- a page under
`docs/users_guide/ocean/tasks/` for the suite and its config options, and an
entry in `docs/users_guide/ocean/suites.md` --- because a capability that ships
undocumented is not finished, and the moment its behavior is fresh is the
moment to write it down.

Deferred past this deliverable, and designed in
{ref}`design-ocean-analysis` rather than here: splitting accumulators into
several steps, process pools inside steps, a considered visual design for the
gallery and the per-product pages that would carry a figure's provenance and
recipe, the mechanical conformance checks, and the `analysis_test` task and its
suite.

## Testing

### Testing and Validation: analysis-suite and data-products

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Unit tests under `tests/ocean/` cover the parts that do not need a simulation:

- expansion of file-name templates over a year range, including the error
  message when years are missing;
- parsing of the elevation and elevation-range config syntax, including invalid
  input and the `top`, `bottom`, and `k<n>` keywords;
- that every plotting step registers a netCDF output for each PNG output, which
  keeps the data-products requirement from quietly regressing.

#### Conformance with the task-parallel groundrules

[Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md) observes
that rules which are only written down are not adopted, and that most of these
can be checked mechanically.  The analysis steps are the first body of code
written to them, so they should be the first to run the checks.

**The checks themselves are not in Phase 1.**  They need harness support that
does not exist, and nothing they protect can go wrong until steps actually run
concurrently, which is Phase 2.  What Phase 1 does is *follow* the rules ---
explicit paths, declared resources, temporary files in the work directory,
logging through the step's logger, and no mutation of process globals --- since
that costs nothing while the code is being written and is what would be
expensive to retrofit.  The checks are listed here so that the first phase that
needs them knows what to build:

- **Working-directory independence.**  Run the step with the process working
  directory set somewhere unrelated and confirm the results are identical.
  This is the check that would have caught the bare relative filenames this
  design carried until recently, which is a fair indication of how easily the
  rule is broken by writing ordinary-looking code.
- **No process-global state mutation.**  Snapshot the globals a step is
  forbidden to touch --- the working directory, `mpas_tools.io.default_format`
  and `default_engine`, `plt.rcParams` --- before and after `run()`, and
  compare.
- **Isolation.**  Compare the set of files the step wrote against its declared
  outputs and its own work directory, which catches both undeclared outputs and
  writes into a shared location.
- **Bounded launching.**  Confirm the step starts no more processes than
  `cpus_per_task`.

They should run against the coarse-resolution regression test, where a whole
suite is cheap enough to exercise, rather than against synthetic steps --- the
point is to check the steps we ship, not a model of them.

### Testing and Validation: repeated-analysis

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The step tree each task builds is a pure function of its config options, so
most of this can be tested without running anything.  Unit tests construct a
task, set config options, call `configure()`, and inspect the resulting steps:

- the range-keyed steps land at subdirectories named for the configured range,
  and changing the range changes those subdirectories;
- an accumulator set up over a range that overlaps an earlier one discovers
  that earlier cache, declares it as an input, and reports the months it
  inherited;
- an accumulator whose provenance stamp does not match a candidate cache ---
  a different simulation, a changed elevation range, a bumped kernel version
  --- ignores it and recomputes;
- a candidate directory without a completion marker is never inherited from;
- the climatology and time series ranges are independent, so changing one does
  not disturb the other's steps.

Two behaviors need an actual run, tested with a stubbed step that records that
it ran:

- re-running with an unchanged range does no work;
- after analyzing a second range, the first range's staged results are still
  present, which is the requirement that a new range must not clobber an old
  one.

Finally, a check that the range recorded in a netCDF file's attributes matches
the range in its path, which is what would catch a plot labeled with the wrong
range if the step tree and the metadata ever drifted apart.

### Testing and Validation: publication

Date last modified: 2026/08/29

Contributors: Xylar Asay-Davis, Claude

Publication is cheap to test properly because none of it needs a simulation: a
few hand-written manifest fragments and a handful of small PNGs exercise every
path.  The unit tests live with the branch that adds them.

On the manifest and the collector:

- fragments written by the writer round-trip through the collector, and the
  merged manifest names every product the fragments did;
- a fragment naming a file that is not on disk is reported rather than
  silently omitted, which is the failure this design promises to catch;
- order is preserved --- products keep their within-fragment order and
  fragments are ordered by group and gallery --- since a gallery reading ANN,
  DJF, MAM, JJA, SON rests on nothing else;
- two ranges of the same product publish to distinct names and both survive,
  which is the same guarantee `repeated-analysis` makes, checked here on the
  staging tree rather than the work tree.

On thumbnails:

- one is generated for every plot, at the configured width, in the configured
  format, and is smaller than its PNG by the order of magnitude the design
  claims --- a bound rather than an exact size, since encoders differ;
- a thumbnail already newer than its plot is not regenerated, which is what
  keeps adding one product from costing three hundred;
- a PNG with an alpha channel produces a thumbnail with no transparency,
  since that is what silently produces black backgrounds otherwise.

On the generated site:

- every link and every `src` in the generated HTML resolves to a file that
  exists, which is the check that a broken gallery fails on;
- every product in the merged manifest appears on exactly one gallery page,
  and every gallery is reachable from the landing page;
- every `<img>` carries `loading="lazy"` and explicit dimensions.  This is a
  test of the thing that is easiest to lose in a template edit and whose loss
  is invisible until a page is served over a throttled link.

One thing here cannot be a unit test and should not be pretended into one.
**Whether the LCRC portal throttles bytes or requests is unknown**, and it
decides which further measures are worth taking.  The measurement is to publish
a realistic result set to the portal and time a cold load of the largest
gallery page, with the browser's network panel showing whether the limit is
reached in bytes or in concurrent requests.  This should be done once the first
real analysis is published, and the answer recorded here.

### Testing and Validation: climatology

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A small synthetic monthly-mean data set --- a handful of cells, a few levels,
three years of months with known values, written with Omega names and CF time
metadata --- is written to a temporary directory, `ncclimo` is run on it, and
the resulting `ANN`, `DJF`, and monthly climatologies are compared against
day-weighted means computed directly in the test.  This validates our `ncclimo`
invocation, including the `-a sdd` convention and the claim that `ncclimo` can
read Omega-style files without `-P mpaso`, rather than validating `ncclimo`
itself.

The test is skipped if `ncclimo` is not on the path.

### Testing and Validation: climatology-maps

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Unit tests on `apply_vertical_reduction`, in its slicing cases, with synthetic
columns having known layer geometry, `minLevelCell`, and `maxLevelCell`:

- `top` and `bottom` return the values at `minLevelCell` and `maxLevelCell`,
  including for a column with `minLevelCell > 0` (an ice-shelf cavity) and a
  column with `maxLevelCell` less than the number of levels;
- a fixed index returns that index and is masked where the index is outside the
  valid range;
- interpolation to an elevation exactly at a layer midpoint returns that
  layer's value exactly;
- interpolation to an elevation midway between two midpoints returns the
  average of the two values;
- an elevation above the topmost midpoint returns the topmost value, and an
  elevation below the seafloor is masked;
- a linear-in-$z$ field is recovered exactly at arbitrary elevations.

The last of these is the strongest test: it catches index-off-by-one and
weight-inversion errors that the others can miss.

### Testing and Validation: mixed-layer depth

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

If the offline fallback is implemented, unit tests on synthetic profiles:

- a two-layer profile with a density jump exactly at an interface returns that
  interface elevation;
- a linearly stratified profile returns the elevation at which the density
  threshold is crossed, matching an analytic answer, which exercises the
  interpolation between bounding layers;
- a fully mixed column returns the seafloor elevation rather than an
  extrapolated value or `NaN`;
- the computation agrees with a direct `gsw` evaluation at the reference
  elevation, so that a mistake in the reference pressure is caught.

### Testing and Validation: ocean-heat-content

Date last modified: 2026/08/25

Contributors: Xylar Asay-Davis, Claude

Unit tests on `elevation_range_weights` and `heat_content` are written in
pseudo-height, since that is the coordinate the
integral is actually taken in, and every synthetic column is built with
$\tilde{h} \ne h$ so that a formulation that confused the two would fail rather
than coincidentally pass:

- for a range aligned with layer interfaces, the weights are exactly the layer
  masses $\rho_0 \tilde{h}_k$ in the range and zero outside;
- for such a range, a constant temperature $\Theta_0$ gives heat content
  exactly $\rho_0 c_p^0 \Theta_0 \Delta\tilde{z}$, where $\Delta\tilde{z}$ is
  the pseudo-thickness of the range --- *not* its geometric thickness;
- the whole-column result equals $c_p^0 \sum_k \Theta_k \rho_0 \tilde{h}_k$ and
  is unchanged if the geometric interfaces are perturbed while pseudo-thickness
  is held fixed, which is the property that distinguishes the mass-weighted
  form from the geometric one;
- for a range boundary in the interior of a layer --- the one place geometry
  legitimately enters --- the weight of that layer is its mass scaled by the
  exact geometric fraction $w_k/h_k$, and a range boundary swept across a layer
  gives a result that varies linearly between the two whole-layer answers;
- for a range extending below the seafloor, the result is truncated at the
  seafloor;
- the whole-ocean range equals the sum of a set of ranges that partition it,
  which is a useful invariant that also exercises the `bottom` keyword;
- for a column entirely above $z_{top}$, the result is zero rather than `NaN`,
  since a `NaN` here would poison the global sum.

### Testing and Validation: time series and MOC

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The time series and MOC steps are mostly file handling and plotting, and are
covered by:

- a unit test that months already present in an inherited cache are reused
  rather than recomputed, and that adding a year extends the series correctly;
- a unit test that a cache written with one provenance stamp is not inherited
  by a step asking under another;
- a unit test on the construction of `GlobalStats` variable names from
  Polaris-standard field names and the configured statistics;
- a unit test that a configured field or statistic missing from the dataset is
  skipped rather than raising, that a field with no surviving statistics is
  dropped, and that a dataset with none of the configured variables does
  raise --- this is the behavior most likely to regress into an exception the
  first time a simulation writes an unexpected subset;
- a unit test that the MOC time average weights reduction periods correctly on
  a synthetic data set with unequal period lengths.

### Testing and Validation: end-to-end

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

End-to-end validation is against Omega, staged as Omega capabilities land.
None of it belongs in the `pr` or `nightly` suites, since it requires a
completed simulation as input and its cost is dominated by that simulation.

1. **As each Omega capability lands**, the corresponding product is run against
   real Omega output at low resolution and inspected.  `GlobalStats` output
   exists today, so the global-stats time series can be validated first; the
   MOC plot follows when the MOC analysis group is available; the climatology,
   map, and heat content products follow when monthly means are available.
   Staging the validation this way is what keeps the September 15 date
   credible, since it front-loads discovery of mismatches between what the
   design assumes and what Omega actually writes.
2. **A short Omega run as a smoke test.**  Once Omega can write monthly means,
   the QU240 `realistic_global` task is configured to write two years of
   monthly means, `GlobalStats`, and MOC output, and the whole suite is run on
   it.  This confirms that the suite runs end to end and produces every
   expected file.  It is fast enough that it could later be added to a suite if
   we decide the coverage is worth the cost, but that is a separate decision.

We do not validate by running this analysis on MPAS-Ocean output.  MPAS-Ocean
differs from Omega in variable and dimension names, in time metadata, and in
which analysis member produces its monthly means, so an MPAS-Ocean test would
exercise code paths we do not ship and would give false confidence about the
paths we do.  Confidence in the numerics comes instead from the unit tests
above, which check the kernels against analytic answers rather than against
another model's output.

Where a diagnostic's *magnitude* needs a sanity check --- is the heat content
in the right ballpark, is the MOC of a plausible strength --- published
MPAS-Analysis results for E3SM simulations are a reasonable reference to
eyeball against.  That is a science judgment made by the person reviewing the
plots, not an automated test.

## Open questions

*These are the decisions that should be settled before implementation starts.
They are collected here rather than buried in the sections above.*

1. **Mixed-layer depth.**  Can Omega deliver an in-situ, density-threshold
   mixed-layer depth diagnostic, averaged monthly, by September 15?  If not, we
   ship the offline fallback with its caveats.  This needs a team discussion
   rather than a decision in this document, and it affects both the Omega
   schedule and work item 14 above.
2. *(Settled.)*  **`ncclimo` and Omega output.**  `ncclimo` reads Omega
   monthly-mean files without the MPAS-specific `-P mpaso` processing type,
   provided `time_bnds` is present with the expected values.  Confirmed against
   the QU240 mock-up described under `omega-monthly-means`.  Recorded here
   because it was the item on the critical path; what remains is to repeat it
   at high resolution and against Omega's own monthly reduction rather than a
   mock-up of it.
3. **Omega MOC output conventions.**  The variable, dimension, and coordinate
   names, and whether the mean interface elevations are written alongside the
   streamfunction, need to be confirmed against the MOC implementation.  This
   should be straightforward to settle once the vertical-coordinate question
   above is resolved and the Omega MOC analysis is rerun.
4. **The default `GlobalStats` field and statistic list.**  Which quantities a
   reader most wants to see drift in is a judgment call and is still open.  How
   the list behaves is settled: it lives in Polaris's config file, and entries
   the simulation did not write are skipped rather than raising.

Two questions from earlier drafts are now settled and are recorded here so that
they are not reopened by accident:

- **Constants for heat content:** Phase 1 uses the PCD values, since adding
  $c_p^0$ to the PCD cannot be completed by September 15.  Switching to the
  TEOS-10 constant is a deferred item in {ref}`design-ocean-analysis`.
- **Task granularity for ocean heat content:** one task, two steps.
