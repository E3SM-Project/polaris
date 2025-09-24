# ocean

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean

.. autosummary::
   :toctree: generated/

   Ocean

   add_tasks.add_ocean_tasks
```

## Tasks

### baroclinic_channel

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.baroclinic_channel

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

### barotropic_gyre

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.barotropic_gyre

.. autosummary::
   :toctree: generated/

   add_barotropic_gyre_tasks

   BarotropicGyre

   analysis.Analysis
   analysis.Analysis.compute_error
   analysis.Analysis.exact_solution
   analysis.Analysis.run

   forward.compute_max_time_step
   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.setup
   init.Init.run

```

### cosine_bell

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.cosine_bell

.. autosummary::
   :toctree: generated/

   add_cosine_bell_tasks

   CosineBell
   CosineBell.configure

   init.Init
   init.Init.run
   init.cosine_bell

   forward.Forward

   analysis.Analysis
   analysis.Analysis.exact_solution

   validate.Validate
   validate.Validate.run

   viz.Viz
   viz.Viz.run

   decomp.Decomp

   restart.Restart

   restart.RestartStep
   restart.RestartStep.dynamic_model_config

```

### drying_slope

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.drying_slope

.. autosummary::
   :toctree: generated/

   add_drying_slope_tasks

   baroclinic.Baroclinic
   baroclinic.Baroclinic.configure

   barotropic.Barotropic

   convergence.Convergence
   convergence.analysis.Analysis
   convergence.analysis.Analysis.exact_solution
   convergence.forward.Forward
   convergence.forward.Forward.compute_cell_count
   convergence.forward.Forward.dynamic_model_config

   decomp.Decomp

### geostrophic

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.geostrophic

.. autosummary::
   :toctree: generated/

   add_geostrophic_tasks

   Geostrophic
   Geostrophic.configure

   init.Init
   init.Init.run

   forward.Forward

   analysis.Analysis
   analysis.Analysis.exact_solution
   analysis.Analysis.get_output_field

   viz.Viz
   viz.Viz.run
```

### ice_shelf_2d

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.ice_shelf_2d

.. autosummary::
   :toctree: generated/

   add_ice_shelf_2d_tasks

   default.Default

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   validate.Validate
   validate.Validate.run

   viz.Viz
   viz.Viz.run
```

### inertial_gravity_wave

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.inertial_gravity_wave

.. autosummary::
   :toctree: generated/

   add_inertial_gravity_wave_tasks

   InertialGravityWave

   analysis.Analysis
   analysis.Analysis.exact_solution

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normal_velocity

   forward.Forward
   forward.Forward.compute_cell_count

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run
```

### internal_wave

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.internal_wave

.. autosummary::
   :toctree: generated/

   add_internal_wave_tasks

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run

   default.Default

   rpe.Rpe
   rpe.Rpe.configure
   rpe.analysis.Analysis
   rpe.analysis.Analysis.run
```


### manufactured_solution

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.manufactured_solution

.. autosummary::
   :toctree: generated/

   add_manufactured_solution_tasks

   ManufacturedSolution

   analysis.Analysis
   analysis.Analysis.exact_solution

   exact_solution.ExactSolution
   exact_solution.ExactSolution.ssh
   exact_solution.ExactSolution.normal_velocity

   forward.Forward
   forward.Forward.compute_cell_count

   init.Init
   init.Init.run
   init.Init.setup

   viz.Viz
   viz.Viz.run
```

### merry_go_round

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.merry_go_round

.. autosummary::
   :toctree: generated/

   add_merry_go_round_tasks

   default.Default
   default.viz.Viz
   default.viz.Viz.setup
   default.viz.Viz.run

   forward.Forward
   forward.Forward.compute_cell_count

   init.Init
   init.Init.setup
   init.Init.run

   analysis.Analysis

   viz.Viz
   viz.Viz.setup
   viz.Viz.run
