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

For example, for `u.oi30.lr10`:

- `e3sm/init/u.oi30.lr10/component_inputs/tasks/all`

The supported unified mesh names are those listed in
{ref}`users-mesh-unified-base-mesh`.

The `ocean` and `all` tasks depend on the realistic-global dynamic
adjustment, because the ocean initial condition is the final adjustment
stage's restart rather than the interpolated initial state.  That is a
multi-hour model run on the finer meshes.

The `seaice` task does **not**: every sea-ice product is built from the
culled mesh alone, so it can be set up and run without the ocean.  If you
only need the sea-ice files, use that task rather than `all`.

## Mesh short names

Each mesh needs an E3SM short name, which identifies a released mesh rather
than saying how the mesh was built.  The unified mesh team assigns a unique
two-digit ID when a mesh reaches E3SM's master branch and the inputdata
server:

| Polaris mesh name | E3SM short name |
|---|---|
| `u.oi6to18.lr6to10` | `u01.oi6to18.lr6to10` |
| `u.oi30.lr10` | `u02.oi30.lr10` |
| `u.oi240.lr240` | `u03.oi240.lr240` |
| `u.oi.so12to30.lr10` | `uXX.oi.so12to30.lr10` |

These are registered in each mesh's config file, so the four unified meshes
set up without any extra configuration.

`u.oi.so12to30.lr10` is not headed for E3SM and so has no assigned ID.  Its
`uXX` placeholder is deliberately not a valid ID, so anything staged under it
is self-evidently a test artifact.

A mesh with no registered short name fails at setup with a message naming the
option to set.  There is no default and no autodetection: only a person can
decide that a mesh has earned a short name.

## Staged layout

With `<short>` the mesh short name and `<date>` the creation date, the tree
under `assemble/<target>/assembled_files/` is:

| Product | Staged path |
|---|---|
| base mesh + maps | `inputdata/share/meshes/mpas/unified/<short>.base.<date>.nc` |
| SCRIP, per region | `inputdata/share/meshes/mpas/unified/<short>.<region>.scrip.<date>.nc` |
| ocean mesh | `inputdata/ocn/mpas-o/<short>/<short>.<date>.nc` |
| ocean IC | `inputdata/ocn/mpas-o/<short>/mpaso.<short>.<date>.nc` |
| ocean partitions | `inputdata/ocn/mpas-o/<short>/partitions/mpas-o.graph.info.<date>.part.<n>` |
| MOC masks | `inputdata/ocn/mpas-o/<short>/<short>.mocBasinsAndTransects<features_date>.<date>.nc` |
| sea-ice mesh | `inputdata/ice/mpas-seaice/<short>/<short>.<date>.nc` |
| sea-ice IC | `inputdata/ice/mpas-seaice/<short>/mpassi.<short>.<date>.nc` |
| sea-ice partitions | `inputdata/ice/mpas-seaice/<short>/partitions/mpas-seaice.graph.info.<date>.part.<n>` |

The three SCRIP regions are `ocean`, `ocean_no_cavities` and `land`, matching
the meshes the cull step produces.

The assembly step deletes `assembled_files/` and rebuilds it every time it
runs, so the tree always describes one assembly rather than the union of
several. This matters after a fresh setup: `creation_date` is stamped with
today's date when the work-directory config is rebuilt, and without the delete
the previous run's names would linger, still resolving but now pointing at
newer content. Pin `[component_inputs] creation_date` in a user config if you
want the stamp to survive a re-setup.

The base mesh is filed under `share/meshes/mpas/unified/` rather than Compass'
`share/meshes/mpas/ocean/`, because for a unified mesh it belongs to the
ocean, sea-ice, land and river components equally.

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

If the file is missing, neither member aborts. `nRegions` and `nRegionGroups`
fall back to 1, the MOC member logs that its region group was not found and
continues, and the run produces output computed against a meaningless region.
Nothing in a run announces the problem, which is why this file is staged here
rather than with the analysis products in the follow-up work.

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

Only the `MOC Basins` group is built here. The other mask groups are for
MPAS-Analysis and post-processing and remain follow-up work.

## Graph partitions

`get_core_list` builds a list of likely core counts from the culled ocean
cell count and two config options, and one `gpmetis` call is made per entry.
The largest partition asked for is `ncells / min_cells_per_core`.

`gpmetis` fails above roughly 750,000 parts, so a mesh with more than about
1.5 million ocean cells needs `min_cells_per_core` raised above the default
of 2. Only `u.oi6to18.lr6to10` is currently that large, and its config sets
`min_cells_per_core = 6`, following what Compass does for `rrs6to18`. A new
mesh above that size needs the same treatment.

This step is also the longest in the workflow — hours on the finer meshes,
since both the number of core counts and the cost per call grow with the mesh
— so give it its own job with a generous walltime rather than sharing one with
the model runs.

Both partition steps resume. A rerun rebuilds only the partitions that are
missing or unfinished, so a job that runs out of walltime costs the partitions
it was in the middle of, not the ones it had already written. A file counts as
finished only when it has one line per cell, so a partition truncated by a
kill is rebuilt rather than trusted; checking takes about a minute even for
several hundred files on the finest mesh.

## Ice-shelf cavities

Not supported.  These tasks are for meshes culled with the `calving_front`
Antarctic boundary convention, which have no cavities, and the staged files
carry no land-ice fields.  MPAS-Ocean does not require them: the `landIce*`
variables are gated on `landIcePressurePKG`, which is inactive when
`config_land_ice_flux_mode` is `off`.

## Omega

Not supported yet.  Setting `[component_inputs] ocean_model = omega` raises
at setup with a message saying so, rather than staging MPAS-Ocean files under
an Omega name.

## Configuration Options

These tasks create a shared config file in their work directories:

```cfg
# Options related to staging the component input files for an E3SM run
[component_inputs]

# The E3SM short name of the mesh, which identifies a released mesh rather
# than saying how it was built.  There is deliberately no default: only a
# person can decide that a mesh has earned one.  Unified meshes register
# theirs as [unified_mesh] e3sm_short_name; setting this option overrides it.
mesh_short_name =

# The creation date the staged files are stamped with, as YYYYMMDD.  Filled in
# with today's date at setup if left blank, so that re-running a step does not
# rename every staged file.
creation_date =

# The ocean model the staged files are for: mpas-ocean or omega
ocean_model = mpas-ocean

# The sea-ice model the staged files are for: mpas-seaice or none
seaice_model = mpas-seaice

# The approximate maximum number of cells per core, which sets the smallest
# graph partition created
max_cells_per_core = 30000

# The approximate minimum number of cells per core, which sets the largest
# graph partition created
min_cells_per_core = 2

# Whether to plot the sea-ice partitions as they are created
plot_seaice_partitions = False
```

`creation_date` is filled in during setup so that it lands in the work
directory's config file.  Re-running a step then reuses the date it was set up
with, rather than renaming every staged file to today's.

## Running on a login node

Everything except `seaice_partition_map` is post-processing of files that
already exist, and is safe to run on a login node.  That one step builds the
remapping weights the sea-ice partitioning needs, using MPI, and wants a
compute node; the partitioning itself only applies them and is serial.

The `ocean` and `all` tasks additionally depend on the dynamic-adjustment
model runs, which are compute-node jobs in their own right.
