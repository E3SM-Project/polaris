(dev-e3sm-analysis-misomip)=

# misomip

The tasks are
{py:class}`polaris.tasks.e3sm.analysis.misomip.task.MisomipAnalysisTask`,
one per experiment and pair of meshes, sharing the config
`e3sm/analysis/misomip_analysis.cfg`.  A task builds its steps in
`configure()`, once the user's config is read, from the runs
{py:func}`polaris.tasks.e3sm.analysis.misomip.runs.get_configured_runs`
finds.  Every task sharing the config is configured, including those not
being set up, so a task without runs gets only its `publish` step, whose
`setup()` reports the missing runs.

Each run gets two shared steps, named for the months it has:

- {py:class}`polaris.tasks.e3sm.analysis.misomip.diagnostics.RunDiagnostics`
  links the run's initial condition, monthly means and daily global
  statistics, and writes `time_series.nc`, `time_mean.nc`,
  `monthly_maps.nc` and `daily.nc`;
- {py:class}`polaris.tasks.e3sm.analysis.misomip.plots.RunPlots` plots them
  and describes each plot as a product.

The diagnostics read each of the run's files once, keeping only the fields
they use (`MONTHLY_MEAN_FIELDS`, `DAILY_MEAN_FIELDS`, `DAILY_FIELDS` and
`LANDICE_FIELDS`), with {py:func}`polaris.mpas.read_time_series()`.  A field
used only where a run writes it belongs in these lists too, since the
diagnostics test for it by name.

The diagnostics mark each month's columns that are wet, rather than holding
only the thin film, as `wetColumn`, with
{py:func}`polaris.ocean.ice_shelf.get_film_columns()` on that month's mean
column.  `time_mean.nc` and the comparison's mean maps come from
{py:func}`polaris.tasks.e3sm.analysis.misomip.diagnostics.compute_time_means`:
the fields of the ocean's state in `WET_MEAN_WEIGHTS` are averaged over the
months each column is wet, by
{py:func}`polaris.ocean.ice_shelf.compute_wet_time_mean()`, weighted by
layer thickness on layers.  Fluxes, such as melt, are averaged over all
months, and the transports, the barotropic and overturning
streamfunctions, come from the plain means of velocity, layer thickness
and the layer thickness flux.  `partlyWetColumn` marks the columns wet in
only some months, which
{py:func}`polaris.tasks.e3sm.analysis.misomip.plots.get_hatched_cells`
hatches in the maps and sections of the state.

{py:class}`polaris.tasks.e3sm.analysis.misomip.comparison.RunComparison`
compares the two runs' diagnostics, and
{py:class}`polaris.tasks.e3sm.analysis.misomip.conservation.CouplerConservation`
reads the coupler's budgets.  A run with daily global statistics and
daily means, or with tidal forcing and monthly snapshots of layer thickness,
gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.conservation.OceanVolumeBudget`
step, which plots the ocean's volume budgets that
{py:func}`polaris.tasks.e3sm.analysis.misomip.diagnostics.compute_daily_volume_budget`
and
{py:func}`polaris.tasks.e3sm.analysis.misomip.diagnostics.compute_monthly_volume_budget`
compute in the run's diagnostics.  Every E3SM run gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.performance.RunPerformance`
step, which plots the run's performance from each segment's timing files,
coupler log and memory profile.  It splits the ocean's and MALI's run times
into the parts its `RUN_TIME_PARTS` names, from the models' timers.  In the coupled experiments, IceOcean1r and
IceOcean1ra,
{py:class}`polaris.tasks.e3sm.analysis.misomip.exchange.ModelExchange`
compares the flux the ocean sends with the melt + frazil MALI applies over the
same period, from MALI's global statistics, and
{py:class}`polaris.tasks.e3sm.analysis.misomip.ice_sheet.IceSheetComparison`
compares MALI's ice sheet with standalone MALI runs of MISMIP+ and the
entries of Cornford et al. (2020), which
`[misomip_analysis_mismip_plus]` names.  IceOcean1ra reads IceOcean1r's
initial conditions, since it continues from IceOcean1r's restart.  None of
these reads model output twice: the comparison reads only the diagnostics
steps' files.
{py:class}`polaris.tasks.e3sm.analysis.misomip.publish.MisomipPublish`
publishes a task's products under its mesh and experiment.  It titles every
page with the run's name and gives every page the same bar of links, from
{py:func}`polaris.tasks.e3sm.analysis.misomip.publish.get_site_links`, with
the summary as the site's home.
An experiment with `<experiment>_summary` set also gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.summary.SummaryPage`, a
{py:class}`polaris.analysis.page.PageStep` that depends on the steps making
products.  It reads their fragments to find the name each plot is
published under, and links each plot it shows at `../plots/<name>`, where
the publish step puts it, rather than copying it.  It leads the page with
how the run was made, from the case and namelist as the task is set up,
and the years it covers.

Each run also gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.health_page.RunHealthPage`,
a page of the checks of the run's health that the diagnostics step
computes year by year with the functions in
{py:mod}`polaris.tasks.e3sm.analysis.misomip.health`.  That module is one
of the reducing modules in `years.py`, so a change to it makes the cached
years stale.  The page's tables are in a module of their own, so changing
them does not.  The checks read the density of the seawater the land ice
displaces, `config_land_ice_rho_ocean`, and the minimum thickness of
wetting and drying from the run's namelist, and the restoring salinity
from the run's `interior_restoring` stream where the namelist turns
interior restoring on.

With `write_protocol_fields = True`, each run also gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.protocol.ProtocolMapStep`,
which writes SCRIP files of the run's mesh and the protocol's grid in
`runtime_setup()` and makes a conservative map between them, and a
{py:class}`polaris.tasks.e3sm.analysis.misomip.protocol.ProtocolFields`
step, which writes the protocol's file from the run's monthly means.

Lines of constant $x$ and the sections use the protocol's coordinates,
`xIsomipCell` and `yIsomipCell`, which the inputs' ocean mesh keeps.
