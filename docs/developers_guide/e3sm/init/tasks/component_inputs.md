(dev-e3sm-init-component-inputs)=

# component_inputs

The `polaris.tasks.e3sm.init.component_inputs` package stages the input files
an E3SM run needs from one unified mesh.  See
{ref}`e3sm-init-component-inputs-tasks` for what it produces and how to run it.

## Import direction

This package lives in `e3sm/init` and imports from `polaris.tasks.ocean`,
while `polaris.tasks.ocean.realistic_global` imports from
`polaris.tasks.e3sm.init.topo.cull`.  That is acyclic only in one direction,
and it works because `polaris.tasks` fully imports
`polaris.tasks.e3sm.init` before any `add_*_tasks` function runs.

**Nothing under `polaris.tasks.ocean` may import this package.**  Reversing
the direction is the kind of change a well-meaning refactor makes, and it
fails as an import error that is hard to place.

## Steps

`get_component_inputs_steps(mesh_name, target)` follows the same pattern as
`get_cull_topo_steps` and `get_realistic_dynamic_adjustment_steps`: every step
comes from `Component.get_or_create_shared_step`, so the three tasks that
share most of these steps get the same instances.

It builds **only what `target` needs**.  That is what makes the sea-ice target
independent of the ocean in the sense that matters: asking for `seaice` does
not create the dynamic-adjustment chain at all, so a sea-ice task cannot end
up waiting on a model run it has no use for.

| Step | Reads | Writes |
|---|---|---|
| `BaseMeshStep` | `base_mesh.nc`, the three `*_map_culled_to_base.nc` | `base_mesh_with_maps.nc` |
| `ScripStep` | the cull step's three SCRIP files | `<region>.scrip.nc` |
| `OceanMeshStep` | the initial state's `mesh.nc` and `init.nc` | `ocean_mesh.nc` |
| `OceanInitialConditionStep` | the final adjustment stage's restart | `ocean_initial_condition.nc` |
| `OceanGraphPartitionStep` | `culled_ocean_graph.info` | `mpas-o.graph.info.part.*` |
| `MocMasksStep` | `culled_ocean_mesh.nc` | `<mesh>_mocBasinsAndTransects<features_date>.nc` |
| `SeaiceMeshStep` | `culled_ocean_mesh.nc` | `seaice_mesh.nc`, read by the partition steps rather than staged |
| `SeaiceInitialConditionStep` | `culled_ocean_mesh.nc` | `seaice_initial_condition.nc` |
| `SeaicePartitionMapStep` | `seaice_mesh.nc`, QU60km climatology | the QU60km-to-mesh mapping file |
| `SeaiceGraphPartitionStep` | `seaice_mesh.nc`, QU60km climatology and ice-present mask, the mapping file | `mpas-seaice.graph.info.part.*` |
| `AssembleStep` | the above, plus the cull step's `culled_land_mesh.nc` | `assembled_files/` |

The sea-ice partitioning is two steps rather than one because building the
remapping weights is an MPI job sized for the mapping tool, while using them
is serial.  `SeaicePartitionMapStep` descends from
{py:class}`polaris.remap.MappingFileStep`; `SeaiceGraphPartitionStep` depends
on it and reads the weights off its remapper, since the mapping file's path is
not known until it has run.  This is the same division `realistic_global` uses
between `Woa23MapStep` and `RemapWoa23Step`.

Work directories are `e3sm/init/<mesh>/component_inputs/<step_name>`, and the
tasks are at `e3sm/init/<mesh>/component_inputs/tasks/{ocean,seaice,all}`.
Putting the tasks under `tasks/` keeps a task subdirectory from colliding with
a step subdirectory, which is a real risk when three tasks share most of their
steps.

The land mesh has no step of its own.  Unlike the SCRIP files it carries no
mesh name to restamp, and unlike the ocean mesh it needs no vertical
coordinate, so there is nothing to compute between the cull step and the
staged tree; `AssembleStep` declares it directly.

