(ocean-realistic-global)=

# realistic_global

This category contains ocean preprocessing tasks that are upstream of any
particular MPAS mesh.  The `woa23` task builds a reusable World Ocean Atlas
2023 (WOA23) hydrography product on the native 0.25-degree latitude-longitude
grid, and the `jra55` task builds a reusable wind-stress product on the native
JRA55-do TL319 grid.

## supported models

This task is model-independent and does not require either MPAS-Ocean or
Omega to be built.

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

The task is organized into three inspectable steps:

1. `combine_topo` from the `e3sm/init` component is used to combine topography
   GEBCO and Bedmap3 datasets on the WOA23 0.25-degree latitude-longitude grid.
2. `combine` creates `woa_combined.nc` by combining January and annual WOA23
   in-situ temperature and practical-salinity fields, then deriving
   conservative temperature and absolute salinity.
3. `extrapolate` creates the final
   `woa23_decav_0.25_jan_extrap.nc` product.

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
```

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
`initial_condition_database`.  Once the derived product is in the Polaris
cache database, this happens only when you deliberately regenerate it, and
ordinary users of the `init` task get the few-MB product from the Polaris
server instead.
:::

The stress is computed at every 3-hourly step and then time-averaged, rather
than computing the stress of the time-mean wind.  Averaging the wind first
discards the gust contribution and underestimates the stress in the storm
tracks, which is why the 3-hourly data is needed at all.  The bulk formula is
the Large and Yeager (2004, 2009) neutral 10-m drag law; the stability
correction, the ocean-current-relative wind and any sea-ice drag distinction
are deliberately omitted as second-order for this purpose.

### steps

1. `stress` downloads the raw winds and writes `jra55_stress.nc` on the native
   TL319 grid.  Cached by default.
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

### config options

```cfg
# Options related to generating a reusable JRA55-do wind-stress product
[jra55]

# the input4MIPs source and version of the JRA55-do dataset
source_id = MRI-JRA55-do-1-5-0
version = v20200916

# the year and month to average
year = 1958
month = 1

# air density used in the bulk formula (kg m^-3)
rho_air = 1.22

