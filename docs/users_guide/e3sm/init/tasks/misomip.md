(e3sm-init-misomip-tasks)=

# MISOMIP Tasks

The `e3sm/init` `misomip` tasks make the inputs E3SM needs to run the
ISOMIP+ experiments Ocean0–4 and the MISOMIP1 experiments IceOcean1r and
IceOcean1ra
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)), with
MPAS-Ocean coupled to MALI.

## Tasks

There is a task for each experiment on each pair of ocean and MALI meshes:

- `e3sm/init/<mesh_name>/misomip/<experiment>`

where `<mesh_name>` is `misomip-o4km-li1km` or `misomip-o2km-li1km` and
`<experiment>` is one of `ocean0`, `ocean1`, `ocean2`, `ocean3`, `ocean4`,
`iceocean1r` or `iceocean1ra`.

The ocean meshes are the 4 and 2 km planar meshes of the
{ref}`ocean-isomip-plus` tasks, and MALI's is the 1 km mesh of the
{ref}`landice-mismip-plus` tasks.  The tasks run the steps that make
these meshes, so the first task to run on a pair of meshes takes the
longest.

## Meshes and maps

Each pair of meshes gets latitude and longitude from a transverse Mercator
projection on a sphere of E3SM's radius, 6,371,220 m.  The projection
puts the center of the ISOMIP+ box, $x = 560$ km and $y = 40$ km, at 75°S
on the prime meridian.  As in the protocol, $x$ points north and $y$ west.

The `ocean_mesh` and `landice_mesh` steps write the meshes with this
latitude and longitude, and a SCRIP file for each.  The ocean mesh also
gets the global attribute `sphere_radius`.  In MALI's SCRIP file, the
cells on the domain's walls, $y = 0$ and $y = 80$ km, are trimmed to the
walls, since MALI's mesh gives them half a cell's area.

The `maps` steps make the maps between the two meshes that E3SM's coupler
reads.  Conservative maps in each direction carry fluxes.  A smoothed map
from MALI to the ocean carries MALI's geometry: it inflates each ocean cell
by one cell width, 4 km for `misomip-o4km-li1km` and 2 km for
`misomip-o2km-li1km`, which spreads the steps in the draft at the grounding
line over neighboring cells.

## MALI's initial conditions and data-mode files

MALI's mesh is the MISMIP+ 1 km mesh extended to $x = 660$ km, 20 km
past the calving front, so the ocean sees ice-free MALI cells beyond the
front.  The `landice_steady_state` step copies the cached MISMIP+ steady
state ({ref}`landice-mismip-plus`) onto it by position, removing the ice
where the calving mask is 1, beyond the protocol's calving front.  The
cells past the MISMIP+ mesh have no ice.

Every MALI initial condition starts from that steady state, with the
projection's latitude and longitude and its time set to the start of the
run.  The `landice_init` step of
Ocean0–4 replaces the thickness where the ISOMIP+ input geometry covers
MALI's mesh, $x \ge 320$ km, with the input's, remapped conservatively by
the `maps/input_to_landice_aave` step:

| Experiment | Input geometry       |
|------------|----------------------|
| `ocean0`   | Ocean1               |
| `ocean1`   | Ocean1               |
| `ocean2`   | Ocean2               |
| `ocean3`   | Ocean3, first record |
| `ocean4`   | Ocean4, first record |

Floating ice thinner than 100 m is then calved, as is any ice beyond
$x = 640$ km.  For `iceocean1r`, the initial condition is the steady state.
`iceocean1ra` continues from `iceocean1r` and has no initial condition.

The `landice_data` step of `ocean3` and `ocean4` writes MALI's data-mode
file: 1,201 records of thickness, at the start of each month of years 1 to
101 in E3SM's no-leap calendar.  Each record is interpolated linearly in
time between the protocol's yearly records and then calved.

## MPAS-Ocean's initial conditions

In E3SM, MPAS-Ocean takes its land-ice pressure and fractions from MALI
through the coupler.  Its initial condition holds what the coupler delivers
from MALI's initial geometry, so the first import changes nothing.  The
`land_ice_on_ocean` step computes these fields as E3SM does: MALI's
ice-shelf exports with E3SM's gravity, the smoothed map from MALI to the
ocean, and MPAS-Ocean's normalization by the part of each cell below
sea level in MALI.  A cell with a land-ice fraction at or below
`[misomip_land_ice_on_ocean] min_land_ice_fraction`, $10^{-3}$, is open
ocean, with no land-ice pressure, fractions or mask, as MPAS-Ocean's
import leaves it.  For `ocean3` and `ocean4`, it does so for every record
of MALI's data-mode file.

