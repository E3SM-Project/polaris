# e3sm/analysis

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.analysis

.. autosummary::
   :toctree: generated/

   add_tasks.add_e3sm_analysis_tasks
```

## Tasks

### misomip

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.analysis.misomip

.. autosummary::
   :toctree: generated/

   add_misomip_analysis_tasks
   task.MisomipAnalysisTask
   task.MisomipAnalysisTask.configure
   runs.ConfiguredRun
   runs.get_configured_runs
   runs.get_mean_months
   runs.runs_section
   diagnostics.RunDiagnostics
   diagnostics.RunDiagnostics.run
   diagnostics.read_initial_condition
   diagnostics.isomip_mesh
   plots.RunPlots
   plots.RunPlots.run
   comparison.RunComparison
   comparison.RunComparison.run
   conservation.CouplerConservation
   conservation.CouplerConservation.run
   published.PublishedComparison
   published.PublishedComparison.run
   yung2026.Yung2026
   yung2026.Yung2026.run
   yung2026.get_yung2026_step
   protocol.ProtocolMapStep
   protocol.ProtocolMapStep.runtime_setup
   protocol.ProtocolFields
   protocol.ProtocolFields.run
   protocol.write_protocol_scrip
   protocol.bin_column
   comparisons.SeriesComparison
   comparisons.SeriesComparison.run
   comparisons.MisomipExperimentsTask
   comparisons.MisomipExperimentsTask.configure
   comparisons.MisomipResolutionsTask
   comparisons.MisomipResolutionsTask.configure
   task.get_diagnostics_steps
   task.get_resolution
   publish.MisomipPublish
   publish.MisomipPublish.setup
   publish.MisomipPublish.output_path
```

## Framework

### case

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.case

.. autosummary::
   :toctree: generated/

   E3smCase
   E3smCase.get_value
   E3smCase.read_streams
   E3smCase.find_stream_files
   E3smCase.find_logs
```

### budgets

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.budgets

.. autosummary::
   :toctree: generated/

   BudgetTable
   read_budget_tables
   read_initial_start
   budget_time_series
```

### runs

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.runs

.. autosummary::
   :toctree: generated/

   E3smRun
   E3smRun.find_stream_files
   E3smRun.namelist_option
   StandaloneRun
   StandaloneRun.find_stream_files
   StandaloneRun.namelist_option
   select_months
   month_range_key
```
