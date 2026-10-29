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

### staging E3SM input files

```{eval-rst}
.. currentmodule:: polaris.e3sm.init

.. autosummary::
   :toctree: generated/

   assemble.AssembleStep
   assemble.AssembleStep.run
   assemble.AssembleStep.stage
   assemble.AssembleStep.stage_partitions
   assemble.AssembleStep.step_dir
   assemble.SYNC_SCRIPT

   graph_partition.GraphPartitionStep
   graph_partition.GraphPartitionStep.setup
   graph_partition.GraphPartitionStep.constrain_resources
   graph_partition.GraphPartitionStep.run
   graph_partition.GraphPartitionStep.get_core_counts

   inputdata.ASSEMBLED_FILES
   inputdata.get_nonempty_option
   inputdata.get_creation_date
   inputdata.set_creation_date
   inputdata.ocean_dir
   inputdata.seaice_dir
   inputdata.ocean_initial_condition_path
   inputdata.ocean_graph_path
   inputdata.ocean_partition_path
   inputdata.seaice_initial_condition_path
   inputdata.seaice_partition_path

   partitions.get_core_list
   partitions.partitions_to_build
   partitions.read_graph_cell_count
   partitions.build_partitions
   partitions.RegionGraph
   partitions.get_region_graph
   partitions.write_graph
```

### topo

#### combine

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.combine

.. autosummary::
   :toctree: generated/

   PrepareCombineStep
   PrepareCombineStep.setup
   PrepareCombineStep.run
   CombineWeightsStep
   CombineWeightsStep.setup
   CombineWeightsStep.constrain_resources
   CombineStep
   CombineStep.get_subdir
   CombineStep.get_name
   CombineStep.setup
   CombineStep.run
   get_cubed_sphere_topo_steps
   get_lat_lon_topo_steps
   get_combine_topo_symlinks
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

   PrepareRemapTopoStep
   PrepareRemapTopoStep.setup
   PrepareRemapTopoStep.define_smoothing
   PrepareRemapTopoStep.run

   RemapTopoWeightsStep
   RemapTopoWeightsStep.setup
   RemapTopoWeightsStep.constrain_resources
   RemapTopoWeightsStep.runtime_setup

   RemapTopoStep
   RemapTopoStep.setup
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
   consistency.check_sea_ice_removed_regions
   dc_edge_diagnostics.check_ocean_dc_edge
   land_locked.find_dead_end_cells
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

   ComponentInputsAssembleStep
   ComponentInputsAssembleStep.run

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
   seaice_partition_map.SeaicePartitionMapStep.runtime_setup

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
   names.ocean_grid_name
   names.base_mesh_path
   names.scrip_path
   names.ocean_scrip_path
   names.culled_mesh_path
   names.ocean_moc_masks_path

   maps.map_base_to_culled
   maps.base_to_culled_maps

   models.check_ocean_model
   models.check_seaice_model
```
