# Landice Component

Creation date: 2026/10/22

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Polaris gains a `landice` component that builds and runs MALI, the
MPAS-Albany Land Ice model. MALI's first-order velocity solver comes from
the Albany library, which Polaris environments can include again.
Polaris's MISMIP+ tasks and its inputs for E3SM's MISOMIP runs build on
it.

The component follows the ocean's pattern: a build module and template, a
`mali` model, a model step, a config file for the model and tasks under
`polaris/tasks/landice/`. Albany returns through Polaris's deployment hooks,
as it did in Compass's move to `mache.deploy`. The first tasks port
Compass's `dome` test at 2 km, with the shallow-ice and first-order solvers.

Success means:

- Polaris builds MALI from MALI-Dev or FAnSSIE, with and without Albany;
- `./deploy.py --with-albany` gives an environment that a MALI build links
  to Albany from;
- the `dome` tasks pass with both velocity solvers, including their
  decomposition and restart checks;
- MALI meshes can be made by steps in other components without a MALI
  build.

## Requirements

### Requirement: Polaris builds MALI

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

Polaris builds MALI from any E3SM branch, with or without Albany, during
setup, as it builds MPAS-Ocean.

### Requirement: Polaris environments can include Albany

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

On supported machines and toolchains, a Polaris environment can include
Albany and Trilinos at versions that work with MALI-Dev's `develop`.
Environments without Albany are unchanged.

### Requirement: MALI tasks belong to a landice component

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

Tasks that run MALI belong to a `landice` component with its own config
options, database area and suites.

### Requirement: MALI meshes can be made without a MALI build

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

A step in any component can turn a planar MPAS mesh into a MALI mesh
without MALI being built.

### Requirement: The first tasks show that MALI runs

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

Tasks run MALI with the shallow-ice velocity solver and with Albany's
first-order solver. They check that results do not depend on the domain
decomposition or on restarts.

### Requirement: Changes to FAnSSIE's MALI are regression tested

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

MALI from FAnSSIE runs in the suite that tests every change to FAnSSIE.

## Implementation

### Implementation: Polaris builds MALI

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`polaris/build/mali.py` and `build_mali.template` mirror MPAS-Ocean's build.
The script builds in `components/mpas-albany-landice` of the branch and
copies `landice_model`, `default_inputs/namelist.landice`,
`default_inputs/streams.landice` and `src/Registry_processed.xml` into the
build directory, `${paths:base_work_dir}/landice_build` by default. It
writes `mali_source.txt`, a source record like `mpas_ocean_source.txt`, which
also records whether the build has Albany.

The make target is the machine's `[build] <compiler>_<mpi>_target`, which
MPAS-Ocean also uses. A build with Albany adds `ALBANY=true` and appends
`POLARIS_ALBANY_LINK_LIBS` to `MPAS_EXTERNAL_LIBS` (D3). The script
initializes no submodules: `SeaLevelModel`, and `FastIsostasy` and
`fesm-utils` from MALI-Dev's `develop`, are built only with `SLM=true` or
`FASTISOSTASY=true`.

`--model mali` selects the model, and `--landice_branch` and `--landice_path`
work as they do for other components. The default branch is
`e3sm_submodules/MALI-Dev` (D1). Coupling work points to FAnSSIE explicitly,
as MPAS-Ocean builds do.

```cfg
[build]
branch = ${paths:polaris_branch}/e3sm_submodules/MALI-Dev

# whether to build MALI with Albany: True, False or detect (with Albany if
# the environment provides it)
albany = detect
```

With `detect`, a build has Albany whenever the environment provides it
(D4). Setup fails if a step needs the first-order solver and the build will
not have Albany, or an existing build's source record says it has none.

MPAS-Ocean and MALI share one framework build in an E3SM checkout, in
`components/mpas-framework/src`. Both build scripts record each build's
configuration there: the component, machine, compiler, MPI library, make
target and flags, Albany and load script. A build starts with `make clean`
when the last one in the checkout had a different configuration, when the
checkout was built outside Polaris, or when MPAS's `.mpas_core_<core>`
marker shows that another component was built since (D8). Two builds from
one checkout at the same time still collide.

### Implementation: Polaris environments can include Albany

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`./deploy.py --with-albany` adds Albany and Trilinos to the Spack library
environment (D2). The flag lives in `deploy/custom_cli_spec.json`, so
`deploy.py` and `deploy/cli_spec.json`, which mache owns, are untouched. The
`pre_spack` hook in `deploy/hooks.py`:

- checks the machine, compiler and MPI library against
  `deploy/albany_supported.txt`, which starts with Chrysalis, gnu and
  OpenMPI;
- names the library environments `spack_env_albany_<compiler>_<mpi>`, so
  environments without Albany are not modified;
- excludes the machine's cmake, since this Trilinos needs cmake 3.27 and
  Chrysalis provides 3.24;