The ocean steps are shared steps of the ocean component, in
`ocean/planar/misomip/<mesh_name>/`:

- `topo/map` and `topo/remap` remap the protocol's bed to the ocean's mesh,
  smoothed over the same distance as MALI's geometry;
- `<experiment>/init` builds the initial condition and forcing as the
  {ref}`ocean-isomip-plus` tasks with a thin film do, from these land-ice
  fields and with the projection's latitude and longitude.  The draft
  follows from the land-ice pressure with E3SM's gravity.  Every cell is
  kept, with a thin film under grounded ice;
- `<experiment>/ssh_adjustment/` adjusts the SSH to the land-ice pressure,
  as the ISOMIP+ tasks do.

The task's `ocean_initial_condition` step then writes the initial condition
E3SM reads: the mesh and the state the SSH adjustment finished with, in one
file.

The profiles of the initial condition and restoring are:

| Experiment    | Initial profiles   | Restoring |
|---------------|--------------------|-----------|
| `ocean0`      | WARM               | WARM      |
| `ocean1`      | COLD               | WARM      |
| `ocean2`      | WARM               | COLD      |
| `ocean3`      | WARM               | WARM      |
| `ocean4`      | COLD               | COLD      |
| `iceocean1r`  | COLD               | WARM      |
| `iceocean1ra` | from `iceocean1r`  | COLD      |

`iceocean1ra` continues from `iceocean1r` in E3SM, so it gets only the
restoring, made on `iceocean1r`'s initial geometry.

For `ocean0`–`ocean4`, the `forward` step runs MPAS-Ocean alone from the
adjusted initial condition, with the same physics, wetting and drying,
outflow and land-ice geometry, for comparison with E3SM.  It is not run by
default; run it with `polaris serial` in its directory.  Its length is
`[isomip_plus_forward] run_duration`, one month (744 hours) by default.  For
`ocean3` and `ocean4`, it reads the land-ice fields of every data-mode
record, one a month, and MPAS-Ocean interpolates between them, while MALI's
data mode steps from record to record.  `iceocean1r` has one only for its
namelist, which both IceOcean cases share; in it, MALI's geometry stays
fixed.  `iceocean1ra` has none.

The `forward` step runs with RK4.  Beside it, `split_explicit/forward`
runs from the same initial condition with the split-explicit time
integrator of the ISOMIP+ `split_explicit` tasks, with its time steps,
which scale with resolution, and the split form of the Coriolis term.  It
is not run by default either.

Besides the daily `output.nc`, `land_ice_fluxes.nc` and global statistics,
the `forward` step writes E3SM's monthly means,
`timeSeriesStatsMonthly.<date>.nc`, with the fields E3SM's monthly files
hold that the standalone run computes.  For `ocean3` and `ocean4`, they
also hold the land-ice pressure, fraction, floating fraction and the draft
the ocean's SSH sees, `landIceDraftForSsh`.

## Graph partitions

The `ocean_partitions` and `landice_partitions` steps partition each
model's graph with `gpmetis` into a range of core counts, which the config
options below set.  The partition files are named as E3SM names them:
`mpas-o.graph.info.part.<n>` for MPAS-Ocean and
`mpasli.graph.info.part.<n>` for MALI.

## Staged files

The task's `assemble` step links the experiment's files into
`assembled_files/` in its work directory, laid out as in E3SM's inputdata.
With the default grid names and creation date `<date>`, the files of
`ocean3` on the 4 km ocean mesh are:

```none
assembled_files/
    README
    inputdata/
        ocn/mpas-o/misomip-o4km/
            mpaso.misomip-o4km.ocean3.<date>.nc
            mpaso.misomip-o4km.ocean3_forcing.<date>.nc
            misomip-o4km.scrip.<date>.nc
            partitions/mpas-o.graph.info.<date>.part.<n>
        glc/mpasli/misomip-li1km/
            misomip-li1km.ocean3.<date>.nc
            misomip-li1km.ocean3_datamode.<date>.nc
            misomip-li1km.scrip.<date>.nc
            mpasli.graph.info.<date>.part.<n>
        cpl/gridmaps/misomip-o4km/
            map_misomip-o4km_to_misomip-li1km_aave.<date>.nc
        cpl/gridmaps/misomip-li1km/
            map_misomip-li1km_to_misomip-o4km_aave.<date>.nc
            map_misomip-li1km_to_misomip-o4km_smoothed.<date>.nc
    case_config/ocean3/
        README
        create_case.sh
        pes.xml
        user_mods/
            config_grids.xml
            shell_commands
            user_nl_mpaso
            user_nl_mali
    case_config/split_explicit/ocean3/
        ...
```

