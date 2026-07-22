(dev-ocean-overflow)=

# overflow

The overflow task group is comprised of six `smoke_test` tasks for quick
testing (one for each horizontal advection order, 2, 3, and 4, each with
and without del4 viscosity enabled) and one `rpe` test which shows how the
resting potential energy changes across forward runs with different del2
viscosities.

The tasks are created in three trees by
{py:func}`polaris.tasks.ocean.overflow.add_overflow_tasks()`, which loops
over combinations of the equation of state (EOS) and the vertical
coordinate used for the initial condition:

| subdir                            | EOS cfg      | init step class | coord  |
|-----------------------------------|--------------|-----------------|--------|
| `planar/overflow/linear/zstar`    | `linear.cfg` | `Init`          | z-star |
| `planar/overflow/linear/pstar`    | `linear.cfg` | `PStarInit`     | p-star |
| `planar/overflow/nonlinear/pstar` | `teos10.cfg` | `PStarInit`     | p-star |

Each tree has its own shared config parser (combining the shared EOS
config file, `overflow.cfg` and — for the p-star trees —
`overflow_pstar.cfg`) and its own shared `init` step.

## framework

The shared config options for `overflow` tests  are described in
{ref}`ocean-overflow` in the User's Guide.

Additionally, the tests share a `forward.yaml` file with a few common model
config options related to time management, time integration, and Laplacian
viscosity, as well as defining `mesh`, `input`, `restart`, and `output`
streams.

### mesh

The module `polaris.tasks.ocean.overflow.mesh` contains helpers shared by
the two init steps:
{py:func}`polaris.tasks.ocean.overflow.mesh.build_overflow_mesh()` builds
and culls the planar hex mesh, adds the Coriolis parameter and writes the
mesh files;
{py:func}`polaris.tasks.ocean.overflow.mesh.compute_bottom_depth()`
computes the tanh shelf bathymetry; and
{py:func}`polaris.tasks.ocean.overflow.mesh.compute_initial_temperature()`
computes the cold-block temperature profile.

### init

The class {py:class}`polaris.tasks.ocean.overflow.init.Init`
defines a step for setting up the z-star initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the x and y directions.  The bottom topography
is defined along with a vertical grid with 60 layers by default.  Next, the
ocean state is generated with cold water on the continental shelf.

### pstar_init

The class {py:class}`polaris.tasks.ocean.overflow.pstar_init.PStarInit`
defines the p-star init step used by the two `pstar` trees.  It builds on
{py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep` (see
{ref}`dev-ocean-framework-vertical`): it builds the same mesh and tanh
shelf bathymetry as `Init` (via the shared mesh helpers), iterates the
p-star coordinate to convergence with zero surface pressure, and
implements `init_tracers()` as the overflow profile (interpreted as
conservative temperature and absolute salinity) evaluated at the current
p-star layer midpoints.  After convergence, the shared
`polaris.ocean.vertical.pstar_state` helpers add layer thickness,
quiescent velocity and density, and (for MPAS-Ocean) convert the tracers
to potential temperature and practical salinity at a nominal lon/lat.
The step writes `vert_coord.nc` and `init.nc` with the same filenames as
`Init`, so the `forward`, `viz` and `analysis` steps need no retargeting.

### forward

The class {py:class}`polaris.tasks.ocean.overflow.forward.Forward`
defines a step for running the ocean from the initial condition produced in
the `init` step. Namelist and streams files are updated in
{py:meth}`polaris.tasks.ocean.overflow.forward.Forward.dynamic_model_config()`
with time steps determined algorithmically based on config options.  The
number of cells is approximated from config options in
{py:meth}`polaris.tasks.ocean.overflow.forward.Forward.compute_cell_count()`
so that this can be used to constrain the number of MPI tasks that Polaris
tasks have as their target and minimum (if the resources are not explicitly
prescribed).  For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean
model is run. The duration is set by `run_duration` in the config section
corresponding to the task (`overflow_smoke_test` or `overflow_rpe`). Finally,
validation of `layerThickness`, `temperature` and `normalVelocity` in the
`output.nc` file are performed against a baseline if one is provided when
calling {ref}`dev-polaris-setup`.

### viz

The {py:class}`polaris.tasks.ocean.overflow.viz.Viz` plots the initial and
final temperature along a transect perpendicular to the continental slope.

(dev-ocean-overflow-smoke-test)=

## smoke_test

The {py:class}`polaris.tasks.ocean.overflow.smoke_test.SmokeTest`
task runs the `init` step, a short `forward` step, and (optionally, not run
by default) the `viz` step. In each task tree, six instances are created,
one for each horizontal advection order (2, 3, and 4) with and without
del4 viscosity enabled, producing tasks named
`smoke_test_horiz_adv_order_{2,3,4}` and
`smoke_test_horiz_adv_order_{2,3,4}_del4`.

## rpe

The {py:class}`polaris.tasks.ocean.overflow.rpe.Rpe` test performs the `init`
step, 5 `forward` steps corresponding to the viscosity values in the config
file, and the `analysis` step.

### analysis

The {py:class}`polaris.tasks.ocean.overflow.rpe.analysis.Analysis`
computes the Resting Potential Energy (RPE). This step also produces a
figure with RPE time evolution for each forward run and a figure with each of
the forward run's transects at the `plot_time` designated in the config file.
