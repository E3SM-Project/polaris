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
expensive intermediate products (climatologies, per-year heat content) are
written to netCDF as well.

The same simulation can be analyzed repeatedly over different date ranges.
Results accumulate in a range-keyed staging tree that a web interface can serve
later, and re-analyzing a new range reuses the per-year intermediates from
earlier ranges instead of recomputing them.

MPAS-Analysis is the scientific reference for what each of these diagnostics
means, but the implementation is written from scratch with Polaris and Omega in
mind rather than ported.  The reasoning is in {ref}`design-ocean-analysis`.

Three things are deliberately **out of scope** for this deliverable:

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
`salinity`, `layerThickness`, `zMid`, `zInterface`, `minLevelCell`,
`maxLevelCell`, `bottomDepth`, and `areaCell`, and to the dimensions `nCells`,
`nEdges`, `nVertLevels`, `nVertLevelsP1`, and `Time`, regardless of which model
produced the data.  Omega's names --- `Temperature`, `PseudoThickness`,
`GeomZMid`, `GeomZInterface`, `NCells`, `NVertLayers`, and so on --- are
translated to the Polaris standard automatically when a dataset is opened with
`OceanIOStep.open_model_dataset`, using the mapping in
`polaris/ocean/model/mpaso_to_omega.yaml`.  Analysis steps therefore never
branch on the model to get a field name, and config options that name fields
use the MPAS-Ocean names.  Where a field is new to Omega and has no MPAS-Ocean
counterpart, a Polaris-standard name is chosen and added to that mapping.

**The vertical coordinate is elevation, positive up.**  All vertical positions
in config options, algorithms, and output are elevations $z$ in meters with
$z = 0$ at the resting sea surface and $z$ increasing upward, so that positions
within the ocean are negative.  A map "at 100 m below the surface" is requested
as `-100.0`, and the ocean heat content range conventionally called "0 to
700 m" is written `0.0:-700.0`.  This matches `zMid` and `zInterface` as the
models write them and avoids sign flips scattered through the code.  Where the
text uses the word "depth" it is describing a quantity that is positive down,
such as `bottomDepth`, and says so.

## Requirements

### Requirement: analysis-suite

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall provide a suite that computes all of the analysis in this
document for a single simulation.

The user shall supply a config file that provides:

- the path to the E3SM or Omega standalone simulation to be analyzed, together
  with enough information to find its mesh, vertical coordinate, and output
  files;
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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Every plot the suite produces shall be accompanied by a netCDF file containing
exactly the data that were plotted, so that the values can be inspected,
compared against other tools, or re-plotted without recomputation.

Intermediate products that are expensive to compute --- climatologies and
per-year ocean heat content in particular --- shall be written to netCDF, and a
step that finds a complete intermediate product from a previous run shall be
able to reuse it rather than recomputing it.

### Requirement: repeated-analysis

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall support analyzing the same simulation repeatedly with different
climatology and time-series date ranges.

Results shall be staged in a single, range-keyed location that a reader can
navigate without knowing anything about Polaris work directories, and that a
web interface can serve when one is added.  Analyzing a new range shall not
overwrite or remove the results of a range analyzed earlier.

Re-running the analysis with a changed range shall recompute the products that
depend on that range.  It shall not be necessary to delete the work directory
or to pass a flag to force recomputation, and it shall not be possible to
obtain a plot labeled with one range whose contents were computed for another.

Re-running with a changed range shall reuse the intermediate results that do
not depend on the range.  Extending a time series from twenty years to forty
shall cost twenty years of work, not forty.

Re-running with an unchanged range shall recompute nothing.

### Requirement: omega-monthly-means

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

*This requirement describes work in Omega, not in Polaris.  It is stated here
because everything else in this document depends on it.*

Omega shall be able to write monthly means of a configurable list of model
fields.  The monthly-mean output shall:

- cover, at minimum, the fields needed by this analysis: conservative
  temperature, absolute salinity, pseudo-thickness, sea surface height, normal
  velocity (or reconstructed zonal and meridional velocity), and mixed-layer
  depth;
