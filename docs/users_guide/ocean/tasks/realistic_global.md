(ocean-realistic-global)=

# realistic_global

The `realistic_global` task group contains tasks that use realistic global
ocean meshes, bathymetry and forcing. It currently contains five kinds of
tasks:

- {ref}`ocean-realistic-global-woa23`, a mesh-independent preprocessing task
  that builds a reusable World Ocean Atlas 2023 (WOA23) hydrography product on
  the native 0.25-degree latitude-longitude grid.
- {ref}`ocean-realistic-global-jra55`, a mesh-independent preprocessing task
  that builds a reusable wind-stress product on the native JRA55-do TL319 grid.
- {ref}`ocean-realistic-global-init`, which creates mesh-specific ocean initial
  conditions from that hydrography and forcing together with the culled mesh
  from `e3sm/init`.
- {ref}`ocean-realistic-global-analysis-members`, short forward runs on
  realistic global meshes that exercise the global-statistics analysis member
  and compare its output between MPAS-Ocean and Omega.
- {ref}`ocean-realistic-global-restart`, a short run split across a restart,
  checking that the history output survives the restart intact.

## supported models

The `woa23` and `jra55` tasks are model-independent and do not require either
MPAS-Ocean or Omega to be built.

The `init` and `analysis_members` tasks support both MPAS-Ocean and Omega.

The `restart` task supports Omega only.  It is a regression test for the way
Omega writes its history time axis across a restart, and MPAS-Ocean stamps its
output with `xtime` rather than an elapsed time measured from the start of the
clock, so the failure it looks for cannot arise there.

(ocean-realistic-global-woa23)=

## woa23

This task is the Polaris port of the legacy Compass
`utility/extrap_woa` workflow. It combines January and annual WOA23
climatologies, uses a cached `e3sm/init` combined-topography product on the
WOA grid to define the ocean mask used during preprocessing, and then fills
missing temperature and salinity values through staged horizontal and vertical
extrapolation.

The task can be set up with:

```bash
polaris setup -t ocean/spherical/realistic_global/hydrography/woa23 ...
```

### description

The task is organized into inspectable steps:

1. `combine_topo` from the `e3sm/init` component is used to combine topography
   GEBCO and Bedmap3 datasets on the WOA23 0.25-degree latitude-longitude grid.
2. `combine` creates `woa_combined.nc` by combining January and annual WOA23
   in-situ temperature and practical-salinity fields, then deriving
   conservative temperature and absolute salinity.
3. `extrapolate` creates the final
   `woa23_decav_0.25_jan_extrap.nc` product.
4. `viz` produces horizontal maps and vertical sections of the extrapolated
   product.  This step is not run by default.

This layout is intended to match Polaris shared-step conventions so the WOA23
preprocessing pipeline can later be reused by mesh-dependent
`realistic_global` initialization tasks.

### mesh

N/A. This task operates on the native WOA23 latitude-longitude grid rather
than an MPAS mesh.

### vertical grid

N/A. The task preserves the standard WOA23 depth levels.

### initial conditions

The source fields come from the WOA23 January and annual climatologies in the
Polaris input database.

### forcing

N/A.

### time step and run duration

N/A.

### config options

```cfg
# Options related to generating a reusable WOA23 hydrography product
[woa23]

# the minimum weight sum needed to mark a new cell valid in horizontal
# extrapolation
extrap_threshold = 0.01

# target depths for horizontal plots of the extrapolated product (m)
horizontal_plot_depths = 0.0, 200.0, 400.0, 600.0, 800.0

# maximum depth to include in section plots (m)
section_max_depth = 2000.0

# endpoints of a transect through Filchner Trough and into the Filchner
# ice-shelf cavity
filchner_start_lon = -46.0
filchner_start_lat = -71.5
filchner_end_lon = -38.5
filchner_end_lat = -81.2

# endpoints of a transect through the Ross Ice Shelf cavity
ross_start_lon = 176.0
ross_start_lat = -72.0
ross_end_lon = -171.0
ross_end_lat = -84.0
```

