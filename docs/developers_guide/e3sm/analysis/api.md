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
   diagnostics.compute_daily_volume_budget
   diagnostics.compute_monthly_volume_budget
   diagnostics.isomip_mesh
   diagnostics.compute_time_means
   plots.RunPlots
   plots.RunPlots.run
   plots.scale_with_units
   plots.get_map_mask
   plots.get_range_mask
   plots.get_hatched_cells
   plots.get_color_range
   plots.get_color_norm
   plots.plot_section
   comparison.RunComparison
   comparison.RunComparison.run
   conservation.CouplerConservation
   conservation.CouplerConservation.run
   conservation.OceanVolumeBudget
   conservation.OceanVolumeBudget.run
   performance.RunPerformance
   performance.RunPerformance.run
   exchange.ModelExchange
   exchange.ModelExchange.run
   exchange.get_coupling_interval
   exchange.read_landice_steps
   exchange.compare_with_landice
   ice_sheet.IceSheetComparison
   ice_sheet.IceSheetComparison.setup
   ice_sheet.IceSheetComparison.run
   ice_sheet.read_landice_history
   ice_sheet.read_landice_stats
   ice_sheet.get_lines_range
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

### performance

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.performance

.. autosummary::
   :toctree: generated/

   Segment
   WallClockStamps
   Memory
   Job
   find_lid
   find_timing_files
   read_segment
   read_timers
   read_segment_period
   read_segment_start
   select_segment_logs
   read_wall_clock_stamps
   read_root_memory
   read_node_memory
   read_slurm_jobs
   date_to_days
```

### calendar

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.calendar

.. autosummary::
   :toctree: generated/

   xtime_to_days
   month_start_days
```

### runs

```{eval-rst}
.. currentmodule:: polaris.e3sm.analysis.runs

.. autosummary::
   :toctree: generated/

   E3smRun
   E3smRun.find_stream_files
   E3smRun.namelist_option
   E3smRun.input_filename
   StandaloneRun
   StandaloneRun.find_stream_files
   StandaloneRun.namelist_option
   StandaloneRun.input_filename
   select_months
   month_range_key
```
