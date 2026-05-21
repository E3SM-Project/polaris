# mesh

```{eval-rst}
.. currentmodule:: polaris.tasks.mesh.add_tasks

.. autosummary::
   :toctree: generated/

   add_mesh_tasks
```

## Tasks

### Base Mesh Tasks

```{eval-rst}
.. currentmodule:: polaris.tasks.mesh.base

.. autosummary::
   :toctree: generated/

   add_base_mesh_tasks

   BaseMeshTask
```

### Unified Coastline Tasks

```{eval-rst}
.. currentmodule:: polaris.tasks.mesh.spherical.unified.coastline

.. autosummary::
   :toctree: generated/

   CONVENTIONS
   ComputeCoastlineStep
   ComputeCoastlineStep.setup
   ComputeCoastlineStep.run
   RemapCoastlineStep
   RemapCoastlineStep.setup
   RemapCoastlineStep.run
   build_coastline_datasets
   build_coastline_dataset
   get_unified_mesh_coastline_steps
   LatLonCoastlineTask
   add_coastline_tasks
   VizCoastlineStep
   VizCoastlineStep.setup
   VizCoastlineStep.run
```

### Unified River Tasks

```{eval-rst}
.. currentmodule:: polaris.tasks.mesh.spherical.unified.river

.. autosummary::
   :toctree: generated/

   SimplifyRiverNetworkStep
   SimplifyRiverNetworkStep.setup
   SimplifyRiverNetworkStep.run
   simplify_river_network_feature_collection
   RasterizeRiverLatLonStep
   RasterizeRiverLatLonStep.setup
   RasterizeRiverLatLonStep.run
   build_river_network_dataset
   ClipRiverNetworkStep
   ClipRiverNetworkStep.setup
   ClipRiverNetworkStep.run
   get_unified_mesh_river_steps
   VizRiverStep
   VizRiverStep.setup
   VizRiverStep.run
   UnifiedRiverNetworkTask
   add_river_tasks
```

### Unified Sizing-Field Tasks

```{eval-rst}
.. currentmodule:: polaris.tasks.mesh.spherical.unified.sizing_field

.. autosummary::
   :toctree: generated/

   BuildSizingFieldStep
   BuildSizingFieldStep.setup
   BuildSizingFieldStep.run
   sizing_field_dataset
   VizSizingFieldStep
   VizSizingFieldStep.setup
   VizSizingFieldStep.run
   SizingFieldTask
   add_sizing_field_tasks
   get_unified_mesh_sizing_field_steps
   get_sizing_field_config
```
