(dev-visualization)=

# Visualization

Visualization is an optional, but desirable aspect of tasks. Often,
visualization is an optional step of a task but can also be included
as part of other steps such as `init` or `analysis`.

While developers can write their own visualization scripts associated with
individual tasks, the following shared visualization routines are
provided in `polaris.viz`:

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

{py:func}`polaris.viz.plot_horiz_field()` produces a patches-style
visualization of x-y fields across a single vertical level at a single time
step. The image file (png) is saved to the directory from which
{py:func}`polaris.viz.plot_horiz_field()` is called. The function
automatically detects whether the field specified by its variable name is
a cell-centered variable or an edge-variable and generates the patches, the
polygons characterized by the field values, accordingly.

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
plot_horiz_field(config, ds, ds_mesh, 'normalVelocity',
                 'final_normalVelocity.png',
                 t_index=t_index,
                 vmin=-max_velocity, vmax=max_velocity,
                 cmap='cmo.balance', show_patch_edges=True)
```

(dev-visualization-global)=

## global lat/lon plots from spherical meshes

You can use {py:func}`polaris.viz.plot_global_field()` to plot a field on
a regular lon-lat mesh, perhaps after remapping from an MPAS mesh using
{py:class}`polaris.remap.MappingFileStep`.

```{image} images/cosine_bell_final.png
:align: center
:width: 500 px
```

The `plot_land` parameter to {py:func}`polaris.viz.plot_global_field()` is used
to enable or disable continents overlain on top of the data:

```{image} images/cosine_bell_final_land.png
:align: center
:width: 500 px
```

Typical usage might be:
```python
import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_field

class Viz(Step):
    def run(self):
        ds = xr.open_dataset('initial_state.nc')
        ds = ds[['tracer1']].isel(Time=0, nVertLevels=0)
        
        plot_global_field(
            ds.lon.values, ds.lat.values, ds.tracer1.values,
            out_filename='init.png', config=self.config,
            colormap_section='cosine_bell_viz',
            title='Tracer at init', plot_land=False)
```

The `colormap_section` of the config file must contain config options for
specifying the colormap:

```cfg
# options for visualization for the cosine bell convergence task
[cosine_bell_viz]

# colormap options
# colormap
colormap_name = viridis

# the type of norm used in the colormap
norm_type = linear

# A dictionary with keywords for the norm
norm_args = {'vmin': 0., 'vmax': 1.}

# We could provide colorbar tick marks but we'll leave the defaults
# colorbar_ticks = np.linspace(0., 1., 9)
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
