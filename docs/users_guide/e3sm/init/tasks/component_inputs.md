(e3sm-init-component-inputs-tasks)=

# Component Input Tasks

The `e3sm/init` `component_inputs` tasks stage the files an E3SM run needs
from a unified mesh: the base mesh with maps to the meshes culled from it,
SCRIP descriptions of those culled meshes, the MPAS-Ocean and MPAS-Seaice
meshes and initial conditions, and graph partitions for both models.

```{warning}
The staged tree is a **subset** of what E3SM needs for a new mesh.  It does
not include diagnostic mapping files or region masks, E3SM-to-CMIP maps,
iceberg or ice-shelf melt climatologies, sea-surface salinity restoring,
tidal mixing, or velocity-reconstruction coefficients.  Do not upload it to
the inputdata server on its own.  The same warning is staged as a `README`
alongside the files.
```

## Tasks

Three tasks per unified mesh, which share most of their steps:

- `e3sm/init/<mesh>/component_inputs/tasks/ocean`
- `e3sm/init/<mesh>/component_inputs/tasks/seaice`
- `e3sm/init/<mesh>/component_inputs/tasks/all`

For example, for `u-oi30-lr10`:

- `e3sm/init/u-oi30-lr10/component_inputs/tasks/all`

The supported unified mesh names are those listed in
{ref}`users-mesh-unified-base-mesh`.

Each task includes every step it depends on, from the base mesh onward, so
there is no need to set up any other task first.  The `ocean` and `all` tasks
include the realistic-global initial condition and dynamic adjustment,
because the ocean initial condition is the restart from the final adjustment
stage, not the interpolated initial state.  The adjustment is a multi-hour
model run on the finer meshes, and it needs an MPAS-Ocean build, given with
`--ocean_path` (`-p` does not apply, since the `e3sm/init` component has no
model of its own):

```bash
polaris setup -t e3sm/init/u-oi240-lr240/component_inputs/tasks/all \
    --ocean_path <path to MPAS-Ocean build> -w <work dir>
```

The `seaice` task does **not** include the ocean steps.  Every sea-ice product
is built from the culled mesh alone, so if you only need the sea-ice files,
use that task rather than `all`.

## Mesh short names

Each mesh needs an E3SM short name, which identifies a released mesh rather
than saying how the mesh was built.  The unified mesh team assigns a unique
two-digit ID when a mesh reaches E3SM's master branch and the inputdata
server:

| Polaris mesh name | E3SM short name |
|---|---|
| `u-oi30-lr10` | `u02-oi30-lr10` |
| `u-oi240-lr240` | `u03-oi240-lr240` |
| `u-oi6to18-lr12p5` | `u04-oi6to18-lr12p5` |
| `u-oi6to18-lr25` | `u05-oi6to18-lr25` |
| `u-oi-so12to30-lr10` | `uXX-oi-so12to30-lr10` |

These are registered in each mesh's config file, so the five unified meshes
set up without any extra configuration.

`u-oi-so12to30-lr10` is not headed for E3SM and so has no assigned ID.  Its
`uXX` placeholder is not a valid ID, which marks anything staged under it as a
test product.

A mesh with no registered short name fails at setup with a message naming the
option to set.  There is no default and no autodetection: only a person can
decide that a mesh has earned a short name.

## Staged layout

With `<short>` the mesh short name (e.g. `u04-oi6to18-lr12p5`), `<id>` its
leading ID (`u04`), `<grid>` E3SM's name for its ocean and sea-ice grid, the
short name without its land part (`u04-oi6to18`), and `<date>` the creation
date, the tree under `assemble/<target>/assembled_files/` is:

| Product | Staged path |
|---|---|
| base mesh + maps | `inputdata/share/meshes/mpas/unified/<id>/<short>.base.<date>.nc` |
| SCRIP, per region | `inputdata/share/meshes/mpas/unified/<id>/<short>.<region>.scrip.<date>.nc` |
| ocean SCRIP, again | `inputdata/ocn/mpas-o/<grid>/<short>.scrip.<date>.nc` |
| no-cavities SCRIP, again | `inputdata/ocn/mpas-o/<grid>/<short>.no_cavities.scrip.<date>.nc` |
| ocean mesh | `inputdata/share/meshes/mpas/unified/<id>/<short>.ocean.<date>.nc` |
| land mesh | `inputdata/share/meshes/mpas/unified/<id>/<short>.land.<date>.nc` |
| ocean IC | `inputdata/ocn/mpas-o/<grid>/mpaso.<grid>.<date>.nc` |
| ocean graph | `inputdata/ocn/mpas-o/<grid>/partitions/mpas-o.graph.info.<date>` |
| ocean partitions | `inputdata/ocn/mpas-o/<grid>/partitions/mpas-o.graph.info.<date>.part.<n>` |
| MOC masks | `inputdata/ocn/mpas-o/<grid>/<short>.mocBasinsAndTransects<features_date>.<date>.nc` |
| sea-ice IC | `inputdata/ice/mpas-seaice/<grid>/mpassi.<grid>.<date>.nc` |
| sea-ice partitions | `inputdata/ice/mpas-seaice/<grid>/partitions/mpas-seaice.graph.info.<date>.part.<n>` |

