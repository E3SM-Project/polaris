# ocean

```{eval-rst}
.. currentmodule:: polaris.ocean

.. autosummary::
   :toctree: generated/

   Ocean
```

## Tasks

### baroclinic_channel

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.baroclinic_channel

.. autosummary::
   :toctree: generated/

   add_baroclinic_channel_tasks

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.setup
   init.Init.run

   validate.Validate
   validate.Validate.run
   
   viz.Viz
   viz.Viz.run

   default.Default

   decomp.Decomp

   restart.Restart

   restart.restart_step.RestartStep
   restart.restart_step.RestartStep.dynamic_model_config

   threads.Threads

   rpe.Rpe
   rpe.Rpe.configure
   rpe.analysis.Analysis
   rpe.analysis.Analysis.setup
   rpe.analysis.Analysis.run
```

### inertial_gravity_wave 

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.inertial_gravity_wave

.. autosummary::
   :toctree: generated/

   add_inertial_gravity_wave_tasks
   
   InertialGravityWave

   analysis.Analysis
   analysis.Analysis.run

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normal_velocity

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run
```

### cosine_bell

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.cosine_bell

.. autosummary::
   :toctree: generated/

   add_cosine_bell_tasks

   CosineBell
   CosineBell.configure

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
.. currentmodule:: polaris.ocean.tasks.manufactured_solution

.. autosummary::
   :toctree: generated/

   add_manufactured_solution_tasks
   
   ManufacturedSolution

   analysis.Analysis
   analysis.Analysis.run

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normal_velocity

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run
```

### single_column

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.single_column

.. autosummary::
   :toctree: generated/

   add_single_column_tasks

   forward.Forward

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run

   cvmix.CVMix

   ideal_age.IdealAge
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

### Spherical Base Mesh Step

```{eval-rst}
.. currentmodule:: polaris.ocean.mesh.spherical

.. autosummary::
   :toctree: generated/

   add_spherical_base_mesh_step
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