The `_forcing` file holds the ocean's interior restoring and the mask of
its outflow.  Only `ocean3` and `ocean4` have a data-mode file, and
`iceocean1ra` has no initial conditions.  The tree has no runoff map: the
cases turn off MALI's runoff to the ocean.

## Case configuration

The `case_config` step of each experiment writes the configuration of an
E3SM case, which the `assemble` step stages in `case_config/`.  The ocean
takes the options of the standalone `forward` step, with RK4.  The
`split_explicit/case_config` step writes a second configuration, staged in
`case_config/split_explicit/`, from `split_explicit/forward`.  Both read
the same staged files.  The split-explicit cases also need
E3SM-Ocean-Discussion/E3SM#175, the ocean's per-layer limit on drying,
which FAnSSIE does not have yet and which no option turns on, so build
them from a checkout that has it.  The README
gives the compset: MALI is static for `ocean0` to `ocean2`, replays its
geometry in data mode for `ocean3` and `ocean4`, and is prognostic, with
Albany's first-order velocity solver, for `iceocean1r` and `iceocean1ra`.

`create_case.sh` creates, sets up and builds a case from the `user_mods/`
directory beside it.  It needs an E3SM checkout with the changes for
idealized ice-shelf cases, at commit `5eb5f0385b` of the
`fanssie-ocn-glc-coupling` branch of E3SM-Ocean-Discussion/E3SM or later:

```bash
<assembled_files>/case_config/ocean0/create_case.sh \
    -e <E3SM checkout> -c <case directory> -p <project>
```

The case is for the machine Polaris was set up on, and the script stops
on any other.  The project and output root, `-r`, which holds the case's
build and run directories, default to CIME's, and the compiler, `-C`, to
the one Polaris was set up with.  The script does not submit the case;
run `./case.submit` in the case directory.

Every component runs on the same tasks, MALI on them in turn, with 1
thread a task.  The `case_config` step chooses the task count from the
ocean's cells per task, which the partitions' config options below bound,
and the machine's cores per node:

1. The ocean's cells over `goal_cells_per_core` give the target tasks.
   Over `max_cells_per_core` and `min_cells_per_core`, they give the
   fewest and most tasks.
2. On a batch system, the tasks fill whole nodes near the target, at
   least the fewest, and at most the most tasks.  A node is charged
   whether its cores run tasks or not, so the tasks fill it while each
   added task still speeds the run.
3. On a single node, the tasks are the target, or the node's cores if
   fewer.
4. The count is then the most tasks at or below that which both meshes
   are partitioned for.  Fewer than the fewest is an error.

On Chrysalis, `misomip-o4km-li1km` runs on 64 tasks, 1 node, and
`misomip-o2km-li1km` on 128 tasks, 2 nodes, by default.
The README and the step's log give the choice and what it comes from.
`-o` and `-g` choose other counts for the ocean and MALI, which must lie
between the fewest and most tasks and be among the staged partitions.
The script gives `create_newcase` the layout in `pes.xml` beside it, in
place of MPAS-Ocean's, whose layouts on some machines assume 2 threads a
task.

To create a case by hand instead, use the MCT driver:

```bash
./create_newcase --case <case> --driver mct \
    --compset 2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV \
    --res misomip-o4km-li1km \
    --user-mods-dirs <assembled_files>/case_config/ocean0/user_mods \
    --pesfile <assembled_files>/case_config/ocean0/pes.xml
```

and set `NTASKS_OCN` and `NTASKS_GLC` to counts the meshes are partitioned
for before `./case.setup`.

The directory holds:

- `config_grids.xml`, the grid file, which CIME uses in place of E3SM's;
- `shell_commands`, which names the staged files with case variables,
  including the smoothed map, in `GLC2OCN_SHELF_SMAPNAME`,
  gives MALI the time of the data-mode file's first record, from which it
  counts the months between records, turns off the ocean's thermal
  forcing of a prognostic MALI (`GLC_NZOC=0`), whose melt comes through
  ice-shelf coupling, turns off MALI's runoff to the ocean, turns on the coupler's monthly and annual budgets, and sets the
  coupling intervals, the first job's length, restarts every year and the
  number of jobs;