- include the **geometric vertical coordinate**, `GeomZMid` and
  `GeomZInterface`, so that Polaris does not have to reconstruct it (see the
  vertical-geometry algorithm design for why it cannot);
- carry CF-compliant time metadata, with a time coordinate and time bounds that
  identify the averaging period, so that standard tools can identify the month
  each average represents;
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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall produce global maps of climatological fields on the native MPAS
mesh, for each requested field and each requested season.

For fields that have a vertical dimension, the user shall be able to request
maps at any combination of:

- **the sea surface** --- the topmost valid layer of each column;
- **a fixed geometric elevation** --- a given elevation $z$ (positive up, so
  negative within the ocean), obtained by linear interpolation in the vertical;
- **a fixed layer index** --- a given vertical index, common to all columns;
- **the seafloor** --- the bottommost valid layer of each column.

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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Polaris shall compute ocean heat content integrated over elevation ranges from
a climatology of conservative temperature, and shall produce a global map for
each elevation range and each requested season.

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
full record into memory, and shall write per-year intermediate results so that
extending the time series with additional simulation years does not require
recomputing the years already processed.

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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The whole approach rests on separating what depends on the requested range from
what does not:

| Product | Depends on the range? | Cost |
| --- | --- | --- |
| Monthly means (model output) | no | read-only input |
| Per-year ocean heat content integrals | no, keyed by year | expensive |
| Per-year offline mixed-layer depth | no, keyed by year | expensive |
| `ncclimo` climatologies | yes | expensive |
| Climatology and heat content maps | yes | cheap, from the climatology |
| Global stats time series | yes | cheap |
| MOC time average | yes | cheap |

The rule that follows: **every expensive computation is decomposed into a
per-year product keyed by the year, not by the range**, and is given its own
step at a year-keyed subdirectory.  A given year's vertically integrated heat
content is the same quantity no matter which range asked for it, so it is
computed once and reused forever.  Everything that is range-keyed is then
either cheap to redo from those per-year products, or is the climatology
itself.

The climatology is the one expensive computation that genuinely depends on the
range, and it is recomputed for each new range.  In principle a climatology
over a new range could be assembled incrementally from per-year seasonal
partial sums, but `ncclimo` has no such mode, and writing our own incremental
climatology to save a rerun is not a trade we should make for this deliverable.
Two ranges' climatologies coexist without special handling, because `ncclimo`
already encodes the range in its output file names
(`<caseid>_<season>_<YYYYMM>_<YYYYMM>_climo.nc`).

### Algorithm Design: climatology-maps

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

#### Vertical geometry

Everything in this document that involves a vertical position needs the
geometric elevation of layer midpoints, $z^{mid}_{k}$, and of layer interfaces,
$z^{int}_{k}$, for each column.  These are read directly from `zMid` and
`zInterface` --- Omega's `GeomZMid` and `GeomZInterface` --- which is why the
`omega-monthly-means` requirement asks for them as monthly-mean output.

Polaris cannot reconstruct them from the monthly means of the other fields.
Omega builds the geometric coordinate by accumulating upward from
$-\mathrm{BottomGeomDepth}$ using $\mathrm{SpecVol} \times
\mathrm{PseudoThickness}$, and it does so the same way regardless of which
vertical coordinate the simulation uses --- the choice of z-star, p-star, or
sigma determines how `PseudoThickness` is initialized and how it evolves, not
how geometric elevation is computed from it.  Reconstructing $z$ offline
therefore requires specific volume, which means evaluating the TEOS-10 equation
of state on the monthly-mean state.  That is not the monthly mean of
$\mathrm{SpecVol} \times \mathrm{PseudoThickness}$, so the reconstruction would
introduce an error that has nothing to do with the diagnostic being computed.
Having Omega write the geometric coordinate removes the problem entirely, since
the monthly mean of $z$ is exactly the mean layer geometry we want.

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

#### Reconstructed velocities

Omega writes `normalVelocity` on edges.  Zonal and meridional velocity at cell
centers are obtained by the least-squares reconstruction designed in
[Vector Reconstruction](vector_reconstruction.md), whose weights are stored on
the mesh.