# wind speeds below this value (m s^-1) are clamped before evaluating the
# drag law, whose 2.70/U term would otherwise diverge
min_wind_speed = 0.5
```

(ocean-realistic-global-init)=

## init

The `init` task creates a mesh-specific ocean initial condition (and, for
Omega, a vertical-coordinate file) from the WOA23 hydrography and the culled
mesh from `e3sm/init`, together with a surface forcing file from the JRA55-do
wind stress.  One `realistic_global_init` task is registered per MPAS
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
Global maps of the on-mesh wind stress components and magnitude are also
written, which is where remapping artifacts near the North Pole would show up.

### surface forcing

The task ends with a `forcing` step that writes `forcing.nc` containing the
wind stress on the mesh: `SfcStressZonal` and `SfcStressMeridional` for Omega,
`windStressZonal` and `windStressMeridional` for MPAS-Ocean.  Both models take
zonal and meridional components at cell centres and project onto edges
themselves, so no vector rotation happens in Polaris.

Only wind stress is written.  Surface restoring and the thermal and freshwater
fluxes are future work, as are the forward-model settings that switch the
forcing on.

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

- `qu240km`, `icos240km` and `u.oi240.lr240` replace the default 80-layer
  vertical grid with a cheap 16-level `tanh_dz` grid with a 3000 m bottom
  depth.  The shallow ocean is deliberate: these coarse meshes exist for fast
  smoke-testing of E3SM, Omega and MPAS-Ocean rather than for physically
  realistic simulations.
- All four unified meshes set `culled_ocean_cell_count`, the approximate size
  of the ocean + sea-ice culled mesh that the ocean model actually runs.  It is
  used to size MPI task counts and is smaller than the full mesh, which
  includes land and river-channel refinement that is culled away first.
- All four unified meshes, plus `qu240km` and `icos240km`, set the
  resolution-dependent forward-run options described under
  [forward](#ocean-realistic-global-forward): the horizontal mixing
  coefficients, how mixing is scaled across the mesh, which eddy
  parameterizations are active and, where the default scaling is not
  appropriate, the time step.  The three 240 km meshes are qualitatively the
  same mesh and share the same values.

For example, `u.oi240.lr240.cfg` contains:

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

(ocean-realistic-global-forward)=

## forward

A forward run of the ocean model selected by the `[ocean] model` config option
(MPAS-Ocean or Omega), starting from a `realistic_global` initial condition.
The `short` run is a one-day smoke test:
it checks that the model runs stably on the mesh and initial condition, not that
the simulation is physically interesting.

There is no surface forcing yet, so the run is a spin-down from the initial
condition.

### physics options

The horizontal mixing coefficients, the eddy parameterizations and the way
mixing is scaled across a variable-resolution mesh all depend on the mesh, so
they are config options rather than fixed values, and most meshes override them
in their [per-mesh config file](#ocean-realistic-global-mesh-configs).  The
defaults follow how these meshes are configured in E3SM.

A coefficient and its on/off switch are a single option: leaving `mom_del2`
blank turns harmonic momentum mixing off, and giving it a value turns it on with
that coefficient.  This matters more than it might seem — the model defaults
leave horizontal mixing off entirely, and a global run without it grows
grid-scale noise until it produces NaNs.

`hmix_scaling` chooses how the coefficients are scaled across the mesh:
`none` uses them as given, `ref_cell_width` scales them by the cell width
relative to `hmix_ref_cell_width`, and `scale_with_mesh` scales them with the
local mesh density.  Quasi-uniform meshes generally use `ref_cell_width`, and
variable-resolution meshes `scale_with_mesh`.

Some settings are not config options because they should not vary: they are
pinned in `forward.yaml` purely so that MPAS-Ocean and Omega agree.  Where the
two models' own defaults differ, the MPAS-Ocean default wins — horizontal
tracer advection order is pinned to 3 (Omega defaults to 2), and bottom drag to
implicit constant drag with a coefficient of 1e-3 (Omega has no bottom drag by
default).  The CVMix convection and shear-mixing parameters are pinned too;
those values already match both models, and stating them is what keeps them
from drifting apart.

Gent-McWilliams, Redi, the Leith closure and frazil ice are applied only for
MPAS-Ocean.  Omega has no equivalent for any of them and is not expected to gain
GM or Redi, so the two models deliberately differ here; the `short` runs are
smoke tests rather than a model intercomparison, and a careful comparison would
need its own config options chosen for that purpose.

### time integrator

The time integrator is the one setting chosen per model rather than shared:
`mpaso_time_integrator` defaults to `split_explicit_ab2` and
`omega_time_integrator` to `RK4`.  Omega has no split time stepper yet, so
`RK4` (translated to `RungeKutta4`) is the only integrator it supports, while
MPAS-Ocean needs split time stepping to make the month-long spin-ups that build
on this workflow affordable.  Both options use neutral (MPAS-Ocean) naming, and
an `omega_time_integrator` that Omega does not support is an error at run time
rather than at setup, so the option can still be changed after setting a task
up.  Once Omega gains a split integrator the two are expected to become the
same again.

### time step and run duration

The time step is derived from the mesh's minimum resolution: `dt_per_km` gives
the baroclinic step and `btr_dt_per_km` the barotropic subcycling step, each in
seconds per kilometre.  Setting `dt` or `btr_dt` overrides the derived value.
Meshes whose stable time step does not follow the default scaling set
`dt_per_km` and `btr_dt_per_km` in their per-mesh config file.

Because the integrator is chosen per model, so is the time step.  A split
integrator advances on the long baroclinic step and subcycles the barotropic
mode on the short one; a non-split integrator such as `RK4` has no subcycling
and so must advance on the short barotropic step.  With the defaults, MPAS-Ocean
therefore takes a `dt_per_km` step and Omega a much shorter `btr_dt_per_km` one
on the same mesh.

### config options

```cfg
# Options for realistic global ocean forward runs
[realistic_global_forward]

