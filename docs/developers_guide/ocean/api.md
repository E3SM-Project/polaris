# ocean

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean

.. autosummary::
   :toctree: generated/

   Ocean
   Ocean.map_to_native_model_vars
   Ocean.map_var_list_to_native_model
   Ocean.write_model_dataset
   Ocean.map_from_native_model_vars
   Ocean.map_var_list_from_native_model
   Ocean.open_model_dataset

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

### barotropic_channel

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.barotropic_channel

.. autosummary::
   :toctree: generated/

   add_barotropic_channel_tasks

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.setup
   init.Init.run

   viz.Viz
   viz.Viz.run

   default.Default
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

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.compute_max_time_step
   forward.Forward.dynamic_model_config
   forward.Forward.setup

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

### customizable_viz

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.customizable_viz

.. autosummary::
   :toctree: generated/

   add_customizable_viz_tasks

   CustomizableViz

   VizHorizField
   VizHorizField.runtime_setup
   VizHorizField.run

   VizTransect
   VizTransect.runtime_setup
   VizTransect.run
```

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

### horiz_press_grad

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.horiz_press_grad

.. autosummary::
   :toctree: generated/

   add_horiz_press_grad_tasks

   task.HorizPressGradTask
   task.HorizPressGradTask.configure

   reference.ReferenceColumn
   reference.ReferenceColumn.specvol
   reference.ReferenceColumn.dalpha_dx
   reference.ReferenceColumn.hpga
   reference.ReferenceColumn.layer_mean_hpga

   init.Init
   init.Init.run

   forward.Forward
   forward.Forward.setup

   analysis.Analysis
   analysis.Analysis.setup
   analysis.Analysis.run
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
   forward.Forward.setup
   forward.Forward.dynamic_model_config

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

   smoke_test.SmokeTest

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

### realistic_global

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.realistic_global

.. autosummary::
   :toctree: generated/

   add_realistic_global_tasks
```

### realistic_global.hydrography.woa23

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.realistic_global.hydrography.woa23

.. autosummary::
   :toctree: generated/

   Woa23
   get_woa23_steps

   CombineStep
   CombineStep.setup
   CombineStep.run

   ExtrapolateStep
   ExtrapolateStep.setup
   ExtrapolateStep.run
```

### realistic_global.init

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.realistic_global.init

.. autosummary::
   :toctree: generated/

   tasks.add_realistic_global_init_tasks

   task.RealisticGlobalInit

   steps.get_realistic_init_steps

   cull_topo.CullTopoStep
   cull_topo.CullTopoStep.setup
   cull_topo.CullTopoStep.run

   remap_woa23.RemapWoa23Step
   remap_woa23.RemapWoa23Step.setup
   remap_woa23.RemapWoa23Step.run

   pstar_init.RealisticPStarInitStep
   pstar_init.RealisticPStarInitStep.setup
   pstar_init.RealisticPStarInitStep.run
   pstar_init.RealisticPStarInitStep.init_tracers

   initial_state.InitialStateStep
   initial_state.InitialStateStep.setup
   initial_state.InitialStateStep.run

   viz.VizInitStep
   viz.VizInitStep.setup
   viz.VizInitStep.run
```

### seamount

```{eval-rst}
.. currentmodule:: polaris.tasks.ocean.seamount

.. autosummary::
   :toctree: generated/

   add_seamount_tasks

   default.Default

   forward.Forward
   forward.Forward.dynamic_model_config
   forward.Forward.compute_cell_count

   init.Init
   init.Init.setup
   init.Init.run

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

### Conservation utilities

```{eval-rst}
.. currentmodule:: polaris.ocean.conservation

.. autosummary::
   :toctree: generated/

   compute_total_mass
   compute_total_salt
   compute_total_energy
```

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
   OceanIOStep.process_inputs_and_outputs
   OceanIOStep.add_horiz_mesh_input_file
   OceanIOStep.add_vert_coord_input_file
   OceanIOStep.add_init_input_file
   OceanIOStep.get_horiz_mesh_filename
   OceanIOStep.get_vert_coord_filename
   OceanIOStep.get_init_filename
   OceanIOStep.open_vert_coord_dataset
   OceanIOStep.map_to_native_model_vars
   OceanIOStep.write_model_dataset
   OceanIOStep.map_from_native_model_vars
   OceanIOStep.open_model_dataset

   OceanModelStep
   OceanModelStep.setup
   OceanModelStep.check_properties
   OceanModelStep.constrain_resources
   OceanModelStep.compute_cell_count
   OceanModelStep.map_yaml_options
   OceanModelStep.map_yaml_configs

   OceanModelFilesMixin

   get_days_since_start
   get_time_interval_string
```

### Equations of state (EOS)

```{eval-rst}
.. currentmodule:: polaris.ocean.eos

.. autosummary::
   :toctree: generated/

   compute_density
   compute_specvol

   constant.compute_constant_density
   linear.compute_linear_density
   teos10.compute_specvol
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
   vertical.compute_zint_zmid_from_layer_thickness
   vertical.diagnostics.geom_thickness_from_ds
   vertical.diagnostics.pseudothickness_from_ds
   vertical.diagnostics.depth_from_thickness
   vertical.grid_1d.generate_1d_grid
   vertical.grid_1d.write_1d_grid
   vertical.partial_cells.alter_bottom_depth
   vertical.partial_cells.alter_ssh
   vertical.sigma.init_sigma_vertical_coord
   vertical.sigma.update_sigma_layer_thickness
   vertical.sigma.compute_sigma_layer_thickness
   vertical.update_layer_thickness
   vertical.zlevel.init_z_level_vertical_coord
   vertical.zlevel.update_z_level_layer_thickness
   vertical.zlevel.compute_min_max_level_cell
   vertical.zlevel.compute_z_level_layer_thickness
   vertical.zlevel.compute_z_level_resting_thickness
   vertical.zstar.init_z_star_vertical_coord
   vertical.zstar.update_z_star_layer_thickness
   vertical.ztilde.z_tilde_from_pressure
   vertical.ztilde.pressure_from_z_tilde
   vertical.ztilde.pressure_from_geom_thickness
   vertical.ztilde.pressure_and_spec_vol_from_state_at_geom_height
   vertical.ztilde.geom_height_from_pseudo_height
   vertical.pstar.init_pstar_vertical_coord
   vertical.pstar_init.PStarInitStep
   vertical.pstar_init.PStarInitStep.init_tracers
   vertical.pstar_init.PStarInitStep.run_pstar_init
```