Reconstruction is a linear operator on the edge field, so reconstructing from a
climatology of normal velocity gives exactly the climatology of the
reconstructed velocity.  There is therefore no accuracy argument for doing the
reconstruction in the model, and doing it offline avoids adding a dependency on
Omega work.  If Omega later writes reconstructed velocities directly, the step
uses them in preference.

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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

*This algorithm is shared by the heat content maps and the heat content time
series; the two differ in what they integrate over and in what they read, not
in the kernel.*

Ocean heat content per unit area, integrated over an elevation range
$[z_{bot}, z_{top}]$ with $z_{bot} < z_{top} \le 0$, is

$$
Q(z_{bot}, z_{top}) = \rho_0 c_p^0 \int_{z_{bot}}^{z_{top}} \Theta \, dz
            \approx \rho_0 c_p^0 \sum_k \Theta_k \, w_k
$$

where $\Theta$ is conservative temperature and $w_k$ is the thickness of the
overlap between layer $k$ and the requested range:

$$
w_k = \max\left(0, \;
      \min\left(z^{int}_{k}, z_{top}\right) -
      \max\left(z^{int}_{k+1}, z_{bot}\right)\right)
$$

for layers within `[minLevelCell, maxLevelCell]` and $w_k = 0$ elsewhere.  This
expression handles all of the cases the requirement calls for without special
casing: a range boundary in the interior of a layer contributes a partial
thickness; a range extending below the seafloor is truncated because
$z^{int}_{k_{max}+1} = -H$; a `bottom` boundary is expressed as
$z_{bot} = -\infty$; and a column whose seafloor lies above $z_{top}$
contributes zero.

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

**Decision:** Phase 1 uses the PCD values.  $c_p^0$ is not in the PCD today,
and adding a constant to it is not something we can complete by September 15,
so using the PCD is what keeps Polaris consistent with the constants the rest
of E3SM is using in the meantime.  Both constants are exposed as config options
so that a user can experiment with the TEOS-10 value without a code change.

In the long run we do want $c_p^0$: because Omega carries conservative
temperature, $\rho_0 c_p^0 \Theta$ is the definition of heat content rather
than an approximation to it.  Adding $c_p^0$ to the PCD and switching to it is
recorded as a deferred item in {ref}`design-ocean-analysis`.

A constant reference density is used rather than in-situ density.  This is the
MPAS-Analysis convention and keeps the diagnostic comparable; the difference is
a few tenths of a percent and is nearly uniform, so it affects the absolute
heat content much more than the anomaly, which is the quantity of interest.

#### Heat content from a climatology versus from monthly means

The heat content maps are computed from the climatology of $\Theta$ and of the
layer geometry, per the requirement.  Because heat content is a product of
those two, this omits the covariance term:

$$
\overline{\Theta h} = \overline{\Theta}\,\overline{h} +
                      \overline{\Theta' h'}
$$

The neglected term is small for heat content over fixed elevation ranges ---
the range boundaries are fixed in $z$, so the covariance enters only through
the partial layers at the boundaries and through the free surface --- but it is
not identically zero, particularly in regions with a large seasonal cycle in
sea surface height and layer thickness.

The heat content time series does not have this issue, because it integrates
each monthly mean separately and averages afterward.

If the covariance term turns out to matter, the alternative is to compute the
per-month vertically integrated heat content maps first, as the time series
step already does, and then average those maps into a climatology.  That is a
potential follow-up after September 15, not a fallback available before it: it
costs a full pass over the three-dimensional monthly output for every season
plotted, and the requirement asks for heat content from a climatology of
conservative temperature.

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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

#### Tasks, steps, and the suite

New tasks live in `polaris/tasks/ocean/analysis/`, added to the ocean component
by `add_analysis_tasks(component)` in `polaris/tasks/ocean/add_tasks.py`.  The
work-directory layout is:

