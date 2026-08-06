# Plan: `component_inputs` under `e3sm/init`

Branch: `add-e3sm-init-component-inputs`, based on
`add-realistic-global-ocean-dynamic-adjustment` at `a7b6358a9` ("Document the
startup window").

Design: `docs/design_docs/e3sm_init_component_inputs.md` on the
`add-global-ocean-init-design` branch, updated in `aa106978e` ("Update the
component-inputs design for where the code landed").

The design doc is **paused** as of 2026/08/05. We revisit it after seeing how
the implementation actually lands, rather than revising it ahead of the code.
Decisions made here in the meantime — the assigned short names in D4, and
anything the implementation teaches us — go into it then.

Reference, not a port target:
`~/compass/main/compass/ocean/tests/global_ocean/files_for_e3sm/`.

Working document, untracked.

## Where we are

Nothing exists yet. `polaris/tasks/e3sm/init/` contains only `topo/`
(`combine`, `remap`, `cull`), and the branch is otherwise identical to the
dynamic-adjustment branch it sits on.

What the upstream workflows already give us is more than the design assumed
when it was written, and it changes the shape of several steps.

`CullMeshStep` (`e3sm/init/<mesh>/topo/cull/mesh`) writes, for each of the
prefixes `ocean`, `ocean_no_cavities` and `land`:

* `culled_{prefix}_mesh.nc`
* `culled_{prefix}_mesh.scrip.nc`
* `{prefix}_map_culled_to_base.nc` — `mapCulledToBase{Cell,Edge,Vertex}`,
  zero-based base indices
* `culled_{prefix}_graph.info`, for the two ocean prefixes only

and links `base_mesh.nc` from the base-mesh step. So SCRIP generation, ocean
graph generation and the culled-to-base maps are all already done: three
Compass steps become staging or inversion rather than computation.

`CullMaskStep` (`.../topo/cull/mask`) writes `cull_masks.nc` and a
`landIceMask`.

`InitialStateStep`
(`ocean/spherical/realistic_global/<mesh>/init/initial_state`) writes `mesh.nc`
(the culled ocean mesh plus Coriolis) and `init.nc`, both built from
`culled_ocean_mesh.nc` — the full ocean domain, which is the right choice.
`polaris.ocean.coriolis.add_coriolis_to_dataset` already exists.

`RealisticGlobalDynamicAdjustment` chains `Forward` stages; the last one's
restart is the ocean initial condition we want.

## Scope

In: the products an E3SM *run* needs.

* the staged base mesh, carrying base-to-culled index maps
* SCRIP staging for the culled meshes
* `mpaso.*` mesh and initial-condition files
* `mpassi.*` mesh and initial-condition files
* ocean and sea-ice graph partitions

Out, for follow-up branches (in the design, not in this branch):
`diagnostic_maps`, `diagnostic_masks`, `e3sm_to_cmip_maps`,
`remap_iceberg_climatology`, `remap_ice_shelf_melt`,
`add_total_iceberg_ice_shelf_melt`, `remap_sea_surface_salinity_restoring`,
`remap_tidal_mixing`, `write_coeffs_reconstruct`.

Meshes: unified only (`UNIFIED_MESH_NAMES`). Models: MPAS-Ocean and
MPAS-Seaice; Omega raises.

Test mesh: `u.oi240.lr240` (`u03.oi240.lr240`) first, since everything here is
cheap post-processing of a mesh that already exists. `u.oi30.lr10`
(`u02.oi30.lr10`) once oi240 looks right.

## Blocking dependency

The ocean initial condition comes from the final dynamic-adjustment stage's
restart, but `RealisticGlobalDynamicAdjustment._setup_steps()` builds its
`Forward` stages privately — they are not shared steps, so no other task can
depend on them. Xylar is tasking the upstream dynamic-adjustment PR with adding
a `get_dynamic_adjustment_steps(component, mesh_name)` accessor, matching
`get_realistic_init_steps` and `get_cull_topo_steps`.

Until that lands, commits 1–6 and 10–12 below are unblocked; commits 7–9 (the
ocean products) need it. If it slips, they can be written against
`init_steps['initial_state']` and re-pointed in a one-line change, but that
should be a fallback, not the plan.

## Design decisions

Settled with Xylar 2026-08-05 unless marked open.

### D1. Package layout

```
polaris/tasks/e3sm/init/component_inputs/
    __init__.py                   # re-exports; add_component_inputs_tasks
    component_inputs.cfg          # [component_inputs]
    names.py                      # leaf: short name, date, E3SM-facing paths
    maps.py                       # leaf: base-to-culled inversion
    partitions.py                 # leaf: get_core_list
    steps.py                      # get_component_inputs_steps(mesh_name)
    tasks.py                      # add_component_inputs_tasks(component)
    task.py                       # ComponentInputsTask(target=...)
    base_mesh.py                  # BaseMeshStep
    scrip.py                      # ScripStep
    ocean_mesh.py                 # OceanMeshStep
    ocean_initial_condition.py    # OceanInitialConditionStep
    ocean_graph_partition.py      # OceanGraphPartitionStep
    seaice_mesh.py                # SeaiceMeshStep
    seaice_initial_condition.py   # SeaiceInitialConditionStep
    seaice_graph_partition.py     # SeaiceGraphPartitionStep
    assemble.py                   # AssembleStep
```

`names.py`, `maps.py` and `partitions.py` are dependency-light leaf modules, so
the naming rules, the index inversion and the core-count list are all unit
testable without constructing a step or a work directory.

Work directories: steps at `e3sm/init/<mesh>/component_inputs/<step_name>`,
tasks at `e3sm/init/<mesh>/component_inputs/tasks/{ocean,seaice,all}`. Putting
the tasks under `tasks/` keeps a task subdir from ever colliding with a step
subdir, which is a real risk here because three tasks share most of their steps.

`steps.py` follows the `get_cull_topo_steps` / `get_realistic_init_steps`
pattern: build every step with `component.get_or_create_shared_step`, return a
`dict` keyed by symlink name plus the shared config. Each task picks the subset
it wants.

### D2. Import direction

`component_inputs` lives in `e3sm/init` and imports from
`polaris.tasks.ocean.*`; `polaris.tasks.ocean.realistic_global` imports from
`polaris.tasks.e3sm.init.topo.cull`. That is acyclic only in one direction, and
it works because `polaris/tasks/__init__.py` fully imports
`polaris.tasks.e3sm.init` before any `add_*_tasks` runs.

Nothing under `polaris.tasks.ocean` may import `component_inputs`. Say so in the
package docstring — this is the kind of thing that gets reversed by a
well-meaning refactor and then fails as an import error nobody can place.

### D3. Base-to-culled index maps

The requirement that prompted this branch. `BaseMeshStep` reads `base_mesh.nc`,
the three `{prefix}_map_culled_to_base.nc` files, and writes
`base_mesh_with_maps.nc`: the base mesh plus nine integer fields.

Invert rather than recompute. The forward maps already exist, they were built by
a nearest-element query far more expensive than a scatter, and inverting
guarantees the two directions agree.

Naming and convention:

* `mapBaseTo{Ocean,OceanNoCavities,Land}{Cell,Edge,Vertex}`, tracking the cull
  prefixes
* dimensioned by the *base* mesh's `nCells` / `nEdges` / `nVertices`
* one-based, zero meaning "not on that culled mesh", matching `cellsOnCell` and
  the other MPAS index fields
* `long_name` names the target mesh and records the one-based convention, since
  it differs from the zero-based upstream `mapCulledToBase*`

`maps.py` holds `map_base_to_culled(ds_map_culled_to_base, sizes)` returning the
nine fields; the step reads, calls and writes.

Assert two things rather than trusting the inputs: every forward-map value is a
valid base index, and no base index appears twice in one forward map. Both hold
for a genuinely derived culled mesh, so a violation means a stale file from a
different mesh — which would otherwise produce a plausible-looking wrong answer.

Whether to write the maps is gated on the mesh family. The helper takes a flag,
so enabling them for simple base meshes later is a call-site change.

### D4. Mesh short name is required; creation date is recorded

`[component_inputs] mesh_short_name` has no default from the workflow itself.
Setup fails with a message naming the option. Polaris mesh names say how a mesh
was built (`u.oi30.lr10`); E3SM short names identify a released mesh, and only a
person can decide a mesh has earned one.

`creation_date` is set during `configure()` to today if unset, so it lands in
the work directory's config file and a re-run does not silently rename every
staged file.

No autodetection from restart-file global attributes. That is the Compass
behavior that makes staged filenames unpredictable at setup time.

#### Assigned unified-mesh short names

The unified mesh team assigns a unique two-digit ID to each unified mesh that
reaches E3SM's master branch and the inputdata server. The first three proposed:

| Polaris mesh name | E3SM short name |
|---|---|
| `u.oi6to18.lr6to10` | `u01.oi6to18.lr6to10` |
| `u.oi30.lr10` | `u02.oi30.lr10` |
| `u.oi240.lr240` | `u03.oi240.lr240` |
| `u.oi.so12to30.lr10` | `uXX.oi.so12to30.lr10` (placeholder) |

The transform is mechanical — the leading `u.` becomes `u<NN>.` — but the ID is
the point: it is what distinguishes two meshes built to the same resolution
recipe at different times, which is exactly what a Polaris mesh name cannot do.

There is no plan to take `u.oi.so12to30.lr10` into E3SM, so it gets no ID. It is
still the only regionally refined mesh we are testing, and we do want to run
`component_inputs` end to end on it as a workflow test, so it gets the
placeholder `uXX`. The `XX` is doing real work: it is not a valid ID, so a file
staged under it is self-evidently a test artifact and could not be mistaken for
something belonging on the inputdata server.

Where the names live: `[unified_mesh] e3sm_short_name` in each per-mesh config
under `polaris/mesh/spherical/unified/`, with `[component_inputs]
mesh_short_name` still available as an override. All four unified meshes then
set up without ceremony.

The "no default, setup fails" rule from above still applies to any mesh with no
registered name — a new unified mesh, or a simple base mesh if we enable those
later. It is the *absence* of a registered name that fails, not the absence of
an assigned ID.

### D5. Staged layout

With `<short>` the mesh short name and `<date>` the creation date:

| Product | Staged path under `assembled_files/` |
|---|---|
| base mesh + maps | `inputdata/share/meshes/mpas/unified/<short>.base.<date>.nc` |
| SCRIP, per region | `inputdata/share/meshes/mpas/unified/<short>.<region>.scrip.<date>.nc` |
| ocean mesh | `inputdata/ocn/mpas-o/<short>/<short>.<date>.nc` |
| ocean IC | `inputdata/ocn/mpas-o/<short>/mpaso.<short>.<date>.nc` |
| ocean partitions | `inputdata/ocn/mpas-o/<short>/partitions/mpas-o.graph.info.<date>.part.<n>` |
| sea-ice mesh | `inputdata/ice/mpas-seaice/<short>/<short>.<date>.nc` |
| sea-ice IC | `inputdata/ice/mpas-seaice/<short>/mpassi.<short>.<date>.nc` |
| sea-ice partitions | `inputdata/ice/mpas-seaice/<short>/partitions/mpas-seaice.graph.info.<date>.part.<n>` |

`share/meshes/mpas/unified/` rather than Compass' `share/meshes/mpas/ocean/`:
for a unified mesh the base mesh belongs to the ocean, sea-ice, land and river
components equally, and filing it under the ocean would misdescribe it.

All of this lives in `names.py`. Every path in the table is a function there.

### D6. Staging happens only in the assembly step

Compass scatters `symlink()` calls through the product steps, which is what
makes its `assembled_files` tree hard to reason about. Here, product steps write
only their own outputs; `AssembleStep` declares those outputs as inputs and
materializes the tree.

One assembly step per task, at `component_inputs/assemble/{ocean,seaice,all}`,
since the three tasks stage different sets. It also stages the `README` warning
that the tree is a subset of what E3SM needs for a new mesh and must not be
uploaded on its own.

### D7. Sea-ice does not touch the ocean

`SeaiceMeshStep` reads `culled_ocean_mesh.nc`. `SeaiceInitialConditionStep`
computes `fCell`, `fEdge`, `fVertex` from latitude rather than copying them out
of an ocean restart as Compass does — they are functions of latitude alone, and
copying them is the accidental coupling this design exists to remove.

`polaris.ocean.coriolis.add_coriolis_to_dataset` does exactly this but reads
`[coriolis] type` from the ocean config, which is the wrong knob for a sea-ice
step on a sphere. **Open:** reuse it and require `type = sphere`, or compute
`2 Ω sin(lat)` directly in the sea-ice step. Leaning toward the latter — three
lines, no config coupling to a section the step has no business reading.

### D8. Graph partitions

`get_core_list` ports from Compass essentially verbatim into `partitions.py`. It
is a pure function over a cell count and two bounds, so it gets real unit tests
for the first time.

Ocean: `culled_ocean_graph.info` from the cull step — the `ocean` prefix,
matching what the ocean init uses — and `gpmetis` per core count.

Sea-ice: `prepare_seaice_partitions` and `create_seaice_partitions` from
`mpas_tools`, which need `seaice_QU60km_polar.nc` and
`icePresent_QU60km_polar.nc`, plus a QU60km→mesh bilinear map built with
`pyremap`.

**Action item for Xylar:** those two files are not in the Polaris database.
They exist at
`/lcrc/group/e3sm/public_html/mpas_standalonedata/mpas-seaice/partition/` and
need to be copied to `.../polaris/seaice/partition/` before
`database='partition', database_component='seaice'` resolves. This blocks
commit 12 only.

### D9. Omega raises

`[component_inputs] ocean_model` selects `mpas-ocean` or `omega`; `seaice_model`
selects `mpas-seaice` or `none`. The gating matrix is built now, and `omega`
raises `NotImplementedError` at setup with a message saying Omega packaging is
not yet supported.

Building the gate now, rather than when Omega is ready, is the point: it means
the Omega branch fills a named gap instead of retrofitting model selection into
steps that quietly assumed MPAS.

### D10. No suite membership

Nothing here joins `omega_pr` or `omega_nightly`. These are per-mesh staging
tasks against meshes that take hours to build; they are not regression tests.
The unit tests in commits 4, 6, 9, 11 and 13 are what runs in CI.

## Open questions

1. Does anything beyond the SCRIP files and index maps need staging for
   `ocean_no_cavities` — the culled mesh itself, for instance? Assuming not.

## Settled: ice-shelf cavities are out of scope

**Decision (Xylar, 2026-08-05): `with_ice_shelf_cavities` is not supported at
all for now.** Support comes later, as its own piece of work.

So there is no `with_ice_shelf_cavities` config option, no cavity gating in any
step, no land-ice fields staged in the ocean mesh file, and no masked SCRIP
variant. Nothing in this branch branches on cavities, which is a good deal
simpler than the Compass workflow it replaces.

The rest of this section records why that is safe, since the question came up
and the answer is not obvious from the stream definitions.

Checked against `../main/e3sm_submodules/E3SM-Project/components/mpas-ocean` on
2026-08-05. **MPAS-Ocean does not require the `landIce*` fields.**

The stream entries look unconditional — `src/Registry.xml` lists `landIceMask`,
`landIcePressure`, `landIceFraction`, `landIceDraft`, `landIceFloatingMask` and
`landIceFloatingFraction` in both the `input` stream (`init.nc`, line 2028) and
the `restart` stream (line 2131) with no `packages=` attribute on the `<var>`
entries.

But the variable *definitions* carry the gate. `Registry.xml:4177–4199` declares
all six with `packages="landIcePressurePKG"`, so they are not allocated at all
unless that package is active. `src/driver/mpas_ocn_core_interface.F:317–329`
activates it only when `config_land_ice_flux_mode` is `pressure_only`, `data`,
`standalone` or `coupled`; the default is `off` (`Registry.xml:1118`), and
Polaris only overrides it in the ice-shelf tasks
(`polaris/ocean/ice_shelf/ssh_forward.yaml`, `ice_shelf_2d/forward.py`), never
in `realistic_global`.

With the package inactive the fields do not exist, the stream manager skips
them, and nothing reads or requires them. That is consistent with the
dynamic-adjustment stages on this branch running against an `init.nc` that
contains none of them.

One more finding, which argues against hedging by writing the fields as zeros: a
field missing from an input file is not fatal even when it *is* active.
`MPAS_streamAddField` returns an error when the variable is absent
(`mpas_io_streams.F:1963`, "handle this situation gracefully at higher levels")
and the stream manager's calls at `mpas_stream_manager.F:4415–4454` do not pass
`ierr`, so it is dropped and the field is silently skipped. A silently skipped
`landIceFloatingMask` then keeps its `default_value="-1"`
(`Registry.xml:4189`) — neither present nor absent. Writing zeros "to be safe"
would therefore be the safer-*looking* choice that is harder to debug later.
Omitting the fields entirely is both simpler and more honest.

### When cavity support arrives

There is no need to invent a `with_ice_shelf_cavities` option when the time
comes: `[spherical_mesh] antarctic_boundary_convention` already says it, and
already reaches the right places.

Its three values (`polaris/mesh/spherical/coastline.py:12`) decide which
below-sea-level cells are candidate ocean:

| Convention | Antarctic cells treated as ocean | Cavities |
|---|---|---|
| `calving_front` | ice-free cells only | none |
| `grounding_line` | everything but grounded ice — ice shelves included | yes |
| `bedrock_zero` | all below-sea-level cells | yes |

`calving_front` is the default (`polaris/mesh/spherical/spherical.cfg:27`) and
is what every current unified mesh uses, which is *why* cavities are absent
today — it is a property of how the mesh was culled, not an independent switch.
The option is already consumed by `topo/remap/mask.py:142–148`, and
`get_cull_topo_steps` already copies it from the base-mesh step's config into
the cull config, so a `component_inputs` step can read it from the config it
already has.

So the cavity work, when it happens, is roughly: allow a mesh to be built with
`grounding_line` or `bedrock_zero`; set `config_land_ice_flux_mode` away from
`off` in the forward config; and gate the staging of `landIceMask`,
`landIcePressure`, `landIceFraction`, `landIceDraft`, `landIceFloatingMask` and
`landIceFloatingFraction` on the convention rather than on a new option.

Recording this now mainly to head off a mistake later: a second option meaning
"does this mesh have cavities" could disagree with the convention the mesh was
actually culled under, and the staged files would follow the wrong one.

## What the cull prefixes mean

I read `initial_state.py`'s use of `culled_ocean_mesh.nc` as "the unified meshes
are culled with cavities, but run with `land_ice_flux_mode = off`", and flagged
it upstream. That was wrong. Per Xylar (2026-08-05), there is nothing to fix
here and nothing to raise upstream.

The prefixes say what they mean:

* `ocean` — the ocean domain. It does not assert anything about cavities. There
  is no `with_cavities` prefix, and reading `ocean` as though there were is the
  mistake I made.
* `ocean_no_cavities` — the ocean domain with any cavities excluded. When a mesh
  has no cavities this is identical to `ocean`, and that is intentional.
* `land` — the land domain.

`ocean_no_cavities` exists to build mapping files, which is why the cull step
writes its SCRIP description alongside the other two. It is not a byproduct kept
around for the index maps.

Consequence for this branch: the D3 map field names track the prefixes directly,
and the D5 table stages all three SCRIP files. Both are correct as planned.

## Proposed commit series

Repo convention: code and tests as separate commits, docs last. Where a change
is small enough that a separate test commit would be noise, tests ride along.

| # | Commit | What it does |
|---|--------|--------------|
| 1 | Add the `component_inputs` package skeleton | D1: empty package, `component_inputs.cfg` with `[component_inputs]`, `add_component_inputs_tasks` wired into `add_e3sm_init_tasks`, no steps yet. `polaris list` still works. |
| 2 | Name the staged component-input files | D4, D5: `names.py` — short name, creation date, one function per staged path; register `e3sm_short_name` for `u01.oi6to18.lr6to10`, `u02.oi30.lr10` and `u03.oi240.lr240` in their per-mesh configs. Nothing calls it yet. |
| 3 | Map base-mesh indices to the culled meshes | D3: `maps.py` with `map_base_to_culled`, including the two input assertions. Pure function, no step. |
| 4 | Test the base-to-culled index maps | D3: hand-built forward maps; present elements one-based, absent zero, `mapBaseTo*[mapCulledToBase*[i]] == i + 1` round trip, base-mesh dimensioning, both assertions firing. |
| 5 | Stage the base mesh with its culled-mesh maps | `BaseMeshStep` writing `base_mesh_with_maps.nc`; `ScripStep` staging the cull step's SCRIP files; both added by `get_component_inputs_steps`. |
| 6 | Test the shared component-input steps | Steps declare the cull step's outputs as inputs; the family gate decides whether maps are written; the three named meshes resolve their short name from the per-mesh config; a mesh with no assigned name fails at setup naming the option. |
| 7 | Add the MPAS-Ocean mesh and initial-condition steps | D9: `OceanMeshStep` (mesh vars, vertical-coordinate reference fields, `cellMask`, `ssh`, `zMid`; no land-ice fields, no cavity gating) and `OceanInitialConditionStep` from the final dynamic-adjustment restart. **Needs the upstream shared-step accessor.** |
| 8 | Add the ocean graph partitions | D8: `partitions.py` with `get_core_list`, plus `OceanGraphPartitionStep` over `culled_ocean_graph.info`. |
| 9 | Test the ocean component inputs | `get_core_list` bounds and factor rules; the IC step depends on the last stage's restart, not on `initial_state`; Omega raises. |
| 10 | Add the MPAS-Seaice mesh and initial-condition steps | D7: both from `culled_ocean_mesh.nc`; Coriolis computed, not copied. |
| 11 | Test that sea-ice does not depend on the ocean | D7: the sea-ice task's step list contains no ocean step and no dynamic-adjustment dependency; `fCell`/`fEdge`/`fVertex` match `2 Ω sin(lat)`. |
| 12 | Add the sea-ice graph partitions | D8: `SeaiceGraphPartitionStep`, QU60km database inputs, bilinear map, `create_seaice_partitions`. **Needs the database files staged.** |
| 13 | Assemble the staged component-input tree | D6: `AssembleStep`, the three tasks (`ocean`, `seaice`, `all`), the `README`, plus tests that each staged file appears under its expected path. |
| 14 | Document the `component_inputs` tasks | User guide page under `docs/users_guide/e3sm/init/tasks/`, developer guide page and API entries, both indexes updated. |

Commits 1–6 are the shared mesh staging and are unblocked today. 7–9 are the
ocean side and wait on the upstream accessor. 10–12 are the sea-ice side, and
12 waits on the database files. 13 is what makes the tree assemble; 14 is docs.

If the upstream accessor is late, the order becomes 1–6, 10–11, 13, then 7–9
and 12 — the sea-ice side genuinely does not need the ocean, and building it
first would prove that rather than assert it.

## After the code

1. `pytest tests/e3sm/init/` green (this worktree has no `pixi-env/` yet —
   it needs `./deploy.py`, which is Xylar's to run).
2. `polaris setup` the `u.oi240.lr240` `component_inputs/all` task and read the
   config and the declared inputs before running anything.
3. Run it — all of it is post-processing of an existing mesh, so it is login-node
   safe apart from the sea-ice partitioning, which wants a compute node.
4. Check `base_mesh_with_maps.nc` by hand: the round-trip identity, and that the
   ocean and land maps are complementary where they should be.
5. Inspect `assembled_files/` against the D5 table.
6. Repeat on `u.oi30.lr10`.
7. Update the design doc on its own branch with anything the implementation
   taught us.
