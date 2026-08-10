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
  and contiguous, and it checks the resulting masks against the invariants
  described in [Mask Invariants](#mask-invariants) below.
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
- `min_dc_edge_ratio` and `max_dc_edge_ratio`: The allowed range of `dcEdge`
  relative to the local ocean background cell width in the culled
  ocean/sea-ice domain (unified meshes only).

See `cull.cfg` for the full set of options.

## dcEdge Diagnostic for Unified Meshes

For unified meshes, land/river regions are typically meshed at finer
resolution than the CFL-limited ocean/sea-ice regions, so resolution
"leaking" across the coastline into the culled ocean mesh can destabilize
forward runs. After all masks are written, `CullMaskStep` calls
{py:func}`polaris.tasks.e3sm.init.topo.cull.dc_edge_diagnostics.check_ocean_dc_edge`,
which compares `dcEdge` on base-mesh edges interior to the ocean cull mask
against the ocean background cell width sampled from the mesh's sizing
field, writes `ocean_dc_edge_diagnostics.nc`, and raises an error listing
the worst violation clusters if any ratio falls outside
`[min_dc_edge_ratio, max_dc_edge_ratio]`. For simple base meshes there is
no sizing field and the check is skipped. The motivation, mechanisms and
threshold justification are documented in the `unified_mesh_cull_leak`
design doc (see {ref}`design-docs`).

The Antarctic land-ice ownership mask also includes southern cells that have
already been removed from the open-ocean cull mask, so the cull workflow
remains consistent with the remapped topography masks.

(mask-invariants)=
## Mask Invariants

The three cull masks and the land-ice mask together describe how the globe is
divided between the components, and `CullMaskStep` guarantees the following,
for every value of `antarctic_boundary_convention`:

1. The ocean without ice-shelf cavities is a subset of the ocean. Never the
   reverse.
2. The land is exactly the complement of the ocean without cavities, so every
   cell on the globe is owned by exactly one of the two.
3. The land-ice mask is zero at every cell the ocean without cavities retains.
   Equivalently, the ice-shelf cavity cells of the ocean mesh are exactly the
   cells the ocean retains and the ocean without cavities does not.
4. Critical land blockages and critical ocean passages are applied identically
   to the ocean and to the ocean without cavities.
5. Under `calving_front` the ocean and the ocean without cavities are
   identical, so the ocean and the land partition the base mesh.

Invariant 4 is why `CullMaskStep._apply_critical_transects` is shared between
`refine_ocean_cull_mask` and the ocean-without-cavities mask: removing the
land ice from the ocean mask would otherwise undo a critical passage that had
kept an ice-covered cell in the ocean. In the without-cavities pass the
passage override is restricted to cells the ocean itself retains, which is
what makes invariant 1 hold by construction.

Invariant 3 is the decision that critical transects outrank the ice masks. A
cell that a passage forces into the ocean is treated as open water rather than
as an ice-shelf cavity. That is what makes `calving_front` genuinely
cavity-free, and under `grounding_line` and `bedrock_zero` it keeps the
sea-ice mesh from owning a cell that the ocean mesh models as a cavity.

The land-locked-cell ("confined inlet") check is deliberately asymmetric: it
runs on the with-cavities domain for the ocean and on the without-cavities
domain for the ocean without cavities, so a confined inlet is judged against
the connectivity each mesh actually has.

After all masks are written, `CullMaskStep` calls
{py:func}`polaris.tasks.e3sm.init.topo.cull.consistency.check_cull_mask_consistency`,
which raises a `ValueError` listing the offending cell indices if any of
invariants 1, 2, 3 or 5 is violated. These are hard failures because a
violation means the culled meshes handed downstream are wrong in a way that is
hard to notice later.

## Workflow

1. **Mask Generation**: The `CullMaskStep` creates masks for ocean, ocean
   without cavities, land, and Antarctic land ice. It uses critical transects,
   flood-filling from seed points, and land-locked cell detection to ensure the
   masks are contiguous and scientifically meaningful. The ocean and the ocean
   without cavities each get the same critical land blockages and critical
   ocean passages; the land is then the complement of the ocean without
   cavities.
2. **Mesh Culling**: The `CullMeshStep` uses the generated masks to cull the
   MPAS base mesh, producing separate meshes for land, ocean/sea-ice, and ocean
   without ice-shelf cavities. It also generates mapping files and graph files
   as needed.
3. **Output**: The final culled meshes and masks are saved as NetCDF files for
   each region.

## Supported Mesh Types

`add_cull_topo_tasks` registers tasks for all supported base meshes,
including both simple (quasi-uniform and icosahedral) base meshes and
named unified meshes (see {ref}`users-mesh-unified-base-mesh`). The set
of mesh names is the union of `get_base_mesh_step_names()` and
`UNIFIED_MESH_NAMES`.

## Example Usage

To get the shared cull steps for a specific mesh:

```python
from polaris.tasks.e3sm.init.topo.cull import get_cull_topo_steps

steps, config = get_cull_topo_steps(
    mesh_name='u.oi30.lr10',
    include_viz=False,
)
```

To add the full culling workflow as a task for each supported mesh:

```python
from polaris.tasks.e3sm.init.topo.cull import add_cull_topo_tasks

add_cull_topo_tasks(component)
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

Note that `refine_ocean_cull_mask` alters only the ocean domain directly. Its
result still reaches the ocean without ice-shelf cavities, because that mask
starts from the ocean cull mask, but the critical transects, land-locked-cell
check and flood fill are re-run there independently.

`refine_land_cull_mask` receives the complement of the ocean without cavities
and returns it unaltered in the base class, so overriding it means departing
from invariant 2 above. A subclass that does so must also override
`CullMaskStep._check_mask_consistency`, which would otherwise reject the
resulting masks.

You can then use your custom step in place of the default `CullMaskStep` when
constructing your workflow.

### Integration

To use your custom step, simply instantiate it in your workflow or override the
step creation logic in your task or workflow setup.

For more details, refer to the docstrings and source code of
{py:class}`polaris.tasks.e3sm.init.topo.cull.CullMaskStep`.
