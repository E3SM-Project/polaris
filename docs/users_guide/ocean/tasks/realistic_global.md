(ocean-realistic-global)=

# realistic_global

The `realistic_global` task group contains tasks that use realistic global
ocean meshes, bathymetry and forcing. It currently contains four kinds of
tasks:

- {ref}`ocean-realistic-global-woa23`, a mesh-independent preprocessing task
  that builds a reusable World Ocean Atlas 2023 (WOA23) hydrography product on
  the native 0.25-degree latitude-longitude grid.
- {ref}`ocean-realistic-global-jra55`, a mesh-independent preprocessing task
  that builds a reusable wind-stress product on the native JRA55-do TL319 grid.
- {ref}`ocean-realistic-global-init`, which creates mesh-specific ocean initial
  conditions from that hydrography and forcing together with the culled mesh
  from `e3sm/init`.
- {ref}`ocean-realistic-global-forward`, short forward runs from either of two
  sources of initial condition: the `init` workflow above, or a cached file
  downloaded from the Polaris input database.

## supported models

The `woa23` and `jra55` tasks are model-independent and do not require either
MPAS-Ocean or Omega to be built.

The `init` and forward tasks support both MPAS-Ocean and Omega.

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
fluxes are future work.  The settings that switch the forcing on in the model
are described under [forward](#ocean-realistic-global-forward).

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

## forward and cached_forward

A forward run of the ocean model selected by the `[ocean] model` config option
(MPAS-Ocean or Omega), starting from a `realistic_global` initial condition.
The `short` step is a brief run: it checks that the model runs stably on the
mesh and initial condition, not that the simulation is physically interesting.
Two further steps, `global_stats` and `viz`, plot the run's statistics and its
state; neither is run by default.

The two tasks are built from the same steps and differ only in where the
initial condition comes from — and, because of that, in what they are for.

`forward` runs on a mesh and initial condition that
{ref}`ocean-realistic-global-init` builds, and can be set up for any mesh
Polaris knows how to build:

```bash
polaris setup -t ocean/spherical/realistic_global/qu240km/forward ...
```

`cached_forward` downloads a ready-made initial condition instead, so it runs
without the WOA23 remapping and topography culling the `init` chain does
first.  It is defined for the two meshes whose initial conditions have been
staged:

| mesh | cells | time step | run duration |
|------|-------|-----------|--------------|
| `QU.240km` | 7,153 | 10 min | 5 days |
| `EC30to60E2r2` | 236,853 | 45 s | 1 day |

```bash
polaris setup -t ocean/spherical/realistic_global/QU.240km/cached_forward ...
```

(ocean-realistic-global-forward-purposes)=

### what the two tasks are for

These are not two sizes of the same test.  They answer different questions,
and that is what decides how each is configured.

**`cached_forward` compares MPAS-Ocean with Omega.**  Both models start from
the same initial condition on the same mesh, so the interesting result is how
their answers differ.  Anything one model has that the other lacks works
against that, so these runs use only the physics Omega also has: no
Gent-McWilliams, no Redi, no KPP boundary layer, no submesoscale
parameterization, and MPAS-Ocean's default `pressure_and_zmid` pressure
gradient rather than `Jacobian_from_TS`.  Both models use RK4.

The list of things turned off describes what Omega lacks today, not a
considered choice of physics, and it should shrink as Omega gains
capabilities.

**`forward` tests the mesh itself, in E3SM, with MPAS-Ocean.**  Here the point
is that the mesh behaves the way it will in a real E3SM configuration, so these
runs use E3SM's physics: GM, Redi, KPP, the submesoscale parameterization and
`Jacobian_from_TS`, with the resolution-dependent mixing each mesh needs.
MPAS-Ocean uses split-explicit time stepping, which is what makes the long
spin-ups this task feeds into affordable.

Omega can run these too, but only as a smoke test.  It has no split-explicit
integrator, which makes RK4 and its short time step the only option and
dynamic adjustment impractical; and the physics it is missing means the
adjustment coefficients cannot yet be tuned in any meaningful way.

:::{note}
`cached_forward` is expected to be temporary.  Once Omega has the full physics
and the Polaris initialization workflow has been tested end to end, there will
be no reason to keep a separate task on hand-staged initial conditions, and
the comparison can be made on meshes Polaris builds itself.
:::

### surface forcing

The run is forced by time-invariant JRA55-do wind stress — written by the init
workflow's [`forcing` step](#ocean-realistic-global-init) for `forward`, and
carried inside the cached initial-condition file for `cached_forward`.  Wind
stress is the only forcing: there is no surface restoring and there are no thermal or
freshwater fluxes, so the tracers spin down from the initial condition while
the momentum input holds up a circulation.

`forcing.yaml` turns it on with `config_use_bulk_wind_stress`, which
`mpaso_to_omega.yaml` translates to Omega's `SfcStressForcingTendencyEnable`.
Both models default it to off, and it is set for every realistic global forward
run: there is no config option to run without wind forcing.

`forcing.yaml` also sets `config_bulk_wind_stress_interp_isotropic` for
MPAS-Ocean, on every forward run.  Both models take the stress at cell centres
and project it onto edges themselves, but not the same way by default:
MPAS-Ocean uses the two cells adjacent to an edge, and Omega uses four.  This
is set because four is what E3SM runs with today, so it is the E3SM-like
choice for the unified meshes; it also happens to be Omega's only option, so
the two models end up applying the same momentum without anything further
being said.  The isotropic form is slightly less accurate and Omega may not
keep it, so this is worth revisiting when that is decided.

Where the wind stress comes from is a separate question, answered by the
forward step's initial condition.  When it stages a forcing file of its own — as
the init workflow does — `forcing_streams.yaml` points each model's input stream
at the file named by the `[ocean_staged_files] forcing_filename` config option
(`forcing.nc` by default).  A cached initial condition carries the stress
inside the initial-condition file, so the same streams are pointed there
instead.  For MPAS-Ocean that is a `forcing` stream holding
just the two wind-stress variables, rather than the Registry's `forcing_data`
stream, which would also demand the sea-ice and atmospheric pressures and the
tracer restoring fields.

### output

The run writes `output.nc` at `output_interval` and a restart at
`restart_interval`.

`output.nc` holds more than the prognostic state.  For MPAS-Ocean it is the
tracers, velocity, layer thickness, kinetic energy and relative vorticity; for
Omega it is the `State`, `Tracers`, `AuxiliaryState`, `SshCell` and `Eos`
groups, which add the vorticity, divergence and del2 terms, the free surface
and the specific volume and buoyancy frequency.  The extra fields cost file
size and are worth it: without them a run that goes wrong can be seen to have
gone wrong but not diagnosed, and these runs exist partly to be compared
against each other.

It also writes a time series of the global minimum, maximum, mean and RMS of
the state variables, plus the global CFL number for MPAS-Ocean.  This is the
cheapest way to see a run going wrong before it NaNs, which matters most for
the longer spin-ups that build on this task.  MPAS-Ocean produces it through
the `globalStats` analysis member, in `global_stats.nc`, and Omega through its
`GlobalStats` analysis group, in `global_stats_1DayInstants` at the default
`stats_interval` — Omega treats the configured file name as a prefix and
appends the period and the kind of output, with no `.nc` extension.

The two files hold the same quantities under different variable names;
`polaris/ocean/model/mpaso_to_omega.yaml` maps between them.  One caveat there:
MPAS-Ocean's `rms*` is a root mean square while Omega's `SpatialStdDev` is a
standard deviation, so that pair is a name correspondence rather than an
equivalence.

Omega samples the statistics instantaneously rather than averaging them over
the period, because that is what the mapped variable names mean: Omega names a
time-averaged quantity `<name>_TimeMean<period>` and an instantaneous one
plainly `<name>`.  Averaging would also constrain `restart_interval`, since
Omega aborts unless the restart interval is a whole multiple of an averaging
period; instantaneous sampling carries no such constraint.  MPAS-Ocean writes
an instantaneous sample too, so the two are comparable.

MPAS-Ocean additionally writes the temperature-threshold mixed-layer depth at
`output_interval`, through the `mixedLayerDepths` analysis member, in
`mixed_layer_depths.nc`.  It is the standard first look at whether the surface
boundary layer is behaving.  Omega has no equivalent analysis member, so this
file is written only for MPAS-Ocean.

### physics options

The horizontal mixing coefficients, the eddy parameterizations and the way
mixing is scaled across a variable-resolution mesh all depend on the mesh, so
they are config options rather than fixed values, and most meshes override them
in their [per-mesh config file](#ocean-realistic-global-mesh-configs).  The
defaults follow how these meshes are configured in E3SM, which is what the
`forward` tasks want; `cached_forward` overrides several of them for the
reasons in {ref}`ocean-realistic-global-forward-purposes`.

A coefficient and its on/off switch are a single option: leaving `mom_del2`
blank turns harmonic momentum mixing off, and giving it a value turns it on with
that coefficient.  This matters more than it might seem — the model defaults
leave horizontal mixing off entirely, and a global run without it grows
grid-scale noise until it produces NaNs.

`hmix_scaling` chooses how the coefficients are scaled across the mesh.  `none`
uses them as given.  `ref_cell_width` makes them apply at `hmix_ref_cell_width`
and scale from there — as `cellWidth` for the `del2` coefficients and as
`cellWidth**3` for the `del4` ones.  A variable-resolution mesh wants
`ref_cell_width`; on a mesh whose cells are all near the reference width the two
are equivalent.

Set `hmix_ref_cell_width` per mesh to the resolution the coefficients were
chosen for.  For a variable-resolution mesh that is normally its *finest*
resolution, because that is what E3SM's per-grid `mom_del2` and `mom_del4`
values are referenced to — so `u.oi6to18.lr6to10` pairs E3SM's
`RRSwISC6to18E3r5` value of `3.2e09` with a 6 km reference, and
`u.oi.so12to30.lr10` pairs `SOwISC12to30E3r3`'s `1.18e10` with a 12 km one.
Both reproduce E3SM's viscosity as a function of cell width to within about 15%.

:::{note}
MPAS-Ocean spells this as two nested flags, and `ref_cell_width` sets **both**:
`config_hmix_use_ref_cell_width` is read only inside
`if (config_hmix_scaleWithMesh)`.  Setting the first without the second reads as
a request for width-based scaling and silently gets none at all.

MPAS-Ocean's third combination — `scaleWithMesh` with `use_ref_cell_width`
false — scales by the legacy `meshDensity` field instead.  Polaris does not
offer it, and it should not be used: **`meshDensity` is meaningless on E3SM v4
meshes**, which write it as uniformly 1.0, so that branch applies no scaling
either.
:::

`mom_del4_div_factor` scales the divergence part of the biharmonic momentum
operator alone, leaving its rotational part at `mom_del4`.  Blank leaves the
model default of 1.0, the true biharmonic.  Raising it damps the divergent
grid-scale mode — the one carrying C-grid checkerboard and gravity-wave noise —
without blurring the resolved eddy field, which is why E3SM uses 10 on its
eddying `RRSwISC6to18E3r5` mesh and nowhere else.  MPAS-Ocean only.

Some settings are not config options because they should not vary: they are
pinned in `forward.yaml` purely so that MPAS-Ocean and Omega agree.  Where the
two models' own defaults differ, the MPAS-Ocean default wins — horizontal
tracer advection order is pinned to 3 (Omega defaults to 2), and bottom drag to
implicit constant drag with a coefficient of 1e-3 (Omega has no bottom drag by
default).  The CVMix convection and shear-mixing parameters are pinned too;
those values already match both models, and stating them is what keeps them
from drifting apart.

Gent-McWilliams (`use_GM`), Redi (`use_Redi`), the KPP boundary layer
(`use_KPP`), the submesoscale eddy parameterization (`use_submesoscale`), the
Leith closure (`use_Leith_del2`), frazil ice (`use_frazil_ice_formation`) and
the pressure-gradient formulation (`pressure_gradient_type`) are applied only
for MPAS-Ocean.  Omega has no equivalent for any of them, and is not expected
to gain GM or Redi.

They are config options rather than fixed values precisely because the two
tasks want opposite answers — see
{ref}`ocean-realistic-global-forward-purposes`.  The defaults are the
E3SM-like ones, which is what `forward` wants; `cached_forward` turns them off
in its per-mesh config so that MPAS-Ocean and Omega stay comparable.  Several
of them are off by default in MPAS-Ocean itself, so leaving them alone would
not have given E3SM's configuration either.

Blank `pressure_gradient_type` leaves the MPAS-Ocean Registry default of
`pressure_and_zmid`, the ordinary counterpart to Omega's `Centered`;
`Jacobian_from_TS` is how E3SM runs and has no Omega equivalent.

`config_Redi_min_layers_diag_terms` is pinned to 0 in `forward.yaml` rather
than being an option — the Registry default of 6 skips the Redi diagnostic
terms in the top six layers, and Compass computes them everywhere.  It has an
effect only where Redi is on.

### time integrator

The time integrator is the one setting chosen per model rather than shared:
`mpaso_time_integrator` defaults to `split_explicit_ab2` and
`omega_time_integrator` to `RK4`.  Omega has no split time stepper yet, so
`RK4` (translated to `RungeKutta4`) is the only integrator it supports, while
MPAS-Ocean needs split time stepping to make the month-long spin-ups that build
on this workflow affordable.  The `cached_forward` tasks set
`mpaso_time_integrator = RK4` so that both models advance the same way, at the
cost of MPAS-Ocean taking the short step too.  Both options use neutral (MPAS-Ocean) naming, and
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
# Options related to the ocean component
[ocean]

# The equation of state.  The whole realistic_global family is TEOS-10, and it
# is stated here as well as in realistic_global_init.cfg so that a forward task
# is self-contained: a run from a cached initial condition never sets the init
# workflow's config up at all, and still has to name the equation of state to
# find the right file in the database.
eos_type = teos-10


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

# Interval between writes of the global statistics (DDDD_HH:MM:SS).  These are
# a handful of scalars, so they are written far more often than the 3-D output
# and are what makes an excursion within a run visible.  Drives MPAS-Ocean's
# globalStatsOutput stream and Omega's GlobalStats snapshot period alike; for
# Omega it must be a whole number of seconds.
stats_interval = 0001_00:00:00

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

# Rayleigh damping coefficient (1/s); leave blank for no Rayleigh damping.
# MPAS-Ocean only: Omega has no Rayleigh damping, so a non-blank value is an
# error there (https://github.com/E3SM-Project/Omega/issues/495)
damping =

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

# A factor applied to the divergence part of the biharmonic momentum operator
# alone, leaving its rotational part at mom_del4.  Blank leaves the model
# default of 1.0, which is the true biharmonic.  Raising it damps the divergent
# grid-scale mode -- the one that carries C-grid checkerboard and gravity-wave
# noise -- without blurring the resolved eddy field, which is why E3SM uses 10
# on its eddying RRSwISC6to18E3r5 mesh and nowhere else.
# MPAS-Ocean only.
mom_del4_div_factor =

# Whether to use the Leith closure for harmonic momentum mixing
use_Leith_del2 = False

# How horizontal mixing coefficients are scaled across the mesh.  One of:
#   none            - the coefficients above are used as given
#   ref_cell_width  - the coefficients above apply at hmix_ref_cell_width, and
#                     scale as cellWidth for del2 and cellWidth**3 for del4
# A variable-resolution mesh wants ref_cell_width; on a mesh whose cells are
# all near the reference width the two are equivalent.
#
# MPAS-Ocean spells this as two nested flags, and ref_cell_width sets *both*:
# config_hmix_use_ref_cell_width is read only when config_hmix_scaleWithMesh is
# true.  Setting only the former reads as a request for width-based scaling and
# silently gets none.
#
# MPAS-Ocean's third combination -- scaleWithMesh with use_ref_cell_width false
# -- scales by the legacy meshDensity field instead, and is deliberately not
# offered here.  E3SM v4 meshes, including every mesh Polaris builds, write
# meshDensity as uniformly 1.0, so that path silently applies no scaling at
# all.  Do not use it, and do not add a Polaris option for it.
hmix_scaling = none

# The reference cell width (m), used only when hmix_scaling = ref_cell_width.
# Set it per mesh to the resolution the coefficients above were chosen for --
# for a variable-resolution mesh that is normally its finest resolution, which
# is what E3SM's per-grid mom_del2 and mom_del4 values are referenced to.
hmix_ref_cell_width = 30.0e3

# Whether to use the Gent-McWilliams eddy transport parameterization, and the
# closure and constant kappa (m^2/s) it uses.  Leave the closure and kappa blank
# to use the model defaults.  MPAS-Ocean only; Omega has no GM.
use_GM = True
GM_closure =
GM_constant_kappa =

# Whether to use Redi isopycnal mixing.  MPAS-Ocean only; Omega has no Redi.
use_Redi = True

# Whether to use the CVMix KPP boundary-layer scheme.  MPAS-Ocean only; Omega
# has no boundary-layer scheme at all.
use_KPP = True

# Whether to use the submesoscale eddy parameterization.  MPAS-Ocean only.  On
# as in E3SM and in the Compass global_ocean tests; the MPAS-Ocean Registry
# default is off.
use_submesoscale = True

# The MPAS-Ocean horizontal pressure gradient formulation.  Leave blank for the
# Registry default of pressure_and_zmid, which is the ordinary counterpart to
# Omega's Centered.  Jacobian_from_TS is how E3SM runs and has no Omega
# equivalent.
pressure_gradient_type = Jacobian_from_TS

# Whether to form frazil ice.  MPAS-Ocean only.
use_frazil_ice_formation = False

# Whether to write density to the 3-D output stream.  MPAS-Ocean only; Omega
# writes specific volume through its Eos group instead.  On by default, since
# it is part of what makes the two models comparable on the same fields and a
# short run can afford it.  It is the only field in that stream with a switch
# of its own, because it is 3-D and is roughly 13% of the output volume, which
# starts to matter once a workflow writes the stream many times over.
output_density = True

# Simulation start time (config_start_time)
start_time = 0001-01-01_00:00:00
```

### mesh

`forward` runs on a mesh built by {ref}`ocean-realistic-global-init`, so the
mesh is whichever one the task is registered for.  `cached_forward` runs on the
standard E3SM mesh that comes with its cached initial condition: the
quasi-uniform 240-km `QU.240km`, or the eddy-closure `EC30to60E2r2`, which
varies from 30 km to 60 km.

### vertical grid

For `forward`, the vertical grid is the one the `init` workflow built, set by
the `[vertical_grid]` section of the mesh's
[per-mesh config file](#ocean-realistic-global-mesh-configs).  For
`cached_forward` it arrives with the cached initial condition, so those meshes
have no `[vertical_grid]` section at all.

### initial conditions

For `forward`, the mesh, vertical coordinate, initial state and wind-stress
forcing are the outputs of the `init` workflow's steps, which the task runs
first.

For `cached_forward`, a single model-specific file from the `realistic_global`
section of the Polaris input database supplies all of them.  MPAS-Ocean reads a
`zerovel` (zero initial velocity) file along with a prebuilt graph partition
file; Omega reads a TEOS-10 file converted from it, and partitions internally.

### cores

The number of cores used by the `short` step is determined algorithmically from
the number of cells in the mesh — read from the mesh file once it exists, and
estimated from the mesh definition before that.  The `global_stats` and `viz`
steps run serially.

(ocean-realistic-global-dynamic-adjustment)=

## dynamic_adjustment

The `dynamic_adjustment` task runs a sequence of short forward stages that
dissipate the fast waves introduced by the initial condition, producing a
relaxed restart suitable for a longer production run.  One
`realistic_global_dynamic_adjustment` task is registered per MPAS mesh; the
target model (MPAS-Ocean or Omega) is set by the `[ocean] model` config
option.

The task can be set up with:

```bash
polaris setup -t ocean/spherical/realistic_global/<mesh>/dynamic_adjustment ...
```

### description

Each stage is a forward run that restarts from the previous stage, with its own
run duration, time step, output/restart cadence, and (typically decreasing)
Rayleigh damping.  The stages are read from a schedule YAML: a mesh-specific
`<mesh_name>.yaml` when the mesh has one, and otherwise `default.yaml`.  Polaris
ships schedules for all four unified meshes — `u.oi240.lr240`, `u.oi30.lr10`,
`u.oi6to18.lr6to10` and `u.oi.so12to30.lr10` (the last three ported from
Compass' `ec30to60`, `rrs6to18` and `so12to30`).  `default.yaml` is what the
base meshes such as `icos240km` and `qu240km` fall back to; it is only two
stages, which is a quick check that a mesh runs rather than an adjustment worth
keeping.  The final stage, `simulation`, writes the relaxed restart, and its
`output.nc` is compared against a baseline when one is provided.

The number and settings of the stages come from the schedule, so a user can
retune them by editing the checked-in YAML or by pointing the `schedule` config
option at an alternate file before setup.  Because the Polaris step graph is
fixed at setup, changing the schedule requires re-running `polaris setup`.

### schedule format

A stage is a [`forward` run](#ocean-realistic-global-forward), so it starts from
the `[realistic_global_forward]` config options for the mesh — including the
[per-mesh overrides](#ocean-realistic-global-mesh-configs) — and the schedule
supplies only what varies from stage to stage.  The horizontal mixing
coefficients, the eddy parameterizations and the time integrators are therefore
the same as they would be for a `forward` run on that mesh, and are not repeated
in the schedule.

A schedule has a `shared` block of per-stage defaults and an ordered `stages`
block:

```yaml
dynamic_adjustment:
  shared:
    output_interval: 10_00:00:00
    restart_interval: 10_00:00:00
    start_time: 0001-01-01_00:00:00
  stages:
    damped_adjustment_1:
      run_duration: 10_00:00:00
      dt: 00:15:00
      btr_dt: 00:00:30
      damping: 1.0e-4
    simulation:
      run_duration: 10_00:00:00
      dt: 00:30:00
      btr_dt: 00:01:00
      # damping omitted => the config default, which is no Rayleigh damping
```

Every key must name a forward-run setting — a `ForwardStage` field, which is to
say a `[realistic_global_forward]` config option — and overrides that option for
that stage.  A key that names nothing is an error at setup rather than a silent
fall back to the config value, so a schedule cannot quietly go stale when an
option is renamed.  `run_duration` is the one key a stage must set, since the
restart chain's timing follows from it; `restart_interval` defaults to the
stage's own `run_duration` rather than to the config value, because each stage
has to write the restart the next one reads.  Time steps may instead be given per
km of mesh minimum resolution with `dt_per_km` / `btr_dt_per_km`.

Two cadences a stage cannot get wrong are checked at setup, because both fail
only after the model has run.  A `restart_interval` must put the stage's stop
time on MPAS-Ocean's restart alarm, which is measured from a fixed reference of
`0001-01-01_00:00:00` and not from where the stage starts — otherwise the
restart the next stage reads is never written.  And a `stats_interval` must be
no longer than the stage, or the statistics hold only the record written at
startup.  `output_interval` is not checked: an interval longer than the stage is
a legitimate way to say "no 3-D output during the damped stages", which is what
the ported Compass schedules do.

`start_time` belongs in the `shared` block: it is where the chain begins, and
each stage's own start time follows from the durations before it.  The remaining
restart settings (`do_restart`, `restart_in`, `restart_out`) are owned by the
chain and cannot be set by a schedule.

Rayleigh damping runs the other way round from the other options: it is off in
config (`damping` is blank) and turned on per stage by the schedule, so the
`simulation` stage gets an undamped run simply by omitting `damping`.

:::{warning}
Rayleigh damping is MPAS-Ocean only.  Omega has no equivalent
([Omega#495](https://github.com/E3SM-Project/Omega/issues/495)), so a stage that
sets `damping` raises when the configured model is Omega rather than running
undamped and reporting success.  An Omega dynamic adjustment therefore needs a
schedule with no damping at all, which is not what these shipped schedules are.
:::

### restart chaining

The stages share a `restarts` directory beside them in the task work directory.
Each stage writes `restarts/rst.<timestamp>.nc` at the end of its run and
declares it as an output; the next stage declares the same file as an input and
starts from it, so a break in the chain is caught before the model launches.

For MPAS-Ocean the restart stream is both an input and an output stream, so one
`filename_template` serves both directions: a restarting stage sets
`config_do_restart` and `config_start_time` to its predecessor's timestamp and
the template resolves to that file.  There is no restart-pointer file.

:::{warning}
The Omega side of restart chaining is written but has not been run.  Omega needs
a separate `RestartRead` stream, which `restart_streams.yaml` supplies, but its
restart filenames have no `.nc` extension and it has not been established
whether Omega appends one — so the restart files are declared as step inputs and
outputs for MPAS-Ocean only.  Separately,
[Omega#482](https://github.com/E3SM-Project/Omega/issues/482) has restarts and
history output interacting badly, with history output mangled across a restart;
its resolution will change how an Omega restart run has to be configured.
:::

### diagnostics and validation

A final `validate` step summarizes the sequence and then checks it, and a `viz`
step plots the underlying time series.

The summary is `dynamic_adjustment_stats.csv`, one row per stage, and the same
table is written to the step's log.  It is the quickest way to see whether the
damping ramp and the stage durations were chosen well: kinetic energy should be
falling and flattening from stage to stage, the tracer drift should be shrinking,
and nothing should be approaching a blow-up.  Columns ending `_in_stage` are the
extreme reached at any point during the stage; the rest are end-of-stage values.

The numbers come from each stage's global-statistics file wherever the
configured model reports them, because the model has already reduced them over
the whole domain at the `stats_interval` cadence — so an excursion in the middle
of a stage is visible, which it is not in an end-of-stage field.  That cadence is
deliberately separate from the 3-D `output_interval`: the statistics are a
handful of scalars, so they can be written far more often than the 3-D fields
without the output growing.  What the model does
not report is computed from `output.nc` instead, but only for maxima and minima,
which mean the same thing however they are obtained.  A volume-weighted mean does
not, so `kinetic_energy_mean` and `kinetic_energy_total` are left blank rather
than quietly replaced with an unweighted mean.

Omega's `GlobalStats` covers temperature, salinity, layer thickness and normal
velocity but has no kinetic energy, CFL number or volume-weighted sums, so those
columns are blank for an Omega run.  A blank means "this model does not report
it", not that something went wrong; the log says which source each metric came
from.

There are three checks.  Two are per stage and run in a `<stage>_check` step
immediately after that stage, so a stage that is already out of bounds stops the
sequence instead of costing the whole job:

* the maximum temperature in the stage must stay below `temperature_max`;
* the maximum CFL number in the stage must stay below `cfl_max`, which is what
  catches a stage whose time step is too long for the flow it produced.

Both report *when* the extreme occurred as well as how large it was.  That is
worth reading closely: an extreme "at the start of the stage, before any time
step" is in the initial condition, and no change to the schedule will fix it.

The third is made by the final `validate` step against the summary rows, since
no single stage can see it:

* the stage-over-stage *fractional change* in the mean kinetic energy must be
  shrinking over the last `ke_check_num_stages` transitions.

The last of those deserves a word, because the obvious check is the wrong one.
Requiring kinetic energy itself not to rise fails a perfectly healthy run: these
runs start from rest and are wind-forced, so the circulation spins up and
kinetic energy climbs for tens of days for reasons that have nothing to do with
the fast waves the adjustment removes.  What settling means here is that the
change is slowing.  The *mean* is used rather than the maximum because the
maximum is dominated by the transient released each time the damping steps down,
which decays within its own stage; and the *magnitude* of the change is used
rather than the growth ratio because a run converging from above and one
converging from below are both settling.

A constant growth rate passes this check — it detects acceleration rather than
growth, which is about as much as three or four stages can support.  The CFL and
temperature thresholds are what guard against a run that is simply diverging.

Each check is skipped, with a log line, when the configured model does not
report the quantity: Omega's `GlobalStats` has neither kinetic energy nor a CFL
number.  The settling check is also skipped below three stages, as in the coarse
default schedule, since two changes are the fewest that can show a trend.

One caveat the threshold cannot express: Omega's temperature is conservative
temperature where MPAS-Ocean's is potential temperature, so `temperature_max` is
not literally the same quantity in the two models.  Against a blow-up threshold
the difference is immaterial.

The `viz` step writes `dynamic_adjustment_stats.png` from the same statistics,
plotting kinetic energy (maximum, mean and domain-integrated), maximum normal
velocity, CFL number, tracer extremes, mean tracer drift and minimum layer
thickness on one continuous axis, with the stage boundaries marked and each
stage labelled with its damping.  A summary row cannot distinguish a quantity
that was flat through a stage from one that spiked and recovered, and those
call for different changes to the schedule; the figure can.  Reading it against
the damping labels is usually the fastest way to tell a response to the ramp
from a trend that would have happened anyway.

The `viz` step belongs to the standalone task.  If the stages are later reused
as shared steps by a longer spin-up workflow, a figure describing a completed
adjustment is not what that workflow is asking about.

### config options

```cfg
# Options for realistic global ocean dynamic-adjustment runs
[realistic_global_dynamic_adjustment]

# Path to an alternate schedule YAML that overrides the built-in per-mesh
# schedule; leave blank to use the checked-in schedule for the mesh
schedule =

# Maximum allowed temperature (deg C) in any stage's output; exceeding it is
# treated as numerical blow-up
temperature_max = 33.0

# Number of trailing stages over which the maximum cell kinetic energy must not
# increase (the "settling" check)
ke_check_num_stages = 3

# Fractional tolerance allowed when checking that the maximum cell kinetic
# energy is not increasing from one stage to the next
ke_check_rel_tolerance = 0.01
```
