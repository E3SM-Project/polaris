# landice

```{eval-rst}
.. currentmodule:: polaris.tasks.landice

.. autosummary::
   :toctree: generated/

   Landice
   Landice.configure
   Landice.build_model
   get_build_albany

.. currentmodule:: polaris.tasks.landice.add_tasks

.. autosummary::
   :toctree: generated/

   add_landice_tasks
```

## Tasks

### dome

```{eval-rst}
.. currentmodule:: polaris.tasks.landice.dome

.. autosummary::
   :toctree: generated/

   add_dome_tasks

   init.Init
   init.Init.run

   forward.Forward

   validate.Validate
   validate.Validate.run

   viz.Viz
   viz.Viz.run

   smoke_test.SmokeTest

   decomp.Decomp

   restart.Restart
```

### mismip_plus

```{eval-rst}
.. currentmodule:: polaris.tasks.landice.mismip_plus

.. autosummary::
   :toctree: generated/

   add_mismip_plus_tasks
   steps.get_mismip_plus_steady_state_steps

   experiments.Experiment

   init.Init
   init.Init.run

   model.MismipPlusModelStep
   model.MismipPlusModelStep.setup
   model.MismipPlusModelStep.constrain_resources
   model.MismipPlusModelStep.dynamic_model_config

   spin_up.SpinUpTask

   spin_up.SpinUpRun
   spin_up.SpinUpRun.runtime_setup
   spin_up.SpinUpRun.dynamic_model_config

   spin_up.SpinUp
   spin_up.SpinUp.run

   spin_up.SpinUpViz
   spin_up.SpinUpViz.run

   spin_up.run.get_restart_year

   forward.Forward
   forward.Forward.end_restart_filename

   cornford.Cornford2020
   cornford.Cornford2020.run

   analysis.Analysis
   analysis.Analysis.run

   experiment.ExperimentTask

   output.read_output

   plot.plot_thickness_and_speed
   plot.plot_grounding_line
   plot.plot_time_series
   plot.plot_global_stats
```

## Land-ice Framework

### Model

```{eval-rst}
.. currentmodule:: polaris.landice.model

.. autosummary::
   :toctree: generated/

   MaliModelStep
   MaliModelStep.needs_albany
   MaliModelStep.dynamic_model_config
```

### Mesh

```{eval-rst}
.. currentmodule:: polaris.landice.mesh

.. autosummary::
   :toctree: generated/

   make_mali_mesh
```

### MISMIP+

```{eval-rst}
.. currentmodule:: polaris.landice.mismip_plus

.. autosummary::
   :toctree: generated/

   geometry.bed_topography

   mesh.get_mesh_parameters
   mesh.make_mismip_plus_mesh

   diagnostics.thickness_above_flotation
   diagnostics.compute_diagnostics
```