```none
ocean/analysis/
├── climatology/
│   └── 0021-0040/                (shared step: ncclimo, per range)
├── years/                        (shared per-year steps, range-independent)
│   ├── ocean_heat_content/0021/ … 0060/
│   └── mixed_layer_depth/0021/ … 0060/   (only if computed offline)
├── climatology_maps/             (task)
│   └── maps/0021-0040/           (step, per range)
├── ocean_heat_content/           (task)
│   ├── maps/0021-0040/           (step, from the climatology)
│   └── time_series/0001-0060/    (step, from the per-year steps)
├── global_stats/                 (task)
│   └── time_series/0001-0060/    (step)
└── moc/                          (task)
    └── plot/0021-0040/           (step)
```

Step subdirectories are keyed by the date range they cover, and the expensive
per-year work lives in shared steps keyed by year rather than by range.  The
`repeated-analysis` implementation below explains why, and why this structure
is what makes re-running with a new range work.

The `climatology` and `years` steps are shared steps in the sense of
[Shared steps](shared_steps.md): the climatology for a given range is used by
`climatology_maps/maps` and by `ocean_heat_content/maps`, and both sit at
`ocean/analysis`, the highest level at or below which all of the tasks that use
them live.  Each runs once no matter how many of the tasks are run.

Ocean heat content is one task with two steps rather than two tasks: the maps
and the time series share the elevation ranges and the heat content kernel, and
are one product from the reader's point of view even though they read different
inputs.  Running only one of them is still possible with `polaris serial
--steps`.

The suite is `polaris/suites/ocean/omega_analysis.txt`, named to match the
existing `omega_pr` and `omega_nightly` suites:

