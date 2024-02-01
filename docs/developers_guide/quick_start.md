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
MPAS-Ocean, `OMEGA` for OMEGA and `MALI-Dev` for MALI) in a `e3sm_submodules`
directory of the polaris repository.

(dev-conda-env)=

## polaris conda environment, spack environment, compilers and system modules

As a developer, you will need your own
[conda](https://conda.io/projects/conda/en/latest/index.html) environment with
the latest dependencies for polaris and a development installation of polaris
from the  branch you're working on.  On supported machines, you will also need
to point to a shared [spack](https://spack.io/) environment with some tools
and libraries built for that system that polaris needs.

In the root of the repository is a tool, `configure_polaris_envs.py`
that can get you started.

You will need to run `./configure_polaris_envs.py` each time you check
out a new branch or create a new worktree with `git`.  Typically, you will
*not* need to run this command when you make changes to files within the
`polaris` python package.  These will automatically be recognized because
`polaris` is installed into the conda environment in "editable" mode.  You
*will* need to run the command if you add new code files or data files to the
package because these don't get added automatically.

Whether you are on one of the {ref}`dev-supported-machines` or an "unknown"
machine, you will need to specify a path where
[Miniforge3](https://github.com/conda-forge/miniforge#miniforge3) either has
already been installed or an empty directory where the script can install it.
You must have write permission in the base environment (if it exists).

:::{note}
We have found that an existing Miniconda3 installation **does not** always
work well for polaris, so please start with Miniforge3 instead.
:::

:::{note}
It is *very* important that you not use a shared installation of Miniforge3
or Miniconda3 such as the base environment for E3SM-Unified for polaris
development. Most developers will not have write access to shared
environments, meaning that you will get write-permission errors when you
try to update the base environment or create the polaris development
environment.

For anyone who does have write permission to a shared environment, you
would be creating your polaris development environment in a shared space,
which could cause confusion.

Please use your own personal installation of Miniforge3 for development,
letting `configure_polaris_envs.py` download and install Miniforge3 for
you if you don't already have it installed.
:::


### Supported machines

If you are on one of the {ref}`dev-supported-machines`, run:

```bash
./configure_polaris_envs.py --conda <base_path_to_install_or_update_conda> \
    [-c <compiler>] [--mpi <mpi>] [-m <machine>] [--with_albany] \
    [--with_netlib_lapack] [--with_petsc]
```

The `<base_path_to_install_or_update_conda>` is typically `~/miniforge3`.
This is the location where you would like to install Miniforge3 or where it is
already installed. If you have limited space in your home directory, you may
want to give another path.  If you already have it installed, that path will
be used to add (or update) the polaris test environment.

See the machine under {ref}`dev-supported-machines` for a list of available
compilers to pass to `-c`.  If you don't supply a compiler, you will get
the default one for that machine. Typically, you will want the  default MPI
flavor that polaris has defined for each compiler, so you should
not need to specify which MPI version to use but you may do so with `--mpi`
if you need to.

If you are on a login node, the script should automatically recognize what
machine you are on.  You can supply the machine name with `-m <machine>` if
you run into trouble with the automatic recognition (e.g. if you're setting
up the environment on a compute node, which is not recommended).

### Environments with Albany

If you are working with MALI, you should specify `--with_albany`.  This will
ensure that the Albany and Trilinos libraries are included among those built
with system compilers and MPI libraries, a requirement for many MAlI test
cases.  Currently, only Albany is only supported with `gnu` compilers.

It is safe to add the `--with_albany` flag for MPAS-Ocean but it is not
recommended unless a user wants to be able to run both models with the same
conda/spack environment.  The main downside is simply that unneeded libraries
will be linked in to MPAS-Ocean.

### Environments with PETSc and Netlib-LAPACK

If you are working with MPAS-Ocean tasks that need PETSC and
Netlib-LAPACK, you should specify `--with_petsc --with_netlib_lapack` to
point to Spack environments where these libraries are included.  Appropriate
environment variables for pointing to these libraries will be build into the
resulting load script (see below).

### Unknown machines

If you are on an "unknown" machine, typically a Mac or Linux laptop or
workstation, you will need to specify which flavor of MPI you want to use
(`mpich` or `openmpi`):

```bash
./configure_polaris_envs.py --conda <conda_path> --mpi <mpi>
```

Again, the `<conda_path>` is typically `~/miniforge3`, and is the location
where you would like to install Miniforge3 or where it is already installed.
If you already have it installed, that path will be used to add (or update) the
polaris test environment.

We only support one set of compilers for Mac and Linux (`gnu` for Linux and
`clang` with `gfortran` for Mac), so there is no need to specify them.
See {ref}`dev-other-machines` for more details.

In addition, unknown machines require a config file to be specified when setting
up the polaris test environment.  A config file can be specified using
`-f <filename>`, where `<filename>` is an absolute or relative path to the
file. More information, including example config files, can be found
in {ref}`config-files`.

:::{note}
Currently, there is not a good way to build Albany for an unknown machine as
part of the polaris deployment process, meaning MALI will be limited to the
shallow-ice approximation (SIA) solver.

To get started on HPC systems that aren't supported by Polaris, get in touch
with the developers.
:::

### What the script does

In addition to installing Miniforge3 and creating the conda environment for you,
this script will also:

- install [Jigsaw](https://github.com/dengwirda/jigsaw) and
  [Jigsaw-Python](https://github.com/dengwirda/jigsaw-python) from source
  from the `jigsaw-python` submodule. These tools are used to create many of
  the meshes used in Polaris.
- install the `polaris` package from the local branch in "development" mode
  so changes you make to the repo are immediately reflected in the conda
  environment.
- with the `--update_spack` flag on supported machines, installs or
  reinstalls a spack environment with various system libraries.  The
  `--spack` flag can be used to point to a location for the spack repo to be
  checked out.  Without this flag, a default location is used. Spack is used to
  build several libraries with system compilers and MPI library, including:
  [SCORPIO](https://github.com/E3SM-Project/scorpio) (parallel i/o for E3SM
  components) [ESMF](https://earthsystemmodeling.org/) (making mapping files
  in parallel), [Trilinos](https://trilinos.github.io/),
  [Albany](https://github.com/sandialabs/Albany),
  [Netlib-LAPACK](http://www.netlib.org/lapack/) and
  [PETSc](https://petsc.org/). **Please uses these flags with caution, as
  they can affect shared environments!**  See {ref}`dev-deploying-spack`.
- with the `--with_albany` flag, creates or uses an existing Spack
  environment that includes Albany and Trilinos.
- with the `--with_petsc --with_netlib_lapack` flags, creates or uses an
  existing Spack environment that includes PETSc and Netlib-LAPACK.
- make an activation script called `load_*.sh`, where the details of the
  name encode the conda environment name, the machine, compilers, MPI
  libraries, and optional libraries,  e.g.
  `load_dev_polaris_<version>_<machine>_<compiler>_<mpi>.sh` (`<version>`
  is the polaris version, `<machine>` is the name of the
  machine, `<compiler>` is the compiler name, and `mpi` is the MPI flavor).
- optionally (with the `--check` flag), run some tests to make sure some of
  the expected packages are available.

### Optional flags

`--check`

: Check to make sure expected commands are present

`--python`

: Select a particular python version (the default is currently 3.8)

`--env_name`

: Set the name of the environment (and the prefix for the activation script)
  to something other than the default (`dev_polaris_<version>` or
  `dev_polaris_<version>_<mpi>`).

`--update_jigsaw`

: Used to reinstall Jigsaw and Jigsaw-Python into the conda environment if
  you have made changes to the Jigsaw (c++) code in the `jigsaw-python`
  submodule. You should not need to reinstall Jigsaw-Python if you have made
  changes only to the python code in `jigsaw-python`, as the python package
  is installed in
  [edit mode](https://setuptools.pypa.io/en/latest/userguide/development_mode.html).

### Activating the environment

Each time you want to work with polaris, you will need to run:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
```

This will load the appropriate conda environment, load system modules for
compilers, MPI and libraries needed to build and run E3SM components, and
set environment variables needed for E3SM components or polaris.  It will also
set an  environment variable `LOAD_POLARIS_ENV` that points to the activation
script. Polaris uses this to make an symlink to the activation script called
`load_polaris_env.sh` in the work directory.  When the load script is
executed from the base of the polaris repository (i.e., as
`source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh`),
it will install the version of the `polaris` package from that location into
the associated conda environment.  When the load script is executed from the
work directory through the symlink, it will activate the associated conda
environment, but does *not* install the `polaris` package into the conda
environment; it is assumed that is already up to date from when the conda
environment was created or last updated.

It is generally recommended to activate the `polaris` environment (from
either the polaris repo or via the workdir symlink) from a
clean environment.  Unexpected behavior may occur if activating a different
`polaris` environment after having one already activated.

If you switch between different polaris branches, it is safest to rerun
`./configure_polaris_envs.py` with the same arguments as above to make
sure dependencies are up to date and the `polaris` package points to the
current directory.  If you are certain that no polaris dependencies are
different between branches, you can also simply source the activation script
(`load_*.sh`) in the branch.

Once you have sourced the activation script, you can run `polaris` commands
anywhere, and it always refers to that branch.  To find out which branch you
are actually running `polaris` from, you should run:

```bash
echo $LOAD_POLARIS_ENV
```

This will give you the path to the load script, which will also tell you where
the branch is.  If you do not use the worktree approach, you will also need to
check what branch you are currently on with `git log`, `git branch` or
a similar command.

If you wish to work with another compiler, simply rerun the script with a new
compiler name and an activation script will be produced.  You can then source
either activation script to get the same conda environment but with different
compilers and related modules.  Make sure you are careful to set up polaris by
pointing to a version of the MPAS model that was compiled with the correct
compiler.

### Switching between different polaris environments

Many developers are switching between different `polaris` branches.
We have 2 main workflows for doing this: checking out different branches
in the same directory (with `git checkout`) or creating new directories for
each branch (with `git worktree`).  Either way, you need to be careful that
the version of the `polaris` package that is installed in the conda
environment you are using is the one you want.  But how to handle it
differs slightly between these workflows.

If you are developing or using multiple `polaris` branches in the same
directory (switching between them using `git checkout`), you will need
to make sure you update your `polaris` environment after changing
branches.  Often the branches you're developing will make use of the
same conda environment, because they are using the same
`polaris` version (so the dependencies aren't changing).  The same
conda environment (e.g. `dev_polaris_<version>`) can safely be used
with multiple branches if you explicitly reinstall the `polaris` package
you want to use into the conda environment *after* moving to a new branch.
You can do this by simply re-executing
`source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh`
from the *root of the repo* before proceeding.

Similarly, if you are developing or using multiple `polaris` branches
but you use a different directory for each
(creating the directories with `git worktree`),
you will need to make sure the version of the `polaris` package
in your conda environment is the one you want.
If your branches use the same `polaris` version (so the dependencies
are the same), you can use the same conda environment
(e.g. `dev_polaris_<version>`) for all of them.  But you will only
be able to test one of them at a time.  You will tell the conda environment
which branch to use by running
`source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh`
from the *root of the directory (worktree) you want to work with* before
proceeding.

In both of these workflows, you can modify the `polaris` code and the conda
environment will notice the changes as you make them.  However, if you have
added or removed any files during your development, you need to source the
load script again:
`source ./load_<conda_env>_<machine>_<compiler>_<mpi>.sh`
in the root of the repo or worktree so that the added or removed files will be
accounted for in the conda environment.

If you know that `polaris` has different dependencies
in a branch or worktree you are working on compared to a previous branch
you have worked with (or if you aren't sure), it is safest to not just reinstall
the `polaris` package but also to check the dependencies by re-running:
`./configure_polaris_envs.py`  with the same arguments as above.
This will also reinstall the `polaris` package from the current directory.
The activation script includes a check to see if the version of compass used
to produce the load script is the same as the version of compass in the
current branch.  If the two don't match, an error like the following results
and the environment is not activated:

```
$ source load_polaris_test_morpheus_gnu_openmpi.sh
This load script is for a different version of polaris:
__version__ = '0.2.0'

Your code is version:
__version__ = '0.3.0-alpha.1'

You need to run ./configure_polaris_envs.py to update your conda
environment and load script.
```

If you need more than one conda environment (e.g. because you are testing
multiple branches at the same time), you can choose your own name
for the conda environment.  Typically, this might be something related to the
name of the branch you are developing.  This can be done with the
`--env_name` argument to `./configure_polaris_envs.py`.  You
can reuse the same custom-named environment across multiple branches
if that is useful.  Just remember to reinstall `polaris` each time you
switch branches.

:::{note}
If you switch branches and *do not* remember to recreate the conda
environment (`./configure_polaris_envs.py`) or at least source the
activation script (`load_*.sh`), you are likely to end up with
an incorrect and possibly unusable `polaris` package in your conda
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
With the conda environment activated, you can switch branches and update
just the `polaris` package with:

```bash
python -m pip install -e .
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
./configure_polaris_envs.py --conda <conda_path> -c <compiler> --recreate
```

The `--recreate` flag will delete the conda environment and create it from
scratch.  This takes just a little extra time.

(dev-creating-only-env)=

## Creating/updating only the polaris environment

For some workflows (e.g. for MALI development with the Albany library when the
MALI build environment has been created outside of `polaris`, for example,
on an unsupported machine), you may only want to create the conda environment
and not build SCORPIO, ESMF or include any system modules or environment
variables in your activation script. In such cases, run with the
`--env_only` flag:

```bash
./configure_polaris_envs.py --conda <conda_path> --env_only ...
```

Each time you want to work with polaris, you will need to run:

```bash
source ./load_<env_name>.sh
```

This will load the appropriate conda environment for polaris.  It will also
set an environment variable `LOAD_POLARIS_ENV` that points to the activation
script. Polaris uses this to make a symlink to the activation script
called `load_polaris_env.sh` in the work directory.

If you switch to another branch, you will need to rerun:

```bash
./configure_polaris_envs.py --conda <conda_path> --env_only
```

to make sure dependencies are up to date and the `polaris` package points
to the current directory.

:::{note}
With the conda environment activated, you can switch branches and update
just the `polaris` package with:

```bash
python -m pip install -e .
```

This will be substantially faster than rerunning
`./configure_polaris_envs.py ...` but at the risk that dependencies are
not up-to-date.  Since dependencies change fairly rarely, this will usually
be safe.
:::

(dev-build-components)=

## Building E3SM components

There are 3 E3SM repositories that are submodules within the polaris
repository.  To build MPAS-Ocean, you would typically run:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
cd e3sm_submodules/E3SM-Project/components/mpas-ocean/
make <mpas_make_target>
```

MALI should typically be compiled with the Albany library that contains the
first-order velocity solver.  The Albany first-order velocity solver is the
only velocity option that is scientifically validated.  On supported machines
and with compilers that support albany, you can run:

```bash
./configure_polaris_envs.py --with_albany ...
```

Then, you can build MALI:

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>_albany.sh
cd e3sm_submodules/MALI-Dev/components/mpas-albany-landice
make ALBANY=true <mpas_make_target>
```

For MPAS-Ocean and MALI both, see the last column of the table in
{ref}`dev-supported-machines` for the right `<mpas_make_target>` command for
each machine and compiler.

Instructions for building OMEGA will be added as development proceeds.

(dev-working-with-polaris)=

## Running polaris from the repo

If you follow the procedure above, you can run polaris with the `polaris`
command-line tool exactly like described in the {ref}`quick-start`
and as detailed in {ref}`dev-command-line`.

To list tasks you need to run:

```bash
polaris list
```

The results will be the same as described in {ref}`setup-overview`, but the
tasks will come from the local polaris directory.

To set up a task, you will run something like:

```bash
polaris setup -t ocean/global_ocean/QU240/mesh -m $MACHINE -w $WORKDIR -p $COMPONENT
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
polaris run
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
a tools that helps to enforce this standard by checking your code each time you
make a commit.  It will tell you about various types of problems it finds.
Internally, it uses [flake8](https://flake8.pycqa.org/en/latest/) to check PEP8
compliance, [isort](https://pycqa.github.io/isort/) to sort, check and format
imports, [flynt](https://github.com/ikamensh/flynt) to change any format
strings to f-strings, and [mypy](https://mypy-lang.org/) to check for
consistent variable types. An example error might be:

```bash
example.py:77:1: E302 expected 2 blank lines, found 1
```

For this example, we would just add an additional blank line after line 77 and
try the commit again to make sure we've resolved the issue.

You may also find it useful to use an IDE with a PEP8 style checker built in,
such as [PyCharm](https://www.jetbrains.com/pycharm/). See
[this tutorial](https://www.jetbrains.com/help/pycharm/tutorial-code-quality-assistance-tips-and-tricks.html)
for some tips on checking code style in PyCharm.

Once you open a pull request for your feature, there is an additional PEP8
style check at this stage (again using pre-commit).

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
