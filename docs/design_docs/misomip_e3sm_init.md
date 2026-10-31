# MISOMIP Inputs for E3SM

Creation date: 2026/10/30

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

E3SM will run the ISOMIP+ experiments Ocean0–4 and the MISOMIP1
experiments IceOcean1r and IceOcean1ra, with MPAS-Ocean coupled to MALI
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016)).
Section and equation numbers in this design refer to that protocol. In
Ocean0–2, the ice-shelf geometry is fixed. In Ocean3 and Ocean4, it
evolves for 100 years as the protocol prescribes, and MALI replays it in
data mode: MALI reads its thickness from a file instead of evolving it. In
IceOcean1r and IceOcean1ra, MALI evolves from the MISMIP+ steady state.

This design covers the inputs those E3SM runs read:

- **Meshes and maps.** Shared steps in `e3sm/init` give the ocean's
  planar 4 and 2 km meshes and MALI's 1 km mesh latitude and longitude
  from one projection. They write SCRIP files and the maps between the two
  models that E3SM's coupler reads.
- **E3SM inputs.** Tasks `e3sm/init/<mesh_name>/misomip/<experiment>`
  build MALI's initial conditions and data-mode files, MPAS-Ocean's
  initial conditions, graph partitions for both models and each
  experiment's case configuration. They stage the files in a tree laid out
  like E3SM's inputdata.

The work reuses three parts of Polaris rather than copying them:

