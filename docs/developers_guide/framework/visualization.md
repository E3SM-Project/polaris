(dev-visualization)=

# Visualization

Visualization is an optional, but desirable aspect of test cases. Often,
visualization is an optional step of a test case but can also be included
as part of other steps such as `initial_state` or `analysis`.

While developers can write their own visualization scripts associated with
individual test cases, the following shared visualization routines are
provided in `polaris.viz`:

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