The `viz` step is further controlled by the `[woa23_viz_temperature]`,
`[woa23_viz_salinity]`, `[woa23_viz_section_temperature]` and
`[woa23_viz_section_salinity]` sections, each of which supports the standard
Polaris colormap options described in {ref}`dev-visualization-global`.

### cores

The local `combine` and `extrapolate` steps run serially. The
`combine_topo` step is intended to use the cached `e3sm/init` output because
regenerating the combined topography product is substantially more expensive.

(ocean-realistic-global-jra55)=

## jra55

This task builds a time-invariant global wind-stress product from JRA55-do
10-m winds.  Its purpose is narrow: standalone runs need a realistic,
constant-in-time momentum input so that dynamic adjustment can spin down fast
waves against a physically sensible circulation.  It is not intended as a
climate forcing product, and it does not include surface restoring, thermal or
freshwater fluxes, or any time variation.

```bash
polaris setup -t ocean/spherical/realistic_global/forcing/jra55 ...
```

The source is JRA55-do v1.5.0 (`MRI-JRA55-do-1-5-0`), variables `uas` and
`vas`: 10-m winds on the TL319 Gaussian grid, 3-hourly, distributed as
input4MIPs on ESGF.  E3SM forces ocean-only (G-case) runs with JRA55, so the
adjusted state is adjusted against something close to what a coupled run will
apply.  The default time window is January 1958, the first month of the record
and of an interannually forced G-case.

:::{warning}
Running the `stress` step downloads about 3.5 GiB of raw reanalysis into the
`initial_condition_database`.  The derived product is in the Polaris cache
database, so this happens only when you run this task to regenerate it, and
users of the `init` task get the few-MB product from the Polaris server
instead.
:::

The stress is computed at every 3-hourly step and then time-averaged, rather
than computing the stress of the time-mean wind.  Averaging the wind first
discards the gust contribution and underestimates the stress in the storm
tracks, which is why the 3-hourly data is needed at all.  The bulk formula is
the Large and Yeager (2004, 2009) neutral 10-m drag law; the stability
correction, the ocean-current-relative wind and any sea-ice drag distinction
are deliberately omitted as second-order for this purpose.

### description

The task contains two steps:

1. `stress` downloads the raw winds and writes `jra55_stress.nc` on the native
   TL319 grid.  It is cached by default, but this task always runs it.
2. `viz` plots global maps of the stress components and magnitude, plus a
   zonal-mean `taux` curve.  It runs by default in this task, but is left out
   when the wind-stress steps are pulled into other workflows as shared
   dependencies, so the plots are not regenerated for every mesh.

The zonal-mean curve is the diagnostic worth looking at.  For the default
January window it peaks near +0.12 N m^-2 around 50S in the Southern Ocean
westerlies, with a trade-wind minimum near -0.06 N m^-2.  Do not compare those
against published *annual-mean* stress climatologies, which are considerably
stronger in the Southern Ocean -- the Compass NCEP 1958-2000 annual mean peaks
at +0.19 N m^-2 -- because the Southern Ocean westerlies are weaker in austral
summer.  Compare like with like, or expect a January product to look weak.

### mesh

N/A. This task operates on the native JRA55-do TL319 grid rather than an MPAS
mesh.

### vertical grid

N/A.

### initial conditions

N/A.

### forcing

N/A. This task produces wind stress for the `init` task rather than applying
any forcing itself.

### time step and run duration

N/A.

### config options

```cfg
# Options related to generating a reusable JRA55-do wind-stress product
[jra55]

# the input4MIPs source and version of the JRA55-do dataset
source_id = MRI-JRA55-do-1-5-0
version = v20200916

# the ESGF data node and root path used to download the raw winds.  The
# retired esgf-node.llnl.gov and esgf-node.ornl.gov paths no longer work.
base_url = https://esgf.ceda.ac.uk/thredds/fileServer/esg_cmip6/input4MIPs/CMIP6/OMIP/MRI

# the year and month to average.  January 1958 is the first month of the
# JRA55-do record and of an interannually forced E3SM G-case.
year = 1958
month = 1

# air density used in the bulk formula (kg m^-3)
rho_air = 1.22

# wind speeds below this value (m s^-1) are clamped before evaluating the
# drag law, whose 2.70/U term would otherwise diverge
min_wind_speed = 0.5

# number of time slices to process at once when averaging the stress
time_chunk_size = 24
```

