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

The `maps` steps make the conservative maps between the two meshes that
E3SM's coupler reads, in each direction.

## MALI's initial conditions and data-mode files

Every MALI initial condition starts from the cached MISMIP+ steady state
({ref}`landice-mismip-plus`), with the projection's latitude and longitude
and its time set to the start of the run.  The `landice_init` step of
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
ice-shelf exports with E3SM's gravity, the conservative map from MALI to
the ocean, and MPAS-Ocean's normalization by the part of each cell below
sea level in MALI.  For `ocean3` and `ocean4`, it does so for every record
of MALI's data-mode file.

The ocean steps are shared steps of the ocean component, in
`ocean/planar/misomip/<mesh_name>/`:

- `topo/map` and `topo/remap` remap the protocol's bed to the ocean's mesh
  without smoothing, so the ocean's grounding line stays at MALI's;
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
data mode steps from record to record.  `iceocean1r` and `iceocean1ra` have
no standalone counterpart.

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
    case_config/ocean3/
        README
        user_mods/
            config_grids.xml
            shell_commands
            user_nl_mpaso
            user_nl_mali
```

The `_forcing` file holds the ocean's interior restoring and the mask of
its outflow.  Only `ocean3` and `ocean4` have a data-mode file, and
`iceocean1ra` has no initial conditions.  The tree has no runoff map: the
cases turn off MALI's runoff to the ocean.

## Case configuration

The `case_config` step of `ocean0` to `ocean4` writes the configuration of
an E3SM case, which the `assemble` step stages in `case_config/`.  The
README gives the compset: MALI is static for `ocean0` to `ocean2` and
replays its geometry in data mode for `ocean3` and `ocean4`.  A case is
created from the `user_mods/` directory:

```bash
./create_newcase --case <case> --driver mct \
    --compset 2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV \
    --res misomip-o4km-li1km \
    --user-mods-dirs <assembled_files>/case_config/ocean0/user_mods
```

The directory holds:

- `config_grids.xml`, the grid file, which CIME uses in place of E3SM's;
- `shell_commands`, which names the staged files with case variables,
  turns off MALI's runoff to the ocean and sets the run length;
- `user_nl_mpaso`, with the options of the standalone ocean run, and every
  option whose E3SM default differs from that run's value, except the bulk
  wind stress, through which E3SM's ocean takes the coupler's;
- `user_nl_mali`, with the densities the ocean's land-ice pressure used.

The case needs an E3SM that has these case variables and grids it does not
list.  `iceocean1r` and `iceocean1ra`, with a prognostic MALI, have no case
configuration yet.

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
cells per core:

```cfg
# options for the graph partitions of the ocean's mesh
[misomip_ocean_partitions]

# The approximate maximum number of cells per core, which sets the fewest
# cores a partition is made for
max_cells_per_core = 2000

# The approximate minimum number of cells per core, which sets the most cores
# a partition is made for
min_cells_per_core = 40
```

The section `[misomip_landice_partitions]` sets the same options for MALI,
30000 and 100 by default.

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
# case run before then
inputdata_root =

# The months each job of a case runs, a divisor of every experiment's length
months_per_job = 1
```

MCT reads map paths of up to 256 characters, so a directory given in
`inputdata_root` needs a short path.
