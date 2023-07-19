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
   BaroclinicChannelTestCase.validate
   
   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.setup
   init.Init.run

   viz.Viz
   viz.Viz.run

   default.Default
   default.Default.validate

   decomp.Decomp
   decomp.Decomp.validate

   restart.Restart
   restart.Restart.validate

   restart.restart_step.RestartStep
   restart.restart_step.RestartStep.dynamic_model_config

   threads.Threads
   threads.Threads.validate

   rpe.Rpe
   rpe.Rpe.configure
   rpe.Rpe.validate
   rpe.analysis.Analysis
   rpe.analysis.Analysis.setup
   rpe.analysis.Analysis.run
```

### inertial_gravity_wave 

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.inertial_gravity_wave

.. autosummary::
   :toctree: generated/

   InertialGravityWave 

   analysis.Analysis
   analysis.Analysis.run

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normalVelocity

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run

   convergence.Convergence
   convergence.Convergence.validate
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

   viz.Viz
   viz.Viz.run
```

### manufactured_solution

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.manufactured_solution

.. autosummary::
   :toctree: generated/

   ManufacturedSolution

   analysis.Analysis
   analysis.Analysis.run

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normalVelocity

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run

   convergence.Convergence
   convergence.Convergence.validate
```

### single_column

```{eval-rst}
.. currentmodule:: polaris.ocean.tests.single_column

.. autosummary::
   :toctree: generated/

   SingleColumn

   forward.Forward

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run

   cvmix.CVMix
   cvmix.CVMix.validate

   ideal_age.IdealAge
   ideal_age.IdealAge.validate
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