```

### overflow

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.overflow

.. autosummary::
   :toctree: generated/

   add_overflow_tasks

   default.Default

   forward.Forward
   forward.Forward.dynamic_model_config
   forward.Forward.compute_cell_count

   init.Init
   init.Init.setup
   init.Init.run

   rpe.Rpe
   rpe.Rpe.configure

   rpe.analysis.Analysis
   rpe.analysis.Analysis.run
   
   viz.Viz
   viz.Viz.run
   
```

### single_column

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.single_column

.. autosummary::
   :toctree: generated/

   add_single_column_tasks

   cvmix.CVMix

   ekman.Ekman
   ekman.analysis.Analysis
   ekman.analysis.Analysis.run

   forward.Forward
   forward.Forward.dynamic_model_config

   ideal_age.IdealAge

   inertial.Inertial
   inertial.analysis.Analysis
   inertial.analysis.Analysis.run

   init.Init
   init.Init.run

   viz.Viz
   viz.Viz.run
```

### sphere_transport

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.sphere_transport

.. autosummary::
   :toctree: generated/

   add_sphere_transport_tasks

   SphereTransport
   SphereTransport.configure

   init.Init
   init.Init.run

   forward.Forward

   analysis.Analysis
   analysis.Analysis.convergence_parameters

   mixing_analysis.MixingAnalysis
   mixing_analysis.MixingAnalysis.run

   filament_analysis.FilamentAnalysis
   filament_analysis.FilamentAnalysis.run

   viz.Viz
   viz.Viz.run
```

## Ocean Framework

### Convergence Tests

```{eval-rst}
.. currentmodule:: polaris.ocean.convergence

.. autosummary::
   :toctree: generated/

   get_resolution_for_task
   get_timestep_for_task

   forward.ConvergenceForward
   forward.ConvergenceForward.compute_cell_count
   forward.ConvergenceForward.dynamic_model_config

   analysis.ConvergenceAnalysis
   analysis.ConvergenceAnalysis.compute_error
   analysis.ConvergenceAnalysis.convergence_parameters
   analysis.ConvergenceAnalysis.exact_solution
   analysis.ConvergenceAnalysis.get_output_field
   analysis.ConvergenceAnalysis.plot_convergence
   analysis.ConvergenceAnalysis.run
   analysis.ConvergenceAnalysis.setup
```
### Spherical Convergence Tests

```{eval-rst}
.. currentmodule:: polaris.ocean.convergence.spherical

.. autosummary::
   :toctree: generated/

   SphericalConvergenceForward
   SphericalConvergenceForward.compute_cell_count
```

### Ice Shelf

```{eval-rst}
.. currentmodule:: polaris.ocean.ice_shelf

.. autosummary::
   :toctree: generated/

   IceShelfTask
   IceShelfTask.setup_ssh_adjustment_steps

   SshAdjustment
   SshAdjustment.run

   SshForward
   SshForward.compute_cell_count
   SshForward.dynamic_model_config
```

### Ocean Model

```{eval-rst}
.. currentmodule:: polaris.ocean.model

.. autosummary::
   :toctree: generated/

   OceanIOStep
   OceanIOStep.setup
   OceanIOStep.map_to_native_model_vars
   OceanIOStep.write_model_dataset
   OceanIOStep.map_from_native_model_vars
   OceanIOStep.open_model_dataset

   OceanModelStep
   OceanModelStep.setup
   OceanModelStep.constrain_resources
   OceanModelStep.compute_cell_count
   OceanModelStep.map_yaml_options
   OceanModelStep.map_yaml_configs

   get_time_interval_string
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
   vertical.sigma.init_sigma_vertical_coord
   vertical.sigma.update_sigma_layer_thickness
   vertical.update_layer_thickness
   vertical.zlevel.init_z_level_vertical_coord
   vertical.zlevel.update_z_level_layer_thickness
   vertical.zlevel.compute_min_max_level_cell
   vertical.zlevel.compute_z_level_layer_thickness
   vertical.zlevel.compute_z_level_resting_thickness
   vertical.zstar.init_z_star_vertical_coord
   vertical.zstar.update_z_star_layer_thickness
```

