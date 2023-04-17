# ocean

```{eval-rst}
.. currentmodule:: polaris.ocean

.. autosummary::
   :toctree: generated/

   Ocean
```

## Test Groups

### baroclinic_channel

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.baroclinic_channel

.. autosummary::
   :toctree: generated/

   BaroclinicChannel

   BaroclinicChannelTestCase
   BaroclinicChannelTestCase.configure
   BaroclinicChannelTestCase.validate
   
   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   initial_state.InitialState
   initial_state.InitialState.setup
   initial_state.InitialState.run

   viz.Viz
   viz.Viz.run

   default.Default
   default.Default.validate

   decomp_test.DecompTest
   decomp_test.DecompTest.validate

   restart_test.RestartTest
   restart_test.RestartTest.validate

   restart_test.restart_step.RestartStep
   restart_test.restart_step.RestartStep.dynamic_model_config

   threads_test.ThreadsTest
   threads_test.ThreadsTest.validate

   rpe_test.RpeTest
   rpe_test.RpeTest.configure
   rpe_test.RpeTest.validate
   rpe_test.analysis.Analysis
   rpe_test.analysis.Analysis.setup
   rpe_test.analysis.Analysis.run
```

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

   viz.VizMap
   viz.VizMap.run

```

## Ocean Framework

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

### Reference Potential Energy (RPE)

```{eval-rst}
.. currentmodule:: polaris.ocean

.. autosummary::
   :toctree: generated/

   rpe.compute_rpe

```

### Vertical coordinates

```{eval-rst}
.. currentmodule:: polaris.ocean

.. autosummary::
   :toctree: generated/

   vertical.init_vertical_coord
   vertical.grid_1d.generate_1d_grid
   vertical.grid_1d.write_1d_grid
   vertical.partial_cells.alter_bottom_depth
   vertical.partial_cells.alter_ssh
   vertical.zlevel.init_z_level_vertical_coord
   vertical.zlevel.compute_min_max_level_cell
   vertical.zlevel.compute_z_level_layer_thickness
   vertical.zlevel.compute_z_level_resting_thickness
   vertical.zstar.init_z_star_vertical_coord
```
