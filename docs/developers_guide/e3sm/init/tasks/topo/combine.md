(dev-e3sm-init-topo-combine-tasks)=

# Combine Steps and Tasks

```{image} images/bathymetry_500.png
:align: center
:width: 500 px
```

Global datasets of base elevation (land surface elevation and ocean bathymetry)
do not typically include the latest datasets around Antarctica needed for
ice-sheet and ice-shelf modeling. For this reason, we typically combine a
global topography dataset north of the Southern Ocean with one for Antarctica.

The {py:class}`polaris.tasks.e3sm.init.topo.combine.CombineStep` step is a key
component of the topography framework. It is responsible for combining global
and Antarctic topography datasets into a single dataset suitable for use in
E3SM simulations. The step supports blending datasets across specified latitude
ranges and remapping them to a target grid.

The
{py:class}`polaris.tasks.e3sm.init.topo.combine.CubedSphereCombineTask`
and
{py:class}`polaris.tasks.e3sm.init.topo.combine.LatLonCombineTask`
wrap the `CombineStep` into tasks that can be used to generate and cache
combined topography datasets for reuse in other contexts.

The {py:class}`polaris.tasks.e3sm.init.topo.combine.VizCombinedStep` step is
an optional visualization step that can be added to the workflow to create
plots of the combined topography dataset. This step is particularly useful for
debugging or analyzing the combined dataset.

## Target Grids and Resolutions

The combine framework is now organized explicitly around the target grid and
resolution rather than around a special “low-resolution” mode. Current tasks
include:

1. Cubed-sphere topography on `ne3000`
2. Cubed-sphere topography on `ne120`
3. Latitude-longitude topography on `1.0000_degree`
4. Latitude-longitude topography on `0.2500_degree`
5. Latitude-longitude topography on `0.0625_degree`

These resolutions are intended for different downstream uses:

- `ne3000` is the standard high-resolution cubed-sphere product. At roughly
   1 km resolution, it is suitable for remapping topography to standard and
   high-resolution MPAS meshes, approximately 60 km and finer, for scientific
   applications.
- `ne120` is a lower-cost cubed-sphere product at roughly 25 km resolution.
   It is useful for remapping to coarse meshes such as Icos240 and for
   regression testing or other non-scientific workflows where the full
   high-resolution product is not needed.
- `1.0000_degree` is intended for quick, non-scientific testing when a very
   coarse latitude-longitude product is sufficient.
- `0.2500_degree` aligns with the WOA23 (World Ocean Atlas 2023) dataset and
   can also be used when defining mesh resolution at moderate scales, roughly
   down to 30 km.
- `0.0625_degree` is intended for defining mesh resolution for most
   scientific runs and will be used by the E3SM v4 unified MPAS mesh across
   land, river, ocean, and sea-ice.

A series of standalone tasks are available to create each topography dataset
on its own:

- `e3sm/init/topo/combine_bedmap3_gebco2023/cubed_sphere/ne3000/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/cubed_sphere/ne120/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/1.0000_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.2500_degree/task`
- `e3sm/init/topo/combine_bedmap3_gebco2023/lat_lon/0.0625_degree/task`

Downstream workflows such as topography remapping to the MPAS mesh,
extrapolation of the WOA23 dataset and defining mesh resolution for unified
E3SM v4 meshes will use shared `topo/combine` steps referenced by their
grid and resolution.

## Key Features

- **Dataset Support**: Supports multiple datasets, including `bedmap3`,
  `bedmachinev3`, and `gebco2023`.
- **Grid Types**: Handles both lat-lon and cubed-sphere target grids.
- **Blending**: Blends global and Antarctic datasets across a configurable
  latitude range.
- **Remapping**: Uses tools like `mbtempest`, `ESMF_RegridWeightGen` and
  `ncremap` for remapping datasets to the target grid.
- **Output**: Produces combined topography datasets with consistent variables
  and attributes.
- **Visualization**: Generates rasterized images of various fields (e.g.,
  base elevation, ice draft) using the `datashader` library.

## Configuration Options

The `CombineStep` step is configured through the `[combine_topo]` section in
the configuration file. Key options include:

- `resolution_latlon`: Target resolution for lat-lon grids (in degrees).
- `resolution_cubedsphere`: Target resolution for cubed-sphere grids (e.g.,
  `3000` for NExxx grids).
- `latmin` and `latmax`: Latitude range for blending datasets.
- `ntasks` and `min_tasks`: Number of MPI tasks for remapping.
- `method`: Remapping method (e.g., `bilinear`).
- `lat_tiles` and `lon_tiles`: Number of tiles to split the global dataset for parallel remapping.
- `renorm_thresh`: Threshold for renormalizing Antarctic variables during blending.

## Workflow

1. **Setup**: The step downloads required datasets and sets up input/output
   files.
2. **Modification**: Antarctic and global datasets are modified to include
   necessary variables and attributes.
3. **Remapping**: Datasets are remapped to the target grid using SCRIP files
   and weight generation.
4. **Blending**: The datasets are blended across the specified latitude range.
5. **Output**: The combined dataset is saved in NetCDF format.
6. **Optional Field Plotting**: Each field in the dataset is rasterized and
   saved as an image with a colorbar.

## Example Usage

Below is an example of how the `CombineStep` can be added to a Polaris
task:

```python
from polaris.tasks.e3sm.init.topo.combine import CombineStep

component = task.component
subdir = CombineStep.get_subdir()
if subdir in component.steps:
    step = component.steps[subdir]
else:
    step = CombineStep(component=component, subdir=subdir)
    component.add_step(step)
task.add_step(step)
```

To create a cubed-sphere combine task for caching combined datasets:

```python
from polaris.tasks.e3sm.init.topo.combine import CubedSphereCombineTask

combine_task = CubedSphereCombineTask(component=my_component, resolution=3000)
my_component.add_task(combine_task)
```

To create a latitude-longitude combine task:

```python
from polaris.tasks.e3sm.init.topo.combine import LatLonCombineTask

combine_task = LatLonCombineTask(component=my_component, resolution=0.25)
my_component.add_task(combine_task)
```

Below is an example of how the `VizCombinedStep` can be added to a Polaris task:

```python
from polaris.tasks.e3sm.init.topo.combine import VizCombinedStep

viz_step = VizCombinedStep(component=my_component, combine_step=combine_step)
my_component.add_step(viz_step)
```

Since there is a single shared step for each pair of Antarctic and global
datasets, the step should be added only once to the component and the existing
step (identifiable via its `subdir`) should be used subsequently.

The `VizCombinedStep` is typically added only when visualization is explicitly required, as it is not part of the default workflow.

For more details, refer to the source code of the
{py:class}`polaris.tasks.e3sm.init.topo.combine.CombineStep` and
{py:class}`polaris.tasks.e3sm.init.topo.combine.CubedSphereCombineTask` and
{py:class}`polaris.tasks.e3sm.init.topo.combine.LatLonCombineTask` classes.

```{note}
Since this step is expensive and time-consuming to run, most tasks will
want to use cached outputs from this step rather than running it in full.
```
