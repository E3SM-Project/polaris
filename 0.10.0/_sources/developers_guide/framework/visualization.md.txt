(dev-visualization)=

# Visualization

Visualization is an optional, but desirable aspect of tasks. Often,
visualization is an optional step of a task but can also be included
as part of other steps such as `init` or `analysis`.

Horizontal visualization of MPAS fields is enabled through the use of
[`mosaic`](https://docs.e3sm.org/mosaic/). While developers can write their
own visualization scripts associated with individual tasks, the following
shared visualization routines are provided in `polaris.viz`:

(dev-visualization-style)=

## common matplotlib style

The function {py:func}`polaris.viz.use_mplstyle()` loads a common 
[matplotlib style sheet](https://matplotlib.org/stable/users/explain/customizing.html#customizing-with-style-sheets)
that can be used to make font sizes and other plotting options more consistent
across Polaris.  The plotting functions described below make use of this common
style.  Custom plotting should call {py:func}`polaris.viz.use_mplstyle()`
before creating a `matplotlib` figure.

(dev-visualization-planar)=

## horizontal fields from planar meshes

{py:func}`polaris.viz.plot_horiz_field()` produces a visualization of 
horizontal fields at their native mesh location (i.e. cells, edges, or
vertices) at a single vertical level and a single time step. The image file
(png) is saved to the directory from which 
{py:func}`polaris.viz.plot_horiz_field()` is called. 
{py:func}`polaris.viz.plot_horiz_field()` is jut a wrapper for
{py:func}`mosaic.polypcolor()`, which automatically detects whether the field
to be plotted is defined at cells, edges, or vertices and generates the patches
(i.e. the polygons characterized by the field values) accordingly.

```{image} images/baroclinic_channel_cell_patches.png
:align: center
:width: 250 px
```

```{image} images/baroclinic_channel_edge_patches.png
:align: center
:width: 250 px
```

An example function call that uses the default vertical level (top) is:

```python
cell_mask = ds_init.maxLevelCell >= 1
edge_mask = cell_mask_to_edge_mask(ds_init, cell_mask)

plot_horiz_field(ds_mesh, ds['normalVelocity'], 'final_normalVelocity.png',
                 t_index=t_index, vmin=-max_velocity, vmax=max_velocity,
                 cmap='cmo.balance', show_patch_edges=True, 
                 field_mask=edge_mask)
```

The `field_mask` argument can be any field indicating which horizontal mesh
locations are valid and which are not, but it must be the same shape as data
array being plotted.  A typical value for ocean plots is as shown 
above: whether there are any active cells in the water column and then the cell
mask is converted to an edges mask using the
{py:func}`polaris.mpas.cell_mask_to_edge_mask()` function.

For increased efficiency, you can store the instance of 
{py:class}`mosaic.Descriptor` returned by `plot_horiz_field()` and reuse it in
subsequent calls; assuming you are plotting with the same mesh.
```python
cell_mask = ds_init.maxLevelCell >= 1
descriptor = plot_horiz_field(ds_mesh, ds['ssh'], 'plots/ssh.png',
                              vmin=-720, vmax=0, figsize=figsize,
                              field_mask=cell_mask)

plot_horiz_field(ds_mesh, ds['bottomDepth'], 'plots/bottomDepth.png',
                 vmin=0, vmax=720, figsize=figsize, field_mask=cell_mask,
                 descriptor=descriptor)

edge_mask = cell_mask_to_edge_mask(ds_mesh, cell_mask)
plot_horiz_field(ds_mesh, ds['normalVelocity'], 'plots/normalVelocity.png',
                 t_index=t_index, vmin=-0.1, vmax=0.1, cmap='cmo.balance',
                 field_mask=edge_mask, descriptor=descriptor)

...
```

(dev-visualization-global)=

## global lat/lon plots

### plotting from spherical MPAS meshes

You can use {py:func}`polaris.viz.plot_global_mpas_field()` to plot a field on
a spherical MPAS mesh. Like the planar visualization function, this is also
just a wrapper to {py:func}`mosaic.polypcolor()`. Thanks to `mosaic` variables
defined at cells, edges, and vertices are all support as well as meshes with
culled land boundaries are also supported. While `mosaic`
[supports](https://docs.e3sm.org/mosaic/user_guide/wrapping.html) a variety
of map projection for spherical meshes,
{py:func}`polaris.viz.plot_global_mpas_field()` currently only supports
[`cartopy.crs.PlateCarree`](https://scitools.org.uk/cartopy/docs/latest/reference/projections.html#cartopy.crs.PlateCarree).

```{image} images/cosine_bell_final_mpas.png
:align: center
:width: 500 px
```

Typical usage might be:
```python
import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_mpas_field

class Viz(Step):
    def run(self):
        
        ds = xr.open_dataset('initial_state.nc')
        da = ds['tracer1'].isel(Time=0, nVertLevels=0)
        
        plot_global_mpas_field(
            mesh_filename='mesh.nc', da=da,
            out_filename='init.png', config=self.config,
            colormap_section='cosine_bell_viz',
            title='Tracer at init', plot_land=False,
            central_longitude=180.)
```

The `plot_land` parameter to {py:func}`polaris.viz.plot_global_mpas_field()` is
used  to enable or disable continents overlain on top of the data.

The `central_longitude` defaults to `0.0` and can be set to another value
(typically 180 degrees) for visualizing quantities that would otherwise be
divided across the antimeridian.

The `<task>_viz` section of the config file must contain config options for
specifying the colormap:

```cfg
# options for visualization for the cosine bell convergence test case
[cosine_bell_viz]

# colormap options
# colormap
colormap_name = viridis

# the type of norm used in the colormap
norm_type = linear

# A dictionary with keywords for the norm
norm_args = {'vmin': 0., 'vmax': 1.}
```

`colormap_name` can be any available matplotlib colormap.  For ocean test
cases, we recommend importing [cmocean](https://matplotlib.org/cmocean/) so
the standard ocean colormaps are available.

The `norm_type` is one of `linear` (a linear colormap), `symlog` (a 
[symmetric log](https://matplotlib.org/stable/gallery/images_contours_and_fields/colormap_normalizations_symlognorm.html)
colormap with a central linear region), or `log` (a logarithmic colormap).

The `norm_args` depend on the `norm_typ` and are the arguments to
{py:class}`matplotlib.colors.Normalize`, {py:class}`matplotlib.colors.SymLogNorm`,
and {py:class}`matplotlib.colors.LogNorm`, respectively. 

The config option `colorbar_ticks` (if it is defined) specifies tick locations
along the colorbar. If it is not specified, they are determined automatically.

### plotting from lat/lon grids

You can use {py:func}`polaris.viz.plot_global_lat_lon_field()` to plot a field 
on a regular lon-lat grid, perhaps after remapping from an MPAS mesh using
{py:class}`polaris.remap.MappingFileStep`.

```{image} images/cosine_bell_final.png
:align: center
:width: 500 px
```

The `plot_land` parameter to {py:func}`polaris.viz.plot_global_lat_lon_field()`
is used  to enable or disable continents overlain on top of the data:

```{image} images/cosine_bell_final_land.png
:align: center
:width: 500 px
```

Typical usage might be:
```python
import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_lat_lon_field

class Viz(Step):
    def run(self):
        ds = xr.open_dataset('initial_state.nc')
        ds = ds[['tracer1']].isel(Time=0, nVertLevels=0)
        
        plot_global_lat_lon_field(
            ds.lon.values, ds.lat.values, ds.tracer1.values,
            out_filename='init.png', config=self.config,
            colormap_section='cosine_bell_viz',
            title='Tracer at init', plot_land=False)
```

The `<task>_viz` of the config file is the same as what's used by
{py:func}`polaris.viz.plot_global_mpas_field()`.
