(ocean-global-convergence)=

# global_convergence

The `global_convergence` test group implements convergence studies on the
full globe.  Currently, the only test case is the advection of a cosine bell.

(ocean-global-convergence-cosine-bell)=

## cosine_bell

The `cosine_bell` test case implements the Cosine Bell test case as first
described in [Williamson et al. 1992](<https://doi.org/10.1016/S0021-9991(05)80016-6>)
but using the variant from Sec. 3a of
[Skamarock and Gassmann](https://doi.org/10.1175/MWR-D-10-05056.1).  A flow
field representing solid-body rotation transports a bell-shaped perturbation
in a tracer $psi$ once around the sphere, returning to its initial
location.  The bell is defined by:

$$
\psi =
    \begin{cases}
        \left( \psi_0/2 \right) \left[ 1 + \cos(\pi r/R )\right] &
            \text{if } r < R \\
        0 & \text{if } r \ge R
    \end{cases}
$$

where $\psi_0 = 1$, the bell radius $R = a/3$, and $a$ is
the radius of the sphere.  The equatorial velocity
$u_0 = 2 \pi a/ (\text{24 days})$. The time step is proportional to the
grid-cell size.

By default, the resolution is varied from 60 km to 240 km in steps of 30 km.
The result of the `analysis` step of the test case is a plot like the
following showing convergence as a function of the number of cells:

```{image} images/cosine_bell_convergence.png
:align: center
:width: 500 px
```

### config options

The `cosine_bell` config options include:

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 3

# Depth of the bottom of the ocean
bottom_depth = 300.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

# options for cosine bell convergence test case
[cosine_bell]

# time step per resolution (s/km), since dt is proportional to resolution
dt_per_km = 30

# the constant temperature of the domain
temperature = 15.0

# the constant salinity of the domain
salinity = 35.0

# the central latitude (rad) of the cosine bell
lat_center = 0.0

# the central longitude (rad) of the cosine bell
lon_center = 3.14159265

# the radius (m) of cosine bell
radius = 2123666.6667

# hill max of tracer
psi0 = 1.0

# time (days) for bell to transit equator once
vel_pd = 24.0

# convergence threshold below which the test fails for QU meshes
qu_conv_thresh = 1.8

# Convergence rate above which a warning is issued for QU meshes
qu_conv_max = 2.2

# convergence threshold below which the test fails for icosahedral meshes
icos_conv_thresh = 1.8

# Convergence rate above which a warning is issued for icosahedral meshes
icos_conv_max = 2.2


# options for visualization for the cosine bell convergence test case
[cosine_bell_viz]

# visualization latitude and longitude resolution
dlon = 0.5
dlat = 0.5

# remapping method ('bilinear', 'neareststod', 'conserve')
remap_method = conserve

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

The config options in `[vertical_grid]` define the vertical grid, as described
in {ref}`ocean-vertical`.

The `dt_per_km` option `[cosine_bell]` is used to control the time step, as
discussed below in more detail.

The 7 options from `temperature` to `vel_pd` are used to control properties of
the cosine bell and the rest of the sphere, as well as the advection.  The
options `qu_conv_thresh` to `icos_conv_max` are thresholds for determining
when the convergence rates are not within the expected range.  The options
in the `cosine_bell_viz` section are used in visualizing the initial and
final states on a lon-lat grid.

### resolutions

The default resolutions used in the test case depends on the mesh type. For
the `icos` mesh type, the defaults are:

```cfg
resolutions = 60, 120, 240, 480
```

for the `qu` mesh type, they are:

```cfg
resolutions = 60, 90, 120, 150, 180, 210, 240
```

To alter the resolutions used in this test, you will need to create your own
config file (or add a `cosine_bell` section to a config file if you're
already using one).  The resolutions are a comma-separated list of the
resolution of the mesh in km.  If you specify a different list
before setting up `cosine_bell`, steps will be generated with the requested
resolutions.  (If you alter `resolutions` in the test case's config file in
the work directory, nothing will happen.)  For `icos` meshes, make sure you
use a resolution close to those listed in {ref}`dev-spherical-meshes`.  Each
resolution will be rounded to the nearest allowed icosahedral resolution.

### time step

The time step for forward integration is determined by multiplying the
resolution by `dt_per_km`, so that coarser meshes have longer time steps.
You can alter this before setup (in a user config file) or before running the
test case (in the config file in the work directory).

### cores

The number of cores (and the minimum) is proportional to the number of cells,
so that the number of cells per core is roughly constant.  You can alter how
many cells are allocated to each core with `goal_cells_per_core` in the 
`[ocean]` config section.  You can  control the maximum number of cells that 
are allowed  to be placed on a single  core (before the test case will fail) 
with `max_cells_per_core` also in `[ocean]`.  If there  aren't enough 
processors to handle the finest resolution, you will see that  the step (and 
therefore the  test case) has failed.

```cfg
# Options related the ocean component
[ocean]

# the number of cells per core to aim for
goal_cells_per_core = 200

# the approximate maximum number of cells per core (the test will fail if too
# few cores are available)
max_cells_per_core = 2000
```
