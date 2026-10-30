(dev-e3sm-init-misomip)=

# MISOMIP Tasks

The tasks in `polaris.tasks.e3sm.init.misomip` make E3SM's inputs for the
MISOMIP experiments.  {py:func}`polaris.tasks.e3sm.init.misomip.add_misomip_tasks()`
adds a {py:class}`polaris.tasks.e3sm.init.misomip.MisomipTask` for each
experiment in `EXPERIMENTS` on each pair of meshes in `MESH_PAIRS`.

## Shared steps

{py:func}`polaris.tasks.e3sm.init.misomip.get_misomip_mesh_steps()` gets or
creates the shared steps of a pair of meshes, with a shared config file,
`misomip.cfg`, in `e3sm/init/<mesh_name>/`.  It also returns the steps
that make the meshes:

- the ISOMIP+ ocean mesh, from
  {py:func}`polaris.tasks.ocean.isomip_plus.get_isomip_plus_mesh_steps()`;
- MALI's mesh, from
  {py:func}`polaris.tasks.mesh.planar.mismip_plus.get_mismip_plus_mesh_steps()`.

The steps of the `e3sm/init` component are:

- {py:class}`polaris.tasks.e3sm.init.misomip.mesh.OceanMeshStep` gives the
  culled ISOMIP+ mesh the projection's latitude and longitude and the
  global attribute `sphere_radius`, and writes its SCRIP file and graph.
  It keeps `xIsomipCell` and `yIsomipCell`, which the ISOMIP+ restoring
  reads.
- {py:class}`polaris.tasks.e3sm.init.misomip.mesh.LandiceMeshStep` gives
  MALI's mesh the projection's latitude and longitude and writes its SCRIP
  file, with the polygons of the cells on the walls trimmed to the walls.
- {py:class}`polaris.tasks.e3sm.init.misomip.maps.MapStep` makes one of
  the maps in `MAPS` from the two SCRIP files, through
  {py:meth}`polaris.remap.MappingFileStep.src_from_scrip()` and
  {py:meth}`polaris.remap.MappingFileStep.dst_from_scrip()`.

## Projection and SCRIP files

{py:func}`polaris.tasks.e3sm.init.misomip.projection.get_lat_lon()`
converts the protocols' planar coordinates to latitude and longitude, in
radians, with longitude between 0 and $2\pi$.
{py:func}`polaris.tasks.e3sm.init.misomip.projection.add_lat_lon()` sets
them for a mesh's cells, edges and vertices.

{py:func}`polaris.tasks.e3sm.init.misomip.scrip.write_scrip()` writes a
SCRIP file from the planar mesh, with corners from the projection.  Its
`grid_area` is `areaCell` divided by the square of E3SM's radius.  Polygons
that cross `y_min` or `y_max` are trimmed with
{py:func}`polaris.tasks.e3sm.init.misomip.scrip.clip_polygon_to_y_band()`.

## MALI's geometry

{py:func}`polaris.tasks.e3sm.init.misomip.calving.get_floating_mask()` and
{py:func}`polaris.tasks.e3sm.init.misomip.calving.get_grounded_mask()`
apply MALI's flotation test, in which ice exactly at flotation floats.
{py:func}`polaris.tasks.e3sm.init.misomip.calving.calve()` removes floating
ice thinner than 100 m and all ice beyond $x = 640$ km.  The densities are
the MISMIP+ tasks', 918 and 1028 kg m$^{-3}$.

{py:func}`polaris.tasks.e3sm.init.misomip.records.get_monthly_record_times()`
gives the `xtime` and the time in seconds of each record of MALI's data-mode
files: the start of each month in E3SM's no-leap calendar, and the start of
the year after the last.
{py:func}`polaris.tasks.e3sm.init.misomip.records.get_interpolation_weights()`
gives the weights for interpolating the protocol's yearly records to them.

## Grid names

{py:func}`polaris.tasks.e3sm.init.misomip.names.get_grid_names()` reads
E3SM's names for the ocean, MALI and model grids from the
`[misomip_grids]` section, and raises an error if one is blank.  Each pair
of meshes sets them in `<mesh_name>.cfg` in the package.
{py:meth}`polaris.tasks.e3sm.init.misomip.MisomipTask.configure()` calls
it, so setup fails without them.
