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
   PrepareCoastlineStep
   PrepareCoastlineStep.setup
   PrepareCoastlineStep.run
   build_coastline_datasets
   build_coastline_dataset
   get_lat_lon_coastline_steps
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

   PrepareRiverSourceStep
   PrepareRiverSourceStep.setup
   PrepareRiverSourceStep.run
   simplify_river_network_feature_collection
   get_mesh_river_source_steps
   PrepareRiverNetworkTask
   PrepareRiverLatLonStep
   PrepareRiverLatLonStep.setup
   PrepareRiverLatLonStep.run
   build_river_network_dataset
   get_mesh_river_lat_lon_steps
   LatLonRiverNetworkTask
   PrepareRiverForBaseMeshStep
   PrepareRiverForBaseMeshStep.setup
   PrepareRiverForBaseMeshStep.run
   get_mesh_river_base_mesh_steps
   VizRiverStep
   VizRiverStep.setup
   VizRiverStep.run
   add_river_tasks
```
