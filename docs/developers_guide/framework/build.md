(dev-build)=

# Build utilities

The `polaris.build` package provides helpers to generate portable build scripts
for model components used by Polaris. These scripts encapsulate machine- and
compiler-specific details via templates and a few environment variables, so you
can reliably build from a clean login environment.

Currently supported builders:

- `polaris.build.mpas_ocean` — build MPAS-Ocean from an E3SM checkout
- `polaris.build.omega` — build Omega from the standalone repo or submodule

## How it works

Each builder renders a Jinja2 template into a machine-specific shell script and
then runs that script from a pristine login environment (clearing the current
process environment) to avoid interference from Conda or other package managers.
The generated scripts are saved so you can re-run or inspect them later.

Locations for generated scripts:

- MPAS-Ocean: `./build_mpas_ocean/build_mpas_ocean_<machine>_<compiler>_<mpi>.sh`
- Omega: `./build_omega/build_omega_<machine>_<compiler>.sh`

## Required environment

Builders read a small number of environment variables to select the correct
template logic and paths, all of which are set by a polaris load script:

Common:
- `POLARIS_BRANCH` — absolute path to the Polaris source tree (used to locate
  submodules and templates)

MPAS-Ocean:
- `POLARIS_MACHINE` — machine ID used by the template (e.g., chrysalis, frontier)
- `POLARIS_COMPILER` — compiler toolchain ID (e.g., intel, gnu)
- `POLARIS_MPI` — MPI library ID (e.g., openmpi, mpich)
- `LOAD_POLARIS_ENV` — path to the shell snippet used to load the Polaris build
  env on the target machine

Omega:
- `POLARIS_MACHINE` — machine ID
- `POLARIS_COMPILER` — compiler toolchain ID
- `METIS_ROOT`, `PARMETIS_ROOT` — paths to METIS and ParMETIS installs

Notes:
- If the `branch` argument points to the corresponding submodule inside
  `POLARIS_BRANCH/e3sm_submodules/...`, the generated script will optionally
  update that submodule before building.
- On NERSC Perlmuter (`POLARIS_MACHINE` in `pm-cpu` or `pm-gpu`), the builder
  sets `NERSC_HOST` as required by the environment.  For whatever reason this
  variable is unset in a fresh bash job and is required to identify the
  machine.

## MPAS-Ocean builder

Python entry points:
- {py:func}`polaris.build.mpas_ocean.build_mpas_ocean()` — render and run a build
- {py:func}`polaris.build.mpas_ocean.make_build_script()` — render the script only

Behavior:
- Renders `polaris.build/build_mpas_ocean.template`
- Writes the script under `./build_mpas_ocean/`
- Executes the script with `env -i HOME="$HOME" bash -l <script>`

## Omega builder

Python entry points:
- {py:func}`polaris.build.omega.build_omega()` — render and run a build
- {py:func}`polaris.build.omega.make_build_script()` — render the script only

Behavior:
- Renders `polaris.build/build_omega.template`
- Writes the script under `./build_omega/`
- Executes the script with `env -i HOME="$HOME" bash -l <script>`

## Usage examples

From Python:

```python
from polaris.build.mpas_ocean import build_mpas_ocean
from polaris.build.omega import build_omega

# Build MPAS-Ocean
build_mpas_ocean(
    branch="/path/to/E3SM-Project",
    build_dir="/path/to/build/mpas-ocean",
    clean=True,
    debug=False,
    make_flags=None,
    make_target="ocean",
)

# Build Omega
build_omega(
    branch="/path/to/Omega",
    build_dir="/path/to/build/omega",
    clean=True,
    debug=False,
    cmake_flags="-DUSE_FEATURE_X=ON",
    account=None,
)
```

Tip: You can call the lower-level `make_build_script(...)` variants to inspect
or tweak the generated scripts before running them yourself.

## Integration with `polaris setup` and `polaris suite`

You can trigger these builders directly from the CLI by passing build flags to
{ref}`dev-polaris-setup` or {ref}`dev-polaris-suite`:

- `--build`: Build the selected component before setup.
- `--branch <path>`: Path to the MPAS-Ocean (E3SM-Project) or Omega checkout.
  Defaults to the corresponding submodule within your Polaris branch. Required
  submodules will be checked out automatically during the build.
- `--clean_build`: Start fresh (removes prior build state) and implies
  `--build`. Without this flag, an incremental build is used when possible to
  save time.
- `--quiet_build`: Write build output to a log file in the base work directory
   but not to stdout/stderr. By default, output is written to both. This
   flag implies `--build`.
- `--cmake_flags <string>`: Extra flags passed through to the build system.
  For MPAS-Ocean, this string is forwarded to `make` (e.g., `-j 8` or extra
  `VAR=VALUE` assignments). For Omega, it is forwarded to CMake as additional
  `-D...` definitions.
- `--debug`: Enable debug builds (`CMAKE_BUILD_TYPE=Debug` for Omega; adds
  `debug=TRUE` to MPAS-Ocean make flags).

Defaults and directories:

- The build output directory used by Polaris (`--component_path`) defaults to:
  - Omega: `build_omega/build_<machine>_<compiler>`
  - MPAS-Ocean: `build_mpas_ocean/build_<machine>_<compiler>_<mpi>`
- MPAS-Ocean copies files required by Polaris into the build directory so you
  can reuse the same source checkout to create builds for different machines,
  compilers, or MPI libraries without conflicts.