The `viz` step is further controlled by the `[jra55_viz_taux]`,
`[jra55_viz_tauy]` and `[jra55_viz_tau_mag]` sections, each of which supports
the standard Polaris colormap options described in
{ref}`dev-visualization-global`.

### cores

Both steps run serially.

(ocean-realistic-global-init)=

## init

The `init` task creates a mesh-specific ocean initial condition (and, for
Omega, a vertical-coordinate file) from the WOA23 hydrography and the culled
mesh from `e3sm/init`, together with a surface forcing file from the JRA55-do
wind stress.  There is one task for each base and unified mesh:

```bash
polaris setup -t ocean/spherical/realistic_global/<mesh_name>/init/task ...
```

The target model, MPAS-Ocean or Omega, is set by the `[ocean] model` config
option, which `polaris setup` takes from `--model` or detects from the build
given with `-p`.

### description

The task runs the `e3sm/init` steps that build and cull the mesh and remap
its topography (see {ref}`e3sm-init-topo-tasks`), the steps of the `woa23`
and `jra55` tasks, which read their products from the cache, and then these
steps of its own:

1. `cull_topo` moves the remapped topography from the base mesh onto the
   culled ocean mesh.
2. `woa23_map` and `remap_woa23` remap the WOA23 conservative temperature and
   absolute salinity to the culled mesh.
3. `jra55_map` and `remap_jra55` remap the JRA55-do wind stress to the culled
   mesh.  The step fails if the mapping leaves any cell uncovered.
4. `pstar_init` builds the p-star vertical coordinate together with the
   temperature and salinity on it, since each depends on the other through
   the equation of state.  It also fits the bathymetry to the depths the
   vertical grid can represent and fills isolated bathymetry holes.
5. `initial_state` writes `mesh.nc`, `init.nc` and, for Omega,
   `vert_coord.nc`.
6. `forcing` writes `forcing.nc` with the wind stress on the mesh.
7. `viz` writes sanity-check plots and ParaView exports for the initial
   condition and vertical coordinate: an `initial_state_summary.png` figure of
   histograms, a `vertical_coordinate.png` structure figure, global maps of
   temperature and salinity at several depths (plus surface and seafloor) and
   of topography and column diagnostics, vertical transects across the major
   ocean basins, and `xdmf/` subdirectories for ParaView.  For Omega, native
   surface/bottom pressure maps and a TEOS-10 in-situ density
   (stratification) check are also produced.  Global maps of the on-mesh wind
   stress components and magnitude are also written, which is where remapping
   artifacts would show up.

On large meshes, `viz` is the most expensive step: it took 78 minutes of a
run of about 2.5 hours on `u-oi6to18-lr6to10`.  It runs only in this task;
other workflows that reuse the init steps leave it out.

### mesh

Any of the base meshes ({ref}`mesh-base-mesh-task`) or unified meshes
({ref}`users-mesh-unified-base-mesh`), culled to the ocean and sea-ice domain
by `e3sm/init`.

### vertical grid

The default is the 80-layer E3SMv1 reference grid with the p-star coordinate
(see {ref}`ocean-p-star`) and partial bottom cells.  The 240 km meshes use a
cheaper 16-level grid instead (see {ref}`ocean-realistic-global-mesh-configs`).

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = 80layerE3SMv1

# the type of vertical coordinate
coord_type = p-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = partial

# the minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

# Minimum number of vertical levels a valid column must contain (3 is the
# practical minimum for baroclinic dynamics).  Also sets the minimum depth
# clamp together with min_bottom_depth.
min_vert_levels = 3

