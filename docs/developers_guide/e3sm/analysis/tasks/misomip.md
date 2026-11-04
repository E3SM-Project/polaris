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

{py:class}`polaris.tasks.e3sm.analysis.misomip.comparison.RunComparison`
compares the two runs' diagnostics, and
{py:class}`polaris.tasks.e3sm.analysis.misomip.conservation.CouplerConservation`
reads the coupler's budgets.  In the coupled experiments, IceOcean1r and
IceOcean1ra,
{py:class}`polaris.tasks.e3sm.analysis.misomip.exchange.ModelExchange`
compares the flux the ocean sends with the melt MALI applies over the
same period, from MALI's global statistics, and
{py:class}`polaris.tasks.e3sm.analysis.misomip.ice_sheet.IceSheetComparison`
compares MALI's ice sheet with standalone MALI runs of MISMIP+ and the
entries of Cornford et al. (2020), which
`[misomip_analysis_mismip_plus]` names.  IceOcean1ra reads IceOcean1r's
initial conditions, since it continues from IceOcean1r's restart.  None of
these reads model output twice: the comparison reads only the diagnostics
steps' files.
{py:class}`polaris.tasks.e3sm.analysis.misomip.publish.MisomipPublish`
publishes a task's products under its mesh and experiment.

With `write_protocol_fields = True`, each run also gets a
{py:class}`polaris.tasks.e3sm.analysis.misomip.protocol.ProtocolMapStep`,
which writes SCRIP files of the run's mesh and the protocol's grid in
`runtime_setup()` and makes a conservative map between them, and a
{py:class}`polaris.tasks.e3sm.analysis.misomip.protocol.ProtocolFields`
step, which writes the protocol's file from the run's monthly means.

Lines of constant $x$ and the sections use the protocol's coordinates,
`xIsomipCell` and `yIsomipCell`, which the inputs' ocean mesh keeps.
