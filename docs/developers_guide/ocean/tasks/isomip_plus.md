(dev-ocean-isomip-plus)=

# isomip_plus

The `isomip_plus` tasks (`polaris.tasks.ocean.isomip_plus`) set up the
ISOMIP+ domain on planar or spherical meshes (see {ref}`ocean-isomip-plus`).
The design is described in the [ISOMIP+ design document](../../../design_docs/isomip_plus.md).

(dev-ocean-isomip-plus-framework)=

## framework

{py:func}`polaris.tasks.ocean.isomip_plus.add_isomip_plus_tasks()` creates
the shared mesh and topography steps for each resolution and mesh type, with
a shared config file `isomip_plus_topo.cfg` in the resolution's directory.
Each task then gets its own config file, `isomip_plus.cfg`, in its work
directory, shared with the steps the task adds itself. The task config
includes the linear equation of state from `polaris.ocean.eos`, and the
SSH-adjustment and freezing-point options from `polaris.ocean.ice_shelf`.
The `inception`, `wetting` and `drying` tasks add `thin_film.cfg`, and
`inception` also `inception.cfg`, which set the forward run's duration and
output interval.

{py:class}`polaris.tasks.ocean.isomip_plus.IsomipPlusTest` is an
{py:class}`polaris.ocean.ice_shelf.IceShelfTask`. Its `thin_film` attribute
is set for the tasks with time-varying geometry (`inception`, `wetting` and
`drying`). Every task has `init`, SSH-adjustment, `forward` and `viz` steps.

The x and y coordinates of the ISOMIP+ domain come from a stereographic
projection ({py:func}`polaris.tasks.ocean.isomip_plus.projection.get_projections()`)
and are added to meshes as `xIsomipCell`, `yIsomipCell`, `xIsomipVertex` and
`yIsomipVertex` by
{py:func}`polaris.tasks.ocean.isomip_plus.mesh.xy.add_isomip_plus_xy()`. The
MPAS cell culler drops these fields, so they are added again after each cull.

(dev-ocean-isomip-plus-shared-steps)=

## shared steps

- {py:class}`polaris.tasks.ocean.isomip_plus.mesh.PlanarMesh` and
  {py:class}`polaris.tasks.ocean.isomip_plus.mesh.SphericalMesh` build the
  base mesh.
- {py:class}`polaris.tasks.ocean.isomip_plus.topo.TopoMap` makes mapping
  files from the 1 km input grid to the base or culled mesh.
- {py:class}`polaris.tasks.ocean.isomip_plus.topo.TopoRemap` calves thin
  floating ice with
  {py:func}`polaris.tasks.ocean.isomip_plus.topo.calving.calve_thin_ice()`,
  computes the land-ice pressure, remaps the geometry and renormalizes it by
  the fraction of the cell with bedrock below sea level.
- {py:class}`polaris.tasks.ocean.isomip_plus.mesh.CullMesh` removes cells
  where the bedrock is above sea level.
- {py:class}`polaris.tasks.ocean.isomip_plus.topo.TopoScale` scales the
  land-ice pressure and draft in time for the `inception`, `wetting` and
  `drying` tasks.

(dev-ocean-isomip-plus-init)=

## init

For tasks without a thin film,
{py:class}`polaris.tasks.ocean.isomip_plus.init.Init` removes the cells that
are less than half floating ice or open ocean from the shared culled mesh,
carrying the topography over with
{py:func}`mpas_tools.mesh.cull.cull_dataset()`. Tasks with a thin film keep
all cells. Every task computes the draft, which is also the initial SSH,
from the land-ice pressure, limited to the bed. Tasks with a thin film mark
the cells where it reaches the bed as thin-film cells. After the vertical
coordinate is built, they raise the SSH where needed so that the column has
`thin_film_layer_thickness` per active layer, and the thin film starts fresh
at its freezing point.
The step writes the task's mesh with Coriolis and its graph file, then
computes the land-ice masks and fractions, SSH, pressure and bottom depth,
the vertical coordinate, and the initial temperature and salinity. The WARM
or COLD profile for each task is given by `PROFILES` in the module. The step
writes the staged files for the ocean model and `forcing.nc` with the
restoring and evaporation fields. With a thin film, `forcing.nc` also has
`tidalInputMask`, which is 1 in the restoring region, and the step writes
`land_ice_forcing.nc` with the pressure and fractions of every record of the
scaled topography.

(dev-ocean-isomip-plus-ssh-adjustment)=

## ssh adjustment

The task sets up the SSH-adjustment steps with
{py:meth}`polaris.ocean.ice_shelf.IceShelfTask.setup_ssh_adjustment_steps()`,
using {py:class}`polaris.tasks.ocean.isomip_plus.ssh_forward.SshForward`,
which turns on the equation of state from the config options. The
`[ssh_adjustment]` section sets `adjust_variable = ssh`, so the
{py:class}`polaris.ocean.ice_shelf.ssh_adjustment.SshAdjustment` steps
adjust SSH and leave the land-ice pressure from `init` unchanged. The model
physics is in `physics.yaml`, which the SSH-adjustment and forward runs share.
It uses RK4 time integration with wetting and drying, following Compass's
thin-film tests, and sets the ISOMIP+ top drag coefficient.
Both model steps estimate their cell count with
{py:func}`polaris.tasks.ocean.isomip_plus.cell_count.estimate_cell_count()`.

(dev-ocean-isomip-plus-forward)=

## forward

{py:class}`polaris.tasks.ocean.isomip_plus.forward.Forward` runs MPAS-Ocean
from the last SSH-adjustment output with the settings in `physics.yaml` and
`forward.yaml`. It reads `forcing.nc` as the `forcing_data` stream and writes
`output.nc` and `land_ice_fluxes.nc`, whose variables are compared with a
baseline. With a thin film, it also links `land_ice_forcing.nc` and adds
`thin_film.yaml`, which turns on MPAS-Ocean's time-varying land-ice forcing
and its tidal forcing. The tidal forcing, in its `direct` mode with zero
amplitude, holds the SSH at zero where `tidalInputMask` is 1, so the water
that the ice displaces can leave the domain. MPAS-Ocean finds the land-ice
forcing records by their spacing, which the step reads from
`land_ice_forcing.nc` at runtime with
{py:func}`polaris.tasks.ocean.isomip_plus.xtime.get_record_times()`, since
the file does not exist at setup.

(dev-ocean-isomip-plus-viz)=

## viz

{py:class}`polaris.tasks.ocean.isomip_plus.viz.Viz` plots the initial
condition and the end of the forward run with
{py:func}`polaris.viz.plot_horiz_field()` and the transect functions from
`mpas_tools.ocean.viz.transect`, substituting the ISOMIP+ coordinates for the
mesh coordinates so that planar and spherical meshes are plotted the same way.
With a thin film, it also plots the water-column thickness at each output
time, and time series of the area under the ice where the column is less
than twice the thin film and of the mean SSH in the open ocean.