# Minimum geometric water-column depth (m); cells shallower than this (or than
# the depth needed for min_vert_levels layers) are clamped to it.
min_bottom_depth = 10.0
```

Columns deeper than the reference grid can represent are made shallower to
fit it.

### initial conditions

Temperature and salinity come from the extrapolated WOA23 January
climatology built by the {ref}`ocean-realistic-global-woa23` task.  They are
conservative temperature and absolute salinity for Omega, and potential
temperature and practical salinity for MPAS-Ocean.  The ocean starts at rest,
with the sea surface at zero height.  Ice-shelf cavities are not supported.

### forcing

`forcing.nc` holds constant-in-time wind stress from the
{ref}`ocean-realistic-global-jra55` task: `SfcStressZonal` and
`SfcStressMeridional` for Omega, `windStressZonal` and `windStressMeridional`
for MPAS-Ocean.  Both models take zonal and meridional components at cell
centers and project onto edges themselves.  Surface restoring and the thermal
and freshwater fluxes are future work, as are the forward-model settings that
apply the forcing.

### time step and run duration

N/A. This task does not run the ocean model.

### config options

```cfg
[realistic_global_init]
# Approximate number of MPAS cells to target per MPI task when building
# the WOA23 and JRA55-do remapping weights with mbtempest / ESMF.  Building
# weights is a purely horizontal, geometric problem with no vertical
# structure, so these counts are much larger than the ~200 cells per core
# used to size forward runs.
remap_cells_per_task = 10000

# Maximum cells per task, used to compute the minimum task count (min_tasks).
remap_min_cells_per_task = 50000


# Options related the ocean component
[ocean]

# Equation of state type, defaults to mpas-ocean default
eos_type = teos-10


# Options related to the Coriolis force
[coriolis]

# Coriolis type for a realistic global (Earth-rotation) mesh, giving
# f = 2 * omega * sin(latitude)
type = spherical


# Options for the realistic global init visualization step
[realistic_global_init_viz]

# Projection for the global maps, must be supported by polaris.viz
projection = Robinson

# Longitude of the center of the global maps
central_longitude = 200.

# Depths (m below the surface) at which to plot global temperature/salinity
# maps.  One vertical level is selected per depth; its actual depth may vary.
depths = 0, 100, 500, 1000, 2000, 4000

# the type of norm used in the colormaps (set per-variable at run time)
norm_type = linear

# additional arguments to provide to the colormap norm (set at run time)
norm_args = {}


# Vertical transects to plot, crossing relevant ocean basins.  Each named
# transect is a list of an even number (>= 4) of values giving alternating
# lon, lat waypoints in degrees (a straight line uses two waypoints; a zonal
# circumnavigation needs intermediate waypoints).
[realistic_global_init_viz_transects]

# comma-separated list of transects to plot (each defined as an option below)
transects = atlantic_meridional, pacific_meridional, indian_meridional,
    southern_ocean_zonal

# Atlantic meridional section near 30 W
atlantic_meridional = -30.0, -60.0, -30.0, 65.0

# Pacific meridional section near 150 W
pacific_meridional = -150.0, -60.0, -150.0, 60.0

# Indian meridional section near 80 E
indian_meridional = 80.0, -60.0, 80.0, 25.0

# Southern Ocean zonal section near 60 S (waypoints around the globe)
southern_ocean_zonal = -180.0, -60.0, -90.0, -60.0, 0.0, -60.0, 90.0, -60.0,
    180.0, -60.0
