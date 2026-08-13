# e3sm/init

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init

.. autosummary::
   :toctree: generated/

   add_tasks.add_e3sm_init_tasks
```

## Tasks

### topo resolution constants

```{eval-rst}
.. currentmodule:: polaris.e3sm.init.topo.resolutions

.. autosummary::
   :toctree: generated/

   STANDARD_CUBED_SPHERE_RESOLUTION
   LOW_RES_CUBED_SPHERE_RESOLUTION
   LOW_RES_BASE_MESH_CELL_WIDTH
   LAT_LON_RESOLUTION_DECIMALS
```

### topo shared utilities

```{eval-rst}
.. currentmodule:: polaris.e3sm.init.topo

.. autosummary::
   :toctree: generated/

   CUBED_SPHERE_RESOLUTIONS
   LAT_LON_RESOLUTIONS
   format_lat_lon_resolution_name
   get_cubed_sphere_resolution
   uses_low_res_cubed_sphere
```

### topo

#### combine

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.combine

.. autosummary::
   :toctree: generated/

   CombineStep
   CombineStep.get_subdir
   CombineStep.get_name
   CombineStep.setup
   CombineStep.constrain_resources
   CombineStep.run
   get_cubed_sphere_topo_steps
   get_lat_lon_topo_steps
   CubedSphereCombineTask
   LatLonCombineTask
   VizCombinedStep
   VizCombinedStep.setup
   VizCombinedStep.run
```

#### remap

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.remap

.. autosummary::
   :toctree: generated/

   MaskTopoStep
   MaskTopoStep.setup
   MaskTopoStep.constrain_resources
   MaskTopoStep.define_masks
   MaskTopoStep.run

   RemapTopoStep
   RemapTopoStep.setup
   RemapTopoStep.constrain_resources
   RemapTopoStep.define_smoothing
   RemapTopoStep.run

   RemapTopoTask

   VizRemappedTopoStep
   VizRemappedTopoStep.run

   get_remap_topo_steps
   add_remap_topo_tasks
```


#### cull

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.cull

.. autosummary::
   :toctree: generated/

   CullMaskStep
   CullMaskStep.setup
   CullMaskStep.constrain_resources
   CullMaskStep.define_critical_land_transects
   CullMaskStep.define_critical_ocean_transects
   CullMaskStep.refine_ocean_cull_mask
   CullMaskStep.refine_land_cull_mask
   CullMaskStep.run

   CullMeshStep
   CullMeshStep.setup
   CullMeshStep.constrain_resources
   CullMeshStep.run

   CullTopoTask

   get_cull_topo_steps
   add_cull_topo_tasks

   consistency.check_cull_mask_consistency
   consistency.check_land_locked_criteria
   consistency.check_critical_passages
   dc_edge_diagnostics.check_ocean_dc_edge
   land_locked.remove_land_locked_cells
   land_locked.remove_ocean_land_locked_cells
```


### component_inputs

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.component_inputs

.. autosummary::
   :toctree: generated/

   BaseMeshStep
   BaseMeshStep.output_filename
   BaseMeshStep.setup
   BaseMeshStep.run

   ScripStep
   ScripStep.scrip_filename
   ScripStep.setup
   ScripStep.run

   AssembleStep
   AssembleStep.run

   ComponentInputsTask
   ComponentInputsTask.configure

   get_component_inputs_steps
   add_component_inputs_tasks
```

#### ocean products

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.component_inputs

.. autosummary::
   :toctree: generated/

   ocean_mesh.OceanMeshStep
   ocean_mesh.OceanMeshStep.setup
   ocean_mesh.OceanMeshStep.run
   ocean_mesh.VERT_COORD_VARS

   ocean_initial_condition.OceanInitialConditionStep
   ocean_initial_condition.OceanInitialConditionStep.setup
   ocean_initial_condition.OceanInitialConditionStep.run

   ocean_graph_partition.OceanGraphPartitionStep
   ocean_graph_partition.OceanGraphPartitionStep.setup
   ocean_graph_partition.OceanGraphPartitionStep.run

   moc_masks.MocMasksStep
   moc_masks.MocMasksStep.setup
   moc_masks.MocMasksStep.run
   moc_masks.MESH_FILENAME
```

#### sea-ice products

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.component_inputs

.. autosummary::
   :toctree: generated/

   seaice_mesh.SeaiceMeshStep
   seaice_mesh.SeaiceMeshStep.setup
   seaice_mesh.SeaiceMeshStep.run

   seaice_initial_condition.SeaiceInitialConditionStep
   seaice_initial_condition.SeaiceInitialConditionStep.setup
   seaice_initial_condition.SeaiceInitialConditionStep.run

   seaice_partition_map.SeaicePartitionMapStep
   seaice_partition_map.SeaicePartitionMapStep.setup
   seaice_partition_map.SeaicePartitionMapStep.run

   seaice_graph_partition.SeaiceGraphPartitionStep
   seaice_graph_partition.SeaiceGraphPartitionStep.setup
   seaice_graph_partition.SeaiceGraphPartitionStep.run
```

#### leaf modules

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.component_inputs

.. autosummary::
   :toctree: generated/

   names.get_mesh_short_name
   names.get_creation_date
   names.set_creation_date
   names.base_mesh_path
   names.scrip_path
   names.ocean_scrip_path
   names.culled_mesh_path
   names.ocean_initial_condition_path
   names.ocean_moc_masks_path
   names.ocean_partition_path
   names.seaice_mesh_path
   names.seaice_initial_condition_path
   names.seaice_partition_path

   maps.map_base_to_culled
   maps.base_to_culled_maps

   partitions.get_core_list
   partitions.partitions_to_build
   partitions.read_graph_cell_count

   models.check_ocean_model
   models.check_seaice_model
```
