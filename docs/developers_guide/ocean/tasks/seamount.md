(dev-ocean-seamount)=

# seamount

The seamount task group is comprised of a `default` task and a `short` task
in each of four task trees,
`planar/seamount/{linear,nonlinear}/{sigma,zstar}`, combining the equation of
state with the vertical coordinate used for the initial condition.  This
follows the `planar/overflow/{eos}/{coord}` pattern.

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

`tests/ocean/seamount/test_linear_in_pressure.py` covers the
`linear_pressure` stratification: that the layer values are exact means of
the continuous profile over each layer's pressure range, and that the profile
is straight in the pressure reconstructed from the pseudo-thickness rather
than only in the pressure it was built from.  Both Beckmann and Haidvogel
profiles are carried through the same measurement as negative controls, since
"density linear in depth" is close enough to "temperature linear in pressure"
that the difference has to be demonstrated rather than asserted.

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
first on `seamount_stratification_type` and then on `eos_type`: for the two
Beckmann and Haidvogel profiles the linear equation of state is inverted
algebraically with the salinity term included, and TEOS-10 is inverted with
{py:func}`polaris.ocean.eos.ct_from_potential_density()`, which reads the
profile as a potential density referenced to the surface.  See
{ref}`ocean-seamount-init` in the User's Guide for why the surface reference
is the only workable one and what it buys.

The `linear_pressure` stratification takes a different route through
{py:func}`polaris.tasks.ocean.seamount.init_utils.compute_tracers_linear_in_pressure()`,
which needs `layerThickness` rather than `zMid`: it prescribes temperature as
a function of pressure and integrates the hydrostatic balance to find it.
Temperature depends on pressure, pressure on the specific volume and the
specific volume on temperature, so the profile is a fixed point and the
function iterates to `PRESSURE_ITERATION_TOLERANCE` rather than evaluating a
formula.  The iteration contracts by roughly the fractional density range of
the column per pass and converges in well under ten;
`MAX_PRESSURE_ITERATIONS` is a guard rather than a working limit, and failing
to converge raises rather than returning a profile that is nearly straight.
See {ref}`ocean-seamount-linear-in-pressure` in the User's Guide for what the
profile is for.

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
model is run. The duration is set by `run_duration`, in hours, in the config
section corresponding to the task (`seamount_default` or `seamount_short`,
selected by the `task_name` passed to the step). Finally,
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
test runs the `init` step, a 6 day `forward` step, and the `viz` step.  It is
added once per tree, so four times.  Unlike most tasks, `viz` runs by
default here: the forward run is long enough that it is not worth making the
user re-run the task just to get the plots.


(dev-ocean-seamount-short)=

## short

The {py:class}`polaris.tasks.ocean.seamount.short.Short` test is the same
task with a 1 hour `forward` step, and it too is added once per tree.  It
exists as a regression test rather than a measurement: an hour is far too
short for the spurious circulation to develop.  `viz` is opt-in here, as
usual, because re-running the task to get the plots is cheap.

The two tasks differ only in their config section, `seamount_default` versus
`seamount_short`, which is what {py:class}`Forward` looks up from its
`task_name`.

Two of the four short tasks are in the `mpaso_pr` and `omega_pr` suites,
`linear/zstar` and `nonlinear/sigma`, which covers both equations of state
and both coordinates in two runs.  Nothing from the seamount is in the
nightly suites yet; the `default` tasks are 6 day runs.

