(dev-ocean-correlated-tracers-2d)=

# correlated_tracers_2d

The {py:class}`polaris.ocean.tasks.sphere_transport.SphereTransport`
`correlated_tracers_2d` test performs a 12-day run on the sphere that has a periodic
deforming flow which affects tracer distributions. The resolution of the
sphere varies (by default, between 60 and 240 km). After one period, the
tracer distributions are compared the initial condition to evaluate numerical
errors associated with the horizontal advection scheme and determine the rate
of convergence.

## framework

The config options for the `correlated_tracers_2d` test is described in 
{ref}`ocean-correlated-tracers-2d` in the User's Guide.

Additionally, the test uses a `forward.yaml` file with a few common
model config options related to drag and default horizontal and
vertical momentum and tracer diffusion, as well as defining `mesh`, `input`,
`restart`, and `output` streams.  This file has Jinja templating that is
used to update model config options based on Polaris config options, see
{ref}`dev-ocean-convergence`.

### base_mesh

Sphere transport tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.ocean.tasks.sphere_transport.init.Init`
defines a step for setting up the initial state at each resolution. The
initial state is differentiated between `correlated_tracers_2d` and the other tests
set up by the class.

### forward

The class {py:class}`polaris.ocean.tasks.sphere_transport.forward.Forward`
descends from {py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`,
and defines a step for running MPAS-Ocean from an initial condition produced in
an `init` step. See {ref}`dev-ocean-convergence` for some relevant
discussion of the parent class. The time step is determined from the resolution
based on the `dt_per_km` config option in the `[convergence_forward]` 
section.  Other model config options are taken from `forward.yaml`.

### analysis

The class {py:class}`polaris.ocean.tasks.sphere_transport.analysis.Analysis`
descends from
{py:class}`polaris.ocean.convergence.ConvergenceAnalysis`,
and defines a step for computing the error norm (L2) for the results
at each resolution for tracers and layer thickness, saving them in
`convergence_*.csv` and plotting them in `convergence_*.png`.

### mixing_analysis

The class {py:class}`polaris.ocean.tasks.sphere_transport.mixing_analysis.MixingAnalysis`
plots the relationship between two correlated tracers for each resolution in
`triplots.png`.

### viz

Visualization step is available only in the `correlated_tracers_2d/with_viz`
tasks.  It is not included in the `correlated_tracers_2d` in order to keep regression
as fast as possible when visualization isn't needed.

The class {py:class}`polaris.ocean.tasks.sphere_transport.viz.Viz`
is a step for plotting the initial and final states of the advection test for
each resolution.  The colormap is controlled by these options:

```cfg
# options for visualization for the sphere transport test case
[sphere_transport_viz_*]

# colormap options
# colormap
colormap_name = viridis

# the type of norm used in the colormap
norm_type = linear

# colorbar limits
colorbar_limits = 0., 1.
```

See {ref}`dev-visualization-global` for more details.
