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
  {py:func}`polaris.tasks.mesh.planar.mismip_plus.get_mismip_plus_mesh_steps()`,
  with the length
  {py:data}`polaris.tasks.e3sm.init.misomip.landice_steady_state.LANDICE_MESH_LENGTH`.

The steps of the `e3sm/init` component are:

- {py:class}`polaris.tasks.e3sm.init.misomip.mesh.OceanMeshStep` gives the
  culled ISOMIP+ mesh the projection's latitude and longitude and the
  global attribute `sphere_radius`, and writes its SCRIP file and graph.
  It keeps `xIsomipCell` and `yIsomipCell`, which the ISOMIP+ restoring
  reads.
- {py:class}`polaris.tasks.e3sm.init.misomip.mesh.LandiceMeshStep` gives
  MALI's mesh the projection's latitude and longitude and writes its SCRIP
  file, with the polygons of the cells on the walls trimmed to the walls.
- {py:class}`polaris.tasks.e3sm.init.misomip.maps.MapStep`, a
  {py:class}`polaris.e3sm.init.glc_ocean_maps.GlcOceanMapStep`, makes one
  of the maps in `MAPS`.  The conservative maps read the two SCRIP files.
  `SMOOTHED_MAP` reads MALI's SCRIP file and the ocean's mesh, whose cells
  are inflated by
  {py:func}`polaris.tasks.ocean.misomip.topo.get_smoothing_distance()`.
- Two {py:class}`polaris.e3sm.init.graph_partition.GraphPartitionStep`
  steps partition the ocean's graph, from `ocean_mesh`, and MALI's, from
  the MISMIP+ mesh step, with options from `[misomip_ocean_partitions]`
  and `[misomip_landice_partitions]`.

{py:func}`polaris.tasks.e3sm.init.misomip.get_misomip_experiment_steps()`
adds the steps of one experiment to those of its pair of meshes: the
MISMIP+ steps that make the steady state, from
{py:func}`polaris.tasks.landice.mismip_plus.steps.get_mismip_plus_steady_state_steps()`,
and these steps, also of the `e3sm/init` component:

- the MISMIP+ `init` step, on MALI's longer mesh, and
  {py:class}`polaris.tasks.e3sm.init.misomip.landice_steady_state.LandiceSteadyStateStep`,
  which copies the steady state onto that mesh with
  {py:func}`polaris.tasks.e3sm.init.misomip.landice_steady_state.copy_by_position()`,
  matching cells, edges and vertices by position, and removes the ice
  where the calving mask is 1 with
  {py:func}`polaris.tasks.landice.mismip_plus.forward.remove_masked_ice()`.
  The cells past the MISMIP+ mesh keep the `init` step's fields;
- {py:class}`polaris.tasks.e3sm.init.misomip.landice_init.InputMapStep`
  makes the conservative map from the ISOMIP+ input grid, described by the
  projection, to MALI's mesh, from its SCRIP file;
- {py:class}`polaris.tasks.e3sm.init.misomip.landice_init.LandiceInitStep`
  copies that steady state and replaces its thickness with
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
ISOMIP+ `ThinFilmSshForward`, which adds the thin-film tasks' wetting and
drying options, as the forward run does.  `iceocean1ra` (in `CONTINUES_FROM`) gets only the
`init` step, on `iceocean1r`'s land-ice fields.
{py:class}`polaris.tasks.ocean.misomip.MisomipForward` subclasses the ISOMIP+
{py:class}`polaris.tasks.ocean.isomip_plus.forward.Forward` with its
thin-film options, overriding
{py:meth}`polaris.tasks.ocean.isomip_plus.forward.Forward.get_forcing_interval()`
to give the monthly interval of the data-mode records.  With fixed
geometry, it turns the time-varying land-ice forcing off.  Each experiment
with a forward run has two, from the same initial condition: one with RK4,
from the experiment's ocean config, and one in `split_explicit`
(`SPLIT_EXPLICIT` in `polaris.tasks.ocean.misomip`), whose own config
adds the ISOMIP+ `split_explicit.cfg`.  Only the forward run reads that
config, so the SSH adjustment keeps RK4.  The task adds both runs with
`run_by_default=False` (see `NOT_RUN_BY_DEFAULT`).

