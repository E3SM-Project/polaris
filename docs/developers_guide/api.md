(dev-api)=

# API reference

This page provides an auto-generated summary of the polaris API. For more
details and examples, refer to the relevant sections in the main part of the
documentation.

## Components

```{toctree}
:maxdepth: 1
:titlesonly: true

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
```

#### Task

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   Task
   Task.configure
   Task.add_step
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
   ModelStep.map_yaml_to_namelist
   ModelStep.add_namelist_file
   ModelStep.add_streams_file
   ModelStep.dynamic_model_config
   ModelStep.runtime_setup
   ModelStep.process_inputs_and_outputs
   ModelStep.update_namelist_pio
   ModelStep.partition
```

### components

```{eval-rst}
.. currentmodule:: polaris.components

.. autosummary::
   :toctree: generated/

   get_components
```


### config

```{eval-rst}
.. currentmodule:: polaris.config

.. autosummary::
   :toctree: generated/

   PolarisConfigParser
```

### io

```{eval-rst}
.. currentmodule:: polaris.io

.. autosummary::
   :toctree: generated/

   download
   symlink
   imp_res
```

### job
```{eval-rst}
.. currentmodule:: polaris.job

.. autosummary::
   :toctree: generated/

   write_job_script
   get_slurm_options
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

### model_step

```{eval-rst}
.. currentmodule:: polaris.model_step

.. autosummary::
   :toctree: generated/
   
   make_graph_file
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
   MappingFileStep.src_from_mpas
   MappingFileStep.dst_from_mpas
   MappingFileStep.src_from_lon_lat
   MappingFileStep.dst_from_lon_lat
   MappingFileStep.dst_global_lon_lat
   MappingFileStep.src_from_proj
   MappingFileStep.dst_from_proj
   MappingFileStep.dst_from_points
   MappingFileStep.get_remapper
   MappingFileStep.runtime_setup
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

   plot_horiz_field
   globe.plot_global
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
