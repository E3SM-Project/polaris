(dev-ocean-cosine-bell)=

# cosine_bell

The {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.CosineBell`
test performs a series of 24-day runs that advect a bell-shaped tracer blob
around the sphere.  The resolution of the sphere varies (by default, between
60 and 240 km).  Advected results are compared with a known exact solution to
determine the rate of convergence.

## framework

The config options for the `cosine_bell` tests are described in 
{ref}`ocean-cosine-bell` in the User's Guide.

Additionally, the test uses a `forward.yaml` file with a few common
model config options related to drag and default horizontal and
vertical momentum and tracer diffusion, as well as defining `mesh`, `input`,
`restart`, and `output` streams.

### base_mesh

Cosine bell tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.ocean.tasks.cosine_bell.init.Init`
defines a step for setting up the initial state at each resolution with a
tracer distributed in a cosine-bell shape.

### forward

The class {py:class}`polaris.ocean.tasks.cosine_bell.forward.Forward`
defines a step for running MPAS-Ocean from an initial condition produced in
an `init` step.  The time step is determined from the resolution
based on the `dt_per_km` config option.  Other namelist options are taken
from the task's `forward.yaml`.

### analysis

The class {py:class}`polaris.ocean.tasks.cosine_bell.analysis.Analysis`
defines a step for computing the RMSE (root-mean-squared error) for the results
at each resolution and plotting them in `convergence.png`.

### viz

Two visualization steps are available only in the `cosine_bell/with_viz`
tasks.  They are not included in the `cosine_bell` in order to keep regression
as fast as possible when visualization isn't needed.

The class {py:class}`polaris.ocean.tasks.cosine_bell.viz.VizMap`
defines a step for creating a mapping file from the MPAS mesh at a given
resolution to a lon-lat grid at a resolution and interpolation method 
determined by config options.

```cfg
# options for visualization for the cosine bell convergence test case
[cosine_bell_viz]

# visualization latitude and longitude resolution
dlon = 0.5
dlat = 0.5

# remapping method ('bilinear', 'neareststod', 'conserve')
remap_method = conserve
```

The class {py:class}`polaris.ocean.tasks.cosine_bell.viz.Viz`
is a step for plotting the initial and final states of the advection test for
each resolution, mapped to the common lat-lon grid.  The colormap is controlled
by these options:

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

# We could provide colorbar tick marks but we'll leave the defaults
# colorbar_ticks = np.linspace(0., 1., 9)
```

See {ref}`dev-visualization-global` for more details.