- sets a pin that adds `trilinos-for-albany` and `albany` to
  `deploy/spack.yaml.j2`.

The pins are Compass's: Albany `compass-2026-03-21` with `+mpas~py+unit_tests`
and Trilinos `compass-2026-02-06`. Compass runs them with MALI-Dev's
`develop` of 2026-09-16. Both are in `e3sm-spack-packages` `v2026.06.1`,
which mache 5.0.0 uses.

`deploy/load.sh` reads `export_albany.in` from the Spack library view when
it exists. It exports `POLARIS_ALBANY_LINK_LIBS`: Albany's libraries,
`-lstdc++` and, for OpenMPI on Chrysalis, `-lmpi_cxx`.

The environment is tested first from a throwaway Spack checkout in Xylar's
scratch space, then deployed in the shared Polaris Spack area.

### Implementation: MALI tasks belong to a landice component

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The framework is in `polaris/landice/`:

- `landice.cfg` with `[landice] model = mali`, the only model;
- `mali.cfg` with the build options above and the paths to the build's
  namelist, streams, registry and executable;
- `MaliModelStep`, a `ModelStep` that sets `config_velocity_solver`, adds
  the task's `albany_input.yaml` for the first-order solver, and partitions
  the mesh.

`polaris/tasks/landice/` holds the `Landice` component, registered in
`polaris/tasks/__init__.py`. Its `configure()` adds `mali.cfg`, detects an
existing build, and requests a build when there is none. Its
`build_model()` calls `build_mali()`.

Input files go under `landice/` in `database_root`, on Chrysalis
`/lcrc/group/e3sm/public_html/polaris/landice`. The first tasks need none,
so the area is created by the first task that does, likely MISMIP+.

The `mali_pr` suite holds the decomposition and restart tasks for both
solvers.

### Implementation: MALI meshes can be made without a MALI build

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`polaris/landice/mesh.py` converts a culled planar MPAS mesh into a MALI
mesh with a given number of layers, with mpas_tools'
`create_landice_grid_from_generic_mpas_grid`, and writes its graph file
(D6). The module imports nothing from `polaris.tasks.landice`, so steps in
other components, such as those that build E3SM's inputs for MISOMIP, can
call it. Work that remaps fields to MALI cells adds what it needs, such as
mpas_tools' `interpolate_to_mpasli_grid`.

### Implementation: The first tasks show that MALI runs

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The tasks port Compass's `dome` on its 2 km planar mesh (D5):

```none
landice/dome/2km/init                    (shared step)
landice/dome/2km/{sia,fo}/smoke_test
landice/dome/2km/{sia,fo}/decomp
landice/dome/2km/{sia,fo}/restart
```

The shared `init` step makes the mesh and the Halfar dome. `smoke_test`
runs MALI and plots thickness and speed for the User's Guide. `decomp`
compares runs on 1 and 4 tasks: bit for bit with shallow ice, and within
Compass's norms with the first-order solver. `restart` compares a run with
one that restarts halfway.

### Implementation: Changes to FAnSSIE's MALI are regression tested

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The `mali_pr` tasks join `fanssie_pr` (D7). Suites may mix components, so the
suite is set up with `--landice_branch e3sm_submodules/FAnSSIE` alongside its
ocean options. It then needs an environment deployed with `--with-albany`.

## Testing

### Testing and Validation: Polaris builds MALI

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

MALI builds on Chrysalis with gnu and OpenMPI, with and without Albany,
from MALI-Dev and from the E3SM branch that merges MALI-Dev's `develop`
into FAnSSIE. Unit tests check the rendered build script, the Albany check
at setup and when a build must start clean. Building MPAS-Ocean, MALI,
MPAS-Ocean and MALI from one checkout gives working executables, and
`fanssie_pr` with MPAS-Ocean built after MALI from the merge branch is bit
for bit with its baseline from FAnSSIE.

### Testing and Validation: Polaris environments can include Albany

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

A throwaway deployment with `--with-albany` builds Albany and gives a load
script that exports `POLARIS_ALBANY_LINK_LIBS`. A deployment without the
flag renders the same Spack specs as before.

### Testing and Validation: MALI tasks belong to a landice component

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`polaris list` shows the landice tasks, and `polaris suite -c landice -t
mali_pr` sets up. The full `tests/` tree passes.

### Testing and Validation: MALI meshes can be made without a MALI build

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The `dome` `init` step runs in an environment without a MALI build. A unit
test converts a small planar mesh.

### Testing and Validation: The first tasks show that MALI runs

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`mali_pr` passes on Chrysalis with MALI from MALI-Dev and from the merge
branch, and the smoke tests' plots match Compass's.

### Testing and Validation: Changes to FAnSSIE's MALI are regression tested

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`fanssie_pr` passes with the landice tasks, and its ocean tasks are bit
for bit with the FAnSSIE baseline.

