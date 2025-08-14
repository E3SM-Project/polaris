(dev-e3sm-init-topo-cull-tasks)=

# Culling MPAS Base Meshes to Land/River or Ocean/Sea Ice Regions

The `e3sm/init` component includes a workflow for culling MPAS base meshes to
produce meshes for specific regions, such as land/river or ocean/sea-ice
domains. This process uses remapped topography and mask information to remove
cells not belonging to the desired region, ensuring that the resulting meshes
are contiguous and scientifically meaningful for E3SM simulations.

## Culling Workflow Overview

The culling workflow is composed of several modular steps, each responsible for
a specific part of the process:

- **Mask Generation**: The {py:class}`polaris.tasks.e3sm.init.topo.cull.CullMaskStep`
  creates masks for land, ocean (with and without ice-shelf cavities), and
  Antarctic land ice. This step uses critical transects, flood-filling, and
  land-locked cell detection to ensure the masks are physically consistent
  and contiguous.
- **Mesh Culling**: The {py:class}`polaris.tasks.e3sm.init.topo.cull.CullMeshStep`
  uses the generated masks to cull the MPAS base mesh, producing separate
  meshes for land, ocean/sea-ice, and ocean without ice-shelf cavities. It also
  generates mapping files between the culled and base meshes, and graph files
  for the ocean meshes.
- **Task Orchestration**: The {py:class}`polaris.tasks.e3sm.init.topo.cull.CullTopoTask`
  orchestrates these steps for each supported MPAS base mesh.

## Step Dependencies

The typical dependency chain is:

1. `RemapTopoStep` (remaps topography to MPAS mesh, unsmoothed)
2. `CullMaskStep` (creates masks for culling)
3. `CullMeshStep` (culls the mesh to each region)

## Configuration Options

The culling steps are configured through the `[cull_mesh]` section in the configuration file. Key options include:

- `cpus_per_task` and `min_cpus_per_task`: Number of cores to use for culling.
- `include_critical_transects`: Whether to use critical land and ocean
  transects from geometric_features to enforce connectivity.
- `sea_ice_latitude_threshold`: Latitude above which transects are widened to prevent land-locked sea-ice cells.
- `land_locked_cell_iterations`: Number of passes to check for land-locked
  ocean cells.
- `land_ice_max_latitude`: Latitude, south of which critical land transects are
  considered to belong to land ice.
- `land_ice_min_fraction`: Minimum land-ice fraction for flood-filling the
  land-ice mask.

See `cull.cfg` for the full set of options.

## Workflow

1. **Mask Generation**: The `CullMaskStep` creates masks for ocean, ocean
   without cavities, land, and Antarctic land ice. It uses critical transects,
   flood-filling from seed points, and land-locked cell detection to ensure the
   masks are contiguous and scientifically meaningful.
2. **Mesh Culling**: The `CullMeshStep` uses the generated masks to cull the
   MPAS base mesh, producing separate meshes for land, ocean/sea-ice, and ocean
   without ice-shelf cavities. It also generates mapping files and graph files
   as needed.
3. **Output**: The final culled meshes and masks are saved as NetCDF files for
   each region.

## Example Usage

Below is an example of how the culling steps can be added to a Polaris task:

```python
from polaris.tasks.e3sm.init.topo.cull import get_default_cull_topo_steps

steps, config = get_default_cull_topo_steps(
    component=component,
    base_mesh_step=base_mesh_step,
    unsmoothed_topo_step=unsmoothed_topo_step,
    include_viz=False,
)
for step in steps:
    component.add_step(step)
```

## Example: Culled Ocean Mesh

Below is an example of a 30-km ocean mesh from which land has been culled:

```{image} images/icos30_culled_ocean.png
:align: center
:width: 250 px
:alt: Culled ocean mesh
```

The culled mesh is contiguous and ocean flow has been ensured through the use
of ocean critical transects (e.g. narrow straits) or blocked through the use of
land critical transects (e.g. narrow peninsulas or isthmuses).

## Customizing Mask Generation

Developers may wish to customize how masks are generated. To implement a custom
approach for generating masks, create a subclass of
{py:class}`polaris.tasks.e3sm.init.topo.cull.CullMaskStep` and override methods
such as `define_critical_land_transects`, `define_critical_ocean_transects`,
`refine_ocean_cull_mask`, or `refine_land_cull_mask`. These methods receive the
geometric features, base mesh, topography, and current masks, and should return
updated masks as `xarray.DataArray` objects.

**Example:**

```python
from polaris.tasks.e3sm.init.topo.cull import CullMaskStep

class MyCustomCullMaskStep(CullMaskStep):
    def refine_ocean_cull_mask(self, ds_base_mesh, ds_topo, cull_mask):
        # Custom logic for refining the ocean cull mask
        # e.g., add or remove cells based on scientific criteria
        return cull_mask
```

You can then use your custom step in place of the default `CullMaskStep` when
constructing your workflow.

### Integration

To use your custom step, simply instantiate it in your workflow or override the
step creation logic in your task or workflow setup.

For more details, refer to the docstrings and source code of
{py:class}`polaris.tasks.e3sm.init.topo.cull.CullMaskStep`.