```

The mapping steps use the `map_tool` option in the `[mapping]` section,
`moab` by default.  The colormap and its limits for each `viz` plot are set at
run time from the variable and the range of its data, so the
`[realistic_global_init_viz]` colormap options are not meant to be edited.

(ocean-realistic-global-mesh-configs)=

### per-mesh config options

Some config options need to differ from one mesh to the next.  These live in
one optional file per mesh, `<mesh_name>.cfg`, under
`polaris/tasks/ocean/realistic_global/mesh_configs`.  When a
`realistic_global` task is set up, the options for its mesh are added *after*
the task's own config file, so they override the defaults.  Most meshes have
no file there at all and simply use the defaults; you can still override any
option for a single mesh in your own user config file.

These are separate from the per-mesh files in `polaris/mesh/spherical/unified`.
The two are joined by the mesh name but have different owners: the mesh
component describes the mesh itself (resolutions, river networks, sizing
fields, total cell count), while the ocean component describes what the ocean
does on that mesh.  An option specific to the ocean belongs in
`mesh_configs`, not in the mesh component.

Currently:

- `qu240km`, `icos240km` and `u-oi240-lr240` replace the default 80-layer
  vertical grid with a cheap 16-level `tanh_dz` grid with a 3000 m bottom
  depth.  The shallow ocean is deliberate: these coarse meshes exist for fast
  smoke-testing of E3SM, Omega and MPAS-Ocean rather than for physically
  realistic simulations.
- All four unified meshes set `culled_ocean_cell_count`, the approximate size
  of the ocean + sea-ice culled mesh that the ocean model actually runs.  It is
  used to size MPI task counts and is smaller than the full mesh, which
  includes land and river-channel refinement that is culled away first.

For example, `u-oi240-lr240.cfg` contains:

```cfg
# Ocean-specific properties of this mesh
[realistic_global_mesh]

# Approximate cell count of the ocean + sea-ice culled mesh that the ocean
# model actually runs, used to size ocean MPI task counts (ntasks/min_tasks).
culled_ocean_cell_count = 7500


# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = tanh_dz

# Number of vertical levels
vert_levels = 16

# Depth of the bottom of the ocean
bottom_depth = 3000.0

# The minimum layer thickness
min_layer_thickness = 3.0

# The maximum layer thickness
max_layer_thickness = 500.0
```

Options the per-mesh file does not set (`coord_type`, `min_vert_levels`,
`min_bottom_depth`, and so on) are inherited from the task's config file as
usual.

### cores

`woa23_map` and `jra55_map` run on MPI tasks sized from the mesh's ocean-culled
cell count: one task per `remap_cells_per_task` cells, and no fewer than one
per `remap_min_cells_per_task` cells.  The other steps of this task run
serially.

(ocean-realistic-global-analysis-members)=

## analysis_members

These tasks perform a short forward run on a realistic global mesh with the
global-statistics analysis member enabled, then plot time series of the
resulting statistics.  Their main purpose is to compare the analysis-member
output of MPAS-Ocean and Omega on the same mesh and initial condition.

A task is defined for each of two meshes:

| mesh | cells | time step | barotropic step | run duration |
|------|-------|-----------|-----------------|--------------|
| `QU.240km` | 7,153 | 2 h | 4 min | 5 days |
| `EC30to60E2r2` | 236,853 | 30 min | 1 min | 1 day |

They can be set up with, e.g.:

```bash
polaris setup -t ocean/spherical/realistic_global/QU.240km/analysis_members_test ...
```

### description

Each task contains three steps:

1. `forward` runs the ocean model from a cached initial condition, writing
   both a regular `output.nc` history file and the global statistics produced
   by the analysis member.
2. `global_stats` plots time series of the minimum, maximum, mean and standard
   deviation of each state variable, both as absolute values and as anomalies
   relative to the initial value.  This step is not run by default.
3. `viz` plots global maps of the state variables at the beginning and end of
   the run, along with the zonal and meridional wind stress.  This step is not
   run by default.

The `global_stats` step accounts for a difference between the two models:
Omega writes the standard deviation directly, whereas MPAS-Ocean writes the
root-mean-square, from which the standard deviation is computed.

WARNING: As of Omega commit [061d0ab](https://github.com/E3SM-Project/Omega/commit/061d0ab90b2027ac584b997292b3911fa3755af3),
Omega does not area- or volume-weight the global stats while MPAS-Ocean does.
Thus, the two models' stats cannot be directly compared.


### mesh

The meshes are standard E3SM global ocean meshes downloaded from the Polaris
input database rather than generated by the task: the quasi-uniform 240-km
`QU.240km` mesh and the eddy-closure `EC30to60E2r2` mesh, which varies from
30 km to 60 km.

### vertical grid

The vertical grid is the one supplied with the cached initial condition for
each mesh, so there are no vertical-grid config options for these tasks.

### initial conditions

The initial condition is a cached, model-specific file from the
`realistic_global` section of the Polaris input database. For Omega, a
TEOS-10 initial condition is used and the same file supplies the mesh,
vertical coordinate and initial state. For MPAS-Ocean, a `zerovel` (zero
initial velocity) file supplies the mesh and initial state.

### forcing

Zonal and meridional wind stress are read from the initial-condition file and
applied through bulk wind stress. Vertical mixing uses CVMix with convection
and shear mixing enabled, and a constant implicit bottom drag coefficient of
1.0e-3 is applied.

### time step and run duration

The time step and run duration are set per mesh as shown in the table above.
The forward run uses the split-explicit time stepper (`SplitExplicitRK2` in
Omega), so each baroclinic step is 30 barotropic substeps long and divides a
day evenly.  Output, including the global statistics, is written once per day.

### config options

```cfg
[ocean]

