(dev-ocean-geostrophic)=

# geostrophic

The {py:class}`polaris.ocean.tasks.geostrophic.Geostrophic`
test performs a series of 5-day runs starting from an initial condition in
geostrophic balance.  The resolution of the sphere varies (by default, between
60 and 240 km).  The results after 5 days are compared with the exact solution
used to produce the initial condition to determine the rate of convergence.

## framework

The config options for the `geostrophic` tests are described in 
{ref}`ocean-geostrophic` in the User's Guide.

Additionally, the test uses a `forward.yaml` file with a few common
model config options related to drag and default horizontal and
vertical momentum and tracer diffusion, as well as defining `mesh`, `input`,
`restart`, and `output` streams.

### base_mesh

Geostrophic tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.ocean.tasks.geostrophic.init.Init`
defines a step for setting up the initial state at each resolution with a
velocity field and water-column thickness in geostrophic balance, as described
in {ref}`ocean-geostrophic-init` in the User's Guide.

### forward

The class {py:class}`polaris.ocean.tasks.geostrophic.forward.Forward`
descends from {py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`,
and defines a step for running MPAS-Ocean from an initial condition produced in
an `init` step. See {ref}`dev-ocean-convergence` for some relevant
discussion of the parent class. The time step is determined from the resolution
based on the `dt_per_km` config option in the `[spherical_convergences]` 
section.  Other model config options are taken from `forward.yaml`.

### analysis

The class {py:class}`polaris.ocean.tasks.geostrophic.analysis.Analysis`
descends from
{py:class}`polaris.ocean.convergence.ConvergenceAnalysis`,
and defines a step for computing the error norm (L2) for the water-column
thickness and normal velocity at each resolution, saving them in
`convergence_h.csv` and `convergence_normalVelocity.csv`, and plotting them
in `convergence_h.png` and `convergence_normalVelocity.png`.

### viz

The visualization step is available only in the `geostrophic/with_viz`
tasks.  It is not included in the `geostrophic` in order to keep regression
as fast as possible when visualization isn't needed.

The class {py:class}`polaris.ocean.tasks.geostrophic.viz.Viz`
is a step for plotting the initial and final states of the advection test for
each resolution.  The colormap is controlled by the config options discussed in
{ref}`ocean-geostrophic-config`.

See {ref}`dev-visualization-global` for more details on the global lat-lon
plots.
