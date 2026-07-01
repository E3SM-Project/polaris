(ocean-realistic-global)=

# realistic_global

The `realistic_global` task group contains tasks that use realistic global
ocean meshes, bathymetry and forcing. It currently contains three kinds of
tasks:

- {ref}`ocean-realistic-global-woa23`, a mesh-independent preprocessing task
  that builds a reusable World Ocean Atlas 2023 (WOA23) hydrography product on
  the native 0.25-degree latitude-longitude grid.
- {ref}`ocean-realistic-global-init`, which creates mesh-specific ocean initial
  conditions from that hydrography and the culled mesh from `e3sm/init`.
- {ref}`ocean-realistic-global-analysis-members`, short forward runs on
  realistic global meshes that exercise the global-statistics analysis member
  and compare its output between MPAS-Ocean and Omega.

## supported models

The `woa23` task is model-independent and does not require either MPAS-Ocean
or Omega to be built.

The `init` and `analysis_members` tasks support both MPAS-Ocean and Omega.

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

(ocean-realistic-global-init)=

## init

The `init` task creates a mesh-specific ocean initial condition (and, for
Omega, a vertical-coordinate file) from the WOA23 hydrography and the culled
mesh from `e3sm/init`.  One `realistic_global_init` task is registered per MPAS
mesh; the target model (MPAS-Ocean or Omega) is set by the `[ocean] model`
config option.

### visualization

The task ends in a `viz` step that runs by default and writes sanity-check
plots and ParaView exports for the initial condition and vertical coordinate:
an `initial_state_summary.png` figure of histograms, a
`vertical_coordinate.png` structure figure, global maps of temperature and
salinity at several depths (plus surface and seafloor) and of topography and
column diagnostics, vertical transects across the major ocean basins, and
`xdmf/` subdirectories for ParaView.  For Omega, native surface/bottom pressure
maps and a TEOS-10 in-situ density (stratification) check are also produced.

### config options

```cfg
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
# lon, lat waypoints in degrees.
[realistic_global_init_viz_transects]

# comma-separated list of transects to plot (each defined as an option below)
transects = atlantic_meridional, pacific_meridional, indian_meridional,
    southern_ocean_zonal

atlantic_meridional = -30.0, -60.0, -30.0, 65.0
pacific_meridional = -150.0, -60.0, -150.0, 60.0
indian_meridional = 80.0, -60.0, 80.0, 25.0
southern_ocean_zonal = -180.0, -60.0, -90.0, -60.0, 0.0, -60.0, 90.0, -60.0,
    180.0, -60.0
```

(ocean-realistic-global-analysis-members)=

## analysis_members

These tasks perform a short forward run on a realistic global mesh with the
global-statistics analysis member enabled, then plot time series of the
resulting statistics.  Their main purpose is to compare the analysis-member
output of MPAS-Ocean and Omega on the same mesh and initial condition.

A task is defined for each of two meshes:

| mesh | cells | time step | run duration |
|------|-------|-----------|--------------|
| `QU.240km` | 7,153 | 10 min | 10 days |
| `EC30to60E2r2` | 236,853 | 45 s | 1 day |

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
Output, including the global statistics, is written once per day.

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
