(dev-ocean-global-convergence)=

# global_convergence

The `global_convergence` test group
({py:class}`polaris.ocean.tasks.global_convergence.GlobalConvergence`)
implements convergence studies on the full globe. Currently, the only test case
is the advection of a cosine bell.

(dev-ocean-global-convergence-mesh-types)=

## mesh types

The global convergence test cases support two types of meshes: `qu` meshes
created with the {py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` step
and `icos` meshes created with
{py:class}`polaris.mesh.IcosahedralMeshStep`.  In general, the `icos` meshes
are more uniform but the `qu` meshes are more flexible.  The `icos` meshes
only support a fixed set of resolutions described in
{ref}`dev-spherical-meshes`.

(dev-ocean-global-convergence-cosine-bell)=

## cosine_bell

The {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.CosineBell`
test performs a series of 24-day runs that advect a bell-shaped tracer blob
around the sphere.  The resolution of the sphere varies (by default, between
60 and 240 km).  Advected results are compared with a known exact solution to
determine the rate of convergence.  See {ref}`ocean-global-convergence-cosine-bell`.
for config options and more details on the test case.

### mesh

This step builds a global mesh with uniform resolution. The type of mesh
depends on the mesh type (`qu` or `icos`).

### init

The class {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.init.Init`
defines a step for setting up the initial state for each test case with a
tracer distributed in a cosine-bell shape.

### forward

The class {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step.  The time step is determined from the resolution
based on the `dt_per_km` config option.  Other namelist options are taken
from the test case's `namelist.forward`.

### analysis

The class {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.analysis.Analysis`
defines a step for computing the RMSE (root-mean-squared error) for the results
at each resolution and plotting them in `convergence.png`.

### viz

Two visualization steps are available only in the `cosine_bell_with_viz`
test cases.  They are not included in the `cosine_bell` test cases in order
to not slow down regression testing when visualization is not desired.

The class {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.viz.VizMap`
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

The class {py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.viz.Viz`
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
