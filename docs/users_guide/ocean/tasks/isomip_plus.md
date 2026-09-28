(ocean-isomip-plus)=

# isomip_plus

The `isomip_plus` tasks are based on the ocean experiments of the second
Ice Shelf-Ocean Model Intercomparison Project, ISOMIP+
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)). An ice
shelf fed by an ice stream in a channel 80 km wide floats over a cavity
that deepens toward the grounding line. Water in the open ocean north of the
ice-shelf front is restored toward a prescribed temperature and salinity
profile, and the ocean melts the ice shelf from below.

MPAS-Ocean's results from the ISOMIP+ intercomparison
([Yung et al. 2026](https://doi.org/10.5194/tc-20-2053-2026)) were produced
with the legacy Compass package. In Polaris, the setup serves as a platform
for idealized ice-shelf-cavity tests. The `ocean0`, `ocean1` and `ocean2`
tasks run the corresponding ISOMIP+ experiments for a short time. The
`inception`, `wetting` and `drying` tasks, which scale the Ocean1 ice load
in time to test wetting and drying, currently produce only an initial
condition and forcing.

## supported models

These tasks support only MPAS-Ocean.

## shared steps

All tasks at a given resolution and mesh type share steps that build the
mesh and the topography:

- `base_mesh`: a planar hexagonal mesh or a regionally refined spherical
  mesh covering the ISOMIP+ domain plus a buffer;
- `topo/map_base`, `topo/remap_base` and `topo/cull_mesh`: remap the Ocean1
  geometry to the base mesh and remove cells where the bedrock is above sea
  level;
- `topo/map_culled` and `topo/remap_culled/{ocean1,ocean2}`: remap the
  Ocean1 or Ocean2 geometry conservatively to the culled mesh, smoothing it
  by expanding the destination cells;
- `topo/scale/{inception,wetting,drying}`: scale the pressure and draft of
  the Ocean1 geometry in time.

Before remapping, floating ice thinner than 100 m is removed ("calved") as
required by the ISOMIP+ protocol.

## mesh

The domain covers $320 \le x \le 800$ km and $0 \le y \le 80$ km, with
walls on all sides. Meshes are available at 4, 2 and 1 km resolution, either
planar (`ocean/planar/isomip_plus`) or as a region on a sphere at about 75°S
(`ocean/spherical/isomip_plus`). The x and y coordinates of the ISOMIP+
domain are stored as `xIsomipCell`, `yIsomipCell`, `xIsomipVertex` and
`yIsomipVertex` for both mesh types.

For `ocean0`, `ocean1` and `ocean2`, each task's `init` step removes cells
unless at least half of the cell is floating ice or open ocean, so no
grounded cells remain. The `inception`, `wetting` and `drying` tasks keep
every cell of the shared mesh, with a thin film under grounded ice.

```cfg
# config options for ISOMIP+ meshes
[isomip_plus_mesh]

# latitude in degrees for origin of the mesh
lat0 = -75.

# size of the domain in km
lx = 800
ly = 80

# a buffer in km around the domain that will be culled based on the topography
buffer = 80

# config options for ISOMIP+ topography
[isomip_plus_topo]

# the density of ice prescribed in ISOMIP+
ice_density = 918

# minimum ocean fraction (i.e. fraction of bathymetry below sea level) of an
# MPAS cell below which it will be culled from the mesh
min_ocean_fraction = 0.5

# the expansion factor used to smooth the topography
expand_factor = 2.0

# the thickness (m) of floating ice below which it is removed ("calved"),
# as prescribed by the ISOMIP+ protocol
min_ice_thickness = 100.0
```

## vertical grid

The vertical grid has 36 uniform z-star levels over 720 m. Under the ice
shelf, the levels are compressed to fit the water column, with at least 3
levels in each column.

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 36

# Depth of the bottom of the ocean
bottom_depth = 720.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

# The minimum number of vertical levels in a column
min_vert_levels = 3

# The minimum layer thickness in m
min_layer_thickness = 0.0
```

## initial conditions

The ocean starts at rest. Temperature and salinity are linear in depth
between their surface and sea-floor values in either the WARM or the COLD
profile of the ISOMIP+ protocol:

| Task                             | Initial T, S | Restoring T, S |
|----------------------------------|--------------|----------------|
| `ocean0`                         | WARM         | WARM           |
| `ocean1`                         | COLD         | WARM           |
| `ocean2`                         | WARM         | COLD           |
| `inception`, `wetting`, `drying` | WARM         | WARM           |

The sea-surface height is the ice draft, and the land-ice pressure comes
from the weight of the ice. The bottom depth is deepened where needed to
keep a minimum water-column thickness. The equation of state is linear, with
the coefficients of the ISOMIP+ protocol, and the Coriolis parameter is
constant.

## forcing

Temperature and salinity are restored toward the task's restoring profile
within 10 km of the northern boundary, at a rate that increases linearly from
zero at $x = 790$ km to $1/(10\ \mathrm{days})$ at $x = 800$ km. In the same
region, "evaporation" of 200 m/yr removes water at the surface temperature
and salinity to offset the meltwater from the ice shelf. Melt fluxes use
MPAS-Ocean's three-equation parameterization.

## wetting and drying

All model runs use MPAS-Ocean's wetting and drying, so that water columns
under ice heavier than the water it would displace thin to a film rather than
becoming negative. This happens in cells that are partly grounded, where the
land-ice pressure comes from the full weight of the ice. MPAS-Ocean supports
wetting and drying only with the RK4 time integrator.

## SSH adjustment

Before the forward run, the land-ice pressure is adjusted over ten one-hour
runs so that it is in balance with the sea-surface height, as described in
{ref}`ocean-ssh-adjustment`.

```cfg
# Options related to ssh adjustment steps
[ssh_adjustment]

# Time integration scheme, RK4 for wetting and drying
time_integrator = RK4

# Time step in seconds as a function of resolution
rk4_dt_per_km = 6
```

## config options

```cfg
# config options for ISOMIP+ initial conditions
[isomip_plus]

# Minimum fraction of a cell that is floating ice or open ocean for the cell to
# be kept in tasks without a thin film
min_ocean_fraction = 0.5

# Minimum fraction of a cell that contains land ice in order for it to be
# considered a land-ice cell by MPAS-Ocean (landIceMask == 1)
min_land_ice_fraction = 0.5

# Minimum fraction of a cell that contains land ice in order for the land-ice
# pressure to be adjusted during SSH adjustment
min_ssh_adjust_land_ice_fraction = 0.01

# Minimum thickness (m) of the initial ocean column
min_column_thickness = 1.1e-2

# The approximate area (km^2) of the ocean, used to estimate the number of
# cells in the mesh and the resources for model runs
approx_ocean_area = 30000.0

# the WARM profile
# the temperature (C) at the sea surface
warm_top_temp = -1.9
# the temperature (C) at the sea floor
warm_bot_temp = 1.0
# the salinity (PSU) at the sea surface
warm_top_sal = 33.8
# the salinity (PSU) at the sea floor
warm_bot_sal = 34.7

# the COLD profile
# the temperature (C) at the sea surface
cold_top_temp = -1.9
# the temperature (C) at the sea floor
cold_bot_temp = -1.9
# the salinity (PSU) at the sea surface
cold_top_sal = 33.8
# the salinity (PSU) at the sea floor
cold_bot_sal = 34.55


# config options for ISOMIP+ forcing
[isomip_plus_forcing]

# restoring rate (1/days) at the open-ocean boundary
restore_rate = 10.0

# the "evaporation" rate (m/yr) near the open-ocean boundary used to keep sea
# level from rising
restore_evap_rate = 200.0

# southern boundary (m) of the restoring region
restore_xmin = 790e3

# northern boundary (m) of the restoring region
restore_xmax = 800e3


# config options for ISOMIP+ forward runs
[isomip_plus_forward]

# Run duration in hours
run_duration = 1.0

# Time step in seconds as a function of resolution for RK4 time integration,
# which is required for wetting and drying
rk4_dt_per_km = 6


# config options for visualizing ISOMIP+ output
[isomip_plus_viz]

# the y value (m) at which a cross-section is plotted
section_y = 40e3
```

The cavity freezing point uses MPAS-Ocean's default coefficients, which are
in the `ice_shelf_freeze` section.

## cores

The number of cores for model runs is determined by `goal_cells_per_core`
and `max_cells_per_core` in the `ocean` section of the config file, with the
number of cells estimated from `approx_ocean_area`.

(ocean-isomip-plus-ocean0-2)=

## ocean0, ocean1 and ocean2

### description

`ocean0` uses the Ocean1 geometry with WARM initial conditions and
restoring, the quick spin-up experiment of ISOMIP+. `ocean1` starts COLD and
is restored WARM, so warm water gradually enters the cavity. `ocean2` uses
the retreated Ocean2 geometry, starts WARM and is restored COLD.

Each task has the steps `init`, `ssh_adjustment/ssh_forward_*` and
`ssh_adjustment/ssh_adjust_*`, `forward` and `viz`. The `viz` step plots the
initial geometry, the layer interfaces along a section at $y = 40$ km, the
temperature and salinity at the start and end of the run, and the melt rate,
thermal driving and friction velocity at the end of the run.

### time step and run duration

The RK4 time step is 6 s per km of resolution, in both the SSH-adjustment
and forward runs. The forward run lasts one hour. The ISOMIP+ protocol calls for
runs of 1 year (Ocean0) and 20 years (Ocean1 and Ocean2), which these tasks do
not yet support.

(ocean-isomip-plus-scaled)=

## inception, wetting and drying

### description

These tasks scale the pressure and draft of the Ocean1 geometry in time by
the factors in the `isomip_plus_scaling` section: `inception` grows an ice
shelf from open ocean, `wetting` removes the ice load and `drying` doubles it.
The fractions of floating and grounded ice are not scaled, so the area
subject to melting stays fixed.

The tasks currently have only an `init` step, which writes the initial
condition, the restoring forcing and the time-varying land-ice forcing in
`land_ice_forcing.nc`. The ice draft is computed from the land-ice pressure,
assuming the ice floats, and limited to the bed. Where the draft reaches the
bed, the ice is grounded and the cell holds a thin film 1 mm thick whose
temperature is at the freezing point.

```cfg
# config options for ISOMIP+ initial conditions
[isomip_plus]

# Minimum thickness (m) of the initial ocean column in tasks with a thin film
# under grounded ice
min_column_thickness_thin_film = 1e-3

# The density (kg/m^3) of seawater used to compute the ice draft from the
# land-ice pressure in tasks with a thin film
ocean_density = 1028.0
```

```cfg
# config options for ISOMIP+ topography scaling
[isomip_plus_scaling]

# simple thickening and thinning experiments that involve scaling the Ocean1
# landIcePressure and landIceDraft over time
#
# "inception" reference dates
inception_dates = 0001-01-01_00:00:00, 0002-01-01_00:00:00, 0003-01-01_00:00:00
# scaling at each date
inception_scales = 0.0, 1.0, 1.0

# "drying" reference dates
drying_dates = 0001-01-01_00:00:00, 0002-01-01_00:00:00, 0003-01-01_00:00:00
# scaling at each date
drying_scales = 1.0, 2.0, 2.0

# "wetting" reference dates
wetting_dates = 0001-01-01_00:00:00, 0002-01-01_00:00:00, 0003-01-01_00:00:00
# scaling at each date
wetting_scales = 1.0, 0.0, 0.0
```

### time step and run duration

N/A. These tasks do not yet run the model.
