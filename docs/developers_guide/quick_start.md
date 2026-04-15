(dev-quick-start)=

# Quick Start for Developers

(dev-shell)=

## Unix Shell

Currently, polaris only supports `bash` and related unix shells (such as
`ksh` on the Mac).  We do not support `csh`, `tcsh` or other variants of
`csh`.  An activation script for those shells will not be created.

If you normally use `csh`, `tcsh` or similar, you will need to temporarily
switch to bash by calling `/bin/bash` each time you want to use polaris.

(dev-polaris-repo)=

## Set up a polaris repository: for beginners

To begin, obtain the main branch of the
[polaris repository](https://github.com/E3SM-Project/polaris) with:

```bash
git clone git@github.com:E3SM-Project/polaris.git
cd polaris
git submodule update --init --recursive
```

There are 3 submodules with different versions of E3SM (`E3SM-Project` for
MPAS-Ocean, `Omega` for Omega and `MALI-Dev` for MALI) in a `e3sm_submodules`
directory of the polaris repository.

(dev-conda-env)=

## Polaris pixi and spack environments, compilers and system modules

Polaris now uses `mache.deploy` for deployment. In this repository, the
deployment entry point is `./deploy.py`.

For background on this workflow, see:

- [Mache docs index](https://docs.e3sm.org/mache/main/index.html)
- [Mache deploy user guide](https://docs.e3sm.org/mache/main/users_guide/deploy.html)
- [Mache deploy developer guide](https://docs.e3sm.org/mache/main/developers_guide/deploy.html)

As a developer, rerun `./deploy.py` when you check out a new branch or use a
new worktree. In most cases you do not need to rerun deployment while editing
existing files in `polaris`, because the package is installed in editable mode.

Polaris requires Python 3.11 or newer.

:::{note}
Miniforge, Micromamba, and Miniconda are no longer required for Polaris
deployment. If pixi is not already installed, `./deploy.py` can install it.
:::

### Supported machines

If you are on one of the {ref}`dev-supported-machines`, run:

```bash
./deploy.py [--machine <machine>] [--compiler <compiler> ...] \
    [--mpi <mpi> ...] [--deploy-spack] [--no-spack] \
    [--prefix <prefix>] [--recreate]
```

If you are on a login node, machine detection typically works automatically.
You can pass `--machine <machine>` explicitly if needed.

By default, Polaris will reuse existing machine-specific Spack environments
when the current deployment needs them. Use `--deploy-spack` when you want to
build or update those Spack environments. Use `--no-spack` for a Pixi-only
deployment, such as CI or unsupported machines.

### Unknown machines

If a machine is not known to mache, add machine support first
(see {ref}`dev-add-supported-machine`).

For workflows that need custom machine config files, see {ref}`config-files`.

### What the script does

`./deploy.py` can:

- install pixi if needed
- create/update a local pixi deployment prefix (default: `pixi-env`)
- install `polaris` from your local branch in editable/development mode
- optionally deploy Spack environments for selected compiler/MPI toolchains
- generate activation scripts (`load_*.sh`)

### Useful flags

`--machine`

: set machine explicitly instead of automatic detection

`--prefix`

: choose deployment prefix for the pixi environment

`--compiler`, `--mpi`

: compiler/MPI choices (primarily for Spack deployment)

`--deploy-spack`

: deploy supported Spack environments instead of only reusing existing ones

`--no-spack`

: disable all Spack use for this run and rely on Pixi dependencies instead

`--spack-path`

: path to the Spack checkout used for deployment

`--recreate`

: recreate deployment artifacts if they already exist

`--bootstrap-only`

: update only the bootstrap pixi environment used by deployment

`--mache-fork`, `--mache-branch`, `--mache-version`

: test deployment against a specific mache fork/branch/version

See `./deploy.py --help` for the full list.

### Activating the environment

Each time you want to work with Polaris, source one of the generated scripts:

```bash
source ./load_*.sh
```

This activates the deployment environment, loads machine modules when
appropriate, and sets environment variables needed by Polaris and MPAS
components.

When working inside a task or suite work directory, source
`load_polaris_env.sh` (a symlink to the selected load script).

### Switching between different polaris environments

Many developers are switching between different `polaris` branches.
We have 2 main workflows for doing this: checking out different branches
in the same directory (with `git checkout`) or creating new directories for
each branch (with `git worktree`).  Either way, you need to be careful that
the version of the `polaris` package that is installed in the active
environment you are using is the one you want.  But how to handle it
differs slightly between these workflows.

If you are developing or using multiple `polaris` branches in the same
directory (switching between them using `git checkout`), you will need
to make sure you update your `polaris` environment after changing
branches. If dependencies are unchanged, you can usually just re-source a
load script in the branch root.

You can do this by re-executing
`source ./load_*.sh`
from the *root of the repo* before proceeding.

Similarly, if you are developing or using multiple `polaris` branches
but you use a different directory for each
(creating the directories with `git worktree`),
you will need to make sure the version of the `polaris` package
in your active environment is the one you want.
If your branches use the same `polaris` version (so the dependencies
are the same), you can use the same deployment prefix for all of them.
You will tell the environment which branch to use by running
`source ./load_*.sh`
from the *root of the directory (worktree) you want to work with* before
proceeding.

In both of these workflows, you can modify the `polaris` code and the
environment will notice the changes as you make them.  However, if you have
added or removed any files during your development, you need to source the
load script again:
`source ./load_*.sh`
in the root of the repo or worktree so that the added or removed files will be
accounted for in the environment.

If you know that `polaris` has different dependencies
in a branch or worktree you are working on compared to a previous branch
you have worked with (or if you aren't sure), it is safest to not just reinstall
the `polaris` package but also to check the dependencies by re-running:
`./deploy.py` with the same arguments as above.
This will also reinstall the `polaris` package from the current directory.
The activation script includes a check to see if the version of polaris used
to produce the load script is the same as the version of polaris in the
current branch.  If the two don't match, an error like the following results
and the environment is not activated:

```
$ source load_polaris_morpheus_gnu_openmpi.sh
This load script is for a different version of polaris:
__version__ = '0.2.0'

Your code is version:
__version__ = '0.3.0-alpha.1'

You need to run ./deploy.py to update your environment and load script.
```

If you need more than one environment (e.g. because you are testing
multiple branches at the same time), use different deployment prefixes with
`./deploy.py --prefix <path>`.

:::{note}
If you switch branches and *do not* remember to recreate the environment
(`./deploy.py`) or at least source the
activation script (`load_*.sh`), you are likely to end up with
an incorrect and possibly unusable `polaris` package in your
environment.

In general, if one wishes to switch between environments created for
different polaris branches or applications, the best practice is to end
the current terminal session and start a new session with a clean
environment before executing the other polaris load script.  Similarly,
if you want to run a job script that itself sources the load script,
it's best to start a new terminal without having sourced a load script at
all.
:::

:::{note}
With the environment activated, you can switch branches and update
just the `polaris` package with:

```bash
python -m pip install --no-deps --no-build-isolation -e .
```

The activation script will do this automatically when you source it in
the root directory of your polaris branch.  The activation script will also
check if the current polaris version matches the one used to create the
activation script, thus catching situations where the dependencies are out
of date and the configure script needs to be rerun.  Since sourcing the
activation script is substantially faster than rerunning the configure script,
it is best to try the activation script first and run the configure script only
if you have to.
:::

### Troubleshooting

If you run into trouble with the environment or just want a clean start, you
can run:

```bash
./deploy.py [--machine <machine>] [--compiler <compiler> ...] \
  [--mpi <mpi> ...] [--deploy-spack] [--no-spack] --recreate
```

The `--recreate` flag will delete the environment and create it from
scratch.  This takes just a little extra time.

(dev-creating-only-env)=

## Creating/updating only the polaris environment

For some workflows (e.g. for MALI development with the Albany library when the
MALI build environment has been created outside of `polaris`, for example,
on an unsupported machine), you may only want to create the pixi environment
and not build SCORPIO, ESMF or include any system modules or environment
variables in your activation script. In such cases, run:

```bash
./deploy.py --no-spack
```

When `--no-spack` is not used, omitting `--deploy-spack` still means Polaris
will try to reuse any required pre-existing Spack environments.

To update only the bootstrap environment used internally by deployment:

```bash
./deploy.py --bootstrap-only
```

Each time you want to work with polaris, you will need to run:

```bash
source load_polaris.sh
```

For machine-specific deployments that use Spack, the generated script is
typically `load_polaris_<machine>_<compiler>_<mpi>.sh`.

This will load the appropriate environment for polaris.  It will also
set an environment variable `POLARIS_LOAD_SCRIPT` that points to the activation
script. Polaris uses this to make a symlink to the activation script
called `load_polaris_env.sh` in the work directory.

If you switch to another branch, you will need to rerun:

```bash
./deploy.py
```

to make sure dependencies are up to date and the `polaris` package points
to the current directory.

:::{note}
With the environment activated, you can switch branches and update
just the `polaris` package with:

```bash
python -m pip install --no-deps --no-build-isolation -e .
```

This will be substantially faster than rerunning
`./deploy.py ...` but at the risk that dependencies are
not up-to-date.  Since dependencies change fairly rarely, this will usually
be safe.
:::

(dev-build-components)=

## Building E3SM components

There are 3 E3SM repositories that are submodules within the polaris
repository, but the MALI-Dev submodule is not yet used.

For MPAS-Ocean and Omega, the recommended workflow is to let Polaris build
the component automatically during `polaris setup` or `polaris suite`.
By default, Polaris will reuse an existing build at the location specified by
the `component_path` config option when one is already present, which avoids
rebuilding when setting up the same tasks or suites again.  A manual build is
still supported and can be useful for advanced workflows, but should generally
be treated as an opt-in alternative.

If you are not pointing to an existing build with `-p` or `-f`, Polaris cannot
infer whether you want MPAS-Ocean or Omega, so you should always supply
`--model`.

Common optional build flags for this automated workflow:

- `--build`: force a build during setup, even if a build already exists at
  `component_path`
- `--clean_build`: remove any previous build state and start fresh (implies
  `--build`)
- `--quiet_build`: write build output to log files instead of printing full
  build output to the terminal (implies `--build`)
- `--debug`: build a debug executable instead of a release executable

For example:

```bash
polaris setup -t mesh/spherical/icos/base_mesh/240km/task \
  -m $MACHINE -w $WORKDIR --model mpas-ocean --clean_build --debug
```

```bash
polaris suite -c ocean -t nightly \
  -m $MACHINE -w $WORKDIR --model omega --clean_build --quiet_build
```

### Using an existing build (`-p` or `-f`)

If you already have a component build in another location, you can either:

1. provide it directly on the command line with `-p`, e.g.

   ```bash
   polaris setup -t mesh/spherical/icos/base_mesh/240km/task \
     -m $MACHINE -w $WORKDIR --model <mpas-ocean|omega> \
     -p /path/to/your/component/build
   ```

2. create a user config file and supply it with `-f`:

   ```ini
   [paths]
   component_path = /path/to/your/component/build
   ```

   then run:

   ```bash
   polaris setup -t mesh/spherical/icos/base_mesh/240km/task \
     -m $MACHINE -w $WORKDIR --model <mpas-ocean|omega> \
     -f path/to/component_paths.cfg
   ```

Use `-f` when you want a reusable config for multiple commands, and `-p` for
one-off setup commands.

(dev-mpas-build)=

### MPAS-Ocean or MPAS-Seaice

#### Recommended default: automated build from `polaris setup`/`polaris suite`

For MPAS-Ocean, Polaris can build automatically during setup and places the
build in `${WORKDIR}/build` by default:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
polaris setup -t ocean/planar/baroclinic_channel/10km/default \
  -m $MACHINE -w $WORKDIR --model mpas-ocean
```

Use the same approach with `polaris suite`; for repeated setup, add `--build`
to force rebuilding.

#### Manual build (advanced/optional)

For MPAS-Ocean and -Seaice both, see the last column of the table in
{ref}`dev-mpas-supported-machines` for the right `<mpas_make_target>` command for
each machine and compiler.

To build MPAS-Ocean manually, you would typically run:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
cd e3sm_submodules/E3SM-Project/components/mpas-ocean/
make <mpas_make_target>
```

The same applies to MPAS-Seaice except with `mpas-seaice` in the path above.

After a manual build, point `polaris setup` or `polaris suite` to the build
location using `-p` or `-f` as shown above.  When an existing build path is
provided, MPAS-Ocean is usually detected automatically; otherwise, provide
`--model mpas-ocean`.

(dev-omega-build)=

### Omega

See the table in {ref}`dev-omega-supported-machines` for a list of supported
machines.

If you simply wish to run the CTests from Omega, you likely want to use the
[Omega CTest Utility](https://github.com/E3SM-Project/polaris/blob/main/utils/omega/ctest/README.md).

#### Recommended default: automated build from `polaris setup`/`polaris suite`

For Omega, Polaris can build automatically during setup and places the build
in `${WORKDIR}/build` by default:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
polaris setup -t ocean/planar/barotropic_gyre/munk/free-slip \
  -m $MACHINE -w $WORKDIR --model omega
```

Use the same approach with `polaris suite`; for repeated setup, add `--build`
to force rebuilding.

#### Manual build (advanced/optional)

To build Omega manually,
```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
git submodule update --init e3sm_submodules/Omega
cd e3sm_submodules/Omega
git submodule update --init --recursive \
    externals/YAKL \
    externals/ekat \
    externals/scorpio \
    components/omega/external \
    cime
cd components/omega
mkdir build
cd build
cmake \
   -DOMEGA_BUILD_TYPE=Release \
   -DOMEGA_CIME_COMPILER=${POLARIS_COMPILER} \
   -DOMEGA_CIME_MACHINE=${POLARIS_MACHINE} \
   -DOMEGA_METIS_ROOT=${METIS_ROOT} \
   -DOMEGA_PARMETIS_ROOT=${PARMETIS_ROOT} \
   -DOMEGA_BUILD_TEST=ON \
   -Wno-dev \
   -S .. \
   -B .

./omega_build.sh
```
You can remove `-DOMEGA_BUILD_TEST=ON` to skip building CTests.  You can change
`-DOMEGA_BUILD_TYPE=Release` to `-DOMEGA_BUILD_TYPE=Debug` to build in debug
mode.

You can alter the example above to build whichever Omega branch and in whatever
location you like.  After a manual build, point `polaris setup` or
`polaris suite` at that build location with `-p` or `-f` as shown above.
When an existing build path is provided, Omega is usually detected
automatically; otherwise, provide `--model omega`.

(dev-working-with-polaris)=

## Running polaris from the repo

If you follow the procedure above, you can run polaris with the `polaris`
command-line tool exactly like described in the {ref}`quick-start`
and as detailed in {ref}`dev-command-line`.

To list tasks you need to run:

```bash
polaris list
```

The results will be the same as described in {ref}`dev-polaris-setup`, but the
tasks will come from the local polaris directory.

To set up a task, you will run something like:

```bash
polaris setup -t mesh/spherical/icos/base_mesh/240km/task -m $MACHINE -w $WORKDIR -p $COMPONENT
```

where `$MACHINE` is an ES3M machine, `$WORKDIR` is the location where polaris
tasks will be set up and `$COMPONENT` is the directory where the E3SM
component executable has been compiled. See {ref}`dev-polaris-setup` for
details.

To list available suites, you would run:

```bash
polaris list --suites
```

And you would set up a suite as follows:

```bash
polaris suite -c ocean -t nightly -m $MACHINE -w $WORKDIR -p $COMPONENT
```

When you want to run the code, go to the work directory (for the suite or test
case), log onto a compute node (if on an HPC machine) and run:

```bash
source load_polaris_env.sh
polaris serial
```

The first command will source the same activation script
(`load_<env_name>_<machine>_<compiler>_<mpi>.sh`) that you used to set
up the suite or task (`load_polaris_env.sh` is just a symlink to that
activation script you sourced before setting up the suite or task).

(dev-polaris-style)=

## Code style for polaris

Polaris complies with the coding conventions of
[PEP8](https://peps.python.org/pep-0008/). Rather than memorize all the
guidelines, the easiest way to stay in compliance as a developer writing new
code or modifying existing code is to use a PEP8 style checker. When you create
a load script, we automatically install [pre-commit](https://pre-commit.com/),
a tool that helps to enforce this standard by checking your code each time you
make a commit. It will tell you about various types of problems it finds.
Internally, `pre-commit` uses [ruff](https://docs.astral.sh/ruff/) to perform
various checks, such as enforcing PEP8 compliance and sorting and formatting
imports. Additionally, `pre-commit` uses
[flynt](https://github.com/ikamensh/flynt) to update any old-style format
strings to f-strings and [mypy](https://mypy-lang.org/) to check for consistent
variable types. An example error might be:

```bash
example.py:77:1: E302 expected 2 blank lines, found 1
```

For this example, we would just add an additional blank line after line 77 and
try the commit again to make sure we've resolved the issue.

You may also find it useful to use an IDE with a PEP8 style checker built in,
such as [VS Code](https://code.visualstudio.com/). See
[Formatting Python in VS Code](https://code.visualstudio.com/docs/python/formatting)
for some tips on checking code style in VS Code.

Once you open a pull request for your feature, there is an additional PEP8
style check at this stage (again using pre-commit).

(dev-polaris-ai-instructions)=

## AI coding assistant instructions

Polaris also includes repository-level instructions for AI coding assistants:

- `AGENTS.md` provides instructions for Codex and other agent-style tools that
  support repository guidance.
- `.github/copilot-instructions.md` provides repository-wide instructions for
  GitHub Copilot.
- `.github/instructions/python.instructions.md` provides Python-specific
  Copilot instructions.

These files are intended to capture style preferences that are useful for
human contributors and AI tools but are not always enforceable automatically.
Examples include preferring module-level helper functions over nested
functions, putting public functions before private helpers when practical, and
avoiding local imports unless they are needed.

To keep maintenance manageable:

- Put anything that can be enforced automatically in `pyproject.toml` and
  `.pre-commit-config.yaml` first, then keep the AI instruction files focused
  on higher-level preferences.
- Keep the shared guidance short and stable so it is practical to mirror in
  both Codex and Copilot instruction files.
- Treat `AGENTS.md` as the easiest place to edit shared prose first, then
  update the two Copilot instruction files to match when shared guidance
  changes.
- Use `.github/instructions/*.instructions.md` only for path-specific guidance
  such as Python conventions, rather than repeating general repository advice
  in many places.
- If an AI instruction conflicts with automated tooling, the automated tooling
  should win.

When you add or change a style preference, update these three files in the same
pull request so they stay aligned.

(dev-polaris-repo-advanced)=

## Set up a polaris repository with worktrees: for advanced users

This section uses `git worktree`, which provides more flexibility but is more
complicated. See the beginner section above for the simpler version. In the
worktree version, you will have many unix directories, and each corresponds to
a git branch. It is easier to keep track of, and easier to work with many
branches at once. Begin where you keep your repositories:

```bash
mkdir polaris
cd polaris
git clone git@github.com:E3SM-Project/polaris.git main
cd main
```

The `E3SM-Project/polaris` repo is now `origin`. You can add more remotes. For
example:

```bash
git remote add mark-petersen git@github.com:mark-petersen/polaris.git
git fetch mark-petersen
```

To view all your remotes:

```bash
git remote -v
```

To view all available branches, both local and remote:

```bash
git branch -a
```

We will use the git worktree command to create a new local branch in its own
unix directory:

```bash
cd polaris/main
git worktree add -b new_branch_name ../new_branch_name origin/main
cd ../new_branch_name
```

In this example, we branched off `origin/main`, but you could start from
any branch, which is specified by the last `git worktree` argument.

There are two ways to build the E3SM component in standalone mode:

1. Submodules within polaris (easier): This guarantees that the E3SM commit
   that the submodule points to is compatible with polaris.  It is also the
   default location for finding the E3SM component so you don't need to specify
   the `-p` flag at the command line or put the E3SM component path path in
   your config file (if you even need a config file at all).  Here is an
   example for MPAS-Ocean:

   ```bash
   source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
   git submodule update --init --recursive
   cd e3sm_submodules/E3SM-Project/components/mpas-ocean/
   make gfortran
   ```

2. Other E3SM directory (advanced): Create your own clone of the
   `E3SM-Project/E3SM`, `E3SM-Project/Omega` or `MALI-Dev/E3SM` repository
   elsewhere on disk. Either make a config file that specifies the absolute
   path to the path where the `ocean_model` or `landice_model` executable
   is found, or specify this path on the command line with `-p`.  You are
   responsible for knowing if this particular version of MPAS component's code
   is compatible with the version of polaris that you are using.  The
   simplest way to set up a new repo for MALI development in a new directory
   is:

   ```bash
   git clone git@github.com:MALI-Dev/E3SM.git your_new_branch
   cd your_new_branch
   git checkout -b your_new_branch origin/develop
   ```

   The equivalent for MPAS-Ocean development would be:

   ```bash
   git clone git@github.com:E3SM-Project/E3SM.git your_new_branch
   cd your_new_branch
   git checkout -b your_new_branch origin/main
   ```