```none
ocean/analysis/climatology_maps
ocean/analysis/ocean_heat_content
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

# The absolute path to the directory containing the simulation's output
simulation_path =

# A short name for the simulation, used in plot titles and file names
simulation_name = omega

# Where to stage plots and their netCDF files for browsing, organized by
# product and date range.  Defaults to <work_dir>/analysis_output.
output_path =

# The horizontal mesh file, absolute or relative to simulation_path
mesh_filename =

# The vertical-coordinate file (Omega only), absolute or relative to
# simulation_path
vert_coord_filename =

# File-name templates for the simulation output the analysis reads, relative
# to simulation_path.  $Y and $M are replaced by the four-digit year and
# two-digit month.
monthly_mean_template = ocean.hist.MonthlyMean.$Y-$M.nc
global_stats_template = ocean.hist.GlobalStats_1MonthTimeStats.$Y.nc
moc_template = ocean.hist.Moc_1MonthTimeStats.$Y.nc


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
fields = temperature, salinity, velocityZonal, velocityMeridional,
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
# <top>:<bottom> in m, positive up.  "bottom" means the seafloor.
elevation_ranges = 0.0:-700.0, -700.0:-2000.0, -2000.0:bottom, 0.0:bottom

# The reference density and specific heat capacity used to convert
# conservative temperature to heat content.  By default, these come from the
# Physical Constants Dictionary.
#seawater_density = 1026.0
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

Fields that are new to Omega and have no MPAS-Ocean counterpart --- a
mixed-layer depth diagnostic, for instance --- get a Polaris-standard name and
an entry in that mapping as they become available.  No analysis step branches
on `config.get('ocean', 'model')` to choose a field or dimension name; if a
step needs to do so, that is a signal the mapping file is missing an entry.

#### Locating input files

A small helper module, `polaris/tasks/ocean/analysis/sim_files.py`, expands the
file-name templates over a year range into lists of files and checks that they
exist, reporting the missing years clearly.  It is shared by every step that
reads simulation output.  This is deliberately a separate module rather than a
method on a step, so that it can be unit tested and reused.

Input files are symlinked into each step's work directory in `setup()` using
`Step.add_input_file`, which gives the usual Polaris provenance and dependency
checking without copying data.

### Implementation: data-products

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Each plotting step writes, alongside each PNG, a netCDF file with the same base
name containing the plotted field, its coordinates, units, and the config
options --- including the date range --- that produced it as global attributes.
Both go in the step's range-keyed subdirectory and are symlinked into the
staging tree, as described under `repeated-analysis`.

The expensive intermediates are:

- the `ncclimo` output in `ocean/analysis/climatology/<range>/`, already a set
  of netCDF files;
- the per-year heat content file written by each
  `ocean/analysis/years/ocean_heat_content/<year>` step;
- the equivalent per-year mixed-layer depth files, if it is computed offline.

Because each of these is the output of a shared step keyed by year or by range,
reuse across repeated analyses is Polaris's ordinary step-completion behavior
rather than a caching layer of our own.

### Implementation: repeated-analysis

Date last modified: 2026/08/11

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
covers: `climatology/0021-0040`, `climatology_maps/maps/0021-0040`,
`global_stats/time_series/0001-0060`.  A setup with a new range therefore
creates *new steps in new directories*, which have never run and so are not
complete, and they run.  A setup with the same range lands on the same
directories, which are complete, and nothing is recomputed.

This is the behavior the requirement asks for, and it needs nothing beyond the
existing rule that a step is complete when `polaris_step_complete.log` exists
in its work directory.  It also makes it structurally impossible to get a plot
labeled with one range whose contents came from another, since the two ranges
never share a directory.

#### Reuse comes from per-year shared steps

The expensive per-year work --- vertically integrated heat content, and
mixed-layer depth if it is computed offline --- is one shared step per
simulation year, at `years/ocean_heat_content/0021` and so on, created with
`get_or_create_shared_step()`.  Each reads that year's twelve monthly-mean
files and writes one small netCDF.

Because these steps are keyed by year rather than by range, a later analysis
over a different range asks for the same step for any year the two ranges have
in common, finds it already complete, and skips it.  Extending a time series
from twenty years to forty creates twenty new steps and reuses twenty existing
ones, which is exactly the cost the requirement asks for --- and again with no
mechanism beyond shared steps and the completion marker.

A per-year step is also a well-sized unit of work: roughly 1.8 GB of monthly
means read, one small file written.  Making these steps rather than a loop
inside a single step has a second payoff, which is that they are embarrassingly
parallel and become eligible for concurrent execution as soon as Polaris's task
parallelism lands.  See the task-parallelism requirement in
{ref}`design-ocean-analysis`.

#### Staging results

The step directories are already range-keyed, but they are scattered across
four products several levels down in a work directory.  Plots and their netCDF
files are therefore also symlinked into a staging tree whose root is a config
option, so that there is one place to browse and, later, one tree for a web
interface to serve:

```ini
[ocean_analysis]

