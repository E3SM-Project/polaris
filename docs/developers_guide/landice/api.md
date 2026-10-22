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
