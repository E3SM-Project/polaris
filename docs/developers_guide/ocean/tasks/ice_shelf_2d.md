(dev-ocean-ice-shelf-2d)=

# ice_shelf_2d

The `ice_shelf_2d` test group
(`polaris.ocean.tasks.ice_shelf_2d.IceShelf2d`)
implements a very simplified ice-shelf cavity that is invariant in the x
direction (see {ref}`ocean-ice-shelf-2d`). Here, we describe the shared
framework for this test group and the 2 test cases.

(dev-ocean-ice-shelf-2d-framework)=

## framework

The shared config options for the `ice_shelf_2d` test group
are described in {ref}`ocean-ice-shelf-2d` in the User's Guide.

Additionally, the test group has shared `ssh_forward.yaml` and `forward.yaml`
files with common namelist options and streams related to the `ssh_adjustment`
and `forward` steps, respectively.

The test case class is inherited from
{py:class}`polaris.ocean.ice_shelf.IceShelfTask` and
its {py:class}`polaris.ocean.ice_shelf.ssh_forward.SshForward` and
{py:class}`polaris.ocean.ice_shelf.ssh_adjustment.SshAdjustment` step classes
are used to set up one of each step for each iteration given by the config
option `ssh_adjustment:iterations`.

### init

The class :py:class:`polaris.ocean.tasks.ice_shelf_2d.init.Init`
defines a step for setting up the initial state for each test case.

First, a mesh appropriate for the resolution is generated using
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  Then, the mesh is
culled to remove periodicity in the y direction.  A vertical grid is generated,
with 20 layers of 100-m thickness each by default.  Then, the 1D grid is either
"squashed" down so the sea-surface height corresponds to the location of the
ice-ocean interface (ice draft) using a z-star {ref}`dev-ocean-framework-vertical`
or top layers are removed where there is an ice shelf using a z-level
coordinate. Finally, the initial salinity profile is computed along with
uniform temperature and zero initial velocity.

### forward

The class {py:class}`compass.ocean.tests.ice_shelf_2d.forward.Forward`
defines a step for running MPAS-Ocean from the initial condition produced in
the `init` step. For MPAS-Ocean, PIO namelist options are modified and a
graph partition is generated as part of `runtime_setup()`.  Next, the ocean 
model is run. 

### validate

The class {py:class}`polaris.ocean.tasks.ice_shelf_2d.validate.Validate`
defines a step for validating outputs in two step directories against one
another.  This step ensures that `temperature`, `salinity`, `layerThickness` 
and `normalVelocity` are identical in `output.nc` files in the two steps.
It also checks a number of land ice variables and frazil variables stored in
`land_ice_fluxes.nc` and `frazil.nc`, respectively. This step is used by the
restart test (see {ref}`dev-ocean-ice-shelf-2d-restart`).

### viz

The class {py:class}`polaris.ocean.tasks.ice_shelf_2d.viz.Viz` uses the planar
visualization capabilities provided by
{py:func}`polaris.ocean.viz.compute_transect()`.

(dev-ocean-ice-shelf-2d-default)=

## default

The {py:class}`polaris.ocean.tasks.ice_shelf_2d.default.Default` test case
config options are described in {ref}`ocean-ice-shelf-2d-default`.

The test creates and mesh and initial condition, performs 15 iterations of
SSH adjustment to make sure the SSH is as close as possible to being in
dynamic balance with the land-ice pressure.  Then, it performs a 10-minute
 forward simulation. If a baseline is provided, a large number of variables
(both prognostic and related to land-ice fluxes) are checked to make sure
they match the baseline.

The restart test, `ocean/planar/ice_shelf_2d/$RES/$COORD_TYPE/default/with_restart`
is just a variant of the default test that has two additional steps, a `forward`
step and a `validate` step. 

The tidal forcing test, `ocean/planar/ice_shelf_2d/$RES/$COORD_TYPE/default_tidal_forcing`
is a variant of the `default` test that has tidal forcing, is run for longer
(0.1 days), and uses the RK4 time integration scheme by default.