# Where to stage plots and their netCDF files for browsing.  Defaults to
# <work_dir>/analysis_output.  Point this somewhere web-servable if you want
# to share the results.
output_path =
```

The tree is organized product first, then range, because the climatology range
and the time series range are independent and a range-first tree would have to
repeat products under two different range directories:

```none
<output_path>/
├── climatology_maps/0021-0040/
├── ocean_heat_content/maps/0021-0040/
├── ocean_heat_content/time_series/0001-0060/
├── global_stats/0001-0060/
└── moc/0021-0040/
```

Range keys are the zero-padded start and end years, matching the convention
`ncclimo` already uses in its file names.

Writing into the step directory and symlinking, rather than writing directly
into the staging tree, keeps every file owned by the step that produced it, so
Polaris's output checking and provenance continue to work and the staging tree
is a view rather than a second source of truth.

#### Caveats

`polaris setup` rewrites the suite pickle at the root of the work directory, so
the most recently set-up range is the one `polaris serial` will run.  Step
directories from earlier ranges are untouched --- they have their own pickles,
outputs, and completion markers --- so re-running an earlier range means
re-running setup with that range's config, after which everything it needs is
already complete except whatever it is being asked to redo.

Analyzing many ranges accumulates step directories and climatology files.  This
is deliberate, since it is what makes re-analyzing an earlier range nearly
free, but it is worth knowing about on a filesystem with a quota.

Per-year steps also mean a suite with a forty-year time series contains forty
extra steps per per-year product.  That is a larger step count than existing
Polaris tasks produce, though not by orders of magnitude, and it is worth a
look at setup time on a long record before committing to per-year rather than,
say, per-decade granularity.

### Implementation: omega-monthly-means

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

This is Omega work and is implemented in the Omega repository, not in Polaris.
What Polaris needs to do:

- add config options for the monthly-mean file-name template, as above;
- add any new Omega fields, including a mixed-layer depth diagnostic, to
  `polaris/ocean/model/mpaso_to_omega.yaml` once their Omega names are fixed;
- add an Omega YAML fragment that turns on monthly-mean output of the required
  fields, so that a Polaris-run simulation can produce input for its own
  analysis, in the same way `analysis_members.cfg` and `forward.yaml` configure
  `GlobalStats` today.

Development of the Polaris side proceeds against Omega output as each Omega
capability lands, rather than against MPAS-Ocean output.  MPAS-Ocean would be a
misleading development target: its variable and dimension names differ, its
time metadata is not CF compliant, and its monthly means come from a different
analysis member with different conventions, so code that works against
MPAS-Ocean output tells us little about whether it will work against Omega's.
Before Omega can write monthly means at all, development is limited to the
shared kernels, which are exercised by unit tests on synthetic data and do not
need model output of either kind.

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
  the fields needed for heat content (`temperature`), the fields needed for
  velocity reconstruction (`normalVelocity`, when zonal and meridional velocity
  are requested and not written by the model), and the vertical geometry
  (`zMid`, `zInterface`).  Building this list is the reason `Climatology` needs
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
  `cpus_per_task = 12` and `ntasks = 1`.

The output file names produced by `ncclimo` follow the pattern
`<caseid>_<season>_<YYYYMM>_<YYYYMM>_climo.nc`.  Rather than reconstructing
that pattern, downstream steps locate climatology files by globbing on the
season, which is robust to `ncclimo` naming changes.

### Implementation: climatology-maps

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Two new shared modules carry the reusable logic.

`polaris/ocean/vertical/elevation.py`, a dependency-light leaf module beside
the existing vertical-coordinate helpers, unit tested directly:

```python
def get_z_mid_and_interface(ds):
    """Return zMid and zInterface, raising a clear error if absent."""


def parse_elevation_spec(spec):
    """Parse 'top', 'bottom', 'k<n>' or an elevation in m."""


def extract_elevation_slice(da, spec, z_mid, min_level_cell, max_level_cell):
    """Extract a horizontal slice at the requested elevation."""


def elevation_range_weights(z_interface, min_level_cell, max_level_cell,
                            z_top, z_bot):
    """Return the per-layer overlap thickness w_k for an elevation range."""
```

`polaris/ocean/heat_content.py`:

```python
def heat_content(temperature, weights, density, specific_heat):
    """Vertically integrated heat content per unit area [J m-2]."""
```

`elevation_range_weights` lives with the other elevation utilities rather than
with heat content because it is a property of the vertical coordinate, and it
will be reused by any future vertically integrated diagnostic.

The `ClimatologyMaps` step then loops over seasons, fields, and elevations:

```python
for season in plot_seasons:
    ds = self.open_model_dataset(climo_filename(season), self.config)
    z_mid, _ = get_z_mid_and_interface(ds)
    for field in fields:
        da = self._get_field(ds, field)   # reconstructs velocities if needed
        if 'nVertLevels' in da.dims:
            specs = [parse_elevation_spec(spec) for spec in elevations]
        else:
            specs = [None]
        for spec in specs:
            da_slice = (da if spec is None else
                        extract_elevation_slice(da, spec, z_mid,
                                                k_min, k_max))
            write_netcdf(da_slice, out_filename)
            plot_global_mpas_field(
                da=da_slice, out_filename=..., config=self.config,
                colormap_section=f'ocean_analysis_map_{field}',
                mesh_filename='mesh.nc', ...)
