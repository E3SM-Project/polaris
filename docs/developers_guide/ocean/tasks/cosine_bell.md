(dev-ocean-cosine-bell)=

# cosine_bell

The {py:class}`polaris.ocean.tasks.cosine_bell.CosineBell`
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
`restart`, and `output` streams.  This file has Jinja templating that is
used to update model config options based on Polaris config options, see
{ref}`dev-ocean-convergence`.

### base_mesh

Cosine bell tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.ocean.tasks.cosine_bell.init.Init`
defines a step for setting up the initial state at each resolution with a
tracer distributed in a cosine-bell shape.

### forward

The class {py:class}`polaris.ocean.tasks.cosine_bell.forward.Forward`
descends from {py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`,
and defines a step for running MPAS-Ocean from an initial condition produced in
an `init` step. See {ref}`dev-ocean-convergence` for some relevant
discussion of the parent class. The time step is determined from the resolution
based on the `dt_per_km` config option in the `[convergence_forward]` 
section.  Other model config options are taken from `forward.yaml`.

### analysis

The class {py:class}`polaris.ocean.tasks.cosine_bell.analysis.Analysis`
descends from
{py:class}`polaris.ocean.convergence.ConvergenceAnalysis`,
and defines a step for computing the error norm (L2) for the results
at each resolution, saving them in `convergence_tracer1.csv` and plotting them
in `convergence_tracer1.png`.

### viz

The visualization step is available only in the `cosine_bell/with_viz`
tasks.  It is not included in the `cosine_bell` in order to keep regression
as fast as possible when visualization isn't needed.

The class {py:class}`polaris.ocean.tasks.cosine_bell.viz.Viz`
is a step for plotting the initial and final states of the advection test for
each resolution.  The colormap is controlled by these options:

```cfg
# options for visualization for the cosine bell convergence test case
[cosine_bell_viz]

# colormap options
# colormap
colormap_name = viridis

# the type of norm used in the colormap
norm_type = linear

# colorbar limits
colorbar_limits = 0.0, 1.0
```

See {ref}`dev-visualization-global` for more details.