- `user_nl_mpaso`, with the options of the standalone ocean run, and every
  option whose E3SM default differs from that run's value, except the bulk
  wind stress, through which E3SM's ocean takes the coupler's.  The case
  has the standalone run's analysis members, `globalStats` and
  `timeSeriesStatsMonthly`, in place of E3SM's.  MPAS-Ocean imports
  MALI's geometry, and leaves cells at or below
  `[misomip_land_ice_on_ocean] min_land_ice_fraction` open ocean, through
  `config_glc_ice_shelf_coupling_min_floating_fraction`, as the initial
  conditions do;
- `user_nl_mali`, with the densities the ocean's land-ice pressure used,
  and, for `iceocean1r` and `iceocean1ra`, the {ref}`landice-mismip-plus`
  tasks' MALI options with the calving of their Ice1r run, and MALI's own
  defaults where E3SM's differ: no thermal solver, tracer advection, ISMIP6
  or face melt, or regional statistics.  The melt under floating ice comes
  from the ocean;
- for `iceocean1r` and `iceocean1ra`, `SourceMods/src.mali/` with the
  MISMIP+ tasks' Albany input.

The case needs an E3SM that has these case variables and grids it does not
list.

`create_case.sh` also runs `./preview_namelists` and then
`edit_streams.py`, beside it, which edits the streams files E3SM wrote
with more output.  The ocean's goes in `ocean_streams/` in the case
directory, with and without daily means of 3D fields, and MALI's in the
case's SourceMods:

- the ocean's daily means of `landIceFreshwaterFlux`,
  `frazilIceFreshwaterFlux`, `landIceFreshwaterFluxNotSentToGlc` and
  `landIceHeatFlux`, sampled every time step, in place of E3SM's daily
  list and hourly samples, and `landIceFreshwaterFluxNotSentToGlc`,
  `vertAleTransportTop`, `vertVelocityTop` and `normalLayerThicknessFlux`
  (the thickness flux
  the time integrator applies, which `user_nl_mpaso` turns on) in the
  monthly means;
- snapshots of the ocean's `layerThickness` at the start of each month,
  in `<case>.mpaso.hist.am.layerThicknessSnapshot.$Y-$M-$D.nc`, one a
  month, which with `vertAleTransportTop` give an overturning
  streamfunction that is exact where columns wet and dry, checked against
  one from `normalLayerThicknessFlux`;
- in one of the ocean's files, also the daily means of `normalVelocity`,
  `layerThickness`, `activeTracers` and `frazilLayerThicknessTendency`;
- the ocean's daily maximum of `kineticEnergyCell`, checked every time
  step, with the custom time series, and its global statistics every hour
  rather than every day;
- for `iceocean1r` and `iceocean1ra`, MALI's history every month, with
  the MISMIP+ tasks' output fields and the mesh, and a daily MALI stream
  with `floatingBasalMassBal` and `floatingBasalMassBalApplied`.

The script stops, writing nothing, if E3SM's streams files lack a stream
it edits or E3SM's Registry files a field it adds, so an E3SM change cannot
silently drop them.  A keepexe clone shares its SourceMods with the case it
was cloned from, so the script also stops if SourceMods is a link.

A case runs in jobs of up to 4 years for the 100-year experiments, and of
1 year for `ocean0` to `ocean2`, with restarts every year.  `ocean0` runs
3 years rather than the protocol's 1.  The ocean's daily means hold the
3D fields in the first year of every run, the last year of a 100-year run
and all of `ocean0`, and a job runs less than 4 years where it
must end or start at those years: a 100-year run takes jobs of 1 year, 24
of 4 years, 2 years and 1 year.  `create_case.sh` copies `next_segment.sh`
into the case directory, runs it once to set up the first job, and makes
it CIME's `POSTRUN_SCRIPT`, which CIME runs after each job, before it
resubmits the case.  The script reads the months run so far from the
coupler's restart pointer, `rpointer.drv`, and the case's start, so a
rerun or a manual resubmit gets the right job.  It sets the next job's
`STOP_N`, copies the ocean's streams file with or without the daily 3D
fields into `SourceMods/src.mpaso/`, and lowers `RESUBMIT` to the jobs
left, never raising it.  It logs each change in `next_segment.log` and
stops the chain, exiting with an error, if it cannot tell the date or
copy the file.  After its own work, it runs `postrun.local` in the case
directory, if there is one, with the case directory as its argument.

To stop the chain, set `RESUBMIT=0`.  To run on without the script
changing anything, create `next_segment.skip` in the case directory.

`iceocean1ra` is a branch run from an `iceocean1r` case's restarts:

