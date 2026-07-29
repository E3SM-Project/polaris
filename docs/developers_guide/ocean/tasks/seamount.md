(dev-ocean-seamount)=

# seamount

The seamount task group is comprised of one `default` task in each of two task
trees, `planar/seamount/sigma` and `planar/seamount/zstar`, one per vertical
coordinate for the initial condition.

## framework

The shared config options for `seamount` tests  are described in
{ref}`ocean-seamount` in the User's Guide.  `coord_type`, and for z-star
`partial_cell_type`, live in per-coordinate `seamount_sigma.cfg` and
`seamount_zstar.cfg` overrides layered on top of the shared `seamount.cfg`.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, Laplacian
viscosity, bottom drag and vertical mixing, as well as defining `mesh`,
`input`, `restart`, and `output` streams.  It is split into a shared `ocean:`
section and model-specific `mpas-ocean:` and `Omega:` sections.

### support for both ocean models

Both coordinates are geometric, so one `init` step serves either model.  When
`model = omega`, `Ocean.write_vert_coord_dataset()` and
`Ocean.write_model_dataset()` convert `restingThickness` and `layerThickness`
into `RefPseudoThickness` and `PseudoThickness` by integrating gauge pressure
down each column through the configured equation of state.  No p-star-specific
initialization is involved and no reference pseudo-grid is needed, so the
seamount does not use
{py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep`.

`tests/ocean/seamount/test_sigma_to_pseudo.py` covers that conversion: the
geometric round trip, that sigma layers stay proportional to column depth, and
that interior interfaces sit at genuinely different pressures from column to
column, with a flat-bottom negative control for the last of these.

### init

The class {py:class}`polaris.tasks.ocean.seamount.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`. The bottom topography
is defined along with a vertical grid with 32 layers by default.  Next, the
ocean state is generated with a vertical temperature stratification,
back-computed from the target Beckmann and Haidvogel density by inverting the
full linear equation of state, salinity term included, so that the density the
model sees matches the profile the test intends.

### forward

The class {py:class}`polaris.tasks.ocean.seamount.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.seamount.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  Omega has
no split-explicit time integrator, so it takes its step from `omega_dt_per_km`
and its integrator from `omega_time_integrator` rather than the MPAS-Ocean
`dt_per_km` and `time_integrator`.  The
number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.seamount.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run. The duration is set by `run_duration` in the config section
corresponding to the task (`seamount_default`). Finally,
the variables `kineticEnergyCell` and `normalVelocity` in the
`output.nc` file are visualized in the `viz` directory.


### viz

The {py:class}`polaris.tasks.ocean.seamount.viz.Viz` plots the maximum velocity
as a function of time; a horizontal cross-section of the normal velocity;
and a vertical cross-section of the kinetic energy. The vertical cross-section
is also convenient to see the vertical coordinate (sigma versus z-star) and
the bottom topography.

The transect needs a geometric layer thickness, and `layerThickness` is the
right field for both models.  Omega writes `PseudoThickness` rather than a
geometric thickness, but `Ocean.open_model_dataset()` converts it on read,
as `RhoSw * SpecVol * PseudoThickness`.  That is why `SpecVol` has to be in
the Omega `History` stream alongside `State`.


(dev-ocean-seamount-default)=

## default

The {py:class}`polaris.tasks.ocean.seamount.default.Default`
test runs the `init` step, a short `forward` step, and the `viz` step.  It is
added once per coordinate tree.

