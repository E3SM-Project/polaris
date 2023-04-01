# ocean

```{eval-rst}
.. currentmodule:: polaris.ocean

.. autosummary::
   :toctree: generated/

   Ocean
```

## Test Groups

### global_convergence

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.global_convergence

.. autosummary::
   :toctree: generated/

   GlobalConvergence
```

#### cosine_bell

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.global_convergence.cosine_bell

.. autosummary::
   :toctree: generated/

   CosineBell
   CosineBell.configure
   CosineBell.validate

   init.Init
   init.Init.run

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   analysis.Analysis
   analysis.Analysis.run
   analysis.Analysis.rmse

```

## Framework

### OceanModelStep

```{eval-rst}
.. currentmodule:: polaris.ocean.model

.. autosummary::
   :toctree: generated/

   OceanModelStep
   OceanModelStep.setup
   OceanModelStep.constrain_resources
   OceanModelStep.compute_cell_count
   OceanModelStep.map_yaml_to_namelist
```
