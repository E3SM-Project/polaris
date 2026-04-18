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
```
