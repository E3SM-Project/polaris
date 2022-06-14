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

   setup_cases
   setup_case
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
.. currentmodule:: polaris.run.serial

.. autosummary::
   :toctree: generated/

   run_tests
   run_single_step

```

#### cache

```{eval-rst}
.. currentmodule:: polaris.cache

.. autosummary::
   :toctree: generated/

   update_cache

```

### Base Classes

#### component

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   Component
   Component.add_test_group
```

#### testgroup

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   TestGroup
   TestGroup.add_test_case
```

### testcase

```{eval-rst}
.. currentmodule:: polaris

.. autosummary::
   :toctree: generated/

   TestCase
   TestCase.configure
   TestCase.validate
   TestCase.add_step
```

### step

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
   Step.add_namelist_file
   Step.add_namelist_options
   Step.update_namelist_at_runtime
   Step.update_namelist_pio
   Step.add_streams_file
   Step.update_streams_at_runtime
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
   package_path
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

### model

```{eval-rst}
.. currentmodule:: polaris.model

.. autosummary::
   :toctree: generated/
   
   ModelStep
   ModelStep.setup
   ModelStep.set_model_resources
   ModelStep.runtime_setup
   ModelStep.process_inputs_and_outputs

   run_model
   partition
   make_graph_file
```

### components

```{eval-rst}
.. currentmodule:: polaris.components

.. autosummary::
   :toctree: generated/

   get_components
```

### parallel

```{eval-rst}
.. currentmodule:: polaris.parallel

.. autosummary::
   :toctree: generated/

   get_available_cores_and_nodes
   check_parallel_system
   set_cores_per_node
   run_command
```

### provenance

```{eval-rst}
.. currentmodule:: polaris.provenance

.. autosummary::
   :toctree: generated/

   write
```


###validate

```{eval-rst}
.. currentmodule:: polaris.validate

.. autosummary::
   :toctree: generated/

   compare_variables
   compare_timers
```
