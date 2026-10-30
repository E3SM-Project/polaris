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

## Graph partitions

The `ocean_partitions` and `landice_partitions` steps partition each
model's graph with `gpmetis` into a range of core counts, which the config
options below set.  The partition files are named as E3SM names them:
`mpas-o.graph.info.part.<n>` for MPAS-Ocean and
`mpasli.graph.info.part.<n>` for MALI.

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