{py:class}`polaris.tasks.e3sm.init.misomip.ocean_initial_condition.OceanInitialConditionStep`
merges the ocean's mesh, from `init`, with the state the final SSH
adjustment wrote, since E3SM's MPAS-Ocean reads both from its initial
condition.
{py:class}`polaris.tasks.e3sm.init.misomip.case_config.CaseConfigStep`
writes the E3SM case configuration of an experiment for each of the
standalone runs' time integrators, in `INTEGRATOR_SUBDIRS`: RK4's in
`case_config` and split-explicit's in `split_explicit/case_config`.
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
and {py:func}`polaris.tasks.e3sm.init.misomip.names.map_path()`.  The case
configurations' steps are keyed `case_config` and
`split_explicit/case_config`, and their user-mods directories and READMEs
are staged under
{py:func}`polaris.tasks.e3sm.init.misomip.names.case_config_dir()`, with
the integrator's subdirectory.  The
creation date is `[misomip_inputs] creation_date`, which
{py:meth}`polaris.tasks.e3sm.init.misomip.MisomipTask.configure()` fills in
with {py:func}`polaris.e3sm.init.inputdata.set_creation_date()`.

## Case configuration

{py:class}`polaris.tasks.e3sm.init.misomip.case_config.CaseConfigStep`
reads the namelist its standalone forward step wrote at setup, and
MPAS-Ocean's default namelist, found from that step's ocean config
file.  The split-explicit options all differ from MPAS-Ocean's defaults,
which are E3SM's, so they are written like any other.  An MPAS-Ocean
build older than an option leaves it out of the namelist it renders, with
only a warning at setup, so
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.check_time_integrator()`
stops the step unless the namelist has the step's time integrator and
every option of its YAML files, in `INTEGRATOR_YAML_FILES`.  The README of a
split-explicit case names the change it needs that FAnSSIE lacks,
`SPLIT_EXPLICIT_PENDING`, since no option can check for it.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_user_nl_mpaso()`
writes the options whose values differ from the defaults, except in the
groups E3SM sets itself (`STANDALONE_GROUPS`).  Of each analysis member's
group, it writes only whether the member is on, so the case has the
standalone run's members, and E3SM configures their output.  It writes
`MIN_FRACTION_OPTION` from `[misomip_land_ice_on_ocean]
min_land_ice_fraction`, so MPAS-Ocean's import leaves the same cells open
ocean as the initial conditions.  It also
writes every option in `E3SM_DEFAULT_OPTIONS`, with the standalone
value: those whose E3SM default differs from MPAS-Ocean's, or which E3SM
gives a default only for the grids it lists.  A unit test compares that
list with the defaults of the E3SM submodule's MPAS-Ocean, so it fails
when E3SM's defaults change.  The options in `E3SM_OWNED_OPTIONS`, the bulk
wind stress, keep E3SM's values: E3SM's ocean takes the coupler's wind
stress through its bulk forcing, and its time step fails without it.  Values E3SM's namelist builder sets from case
variables, such as the tidal velocity of the melt parameterization, are
added by hand.