These are the directories and names E3SM reads the files from.

The three SCRIP regions are `ocean`, `ocean_no_cavities` and `land`, matching
the meshes the cull step produces.

The assembly step deletes `assembled_files/` and rebuilds it every time it
runs, so the tree only holds the files from the latest assembly.  This matters
because running `polaris setup` again in the same work directory sets
`creation_date` to that day's date (see
{ref}`e3sm-init-component-inputs-config`).  Without the delete, files with the
old date would remain in the tree alongside the new ones.

The base mesh is filed under `share/meshes/mpas/unified/` rather than Compass'
`share/meshes/mpas/ocean/`, because for a unified mesh it belongs to the
ocean, sea-ice, land and river components equally. The culled ocean and land
meshes sit beside it for the same reason: each describes a domain of the
unified mesh rather than a file one component reads at run time, and E3SM does
not look for a mesh under `ocn/mpas-o/`. The ocean mesh carries the vertical
coordinate as well, which is what makes it an ocean mesh rather than a
horizontal one.

Each unified mesh gets its own subdirectory of `share/meshes/mpas/unified/`,
named for its ID (`u04`).  One mesh puts six files there (a base mesh, three
SCRIP descriptions and two culled meshes), and the subdirectory keeps them
together so that one mesh's files can be found, copied or removed as a group.
The short name is still in every filename, so a file copied out of the tree
still says which mesh it belongs to.

The two ocean SCRIP files are staged twice: in the shared mesh directory under
their full region names, and beside the ocean products, since developers look
for them in both places.  Everything in `ocn/mpas-o/` belongs to the ocean, so
the `ocean` in the region name is dropped there, giving
`<short>.scrip.<date>.nc` and `<short>.no_cavities.scrip.<date>.nc`.  Both
copies are links to the same file.  The land SCRIP file is not staged there.

No sea-ice mesh is staged.  It is the culled ocean mesh under another name, so
it would be a second copy of `<short>.ocean.<date>.nc`, and MPAS-Seaice reads
its mesh from the initial condition anyway.  The step that builds it is still
needed, because the partition steps read its output.

No mesh is staged for `ocean_no_cavities`.  It is used to build mapping files,
and on meshes culled with the `calving_front` convention, which all current
unified meshes use, it is identical to the ocean mesh.  Its SCRIP description
is still staged.

### Base-to-culled index maps

The staged base mesh carries nine integer fields alongside the mesh itself:

`mapBaseTo{Ocean,OceanNoCavities,Land}{Cell,Edge,Vertex}`

Each is dimensioned by the **base** mesh and gives the one-based index of
that element on the named culled mesh, or zero if the element is not on it.
The one-based convention matches `cellsOnCell` and the other MPAS index
fields, and differs from the zero-based `mapCulledToBase*` the cull step
writes, so each field's `long_name` records which convention it follows.

These exist because the MOAB coupler maps to and from the base mesh.

### MOC masks

The MOC basin masks and their southern-boundary transects are a run-time input
to MPAS-Ocean, not an analysis product. E3SM points two streams at this one
file, `regionalMasksInput` and `transectMasksInput`, and two analysis members
that are on by default read them: `mocStreamfunction`, which E3SM enables per
mesh and has enabled for every mesh since `EC30to60E2r2`, and
`meridionalHeatTransport`, which is enabled for every mesh.

If the file is missing, neither member stops the run. `nRegions` and
`nRegionGroups` fall back to 1, the MOC member logs that its region group was
not found, and the run writes output computed for a meaningless region.
Because nothing in a run reports the problem, this file is staged with the
files a run needs rather than with the analysis products.

Its name carries two dates because they change independently:

- `<features_date>` is the version of the `geometric_features` aggregation the
  basins come from, upstream data shared by every mesh. It rides with the
  product name, as in the files already on the inputdata server
  (`oRRS18to6v3_mocBasinsAndTransects20210623.nc`).
- `<date>` is the creation date of this mesh's file, in the trailing field
  where every other staged file carries it.

Both are also written into the file as the `mask_features_date`,
`mask_features_source` and `creation_date` global attributes, so the
provenance survives a copy or a rename.

Only the `MOC Basins` group is built here.  The other mask groups are for
MPAS-Analysis and post-processing, and these tasks do not produce them yet.

## Copying into inputdata

The assembly step builds the tree but never writes outside its own work
directory. Copying into a shared inputdata directory is a decision a person
makes, so the step symlinks a script in for you to run by hand from
`component_inputs/assemble/<target>`:

```
./sync_to_inputdata.sh --dry-run /lcrc/group/e3sm/data/inputdata
./sync_to_inputdata.sh /lcrc/group/e3sm/data/inputdata
```

The first lists what would be copied without copying anything.

The destination must already exist, so that a typo stops the copy instead of
creating a second tree beside the real one.

The script runs `rsync --ignore-existing --recursive --copy-links`, so the
staged symlinks are copied as real files and anything already at the
destination is left alone.  This means a staged file whose contents changed
but whose name did not will not be updated.  Delete it from the destination
first if you want it replaced.