```

Output names are `<field>_<season>_<elevation_label>.png` with elevation labels
`top`, `bottom`, `-100m`, and `k10`, so that the set of files in the step
directory is self-describing.

Maps are plotted on the native mesh with the existing
`polaris.viz.plot_global_mpas_field`, which is `mosaic`-based and needs no
remapping.  Native-mesh plotting is not a temporary expedient: it is where
observational comparison is headed too, with observations remapped onto the
MPAS mesh rather than the model remapped onto a comparison grid.

The `mosaic` descriptor is constructed once and reused across all plots, since
building it is the expensive part of plotting a global mesh.

Velocity reconstruction uses the weights on the mesh via
`polaris.mesh.reconstruct`.  If the mesh does not carry reconstruction weights,
the step reports that clearly and skips the zonal and meridional velocity maps
rather than failing the whole step.

If `compute_mixed_layer_depth` is set, the task adds a shared per-year step for
each year of the climatology, structured exactly like the per-year heat content
steps: each computes monthly mixed-layer depth with `gsw` as described in the
algorithm design and writes one file for its year.  A range-keyed step then
averages those into the seasonal and annual means that `maps` plots.  Its
outputs carry an attribute recording that they were computed offline from
monthly means, and the step adds a note to the plot titles, so that a reader
cannot mistake them for an in-situ diagnostic.

### Implementation: ocean-heat-content-maps

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The `maps` step of the `ocean_heat_content` task reads the same climatology
files, computes

```python
weights = elevation_range_weights(z_interface, k_min, k_max, z_top, z_bot)
ohc = heat_content(ds.temperature, weights, rho0, cp0)
```

for each configured elevation range and each plotted season, writes the result
to netCDF in J m⁻² and plots it in GJ m⁻² (a range of $0$ to $-700$ m at a
typical 10 °C is about 29 GJ m⁻², which is a readable number).

Output names are `ohc_<season>_<z_top>_<z_bot>.png`, for example
`ohc_ANN_0m_-700m.png` and `ohc_ANN_-2000m_bottom.png`.  Plot titles state the
elevation range and the season explicitly, and the netCDF carries the range as
attributes, so that a plot cannot be mistaken for a different range.

### Implementation: global-stats-time-series

Date last modified: 2026/08/11

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

The time axis is converted to simulation years from the CF time coordinate.
`polaris.ocean.model.time.get_days_since_start` provides the days-since-start
conversion already used elsewhere; the new code divides by the length of the
year in the file's calendar.

### Implementation: ocean-heat-content-time-series

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

This product is two kinds of step.  A shared `OceanHeatContentYear` step per
simulation year does the expensive work for that year:

```python
class OceanHeatContentYear(OceanIOStep):
    def run(self):
        ds_year = []
        for month in range(1, 13):
            ds = self.open_model_dataset(f'monthly_{month:02d}.nc',
                                         self.config)
            _, z_interface = get_z_mid_and_interface(ds)
            ohc = []
            for z_top, z_bot in elevation_ranges:
                weights = elevation_range_weights(z_interface, k_min, k_max,
                                                  z_top, z_bot)
                column = heat_content(ds.temperature, weights, rho0, cp0)
                ohc.append((area_cell * column).sum('nCells'))
            ds_year.append(...)
        write_netcdf(xr.concat(ds_year, dim='Time'), 'ohc.nc')