{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_grid_file()`
renders `config_grids.template`, with each mesh's cell count from its SCRIP
file.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_shell_commands()`
names the staged files, including the smoothed map in
`GLC2OCN_SHELF_SMAPNAME`, relative to `$DIN_LOC_ROOT`, or to
`[misomip_case_config] inputdata_root`, in which
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_inputdata_root()`
replaces `{experiment}` with the experiment's name, gives
`MALI_DATAMODE_REFERENCE_TIME` the `xtime` of the first record from
{py:func}`polaris.tasks.e3sm.init.misomip.records.get_monthly_record_times()`,
sets the coupling intervals, which it checks against the standalone run's
time step, and splits the
experiment's length, in `RUN_MONTHS`, into jobs.  The README gives the
compset from `COMPSETS`.
The step chooses the case's layout in `_get_layout()`.
{py:func}`polaris.tasks.e3sm.init.misomip.layout.get_task_bounds()` turns
a mesh's cells and its `[misomip_*_partitions]` goal and bounds into a
target, fewest and most tasks: the ocean's, and MALI's as well when it is
prognostic.  {py:func}`polaris.tasks.e3sm.init.misomip.layout.get_layout()`
applies the most restrictive and the machine's tasks per node: the
smaller of `[parallel] cores_per_node` and `max_mpi_tasks_per_node` on a
batch system, whatever node the step runs on, and the cores the
component's parallel system finds on a single node, from
`[parallel] system`.  It then takes the most tasks at or below that which
both meshes are partitioned for.  The code holds no machine's values.
{py:func}`polaris.tasks.e3sm.init.misomip.layout.get_layout_lines()`
describes the choice for the step's log and the README.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_create_case_script()`
renders `create_case.template`, with the layout, the task counts that
{py:func}`polaris.e3sm.init.partitions.get_core_list()` gives for each
mesh, and `[build] machine` and `compiler`, from
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_machine()`.
The script checks the task counts, that the E3SM checkout has
`E3SM_COMMIT`, and that CIME's `query_config` names the same machine,
before it creates the case.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_pes_file()`
renders `pes.template`, the layout the script gives `create_newcase` in
place of MPAS-Ocean's, with 1 thread a task and `MAX_MPITASKS_PER_NODE`
the layout's tasks per node, so CIME's nodes match Polaris's.

Every experiment has a case configuration.  `iceocean1r`'s standalone
run is set up, not run, for its namelist, and `iceocean1ra`, in
`CONTINUES_FROM`, reads `iceocean1r`'s.  For an experiment with a
prognostic MALI (`PROGNOSTIC_EXPERIMENTS`),
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_user_nl_mali()`
adds the MISMIP+ tasks' `namelist.landice`, less
`MISMIP_PLUS_STANDALONE_OPTIONS`, with the rate factor from their
`mismip_plus.cfg` and their Ice1r run's calving, then
`MALI_E3SM_DEFAULT_OPTIONS`, MALI's own defaults where E3SM's differ, each
option once.  A unit test checks that every MALI option whose E3SM default
differs from the submodule's MALI Registry is written or in
`MALI_E3SM_OWNED_OPTIONS`, which keep E3SM's values.  The
step copies their `albany_input.yaml` into `SourceMods/src.mali/`.

For every experiment, the step writes `edit_streams.py` from
`edit_streams.template` through
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_edit_streams_script()`,
with `DAILY_OCEAN_FIELDS`, `MONTHLY_OCEAN_FIELDS`,
`DAILY_MAX_OCEAN_FIELDS` and `GLOBAL_STATS_INTERVAL`, and, with a
prognostic MALI, the MISMIP+ tasks' output fields with
`MALI_HISTORY_FIELDS`, and `MALI_DAILY_FIELDS`.  `user_nl_mpaso` turns on
the daily means and `MONITORING_OPTIONS`.  The script writes the ocean's
streams file with and without `DAILY_3D_OCEAN_FIELDS` into
`OCEAN_STREAMS_DIR` in the case directory.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_segments()`
splits a run into jobs of
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_months_per_job()`
months, ending them at the edges of
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_daily_3d_windows()`,
so each job is wholly in or out of a window.  `get_shell_commands()` sets
the first job's months, `RESTART_MONTHS` and `RESUBMIT` from them, and
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_next_segment_script()`
renders `next_segment.template` with each segment's start, months and
window.  `create_case.sh` runs the script with `--start` and makes it the
case's `POSTRUN_SCRIPT`; it picks the next job from the months between
the case's start and the coupler's restart pointer, so it holds no count
of jobs.
{py:func}`polaris.tasks.e3sm.init.misomip.case_config.get_case_config_files()`
gives what the `assemble` step stages.  For `iceocean1ra`,
`get_shell_commands()` names `iceocean1r`'s initial conditions under its
inputdata root, and `create_case.sh` takes `-R` and `-d` for the branch
run.

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
  divides by the mapped mask, as MPAS-Ocean's import does, caps the
  fractions at 1, and leaves cells with a land-ice fraction at or below a
  minimum open ocean.

## Grid names

{py:func}`polaris.tasks.e3sm.init.misomip.names.get_grid_names()` reads
E3SM's names for the ocean, MALI and model grids from the
`[misomip_grids]` section, and raises an error if one is blank.  Each pair
of meshes sets them in `<mesh_name>.cfg` in the package.
{py:meth}`polaris.tasks.e3sm.init.misomip.MisomipTask.configure()` calls
it, so setup fails without them.