The script then sets directories to `2775` and files to `664` (user and group
read and write, world read, and setgid directories, as elsewhere in
inputdata), but only on the paths this tree adds.  The destination is shared
and often very large, so changing permissions on all of it would touch files
that belong to other meshes and other people.

## Graph partitions

The partition steps build a list of likely core counts from the mesh's cell
count and two config options, and run `gpmetis` once for each count (once per
region for sea ice, below).  The largest partition asked for is
`ncells / min_cells_per_core`.

`gpmetis` fails above roughly 750,000 parts, so a mesh with more than about
1.5 million ocean cells needs `min_cells_per_core` raised above the default
of 2. Only the two `u-oi6to18` meshes are currently that large, and their
configs set `min_cells_per_core = 6`, following what Compass does for
`rrs6to18`. A new mesh above that size needs the same treatment.

The calls are independent, so both partition steps run up to
`partition_cpus_per_task` of them at once on one node, the largest first.
Each call is a serial process, so the steps run best with a whole compute node
to themselves.  Lower `partition_cpus_per_task` if a node runs out of memory:
the largest partitions of a 4-million-cell mesh need about 2 GB each.  The
output of `gpmetis` goes to `gpmetis.log` in the step's work directory, and the
step's own log gets one line per partition.

`gpmetis` must be the 64-bit build, which the Polaris load script provides
from Spack. The 32-bit build in the pixi environment fails on the largest
meshes, and the step's error names it when that is the cause.

The sea-ice partitions give every core a piece of the ice-covered region and
a piece of the rest of the mesh, as MPAS-Tools' `create_seaice_partitions`
does. `prepare_seaice_partitions` decides which region each cell is in, and
the step then builds each region's graph from `cellsOnCell`. It does not call
`create_seaice_partitions`, which culls a copy of the mesh for each region and
took over two hours doing so on the finest mesh.

Both partition steps resume. A rerun rebuilds only the partitions that are
missing or unfinished, so a job that runs out of walltime costs the partitions
it was in the middle of, not the ones it had already written. Each partition
is written under another name and renamed once complete, so a kill cannot
leave a truncated file under a partition's own name. A file also counts as
finished only when it has one line per cell, which catches any truncated
partition an earlier run left.  Checking takes about a minute even for several
hundred files on the finest mesh.

## Ice-shelf cavities

Not supported.  These tasks are for meshes culled with the `calving_front`
Antarctic boundary convention, which have no cavities, and the staged files
carry no land-ice fields.  MPAS-Ocean does not require them: the `landIce*`
variables are gated on `landIcePressurePKG`, which is inactive when
`config_land_ice_flux_mode` is `off`.

## Omega

Not supported yet.  The staged files are for whichever ocean model the
dynamic adjustment runs, which is the one given with `--ocean_model` or
detected from the `--ocean_path` build.  If that is Omega, setup stops with a
message saying so, rather than staging Omega output under MPAS-Ocean names.

(e3sm-init-component-inputs-config)=

## Configuration Options

These tasks create a shared config file in their work directories:

```cfg
# Options related to staging the component input files for an E3SM run
[component_inputs]

# The E3SM short name of the mesh, which identifies a released mesh rather
# than saying how it was built.  There is no default: only a person can decide
# that a mesh has earned one.  Unified meshes register
# theirs as [unified_mesh] e3sm_short_name; setting this option overrides it.
mesh_short_name =

# The creation date the staged files are stamped with, as YYYYMMDD.  Filled in
# with today's date at setup if left blank, so that re-running a step does not
# rename every staged file.
creation_date =

# The approximate maximum number of cells per core, which sets the smallest
# graph partition created
max_cells_per_core = 30000

# The approximate minimum number of cells per core, which sets the largest
# graph partition created
min_cells_per_core = 2

# The number of graph partitions to build at once, if a node has that many
# cores.  Each is a serial gpmetis process, and on a 4-million-cell mesh the
# largest need about 2 GB each, so lower this if a node runs out of memory.
partition_cpus_per_task = 128

# The fewest cores the graph-partition steps can run with
partition_min_cpus_per_task = 1

# Whether to write every sea-ice partition to partition_diag.nc, for plotting
# with seaice_mesh.nc
plot_seaice_partitions = False
```

`creation_date` is filled in during setup, so it is saved in the work
directory's config file and rerunning a step keeps the same date.  Running
`polaris setup` again in the same work directory, though, sets it to that
day's date unless you set it yourself in a user config file.

## Running on a login node

Run these tasks on compute nodes.  They include the steps that build and cull
the mesh and remap topography, and the `ocean` and `all` tasks also include
the ocean initial condition and the dynamic-adjustment model runs.

Of the steps that make the component inputs themselves, all but three only
reorganize files that already exist.  The three exceptions are
`seaice_partition_map`, which builds the remapping weights for the sea-ice
partitions with MPI, and the two graph-partition steps, which run many
`gpmetis` processes at once.  On a login node those are limited to its
`login_cores`, which on the finest meshes stretches them to many hours.
