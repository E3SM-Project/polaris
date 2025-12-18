
(dev-e3sm-init-topo-remap-tasks)=

# Remapping Topography to MPAS Base Meshes

The `e3sm/init` component includes a workflow for remapping combined topography
datasets to MPAS base meshes at a range of resolutions. This process ensures
that bathymetry, land-ice thickness, and related fields are accurately mapped
from the cubed-sphere grid onto the unstructured MPAS mesh used in E3SM
simulations.

## Remapping Workflow Overview

The remapping workflow is composed of several modular steps, each responsible for a specific part of the process:

- **Masking**: The {py:class}`polaris.tasks.e3sm.init.topo.remap.MaskTopoStep` applies ocean and land masks to the combined topography dataset on the cubed-sphere grid. This step generates masked versions of all topography fields, as well as fractional land and ocean coverage.
- **Remapping**: The {py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoStep` remaps the masked topography fields from the cubed-sphere grid to the MPAS mesh. This step can be run with or without smoothing, depending on configuration.
- **Smoothing**: Smoothing is optionally applied during remapping. The workflow supports both unsmoothed and smoothed topography, with the smoothed step depending on the unsmoothed results.
- **Visualization**: The {py:class}`polaris.tasks.e3sm.init.topo.remap.VizRemappedTopoStep` can be added to generate plots of the remapped fields for quality control.

The {py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoTask` orchestrates these steps for each supported MPAS base mesh.

## Step Dependencies

The typical dependency chain is:

1. `CombineStep` (combines global and Antarctic topography)
2. `MaskTopoStep` (applies land/ocean masks)
3. `RemapTopoStep` (remaps to MPAS mesh, optionally with smoothing)
4. `VizRemappedTopoStep` (optional visualization)

## Configuration Options

The remapping steps are configured through the `[remap_topography]` section in
the configuration file. Key options include:

- `ntasks` and `min_tasks`: Number of MPI tasks for remapping.
- `renorm_threshold`: Fractional threshold for renormalizing elevation variables.
- `expand_distance` and `expand_factor`: Smoothing parameters (set to 0 and 1 for no smoothing).
- Additional options for visualization colormaps and normalization.

For the low-resolution version, additional configuration options are provided
in the `remap_low_res.cfg` file.

## Workflow

1. **Masking**: The `MaskTopoStep` applies land and ocean masks to the combined topography dataset, producing masked fields and fractional coverage variables.
2. **Remapping**: The `RemapTopoStep` remaps the masked topography fields to the MPAS mesh. If smoothing is enabled, both unsmoothed and smoothed steps are created, with the smoothed step depending on the unsmoothed output.
3. **Smoothing**: Smoothing parameters are controlled via configuration. If no smoothing is requested, the smoothed step simply symlinks the unsmoothed results.
4. **Visualization**: The `VizRemappedTopoStep` can be added to plot each remapped field using configuration-driven colormaps and normalization.
5. **Output**: The final remapped topography is saved as `topography_remapped.nc` for each mesh and smoothing option.

## Example Usage

Below is an example of how the remapping steps can be added to a Polaris task:

```python
from polaris.tasks.e3sm.init.topo.remap import get_default_remap_topo_steps

steps, config = get_default_remap_topo_steps(
    component=component,
    base_mesh_step=base_mesh_step,
    combine_topo_step=combine_topo_step,
    low_res=low_res,
    smoothing=True,
    include_viz=True,
)
for step in steps:
    component.add_step(step)
```

To add the full remapping workflow as a task for each supported mesh:

```python
from polaris.tasks.e3sm.init.topo.remap import add_remap_topo_tasks

add_remap_topo_tasks(component)
```

This will add a `RemapTopoTask` for each supported base mesh, including all necessary steps (masking, remapping, smoothing, and optional visualization).

## Example: Ocean Fraction on Icos480km Mesh

Below is an example of the ocean fraction field (`ocean_frac`) remapped
to the Icos480km MPAS mesh:

```{image} images/icos_480_ocean_frac.png
:align: center
:width: 500 px
:alt: Ocean fraction remapped to Icos480km MPAS mesh
```

This field indicates the fraction of each MPAS cell that is covered by ocean
after remapping, which is important for subsequent steps such as mesh culling
and mask generation.

## Customization

Remapping options, including smoothing parameters and the number of MPI tasks,
are controlled via the `[remap_topography]` section in the configuration file.
The workflow supports both unsmoothed and smoothed topography, and can generate
visualizations for each remapped field.

For more details, see the source code for
{py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoTask` and related steps,
as well as the configuration files `remap.cfg` and `remap_low_res.cfg`.

## Extending Masking and Smoothing Functionality

Developers may wish to customize how land/ocean masks are generated or how
smoothing is applied during remapping. This can be accomplished by subclassing
the relevant step classes and overriding their methods:

### Customizing Mask Generation

To implement a custom approach for generating land and ocean masks, create a
subclass of {py:class}`polaris.tasks.e3sm.init.topo.remap.MaskTopoStep` and
override the `define_masks()` method. This method receives an `xarray.Dataset`
and should return two `xarray.DataArray` objects representing the ocean and land
masks, respectively.

**Example:**

```python
from polaris.tasks.e3sm.init.topo.remap import MaskTopoStep

class MyCustomMaskStep(MaskTopoStep):
    def define_masks(self, ds):
        # Custom logic for mask generation
        ocean_mask = ...  # compute ocean mask as DataArray
        land_mask = ...   # compute land mask as DataArray
        return ocean_mask, land_mask
```

You can then use your custom step in place of the default `MaskTopoStep` when constructing your workflow.

### Customizing Smoothing Behavior

To implement custom smoothing logic, subclass
{py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoStep` and override the
`define_smoothing()` method. This method receives the unsmoothed topography
dataset and should return the `expand_distance` and `expand_factor` (either as
scalars or `xarray.DataArray` objects) to control the smoothing applied during
remapping.

**Example:**

```python
from polaris.tasks.e3sm.init.topo.remap import RemapTopoStep

class MyCustomRemapStep(RemapTopoStep):
    def define_smoothing(self, ds_unsmoothed):
        # Custom logic for spatially varying smoothing
        expand_distance = ...  # scalar or DataArray
        expand_factor = ...    # scalar or DataArray
        return expand_distance, expand_factor
```

This allows for advanced smoothing strategies, such as spatially varying
parameters based on mesh properties or scientific requirements.

### Integration

To use your custom steps, simply instantiate them in your workflow or override
the step creation logic in your task or workflow setup.

For more details, refer to the docstrings and source code of
{py:class}`polaris.tasks.e3sm.init.topo.remap.MaskTopoStep` and
{py:class}`polaris.tasks.e3sm.init.topo.remap.RemapTopoStep`.
