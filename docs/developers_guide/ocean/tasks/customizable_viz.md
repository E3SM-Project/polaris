(dev-ocean-customizable_viz)=

# customizable_viz

The {py:class}`polaris.tasks.ocean.customizable_viz.CustomizableViz` defines
a configurable visualization step that plots the horizontal fields and/or
transects of MPAS global output, with colormap and other plotting options
controlled via the task configuration.

## framework

The config options for the `customizable_viz` tests are described in
{ref}`ocean-customizable_viz` in the User's Guide.

The test also makes use of `polaris.viz.helper` and `polaris.viz.mplstyle`.

### viz_horiz_field

The class
{py:class}`polaris.tasks.ocean.customizable_viz.viz_horiz_field.VizHorizField`
is a step for plotting global MPAS fields using
{py:func}`polaris.viz.spherical.plot_global_mpas_field`.

The colormap is controlled by the config options discussed in
{ref}`ocean-customizable-viz-config`. Note that if a colormap is specified, the
same colormap will be used for all variables listed. If a colormap is not provided,
the colormaps derive from their defaults and may differ by variable. The same
is true for other variables corresponding to colormap properties.

See {ref}`dev-visualization-global` for more details on the global plots.

### viz_transect

The class
{py:class}`polaris.tasks.ocean.customizable_viz.viz_transect.VizTransect`
is a step for plotting transects through MPAS meshes. It uses
{py:func}`mpas_tools.ocean.viz.transect.vert.compute_transect` and
{py:func}`mpas_tools.ocean.viz.transect.plot.plot_transect` to compute and
plot the transect. There are cfg options available; see
{ref}`ocean-customizable-viz-config`.