# Equation of state type
eos_type = teos-10

[realistic_global]

# Time step duration per kilometer [s]
dt_per_km = 3.0
```

The `viz` step is controlled by the
`[realistic_global_viz_temperature]`, `[realistic_global_viz_salinity]`,
`[realistic_global_viz_layerThickness]`, `[realistic_global_viz_windStress]`
and `[realistic_global_viz_kineticEnergyCell]` sections, each of which
supports the standard Polaris colormap options described in
{ref}`dev-visualization-global`.

### cores

The number of cores used by the `forward` step is determined
algorithmically from the number of cells in the mesh. The `global_stats` and
`viz` steps run serially.

(ocean-realistic-global-restart)=

## restart

This task checks that splitting a run across a restart leaves the history
output alone.  It is a regression test for
[Omega #482](https://github.com/E3SM-Project/Omega/issues/482), where a run
continued from a restart silently overwrote the history frames written before
the restart instead of appending to them, leaving a file that was well formed
and simply missing the earlier half of the run.

It can be set up with:

```bash
polaris setup -t ocean/spherical/realistic_global/QU.240km/restart ...
```

### description

The task contains four steps:

1. `full_run` covers the whole four-hour period in one go.
2. `first_segment` covers the first two hours and writes a restart.
3. `second_segment` continues from that restart and covers the last two hours,
   appending its history frames to the ones `first_segment` left behind.
4. `validate` compares the history of the restart chain with the history of
   the full run.

Each segment writes its restart into a directory of its own under the task's
`restarts` directory, and a continuing segment reads its predecessor's.
`second_segment` starts from a copy of `first_segment`'s `output.nc`, so that
it finds on disk what a continuation run would find: a history file that
already holds the earlier frames and has to be appended to.

`validate` checks two things, because a restart can go wrong in two ways.  The
time axis has to hold every frame of the whole period, in increasing order,
which is what #482 broke.  The state then has to match the uninterrupted run,
which is the usual exact-restart check.

### mesh

The `QU.240km` quasi-uniform 240-km mesh, downloaded from the Polaris input
database, as for the `analysis_members` tasks.

### vertical grid

The vertical grid is the one supplied with the cached initial condition.

### initial conditions

A cached TEOS-10 Omega initial condition from the `realistic_global` section
of the Polaris input database, which supplies the mesh, vertical coordinate
and initial state.

### forcing

As for the `analysis_members` tasks: zonal and meridional wind stress from the
initial-condition file, applied through bulk wind stress.

### time step and run duration

The task uses the split-explicit time stepper (`SplitExplicitRK2` in Omega)
with a 1-hour baroclinic and a 3-minute barotropic time step, and a biharmonic
momentum viscosity of 1.0e15 m^4/s, the settings of the year-long QU240 runs
that the ocean analysis is tested on.  Each segment runs for two hours and the
full run for four, with a history frame every hour, so each segment writes two
frames and the whole period has four.  The period is short on purpose: the
task is about how the model writes its history across a restart, not about the
circulation, and it is meant to be cheap enough for the pull-request suite.

### config options

```cfg
[ocean]

# Equation of state type
eos_type = teos-10

[realistic_global]

# Time step duration per kilometer [s]
dt_per_km = 3.0
```

### cores

The number of cores used by each forward step is determined algorithmically
from the number of cells in the mesh.  The `validate` step runs serially.