```

and a range-keyed `time_series` step concatenates the per-year files for the
requested years and plots them.  The task's `configure()` creates one per-year
step for each year in the configured range with
`get_or_create_shared_step()`, so a year analyzed by an earlier range is reused
rather than recomputed.

Reading a month at a time within the year step is deliberate.  A global
three-dimensional temperature field at 30 km resolution and 80 levels is
roughly 150 MB per month, so a forty-year record is several tens of gigabytes;
a month at a time bounds memory regardless of how long the record is.  Only
`temperature`, `zInterface`, and the vertical-index fields are read.

The plot has two panels: absolute heat content in units of 10²² J, and the
anomaly relative to the first month, with one line per elevation range.  The
concatenated time series is written to `ocean_heat_content_time_series.nc`.

The per-year steps are the most expensive part of the suite.  If they prove too
slow, there are two independent moves available: run them concurrently once
Polaris's task parallelism lands, which needs no changes here because they are
already independent non-MPI steps; or compute the vertical integrals in Omega
in situ, which reduces the whole product to a concatenation.  If mixed-layer
depth is also computed offline, its per-year steps make the same pass over the
same monthly files and could be merged with these; they are kept separate
because a merged step would couple two products for a saving that only matters
if the pass proves expensive.

### Implementation: moc-plot

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The `moc/plot` step reads Omega's global MOC output over the climatology years,
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

### Implementation: commit sequence

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

1. This design document and the umbrella document
   {ref}`design-ocean-analysis`.
2. `polaris/ocean/vertical/elevation.py` --- elevation specifications,
   elevation slicing, and elevation-range weights --- with unit tests.
3. `polaris/ocean/heat_content.py` with unit tests.
4. The `omega_analysis` scaffolding: the `polaris/tasks/ocean/analysis/`
   package, `analysis.cfg`, `sim_files.py`, the range-keyed step subdirectories
   and output staging shared by every step, the four tasks with their
   `configure()` methods, and the `omega_analysis` suite, with steps that do
   nothing yet.  This is the commit where the repeated-analysis structure is
   established, so it should land before anything that depends on it.
5. The `Climatology` step (`ncclimo`).
6. The `ClimatologyMaps` step, including velocity reconstruction.
7. The ocean heat content `maps` step.
8. The `global_stats` `time_series` step, including factoring the shared
   plotting function out of `StatsAnalysis`.
9. The per-year and range-keyed ocean heat content time series steps.
10. The `moc` `plot` step and the `plot_lat_elevation_field` primitive.
11. The offline per-year `mixed_layer_depth` steps, only if Omega's in-situ
    diagnostic will not be ready in time.
12. User's Guide documentation: a page under `docs/users_guide/ocean/tasks/`
    describing the analysis suite and its config options, and an entry in
    `docs/users_guide/ocean/suites.md`.

Commits 2, 3, and 5 through 11 are independently reviewable and each leaves the
suite in a working state for the products delivered so far.

## Testing

### Testing and Validation: analysis-suite and data-products

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests under `tests/ocean/` cover the parts that do not need a simulation:

- expansion of file-name templates over a year range, including the error
  message when years are missing;
- parsing of the elevation and elevation-range config syntax, including invalid
  input and the `top`, `bottom`, and `k<n>` keywords;
- that every plotting step registers a netCDF output for each PNG output, which
  keeps the data-products requirement from quietly regressing.

### Testing and Validation: repeated-analysis

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The step tree each task builds is a pure function of its config options, so
most of this can be tested without running anything.  Unit tests construct a
task, set config options, call `configure()`, and inspect the resulting steps:

- the range-keyed steps land at subdirectories named for the configured range,
  and changing the range changes those subdirectories;
- one per-year step is created for each year in the configured range, at a
  subdirectory named for the year;
- widening the range produces the same per-year steps for the years the two
  ranges share --- literally the same objects, via
  `get_or_create_shared_step()` --- plus new ones for the added years;
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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests on `extract_elevation_slice` with synthetic columns having known
layer geometry, `minLevelCell`, and `maxLevelCell`:

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

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests on `elevation_range_weights` and `heat_content`:

- for a range aligned with layer interfaces, the weights are exactly the layer
  thicknesses in the range and zero outside;
- for a range boundary in the interior of a layer, the weight of that layer is
  the exact partial thickness;
- for a constant temperature $\Theta_0$ over a range $[z_{bot}, z_{top}]$
  entirely within the water column, the heat content is exactly
  $\rho_0 c_p^0 \Theta_0 (z_{top} - z_{bot})$;
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

- a unit test that the per-year heat content files are reused rather than
  recomputed when they already exist, and that adding a year extends the series
  correctly;
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
   schedule and commit 11 above.
2. **`ncclimo` and Omega output.**  Whether `ncclimo` can read Omega
   monthly-mean files without the MPAS-specific processing type needs to be
   confirmed against real output as soon as Omega can produce it.  This is on
   the critical path.
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