# The time integrator, chosen separately for each ocean model because the two
# models do not support the same integrators.  Both are given in neutral
# (MPAS-Ocean) naming; the Omega one is translated to the Omega name.
#
# MPAS-Ocean uses split time stepping ('split_explicit_ab2' or 'RK4'), which is
# far cheaper for the long spin-ups this workflow feeds into.  Omega has no
# split time stepper yet, so only 'RK4' (translated to 'RungeKutta4') is
# supported there and anything else raises an error at run time.  Once Omega
# gains a split integrator, the two options are expected to become the same
# again.
#
# The time step follows from this choice (see dt_per_km and btr_dt_per_km), so
# the two models generally run with different time steps.
mpaso_time_integrator = split_explicit_ab2
omega_time_integrator = RK4

# Run duration as an MPAS-style duration string (DDDD_HH:MM:SS)
run_duration = 0001_00:00:00

# Interval between writes to the output stream (DDDD_HH:MM:SS)
output_interval = 0001_00:00:00

# Interval between writes to the restart stream (DDDD_HH:MM:SS); leave blank to
# default to run_duration (a single restart at the end of the run)
restart_interval =

# Baroclinic time step per km of the mesh minimum resolution (s/km).  Only used
# for split time stepping (split_explicit_ab2).
dt_per_km = 30.0

# Barotropic time step per km of the mesh minimum resolution (s/km).  Used as
# config_btr_dt for split time stepping, and as the single time step for
# non-split integrators such as RK4 and Omega's RungeKutta4.
btr_dt_per_km = 1.5

# Explicit baroclinic/barotropic time steps (DDDD_HH:MM:SS) that override the
# *_per_km values when set; leave blank to derive from *_per_km and the mesh
# minimum resolution
dt =
btr_dt =

# Rayleigh damping coefficient (1/s); leave blank for no Rayleigh damping
Rayleigh_damping_coeff =

# Horizontal mixing coefficients.  A blank value turns the corresponding term
# off; a number turns it on with that coefficient.  These are usually set per
# mesh, since the right values depend on the resolution.
#   mom_del2, mom_del4: harmonic and biharmonic momentum viscosity (m^2/s,
#     m^4/s)
#   tracer_del2, tracer_del4: harmonic and biharmonic tracer diffusivity
#     (m^2/s, m^4/s)
mom_del2 = 1.0e3
mom_del4 = 1.2e11
tracer_del2 =
tracer_del4 =

# Whether to use the Leith closure for harmonic momentum mixing
use_Leith_del2 = False

# How horizontal mixing coefficients are scaled across the mesh.  One of:
#   none            - the coefficients above are used as given
#   ref_cell_width  - scaled by the cell width relative to hmix_ref_cell_width
#   scale_with_mesh - scaled with the local mesh density
hmix_scaling = none

# The reference cell width (m), used only when hmix_scaling = ref_cell_width
hmix_ref_cell_width = 30.0e3

# Whether to use the Gent-McWilliams eddy transport parameterization, and the
# closure and constant kappa (m^2/s) it uses.  Leave the closure and kappa blank
# to use the model defaults.  MPAS-Ocean only; Omega has no GM.
use_GM = True
GM_closure =
GM_constant_kappa =

# Whether to use Redi isopycnal mixing.  MPAS-Ocean only; Omega has no Redi.
use_Redi = True

# Whether to form frazil ice.  MPAS-Ocean only.
use_frazil_ice_formation = False

# Simulation start time (config_start_time)
start_time = 0001-01-01_00:00:00
```
