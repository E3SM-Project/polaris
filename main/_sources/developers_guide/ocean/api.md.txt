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

### sphere_transport

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.sphere_transport

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

   viz.VizMap
   viz.VizMap.runtime_setup

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
   init.cosine_bell

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   analysis.Analysis
   analysis.Analysis.exact_solution

   viz.VizMap
   viz.VizMap.run

   viz.Viz
   viz.Viz.run
```

### geostrophic

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.geostrophic

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

### Convergence Tests

```{eval-rst}
.. currentmodule:: polaris.ocean.convergence

.. autosummary::
   :toctree: generated/

   ConvergenceForward
   ConvergenceForward.compute_cell_count
   ConvergenceForward.dynamic_model_config

   ConvergenceAnalysis
   ConvergenceAnalysis.compute_error
   ConvergenceAnalysis.convergence_parameters
   ConvergenceAnalysis.exact_solution
   ConvergenceAnalysis.get_output_field
   ConvergenceAnalysis.plot_convergence
   ConvergenceAnalysis.run
   ConvergenceAnalysis.setup
```
### Spherical Convergence Tests

```{eval-rst}
.. currentmodule:: polaris.ocean.convergence.spherical

.. autosummary::
   :toctree: generated/

   SphericalConvergenceForward
   SphericalConvergenceForward.compute_cell_count
```

### Ocean Model

```{eval-rst}
.. currentmodule:: polaris.ocean.model

.. autosummary::
   :toctree: generated/

   OceanModelStep
   OceanModelStep.setup
   OceanModelStep.constrain_resources
   OceanModelStep.compute_cell_count
   OceanModelStep.map_yaml_to_namelist
   
   get_time_interval_string
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