## Decisions

### D1: MALI-Dev is the default MALI source

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

`e3sm_submodules/MALI-Dev` stays and becomes the landice default. It moves
to MALI-Dev's `develop` at `5e80df1145`, the commit that the pull request
merging `develop` into FAnSSIE brings in. Builds for ocean–ice-sheet
coupling work point to FAnSSIE explicitly. Xylar chose this on 2026-10-22;
the submodule's previous pin, from 2024, had no particular significance.

```{admonition} Rationale
MALI is developed on MALI-Dev's `develop` and reaches E3SM's `master` in
periodic merges, as Omega is developed on its own `develop`. Compass tests
MALI-Dev, and Polaris's landice tasks should test what MALI developers
change.
```

Rejected:

- removing the submodule and building MALI from `e3sm_submodules/E3SM-Project`
  by default. E3SM's MALI lags MALI-Dev's: `develop` holds 97 MALI commits
  beyond `master` of 2026-05-26;
- FAnSSIE as the default. FAnSSIE is specialized for coupled
  ocean–ice-sheet work, and every landice suite would then test it rather
  than MALI-Dev's `develop`.

### D2: Albany comes from Polaris's deployment

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

Polaris builds Albany in its own Spack library environments, when deployed
with `--with-albany`, as Compass does. Xylar chose this on 2026-10-22.

Rejected:

- linking an existing Compass installation, such as
  `compass_albany_gnu_openmpi` in Compass 2.0.0's Spack area. Its Trilinos
  and Albany were built against Compass's library stack, which differs from
  Polaris's (SCORPIO 1.8.2 against 2.0.3), and Polaris would follow
  Compass's release cadence;
- Albany in every library environment. Trilinos takes hours to build,
  supports only some toolchains, and only MALI needs it.

### D3: Only MALI builds link to Albany

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The load script exports Albany's libraries as `POLARIS_ALBANY_LINK_LIBS`,
and only the MALI build adds them to `MPAS_EXTERNAL_LIBS`.

Rejected: Compass's approach, which appends them to `MPAS_EXTERNAL_LIBS` in
the load script. Every MPAS-Ocean build in an Albany environment would then
link to Trilinos and Albany.

### D4: A build has Albany whenever the environment does

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

By default, a MALI build has Albany when the environment provides it. One
build serves the tasks for both solvers. `[build] albany = False` forces a
build without it, for testing.

Rejected: a build per solver, which doubles the build time for suites that
mix them.

### D5: The first tasks are Compass's `dome`

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The first tasks port `dome` on the 2 km mesh. It is Compass's smallest
test with both solvers, and needs no input files.

Rejected:

- `dome`'s variable-resolution mesh, which needs a database file and tests
  nothing more about the component;
- MISMIP+, a larger port that gets its own tasks;
- Compass's whole `full_integration` suite, which can be ported task by
  task as MALI developers need it.

### D6: MALI mesh conversion lives in the landice framework

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The conversion is in `polaris/landice/mesh.py`, a module that needs no
MALI build, since the `dome` tasks need it now, and MISMIP+ and the E3SM
inputs for MISOMIP need it from other components.

Rejected: a shared mesh step for MISOMIP, which would leave `dome` and
MISMIP+ importing from the `mesh` component's tasks.

### D7: The MALI tasks join `fanssie_pr`

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

The four `mali_pr` tasks join `fanssie_pr`, since FAnSSIE carries MALI changes
for MISOMIP1. `fanssie_pr` then needs an environment deployed with
`--with-albany`, so it runs only where Albany is supported
(`deploy/albany_supported.txt`). Without such an environment, its setup fails
because of D4. The four tasks are timed before they join, to confirm that the
suite still fits in its 1 h wall time; it took 25–26 minutes before the
split-explicit ISOMIP+ tasks were added. Xylar agreed to this on 2026-10-22.

Rejected:

- only the shallow-ice tasks in `fanssie_pr`, which would leave the
  first-order solver that MISOMIP1 uses untested;
- running `mali_pr` against FAnSSIE only for changes that touch MALI, which
  relies on judging which changes do.

### D8: Builds clean the shared MPAS framework when it changes

Date last modified: 2026/10/22

Contributors: Xylar Asay-Davis, Claude

Polaris's MPAS-Ocean and MALI build scripts start with `make clean` when the
shared framework in the E3SM checkout was last built for another component
or with another configuration, such as another compiler. Xylar asked for the
compiler check on 2026-10-22.

```{admonition} Rationale
The framework's driver is compiled differently for each component, and
MPAS's own check, the `.mpas_core_<core>` marker, is in each component's
directory, so it misses another component's build. With D7, `fanssie_pr`
builds both components from the FAnSSIE submodule.
```

Rejected: documenting that `--clean_build` is needed when switching
components, which is easy to forget in a suite that builds both.