- the ISOMIP+ tasks ([ISOMIP+ design](isomip_plus.md)): the ocean meshes,
  geometry, initial condition, thin film, outflow, SSH adjustment and
  E3SM physics. Their
  [Planned Extensions](isomip_plus.md#planned-extensions) list what
  Ocean3–4 and MISOMIP1 in E3SM need from Polaris, which this design
  provides;
- the MISMIP+ tasks ([MISMIP+ design](mismip_plus.md)): MALI's mesh,
  steady state, namelist and Albany input;
- the component-input tasks
  ([component-inputs design](e3sm_init_component_inputs.md)): the
  staging, partitioning and path helpers in `polaris/e3sm/init/`.

The E3SM runs use FAnSSIE, the E3SM development branch for
ocean–ice-sheet coupling that Polaris has as the `e3sm_submodules/FAnSSIE`
submodule. E3SM itself needs changes to run these cases: an ocean without
an atmosphere, the ocean's coupler areas from the map, namelists for
wetting and drying, input files named by case variables, and a switch that
keeps MALI's calving runoff out of the ocean. A separate design covers
these E3SM changes.

No E3SM configuration has run a planar ocean. The first E3SM run will be
4 km Ocean0 with MALI's geometry fixed, using this design's meshes, maps
and Ocean0 initial conditions. Details that only that run can settle are
marked *(first E3SM run)*. None of them blocks this design
([What the first E3SM run settles](#what-the-first-e3sm-run-settles)).

Success means:

- for each ocean resolution, SCRIP files and the coupler's maps for the
  pair of meshes, with map areas within $4\times10^{-5}$ of model areas;
- for each experiment, initial conditions for both models, MALI's
  data-mode file for Ocean3–4, partitions and a case configuration, staged
  at inputdata-style paths;
- ocean land-ice fields that equal the coupler's map applied to MALI's
  initial export, normalized as MPAS-Ocean's import does;
- a standalone MPAS-Ocean run from the same inputs.

## Requirements

### Requirement: Both meshes share one geographic frame

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The ocean's and MALI's meshes take latitude and longitude from one
projection of the protocol's coordinates. Areas on the sphere and planar
model areas agree to $4\times10^{-5}$.

### Requirement: The coupler can map fields between the models

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

For each pair of meshes, Polaris provides SCRIP files and the maps E3SM's
coupler uses for ice-shelf coupling between MPAS-Ocean and MALI.

### Requirement: MALI starts each experiment from the protocol's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

MALI's initial condition for Ocean0–4 holds the protocol's input geometry,
calved as the protocol prescribes. For IceOcean1r, it is the MISMIP+
steady state. Each includes latitude and longitude.

### Requirement: MALI replays the geometry of Ocean3 and Ocean4

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

In data mode, MALI's geometry follows the protocol's Ocean3 or Ocean4
geometry, interpolated in time and calved as the protocol prescribes.

### Requirement: The ocean starts from MALI's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

In E3SM, MPAS-Ocean takes its land-ice pressure and fractions from MALI
through the coupler. Its initial condition holds what the coupler delivers
from MALI's initial geometry, so the first import changes nothing. The
initial condition has a thin film under grounded ice, the experiment's
profiles, restoring and outflow, and an SSH in balance with the land-ice
pressure. It sets `sphere_radius` to E3SM's radius.

```{admonition} Rationale
Separate remaps of the input geometry for each model would disagree at
grounding lines. Going through the coupler's map makes the first import
a no-op for any MALI mesh.
```

### Requirement: Both models can be decomposed at the planned task counts

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Polaris partitions both meshes for every task count the E3SM cases plan to
use.

### Requirement: Each experiment has a case configuration

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A grid file and a user-mods directory configure an E3SM case for each
experiment. Its physics and options come from the same configuration as
the standalone MPAS-Ocean and MALI runs.

### Requirement: The inputs are staged as on inputdata

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The files are staged in a tree laid out like E3SM's inputdata. Copying
them there is a separate, manual step.

### Requirement: A standalone ocean run shares the inputs

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

For Ocean0–4, Polaris can run MPAS-Ocean alone from the E3SM initial
condition, with the same physics and land-ice geometry, so E3SM's ocean
can be compared with it.

## Algorithm Design

### Algorithm Design: Both meshes share one geographic frame

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Both meshes are planar in the protocol's coordinates:

- the ocean's is the ISOMIP+ tasks' shared mesh, which covers the ISOMIP+
  box. Every experiment keeps all of its cells, with a thin film under
  grounded ice, as the ISOMIP+ wetting and drying tasks do;
- MALI's is the MISMIP+ tasks' uniform 1 km mesh ([D1](#decisions)).

```{admonition} Rationale
The grounding line moves in Ocean3–4 and IceOcean1r, so grounded cells
must be active from the start. With the same cells in Ocean0–2, every
experiment at a resolution uses one set of maps.
```

Latitude and longitude come from one transverse Mercator projection on a
sphere of E3SM's radius ([D2](#decisions)):

```none
+proj=tmerc +R=6371220 +lat_0=-75 +lon_0=0 +k_0=1
+x_0=-40000 +y_0=560000 +axis=nwu +units=m
```

The ISOMIP+ box's center, $x = 560$ km and $y = 40$ km, lies at 75°S on
the central meridian, which runs along $x$. As in the protocol (Sect.
3.1.1), $x$ points north and $y$ west. Planar lengths along $x$ equal the
sphere's on the centerline and exceed them by 2 × 10⁻⁵ at the walls.

Each SCRIP file takes its cell polygons from the vertices. MALI's cells on
$y = 0$ and $y = 80$ km are trimmed to the domain, so their map areas equal
their halved model areas
([MISMIP+ design](mismip_plus.md#algorithm-design)). MALI's gutter cells
and all ocean cells stay whole. No cell is masked.

*(first E3SM run)* If E3SM cannot run a planar ocean, a step maps the
ocean mesh onto the sphere with this projection, before the SCRIP file is
written. Lengths change by less than $2\times10^{-5}$, and nothing
downstream changes.

### Algorithm Design: The coupler can map fields between the models

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

With ice-shelf coupling on, FAnSSIE's MCT coupler reads these maps
between the ocean (ocn) and MALI (glc):

| Coupler variable          | What the coupler maps with it             | Method       |
|---------------------------|-------------------------------------------|--------------|
| `GLC2OCN_FMAPNAME`        | all of MALI's ice-shelf exports           | conservative |
| `GLC2OCN_SMAPNAME`        | nothing; read at initialization           | conservative |
| `OCN2GLC_SHELF_FMAPNAME`  | melt flux                                 | conservative |
| `OCN2GLC_SHELF_SMAPNAME`  | interface temperature and its weight      | conservative |

`GLC2OCN_FMAPNAME` is the map $R$ that carries MALI's geometry to the
ocean. `GLC2OCN_SMAPNAME` names the same file. With ice-shelf coupling,
`GLC2OCN_ICE_RMAPNAME` is not read, and `OCN2GLC_TF_SMAPNAME` is read only
with thermal-forcing coupling, which these runs leave off. Neither is
built.

Polaris makes no runoff map. The E3SM changes keep MALI's calving and
face-melt runoff out of the ocean, and MALI has no other runoff here. The
coupler still reads `GLC2OCN_LIQ_RMAPNAME` at initialization, so the
design of the E3SM changes settles what E3SM needs in its place.

```{admonition} Rationale
The coupler maps the ocean's interface temperature without normalizing,
and MALI divides by the remapped weight. A conservative map makes that an
area-weighted mean, as for the fluxes. E3SM's realistic grids use bilinear
state maps; either works with the division.
```

*(first E3SM run)* Whether E3SM needs the unused maps, and which method
the state maps take.

### Algorithm Design: MALI starts each experiment from the protocol's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Every initial condition starts from the MISMIP+ tasks' cached steady
state, which holds every field MALI needs, and keeps its bed (Eqs. 1–4).

For Ocean0–4, the thickness is replaced where the protocol's input covers
MALI's mesh, $x \ge 320$ km:

| Experiment | Input                         |
|------------|-------------------------------|
| Ocean0, 1  | Ocean1                        |
| Ocean2     | Ocean2                        |
| Ocean3     | Ocean3, first record          |
| Ocean4     | Ocean4, first record          |

1. The input thickness, upper surface minus lower surface, is remapped
   conservatively from the input's 1 km grid to MALI's cells, with both
   described by the projection above.
2. It is calved on MALI's cells ([D3](#decisions)). Ice that floats by
   MALI's flotation test, with densities 918 and 1028 kg m⁻³, and is
   thinner than 100 m is removed, as is ice beyond $x = 640$ km.

Upstream of $x = 320$ km, MALI keeps its steady state ([D1](#decisions)).

For IceOcean1r, the initial condition is the steady state, with its time
set to the start of the run, as in the MISMIP+ experiments. IceOcean1ra
continues from IceOcean1r's E3SM restart and needs no initial condition.

Latitude and longitude of cells, edges and vertices come from the
projection. MALI needs no `sphere_radius`: in E3SM, its coupler areas
already divide its planar areas by the square of E3SM's radius.

### Algorithm Design: MALI replays the geometry of Ocean3 and Ocean4

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

All 101 yearly records are remapped as above, without calving. Records are
written at the start of each month of years 1 to 101, 1,201 in all, in
E3SM's no-leap calendar. Each holds the thickness interpolated linearly in
time between the yearly records around it, and then calved. Upstream of
$x = 320$ km, every record holds the steady state's thickness.

```{admonition} Rationale
The protocol interpolates the yearly geometry linearly in time and calves
after interpolating (Sects. 3.1.2 and 3.2.4). MALI's data mode steps from
record to record without interpolating, so yearly records would move the
geometry in yearly jumps.
```

The files hold thickness only, which is all MALI's data mode reads. The
first record equals the initial condition. Each file is about 0.6 GB.

### Algorithm Design: The ocean starts from MALI's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

1. **MALI's export.** From MALI's initial thickness $H$ and bed, Polaris
   computes what MALI exports to the coupler: the below-sea-level mask
   $m$, the pressure $m \rho_i g H$, and $m \phi_f$ and $m \phi_g$ from
   MALI's floating and grounded masks. It uses E3SM's gravity,
   9.80616 m s⁻², not the 9.80665 m s⁻² of Polaris's constants. In data
   mode, it does so for every record.
2. **Through the map.** $R$ is applied to each, and the result is
   normalized as MPAS-Ocean's import does: $p = R(m \rho_i g H)/R(m)$,
   with floating and land-ice fractions $R(m\phi_f)/R(m)$ and
   $R(m(\phi_f + \phi_g))/R(m)$, each capped at 1. All three are zero
   where $R(m) = 0$.
3. **Geometry and state.** The ISOMIP+ initial condition is built with
   these fields in place of its remapped input geometry. The draft follows
   from the pressure with $\rho_{sw} = 1028$ kg m⁻³ and E3SM's gravity.
   Where it is at or below the bed, the cell holds the ISOMIP+ tasks' thin
   film: fresh water, $10^{-3}$ m thick per active layer, the column at
   which MPAS-Ocean caps the land-ice pressure. The bed is the protocol's,
   remapped without smoothing ([D4](#decisions)). The profiles, restoring
   and outflow through the restoring region are the ISOMIP+ tasks'.
4. **Frame.** The projection's latitude and longitude replace the ISOMIP+
   tasks', and the global attribute `sphere_radius` is 6,371,220 m.
   `fCell` is the ISOMIP+ tasks' constant $f = -1.409\times10^{-4}$ s⁻¹,
   so it does not depend on latitude.
5. **SSH adjustment.** The ISOMIP+ SSH adjustment runs with standalone
   MPAS-Ocean, RK4 and the thin-film settings, holding the pressure fixed.
   Its output, with the mesh in the same file, is the initial condition
   E3SM reads.

| Experiment  | Initial profiles | Restoring | Geometry from MALI        |
|-------------|------------------|-----------|---------------------------|
| Ocean0      | WARM             | WARM      | static, Ocean1 input      |
| Ocean1      | COLD             | WARM      | static, Ocean1 input      |
| Ocean2      | WARM             | COLD      | static, Ocean2 input      |
| Ocean3      | WARM             | WARM      | data mode, first record   |
| Ocean4      | COLD             | COLD      | data mode, first record   |
| IceOcean1r  | COLD             | WARM      | steady state              |
| IceOcean1ra | from IceOcean1r  | COLD      | from IceOcean1r           |

IceOcean1ra gets only a restoring file.

*(first E3SM run)* Steps 1 and 2 reproduce code in FAnSSIE's MALI coupling
interface and MPAS-Ocean's import. The first coupling step checks that
they match.

### Algorithm Design: Both models can be decomposed at the planned task counts

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Each model's graph is partitioned with `gpmetis` into the core counts that
`get_core_list()` gives between bounds on cells per core. The bounds are
config options, set so the counts include the planned layouts: 8 and 36
ocean tasks at 4 and 2 km, up to 256 at 2 km, and MALI's counts
*(first E3SM run)*.

### Algorithm Design: Each experiment has a case configuration

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Each experiment's case configuration holds:

- **a user-mods directory** with:
  - a grid file, `config_grids.xml`, which CIME uses in place of E3SM's.
    It holds E3SM's grid defaults, a model grid for the pair of meshes,
    the two grids' domains and the maps above, but no runoff maps. The
    other components' grids are null. Experiments of a pair hold the same
    file;
  - `user_nl_mpaso`: the options of the standalone runs: the ISOMIP+
    tasks' E3SM physics, wetting and drying, and outflow. Every option
    whose E3SM default differs from the standalone value is written;
  - `user_nl_mali`: the MISMIP+ tasks' MALI options, read from their
    files, with `config_always_compute_fem_grid = .false.`;
  - MALI's Albany input for IceOcean1r and IceOcean1ra, the MISMIP+
    tasks' file;
  - a MALI history stream with thickness, `bedTopography` and the mesh
    variables the MISMIP+ diagnostics need;
  - `shell_commands` with the XML changes: the case variables that name
    the initial conditions, the ocean's interior restoring and tidal mask,
    the data-mode file and partitions, MALI's runoff to the ocean turned
    off, and the run length in jobs;
- **a README** with the compset by long name, which sets MALI's mode
  (static, data or prognostic).

```{admonition} Rationale
By default, MALI rebuilds Albany's finite-element grid at every velocity
solve, and each rebuild leaks memory, so a long prognostic run grows and
slows.
```

If the MISMIP+ tasks add thin-ice calving and iceberg removal to Ice1r,
IceOcean1r takes them too, since its options are read from theirs.

The case variables, the runoff option and the compsets are those of the
E3SM changes for idealized ice-shelf cases. E3SM's default coupling
intervals divide evenly into the ocean's time steps. *(E3SM runs)* The
layouts.

### Algorithm Design: The inputs are staged as on inputdata

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

```none
assembled_files/
    README
    inputdata/
        ocn/mpas-o/<ocn grid>/
            mpaso.<ocn grid>.<experiment>.<date>.nc
            mpaso.<ocn grid>.<experiment>_forcing.<date>.nc
            <ocn grid>.scrip.<date>.nc
            partitions/mpas-o.graph.info.<date>.part.<n>
        glc/mpasli/<glc grid>/
            <glc grid>.<experiment>.<date>.nc
            <glc grid>.<experiment>_datamode.<date>.nc
            <glc grid>.scrip.<date>.nc
            mpasli.graph.info.<date>.part.<n>
        cpl/gridmaps/<ocn grid>/map_<ocn grid>_to_<glc grid>_<method>.<date>.nc
        cpl/gridmaps/<glc grid>/map_<glc grid>_to_<ocn grid>_<method>.<date>.nc
    case_config/<experiment>/
        README
        user_mods/
```

Initial conditions carry the experiment in their names, since each
experiment has its own. The realistic component inputs have one set per
mesh. `case_config/` is not inputdata.

### Algorithm Design: A standalone ocean run shares the inputs

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A forward run starts from the E3SM initial condition, with the same
physics, wetting and drying, outflow and RK4. For Ocean3–4, its land-ice
forcing is every data-mode record through $R$, from step 2 above. Its
length is a config option, one month by default, for comparison with the
first E3SM run. IceOcean1r and IceOcean1ra have no standalone counterpart.

MPAS-Ocean interpolates land-ice forcing in time, while MALI's data mode
steps from record to record. Comparisons of E3SM's Ocean3–4 with the
standalone runs treat this as a known difference.

## Implementation

### Implementation: Both meshes share one geographic frame

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

`<mesh_name>` names a pair of meshes, as the unified meshes' names do:
`misomip-o4km-li1km` and `misomip-o2km-li1km`. Shared steps of the
`e3sm/init` component:

```none
e3sm/init/<mesh_name>/ocean_mesh            lat/lon, SCRIP, graph
e3sm/init/<mesh_name>/landice_mesh          lat/lon, SCRIP
e3sm/init/<mesh_name>/maps/<map>            one step per map
e3sm/init/<mesh_name>/ocean_partitions
e3sm/init/<mesh_name>/landice_partitions
e3sm/init/<mesh_name>/misomip/<experiment>  tasks
```

The projection string and helpers are in
`polaris/tasks/e3sm/init/misomip/projection.py`. `ocean_mesh` keeps
`xIsomipCell` and `yIsomipCell`, which the ISOMIP+ restoring reads and
which the ISOMIP+ tasks compute from their own projection. SCRIP files
come from `mpas_tools`' `scrip_from_mpas()`, followed by the trimming of
MALI's wall cells.

The ocean mesh is the ISOMIP+ tasks' `topo/cull_mesh` output and MALI's is
the MISMIP+ tasks' `mesh/planar/mismip_plus/1km/mesh`, through public
accessors (see
[Changes to the ISOMIP+ and MISMIP+ tasks](#implementation)).

### Implementation: The coupler can map fields between the models

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Each map is a `MappingFileStep` from the two SCRIP files, with the tool
in `[mapping] map_tool`. The component-input tasks' `scrip.py` and
`maps.py` do not apply: the first restamps SCRIP files the cull step
wrote, and the second builds index maps, not coupler maps. Map filenames
follow E3SM's `map_<src>_to_<dst>_<method>.<date>.nc`.

### Implementation: MALI starts each experiment from the protocol's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

One `landice_init` step per experiment, with the remapping as a
`MappingFileStep` from the input grid to MALI's mesh, shared by the
experiments of a pair. MALI's flotation test and the calving are functions
in `polaris/tasks/e3sm/init/misomip/`, so they can be unit tested.

### Implementation: MALI replays the geometry of Ocean3 and Ocean4

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A `landice_data` step in the Ocean3 and Ocean4 tasks, writing records one
at a time.

### Implementation: The ocean starts from MALI's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Steps 1 and 2 are an `e3sm/init` step, `land_ice_on_ocean`, that writes
the fields on the ocean's mesh for every record. Steps 3–5 run MPAS-Ocean
or build its inputs, so they are shared steps of the `ocean` component
with an ocean config ([D5](#decisions)):

```none
ocean/planar/misomip/<mesh_name>/topo/...            unsmoothed bed
ocean/planar/misomip/<mesh_name>/<experiment>/init
ocean/planar/misomip/<mesh_name>/<experiment>/ssh_adjustment/...
ocean/planar/misomip/<mesh_name>/<experiment>/forward
```

Their code is in `polaris/tasks/ocean/misomip/`, which imports from
`polaris/tasks/ocean/isomip_plus/` and nothing from `e3sm`:

- `init` subclasses the ISOMIP+ `Init`, reading the mesh from
  `ocean_mesh` and the land-ice fields from `land_ice_on_ocean`;
- the bed comes from the ISOMIP+ `TopoMap` and `TopoRemap` without
  smoothing, at the paths above;
- the SSH adjustment uses the ISOMIP+ `SshForward`, through a function in
  `polaris/ocean/ice_shelf/` that creates the steps in a given component.
  `IceShelfTask.setup_ssh_adjustment_steps()` calls it;
- `compute_land_ice_draft_from_pressure()` and its siblings take an
  optional gravity.

### Implementation: Both models can be decomposed at the planned task counts

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Two `GraphPartitionStep`s from `polaris/e3sm/init/graph_partition.py`,
unchanged, with config sections `[misomip_ocean_partitions]` and
`[misomip_landice_partitions]`.

### Implementation: Each experiment has a case configuration

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

A `case_config` step per experiment writes the user-mods directory and
README. `user_nl_mpaso` comes from the namelist the standalone forward step
renders: the options whose values differ from MPAS-Ocean's defaults, less
those E3SM sets itself (run times, I/O, partitions and analysis members),
plus a list of options whose E3SM defaults differ, with the standalone
values. A case can read the staged files from a directory other than
inputdata, for a run before they are copied there.

```{admonition} Rationale
The namelist includes everything the standalone step sets, from YAML files
and from config options, such as the equation of state, so the list of
YAML files is not repeated.
```

### Implementation: The inputs are staged as on inputdata

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A subclass of `AssembleStep` per experiment. `polaris/e3sm/init/inputdata.py`
gains `landice_dir(grid)` and `gridmaps_dir(grid)`, which any workflow
would stage the same way. MISOMIP's own path functions are in
`polaris/tasks/e3sm/init/misomip/names.py`, built on `ocean_dir()` and
`landice_dir()`. An `ocean_initial_condition` step merges the mesh into
the SSH adjustment's output, which holds only the state. Copying to
inputdata uses
`polaris/e3sm/init/sync_to_inputdata.sh`, by hand.

### Implementation: A standalone ocean run shares the inputs

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

`forward` subclasses the ISOMIP+ `Forward`. The Ocean0–4 tasks include it
with `run_by_default=False`.

### Implementation: Changes to the ISOMIP+ and MISMIP+ tasks

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

- **ISOMIP+ shared steps:** a public `get_isomip_plus_mesh_steps(resolution)`
  in `polaris/tasks/ocean/isomip_plus/` returns the shared mesh and
  topography steps and their config. It creates them with
  `get_or_create_shared_config()` and `get_or_create_shared_step()`, as
  `get_mismip_plus_mesh_steps()` does, so the ISOMIP+ tasks and
  `e3sm/init` share one instance. The private `_get_shared_steps()`
  constructs steps directly, so calling it twice raises "A different step
  has already been added".
- **ISOMIP+ `Init`:** public methods for the mesh file and for the
  land-ice fields, which a subclass overrides. `_compute_geometry()` stays
  as it is otherwise.
- **MISMIP+, optional:** the namelist, Albany input and MALI options move
  from `polaris/tasks/landice/mismip_plus/` to
  `polaris/landice/mismip_plus/`.

## Testing

### Testing and Validation: Both meshes share one geographic frame

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Unit tests: the projection's center, orientation and scale at the walls.
In a run: map areas against model areas, to $4\times10^{-5}$, and MALI's
wall-cell map areas against their halved model areas.

### Testing and Validation: The coupler can map fields between the models

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

In a run: the conservative maps conserve a constant field's integral to
round-off. The first E3SM run checks the rest.

### Testing and Validation: MALI starts each experiment from the protocol's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Unit tests: MALI's flotation test and the calving. In a run: the
grounding line and ice volume against the input's, with the MISMIP+
diagnostics.

### Testing and Validation: MALI replays the geometry of Ocean3 and Ocean4

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Unit tests: record times, interpolation weights and calving on a small
synthetic input. In a run: the first record equals the initial condition.

### Testing and Validation: The ocean starts from MALI's geometry

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Unit tests: the normalization on a synthetic export and map. In a run: the
land-ice fields, recomputed from the staged map and MALI file, equal the
initial condition's to round-off, and SSH adjustment converges as in the
ISOMIP+ thin-film tasks. The first E3SM run checks them against E3SM's
first coupling step.

### Testing and Validation: Both models can be decomposed at the planned task counts

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The planned counts are among the partitions.

### Testing and Validation: Each experiment has a case configuration

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Unit tests: the user-mods options match the standalone namelist, and the
list of options whose E3SM defaults differ matches E3SM's defaults. The
E3SM runs of each experiment test the cases themselves.

### Testing and Validation: The inputs are staged as on inputdata

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Unit tests of the path functions, and a setup test that fails without
grid names.

### Testing and Validation: A standalone ocean run shares the inputs

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A month of 4 km Ocean0 runs to completion. No task joins a suite; the
tasks take tens of minutes to hours on a node.

## What the first E3SM run settles

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

- whether E3SM runs a planar ocean, or needs the ocean mesh mapped onto
  the sphere;
- which maps E3SM needs, and the state maps' method;
- whether Polaris's copy of MALI's export and MPAS-Ocean's import matches
  E3SM at the first coupling step;
- whether E3SM's MPAS-Ocean reads `fCell` from the initial condition
  rather than computing it from `latCell`;
- the case configuration's details and MALI's layouts.

None blocks this design. Each changes which maps are built or what the
case configuration holds, not the steps or the layout. A spherical ocean
adds one step before the SCRIP file. The implementation starts with the
meshes, maps and initial conditions, which the first E3SM run uses. The
case configuration follows that run and the E3SM changes.

## Decisions

### D1: Every experiment uses the MISMIP+ 1 km MALI mesh

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

Ocean0–4 use the mesh IceOcean1r uses. It covers all of the ISOMIP+ box's
ice. Upstream of the protocol's input, $x < 320$ km, MALI keeps its
steady state, which no ocean cell sees.

```{admonition} Rationale
One MALI mesh means one set of SCRIP files and maps per ocean resolution.
The E3SM runs of Ocean0–4 then test the maps that IceOcean1r and
IceOcean1ra use.
```

Rejected: a MALI mesh of the ISOMIP+ box. It would need its own mesh step,
SCRIP files and maps, and its maps would not be the ones IceOcean1r uses.

### D2: The projection is centered on the ISOMIP+ box

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

A transverse Mercator projection puts the box's center at 75°S, the
protocol's latitude, on the central meridian. `+axis=nwu` maps the
protocol's north-pointing $x$ and west-pointing $y$ without a rotation in
code. The `e3sm/init` steps apply it and leave the ISOMIP+ tasks' meshes
alone.

Rejected: the ISOMIP+ tasks' polar stereographic projection, which puts
the box at 65–69°S and scales lengths by 1.016 to 1.032; and switching the
ISOMIP+ tasks to this projection, which would change their baselines for
no benefit to the standalone runs.

### D3: Calving follows remapping, on MALI's cells

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The 100 m criterion is applied to MALI's thickness after remapping, and in
data mode after interpolation in time, as the protocol orders (Sect.
3.1.2).

Rejected: calving the input grid before remapping, as the ISOMIP+ tasks do
for the ocean. MALI would then hold thin ice from cells that straddle the
calving front.

### D4: The ocean's bed is not smoothed

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The ocean's bed is the protocol's, remapped conservatively to the ocean's
cells. The ISOMIP+ tasks smooth theirs by remapping onto cells expanded by
a factor of 2.

```{admonition} Rationale
The land-ice fields cannot be smoothed: the first import must change
nothing. Smoothing only the bed would move the ocean's grounding line away
from MALI's.
```

*Effect:* the bed and draft of E3SM's ocean are unsmoothed, while the
ISOMIP+ tasks smooth both. E3SM's runs are therefore compared with this
design's standalone run, not with the ISOMIP+ tasks. A month of 4 km
Ocean0 in that run is where pressure-gradient noise from the unsmoothed
geometry would show.

Rejected: the ISOMIP+ tasks' smoothed topography; and MALI's bed through
$R$, which leaves the open ocean beyond MALI's mesh without a bed.

### D5: Ocean steps belong to the ocean component

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The ocean's initial condition, SSH adjustment and forward run are shared
steps of the `ocean` component, which the `e3sm/init` tasks include, as
the component-input tasks include the global ocean's dynamic adjustment.

```{admonition} Rationale
Polaris assigns a model per component, and `e3sm/init` has none. A step
from another component must be shared, with a config of its own
component.
```

### D6: Partition counts come from bounds

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

The partition steps are `GraphPartitionStep`, unchanged, with bounds on
cells per core that cover the planned counts. The meshes are small, so the
extra partitions cost little.

Rejected: a list of task counts, which would need a subclass.

### D7: E3SM grid names follow the unified meshes' pattern

Date last modified: 2026/10/30

Contributors: Xylar Asay-Davis, Claude

| `<mesh_name>`        | Ocean grid     | MALI grid       | Model grid           |
|----------------------|----------------|-----------------|----------------------|
| `misomip-o4km-li1km` | `misomip-o4km` | `misomip-li1km` | `misomip-o4km-li1km` |
| `misomip-o2km-li1km` | `misomip-o2km` | `misomip-li1km` | `misomip-o2km-li1km` |

The names are config options for each pair of meshes, as the
component-input tasks' short names are. Each pair's config file sets them,
and setup fails without them.

```{admonition} Rationale
The ocean, MALI and model grids share one pattern, that of E3SM's unified
meshes (`u02-oi30`, `u02-lr10`) and Polaris's mesh names. MALI's existing
grids all start with `mpas.`, but MALI needs no prefix.
```

Rejected: `oMISOMIP4km` with `mpas.misomip1km`, which share a stem but keep
the two components' older patterns; and `isomip-plus-o4km` with
`mismip-plus-li1km`, which name each mesh's protocol but make the model
grid's name long.
