(dev-api)=

# API reference

This page provides an auto-generated summary of the polaris API. For more
details and examples, refer to the relevant sections in the main part of the
documentation.

## Components

```{toctree}
:maxdepth: 1
:titlesonly: true

e3sm/init/api
mesh/api
ocean/api
seaice/api
```

## polaris framework

### Command-line interface

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   __main__.main

```

#### list

```{eval-rst}
.. currentmodule:: polaris.list

.. autosummary::
   :toctree: generated/

   list_cases
   list_machines
   list_suites
```

#### setup

```{eval-rst}
.. currentmodule:: polaris.setup

.. autosummary::
   :toctree: generated/

   setup_tasks
   setup_task
```

#### suite

```{eval-rst}
.. currentmodule:: polaris.suite

.. autosummary::
   :toctree: generated/

   setup_suite
```

#### run

```{eval-rst}
.. currentmodule:: polaris.run

.. autosummary::
   :toctree: generated/

   unpickle_suite
   setup_config
   load_dependencies
   complete_step_run
   serial.run_tasks
   serial.run_single_step

```

#### cache

```{eval-rst}
.. currentmodule:: polaris.cache

.. autosummary::
   :toctree: generated/

   update_cache

```

#### mpas_to_yaml

```{eval-rst}
.. currentmodule:: polaris.yaml

.. autosummary::
   :toctree: generated/

   main_mpas_to_yaml

```


### Base Classes

#### Component

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   Component
   Component.add_task
   Component.add_step
   Component.remove_step
   Component.add_config
   Component.get_or_create_shared_step
```

#### Task

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   Task
   Task.configure
   Task.add_step
   Task.remove_step
   Task.set_shared_config
```

#### Step

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   Step
   Step.set_resources
   Step.constrain_resources
   Step.setup
   Step.runtime_setup
   Step.run
   Step.add_input_file
   Step.add_output_file
   Step.add_dependency
   Step.validate_baselines
   Step.set_shared_config
```


#### ModelStep

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   ModelStep
   ModelStep.setup
   ModelStep.set_model_resources
   ModelStep.add_model_config_options
   ModelStep.add_yaml_file
   ModelStep.map_yaml_options
   ModelStep.map_yaml_configs
   ModelStep.map_yaml_to_namelist
   ModelStep.add_namelist_file
   ModelStep.add_streams_file
   ModelStep.dynamic_model_config
   ModelStep.runtime_setup
   ModelStep.process_inputs_and_outputs
   ModelStep.update_namelist_pio
   ModelStep.partition
```

### config

```{eval-rst}
.. currentmodule:: polaris.config

.. autosummary::
   :toctree: generated/

   PolarisConfigParser
   PolarisConfigParser.setup
```

### io

```{eval-rst}
.. currentmodule:: polaris.io

.. autosummary::
   :toctree: generated/

   download
   symlink
   update_permissions
```

### job
```{eval-rst}
.. currentmodule:: polaris.job

.. autosummary::
   :toctree: generated/

   write_job_script
   get_slurm_options
   get_pbs_options
```

### logging

```{eval-rst}
.. currentmodule:: polaris.logging

.. autosummary::
   :toctree: generated/

   log_method_call
```

### mesh

```{eval-rst}
.. currentmodule:: polaris.mesh

.. autosummary::
   :toctree: generated/

   planar.compute_planar_hex_nx_ny

   spherical.SphericalBaseStep
   spherical.SphericalBaseStep.setup
   spherical.SphericalBaseStep.run
   spherical.SphericalBaseStep.save_and_plot_cell_width

   QuasiUniformSphericalMeshStep
   QuasiUniformSphericalMeshStep.setup
   QuasiUniformSphericalMeshStep.run
   QuasiUniformSphericalMeshStep.build_cell_width_lat_lon
   QuasiUniformSphericalMeshStep.make_jigsaw_mesh

   IcosahedralMeshStep
   IcosahedralMeshStep.setup
   IcosahedralMeshStep.run
   IcosahedralMeshStep.make_jigsaw_mesh
   IcosahedralMeshStep.build_subdivisions_cell_width_lat_lon
   IcosahedralMeshStep.get_subdivisions
   IcosahedralMeshStep.get_cell_width
```

### Uniform Spherical Base Mesh Step

```{eval-rst}
.. currentmodule:: polaris.mesh.base

.. autosummary::
   :toctree: generated/

   add_uniform_spherical_base_mesh_step
   get_base_mesh_steps
```

### model_step

```{eval-rst}
.. currentmodule:: polaris.model_step

.. autosummary::
   :toctree: generated/

   make_graph_file
```

### mpas

```{eval-rst}
.. currentmodule:: polaris.mpas

.. autosummary::
   :toctree: generated/

   area_for_field
   cell_mask_to_edge_mask
   time_index_from_xtime
```

### namelist

```{eval-rst}
.. currentmodule:: polaris.namelist

.. autosummary::
   :toctree: generated/

   parse_replacements
   ingest
   replace
   write
```

### parallel

```{eval-rst}
.. currentmodule:: polaris.parallel

.. autosummary::
   :toctree: generated/

   get_available_parallel_resources
   set_cores_per_node
   run_command
   get_parallel_command

   system.ParallelSystem
   single_node.SingleNodeSystem
   login.LoginSystem
   slurm.SlurmSystem
   pbs.PbsSystem
```

### provenance

```{eval-rst}
.. currentmodule:: polaris.provenance

.. autosummary::
   :toctree: generated/

   write
```


### remap

```{eval-rst}
.. currentmodule:: polaris.remap

.. autosummary::
   :toctree: generated/

   MappingFileStep
   MappingFileStep.run
```

### resolution

```{eval-rst}
.. currentmodule:: polaris.resolution

.. autosummary::
   :toctree: generated/

   resolution_to_string
```

### streams

```{eval-rst}
.. currentmodule:: polaris.streams

.. autosummary::
   :toctree: generated/

   read
   write
   update_defaults
   update_tree
```

### validate

```{eval-rst}
.. currentmodule:: polaris.validate

.. autosummary::
   :toctree: generated/

   compare_variables
```

### viz

```{eval-rst}
.. currentmodule:: polaris.viz

.. autosummary::
   :toctree: generated/

   use_mplstyle
   plot_horiz_field
   plot_global_lat_lon_field
   plot_global_mpas_field
```

### yaml

```{eval-rst}
.. currentmodule:: polaris.yaml

.. autosummary::
   :toctree: generated/

   PolarisYaml
   PolarisYaml.read
   PolarisYaml.update
   PolarisYaml.write

   mpas_namelist_and_streams_to_yaml
   yaml_to_mpas_streams

```