```bash
<assembled_files>/case_config/iceocean1ra/create_case.sh \
    -e <E3SM checkout> -c <case directory> -p <project> \
    -R <iceocean1r case directory> -d <YYYY-MM-DD>
```

The script copies the coupler's, the ocean's and MALI's restarts on that
date into the new case's run directory and points `rpointer.drv` at the
coupler's.  MALI restores its calving front to the extent of the ice it
starts from, which the branch run takes from the `iceocean1r` restart, so
check first that the ice on that date has no ice-free holes behind the
calving front.

The step does not copy the files to inputdata.  Its work directory has
`sync_to_inputdata.sh` for doing that by hand, once the files have been
checked.

## Config options

E3SM's names for the grids are config options, which each pair of meshes
sets:

```cfg
# E3SM's names for the grids of this pair of meshes
[misomip_grids]

# the ocean grid
ocean_grid = misomip-o4km

# MALI's grid
landice_grid = misomip-li1km

# the model grid that pairs them
model_grid = misomip-o4km-li1km
```

Setup fails if any of them is blank.

The maps are made with the tool in `[mapping] map_tool`.

The partitions are made for core counts between bounds on the number of
cells per core, which also bound a case's tasks:

```cfg
# options for the graph partitions of the ocean's mesh, which also set the
# tasks of a case
[misomip_ocean_partitions]

# The number of cells per core a case aims for, which sets its target tasks
goal_cells_per_core = 100

# The approximate maximum number of cells per core, which sets the fewest
# cores a partition is made for and the fewest tasks of a case
max_cells_per_core = 2000

# The approximate minimum number of cells per core, which sets the most cores
# a partition is made for and the most tasks of a case
min_cells_per_core = 40
```

The goal and bounds come from 4 km and 2 km `ocean0` cases on Chrysalis.
At 4 km, doubling the tasks sped a case by 1.5 to 1.7 times above about
170 cells per task, and by about 1.25 times below, down to 21 cells per
task.  At 2 km, doubling sped a case by 1.57 times from 172 to 86 cells
per task, and by 1.43 times from 86 to 43.

The section `[misomip_landice_partitions]` sets the bounds for MALI,
30000 and 100 by default.  In `iceocean1r` and `iceocean1ra`, with a
prognostic MALI, they also bound the case's tasks.  MALI's
`goal_cells_per_core` is blank until prognostic cases give one, so the
ocean's goal sets the target.

The staged files are stamped with a creation date:

```cfg
# options for the staged files
[misomip_inputs]

# The creation date the staged files are stamped with, as YYYYMMDD.  Filled in
# with today's date at setup if left blank, so that re-running a step does not
# rename every staged file.
creation_date =
```

Setting up a task again in the same work directory fills in a new date, so
set it to keep the earlier names.

The case configuration has options of its own:

```cfg
# options for the E3SM case configurations
[misomip_case_config]

# Where an E3SM case finds the staged files: blank for E3SM's inputdata
# directory, DIN_LOC_ROOT, once they are there, or a directory with the same
# layout, such as a short link to an assembly's inputdata directory, for a
# case run before then.  {experiment} is replaced by each experiment's name,
# since each assembly has its own directory.
inputdata_root =

# The most months each job of a case runs, multiples of 12, for the 100-year
# runs and for the shorter ones.  A job runs fewer to end at the first year
# or start the last year of a 100-year run, the years whose daily means hold
# 3D fields.
long_run_months_per_job = 48
short_run_months_per_job = 12

# The wall-clock time each job of a case requests, as HH:MM:SS, or blank for
# the machine's default
job_wall_time =

# The times a day the ocean couples, a divisor of 86400 s whose interval is a
# whole number of ocean time steps
ocean_couplings_per_day = 48

# The times a day MALI couples, a divisor of ocean_couplings_per_day
landice_couplings_per_day = 1
```

The coupling intervals are E3SM's defaults: the ocean couples every 30
minutes, and MALI once a day.

MCT reads map paths of up to 256 characters, so a directory given in
`inputdata_root` needs a short path.  Each experiment's assembly has its
own `inputdata/` directory, so one setting can serve every experiment of a
pair of meshes through a short link per experiment:

```cfg
[misomip_case_config]
inputdata_root = <scratch>/misomip_inputdata/{experiment}
```

where `<scratch>/misomip_inputdata/ocean3` links to
`<work dir>/e3sm/init/misomip-o4km-li1km/misomip/ocean3/assemble/assembled_files/inputdata`,
and so on.
