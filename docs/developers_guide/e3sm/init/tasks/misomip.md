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
- Two {py:class}`polaris.e3sm.init.graph_partition.GraphPartitionStep`
  steps partition the ocean's graph, from `ocean_mesh`, and MALI's, from
  the MISMIP+ mesh step, with options from `[misomip_ocean_partitions]`
  and `[misomip_landice_partitions]`.

{py:func}`polaris.tasks.e3sm.init.misomip.get_misomip_experiment_steps()`
adds the steps of one experiment to those of its pair of meshes: the
MISMIP+ steps that make the steady state, from
{py:func}`polaris.tasks.landice.mismip_plus.steps.get_mismip_plus_steady_state_steps()`,
and these steps, also of the `e3sm/init` component:

- {py:class}`polaris.tasks.e3sm.init.misomip.landice_init.InputMapStep`
  makes the conservative map from the ISOMIP+ input grid, described by the
  projection, to MALI's mesh, from its SCRIP file;
- {py:class}`polaris.tasks.e3sm.init.misomip.landice_init.LandiceInitStep`
  copies the steady state and replaces its thickness with
  {py:func}`polaris.tasks.e3sm.init.misomip.landice_init.get_landice_thickness()`,
  sets the latitude and longitude, and sets the time to the start of the
  run;
- {py:class}`polaris.tasks.e3sm.init.misomip.landice_data.LandiceDataStep`
  remaps the 101 yearly records of Ocean3 or Ocean4 with
  {py:func}`polaris.tasks.e3sm.init.misomip.landice_init.remap_input_thickness()`,
  and writes the monthly records one at a time with
  {py:func}`polaris.tasks.e3sm.init.misomip.landice_data.write_data_mode_file()`.

{py:class}`polaris.tasks.e3sm.init.misomip.land_ice_on_ocean.LandIceOnOceanStep`
computes the land-ice fields on the ocean's mesh from MALI's initial
condition, or from every record of its data-mode file, with
{py:func}`polaris.tasks.e3sm.init.misomip.land_ice_fields.compute_land_ice_fields()`.
The ocean's steps come from
{py:func}`polaris.tasks.ocean.misomip.get_misomip_ocean_steps()`.  They are
shared steps of the ocean component, since Polaris assigns a model per
component, and `polaris.tasks.ocean.misomip` imports nothing from
`e3sm/init`: the steps it builds on are passed in.
{py:class}`polaris.tasks.ocean.misomip.MisomipInit` subclasses the ISOMIP+
{py:class}`polaris.tasks.ocean.isomip_plus.init.Init`, overriding the mesh it
starts from and the topography it reads, with E3SM's gravity and the
experiment's profiles.  The SSH-adjustment steps come from
{py:func}`polaris.ocean.ice_shelf.get_ssh_adjustment_steps()`, with the
ISOMIP+ `SshForward`.  `iceocean1ra` (in `CONTINUES_FROM`) gets only the
`init` step, on `iceocean1r`'s land-ice fields.
{py:class}`polaris.tasks.ocean.misomip.MisomipForward` subclasses the ISOMIP+
{py:class}`polaris.tasks.ocean.isomip_plus.forward.Forward` with its
thin-film options, overriding
{py:meth}`polaris.tasks.ocean.isomip_plus.forward.Forward.get_forcing_interval()`
to give the monthly interval of the data-mode records.  With fixed
geometry, it turns the time-varying land-ice forcing off.  The task adds it
with `run_by_default=False` (see `NOT_RUN_BY_DEFAULT`).

{py:class}`polaris.tasks.e3sm.init.misomip.ocean_initial_condition.OceanInitialConditionStep`
merges the ocean's mesh, from `init`, with the state the final SSH
adjustment wrote, since E3SM's MPAS-Ocean reads both from its initial
condition.
{py:class}`polaris.tasks.e3sm.init.misomip.assemble.MisomipAssembleStep`
subclasses {py:class}`polaris.e3sm.init.assemble.AssembleStep` to stage the
experiment's files.

The experiment's own steps are in the task's directory, so the task adds
them without symlinks.

## Staging

{py:class}`polaris.tasks.e3sm.init.misomip.assemble.MisomipAssembleStep`
takes the steps whose outputs it stages, keyed as in its `PRODUCT_FILES`
and `PARTITION_PRODUCTS`, with each map's step keyed `maps/<map name>`.
An experiment passes only the products it has.  The partitions are found
at run time, so the step depends on the partition steps explicitly.

The paths come from
{py:func}`polaris.e3sm.init.inputdata.landice_dir()`,
{py:func}`polaris.e3sm.init.inputdata.gridmaps_dir()` and
{py:func}`polaris.e3sm.init.inputdata.ocean_partition_path()`, which any
workflow would stage the same way, and from MISOMIP's own path functions in
`polaris.tasks.e3sm.init.misomip.names`, such as
{py:func}`polaris.tasks.e3sm.init.misomip.names.ocean_initial_condition_path()`
and {py:func}`polaris.tasks.e3sm.init.misomip.names.map_path()`.  The
creation date is `[misomip_inputs] creation_date`, which
{py:meth}`polaris.tasks.e3sm.init.misomip.MisomipTask.configure()` fills in
with {py:func}`polaris.e3sm.init.inputdata.set_creation_date()`.

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

## The ocean's land-ice fields

`polaris.tasks.e3sm.init.misomip.land_ice_fields` reproduces what
E3SM's coupler delivers to MPAS-Ocean from MALI, as in FAnSSIE:

- {py:func}`polaris.tasks.e3sm.init.misomip.land_ice_fields.compute_mali_export()`
  computes MALI's ice-shelf exports: the below-sea-level mask $m$, the
  pressure $m \rho_i g H$ with E3SM's gravity, and $m$ times MALI's
  floating and grounded masks;
- {py:func}`polaris.tasks.e3sm.init.misomip.land_ice_fields.read_map()` and
  {py:func}`polaris.tasks.e3sm.init.misomip.land_ice_fields.apply_map()`
  apply a map without normalizing, as the coupler does;
- {py:func}`polaris.tasks.e3sm.init.misomip.land_ice_fields.import_geometry()`
  divides by the mapped mask, as MPAS-Ocean's import does, and caps the
  fractions at 1.

## Grid names

{py:func}`polaris.tasks.e3sm.init.misomip.names.get_grid_names()` reads
E3SM's names for the ocean, MALI and model grids from the
`[misomip_grids]` section, and raises an error if one is blank.  Each pair
of meshes sets them in `<mesh_name>.cfg` in the package.
{py:meth}`polaris.tasks.e3sm.init.misomip.MisomipTask.configure()` calls
it, so setup fails without them.
