# Topography Tasks

The `polaris.tasks.e3sm.init.topo` module provides tools for working with
topography data in Polaris. This includes steps for processing, modifying, and
combining topography datasets to create inputs for E3SM components such as
MPAS-Ocean. The framework is designed to handle both global and regional
datasets, supporting various grid types like lat-lon and cubed-sphere grids.

## Combine Steps and Tasks

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

The {py:class}`polaris.tasks.e3sm.init.topo.combine.CombineTask` wraps the
`CombineStep` into a task that can be used to generate and cache combined
topography datasets for reuse in other contexts.

The {py:class}`polaris.tasks.e3sm.init.topo.combine.VizCombinedStep` step is
an optional visualization step that can be added to the workflow to create
plots of the combined topography dataset. This step is particularly useful for
debugging or analyzing the combined dataset.

### High-Resolution and Low-Resolution Versions

There are two versions of the combine steps and task:

1. **Standard (High-Resolution) Version**: This version maps to a
   high-resolution (ne3000, ~1 km) cubed-sphere grid by default, producing
   topogrpahy that is suitable for remapping to standard and high-resolution
   MPAS meshes (~60 km and finer).

2. **Low-Resolution Version**: This version uses a coarser ne120 (~25 km) grid
   for faster remapping to coarse-resolution MPAS meshes (e.g., Icos240). It is
   designed to reduce computational cost while still providing adequate accuracy
   for low-resolution simulations used for regression testing rather than
   science.

The low-resolution version can be selected by setting the `low_res` parameter
to `True` when creating the `CombineStep` or `CombineTask`.

### Key Features

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

### Configuration Options

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

For the low-resolution version, additional configuration options are provided
in the `combine_low_res.cfg` file.

### Workflow

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

### Example Usage

Below is an example of how the `CombineStep` can be added to a Polaris
task:

```python
from polaris.tasks.e3sm.init.topo.combine import CombineStep

component = task.component
subdir = CombineStep.get_subdir(low_res=False)
if subdir in component.steps:
    step = component.steps[subdir]
else:
    step = CombineStep(component=component, low_res=False)
    component.add_step(step)
task.add_step(step)
```

To create a `CombineTask` for caching combined datasets:

```python
from polaris.tasks.e3sm.init.topo.combine import CombineTask

combine_task = CombineTask(component=my_component, low_res=False)
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
{py:class}`polaris.tasks.e3sm.init.topo.combine.CombineTask` classes.

```{note}
Since this step is expensive and time-consuming to run, most tasks will
want to use cached outputs from this step rather than running it in full.
```