## What is not recomputed

The cull step already writes the SCRIP descriptions, the ocean graph and the
culled-to-base index maps, and the initial-state step already writes every
vertical-coordinate field.  Several steps that were computations in Compass
are therefore staging or inversion here:

- `BaseMeshStep` **inverts** the existing forward maps rather than
  recomputing them.  They came from a nearest-element query far more expensive
  than a scatter, and inverting is what guarantees the two directions agree.
- `ScripStep` only restamps `mesh_name`, using `ncatted` rather than an
  xarray round-trip.  These are `NETCDF3_64BIT_DATA` files the cull step
  already found prohibitively slow to write directly.
- `OceanMeshStep` selects rather than computes; only `zMid` and
  `refLayerThickness` are built here.

## Leaf modules

`names.py`, `maps.py`, `partitions.py` and `models.py` open no file and
construct no step, so the naming rules, the index inversion, the core-count
list and the model gate are all unit testable without a work directory.

- `names.py` — every staged path is a function here, so the layout of the
  assembled tree is described in one place.
- `maps.py` — `map_base_to_culled` and `base_to_culled_maps`.  Both check that
  every forward-map value is a valid base index and that no base index appears
  twice; a violation means a stale file from a different mesh, which would
  otherwise scatter into a plausible-looking wrong answer.
- `partitions.py` — `get_core_list`, ported essentially verbatim from Compass,
  plus `read_graph_cell_count`, which reads the METIS header rather than
  counting lines.
- `models.py` — the ocean and sea-ice model gates.  Built while only MPAS is
  supported so that adding Omega fills a named gap rather than retrofitting
  model selection into steps that quietly assumed MPAS.

## The MOC masks borrow behavior without borrowing a component

`MocMasksStep` builds the one mask file MPAS-Ocean reads at run time.  The
masks themselves come from the mesh component's
{py:class}`polaris.tasks.mesh.spherical.feature_masks.compute.ComputeFeatureMasksStep`,
and the two MOC-specific pieces — the `mocBasinsAndTransects` filename and the
southern-boundary transects appended to the masks — come from
{py:mod}`polaris.tasks.mesh.spherical.feature_masks.moc`, which the ocean
feature-mask step uses as well.

Subclassing the *ocean* feature-mask step would have been the obvious route
and does not work.  That class inherits `OceanIOStep` to translate to and from
Omega's variable names, and `OceanIOStep.process_inputs_and_outputs` reads
`[ocean] model`.  A step owned by `e3sm/init` has no `[ocean]` section — every
config belongs to exactly one component — so setup fails with
`NoSectionError`.  Overriding the two I/O hooks is not enough either, since
`[ocean] model` is read in four places along that inheritance path.

Hence the leaf module: the MOC behavior is model-agnostic and lives where any
component can call it, which keeps this step and the ocean one from drifting
apart without coupling `e3sm/init` to the ocean component.

## Sea-ice does not touch the ocean

Compass copied `fCell`, `fEdge` and `fVertex` out of an ocean restart and
partitioned that restart's mesh.  Both are removed here: the Coriolis fields
are computed from latitude with `add_spherical_coriolis`, and the partitioning
reads `SeaiceMeshStep`'s output.

`add_spherical_coriolis` is called directly rather than through
`add_coriolis_to_dataset`, which would read `[coriolis] type` from a config
section a sea-ice step has no business reading — and whose default of `zero`
would be silently wrong here.

## Staging happens only in the assembly step

Product steps write only their own outputs; `AssembleStep` declares those
outputs as inputs and materializes the tree.  Compass scatters `symlink()`
calls through the product steps, which is what makes its `assembled_files`
tree hard to reason about.

Graph partitions are the exception to declaring outputs: which core counts
exist follows from a cell count that is not known until the graph file has
been written, so they cannot be named at setup.  `AssembleStep` lists what the
partition step produced and raises if it produced nothing.
