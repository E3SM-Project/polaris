(dev-ocean-seamount)=

# seamount

The seamount task group is comprised of one `default` task in each of four
task trees, `planar/seamount/{linear,nonlinear}/{sigma,zstar}`, combining the
equation of state with the vertical coordinate used for the initial
condition.  This follows the `planar/overflow/{eos}/{coord}` pattern.

## framework

The shared config options for `seamount` tests  are described in
{ref}`ocean-seamount` in the User's Guide.  `coord_type`, and for z-star
`partial_cell_type`, live in per-coordinate `seamount_sigma.cfg` and
`seamount_zstar.cfg` overrides layered on top of the shared `seamount.cfg`.
The equation of state is layered on the same way: `seamount_linear.cfg`
carries the `eos_linear_*` options, which mean nothing to the nonlinear
trees and so are added only for the linear ones.  `add_seamount_tasks()`
also picks up `linear.cfg` or `teos10.cfg` from `polaris.ocean.eos` per
tree; the nonlinear trees need nothing beyond that.

Neither equation of state needs new plumbing.  `update_namelist_eos()`
already maps `teos-10` to `jm` for MPAS-Ocean and passes it through to
Omega, and the geometric-to-pseudo-height conversion described below
dispatches on `eos_type` through
{py:func}`polaris.ocean.eos.compute_specvol()`.

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

`tests/ocean/seamount/test_tracers.py` covers the initial condition: that
both equation-of-state branches reproduce the same Beckmann and Haidvogel
profile, and the negative control that in-situ density under TEOS-10 really
does depart from it with depth.

### init

The class {py:class}`polaris.tasks.ocean.seamount.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`. The bottom topography
is defined along with a vertical grid with 32 layers by default.  Next, the
ocean state is generated with a vertical temperature stratification,
back-computed from the target Beckmann and Haidvogel density so that the
density the model sees matches the profile the test intends.

The profile and the back-solve live in
{py:mod}`polaris.tasks.ocean.seamount.init_utils`, a leaf module free of
`mpas_tools` and of the step framework so the unit tests can import it.
{py:func}`polaris.tasks.ocean.seamount.init_utils.compute_tracers()` branches
on `eos_type`: the linear equation of state is inverted algebraically with
the salinity term included, and TEOS-10 is inverted with
{py:func}`polaris.ocean.eos.ct_from_potential_density()`, which reads the
profile as a potential density referenced to the surface.  See
{ref}`ocean-seamount-init` in the User's Guide for why the surface reference
is the only workable one and what it buys.

The step leaves its tracers in the convention implied by `eos_type` and does
nothing model-specific: in the `nonlinear` trees, the framework converts them
to potential temperature and practical salinity at the nominal lon/lat when
the model is MPAS-Ocean (see {ref}`dev-ocean-framework-init-state`), computing
the pressure that conversion needs from the layer thicknesses since a
geometric vertical coordinate carries none.

Note that the tracers carry the `Time` dimension that `layerThickness` and
the rest of the state have.  TEOS-10 requires its inputs to be aligned; the
linear equation of state did not, which is why the seamount got away without
it for a while.

### forward

The class {py:class}`polaris.tasks.ocean.seamount.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.seamount.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  Both
models take the same step from `dt_per_km` and the same integrator from
`time_integrator`; the only model-dependent part is translating the
integrator name to Omega's (`RK4` becomes `RungeKutta4`).  The
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
added once per tree, so four times.

