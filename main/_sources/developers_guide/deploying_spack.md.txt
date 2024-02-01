(dev-deploying-spack)=

# Deploying a new spack environment

## Where do we update polaris dependencies?

### Mache

If system modules change in E3SM, we try to stay in sync:

- compilers
- MPI libraries
- netcdf-C
- netcdf-fortran
- pnetcdf
- mkl (or other linear algebra libs)

When we update the `mache` version in Polaris, we also need to bump the
Polaris version (typically either the major or the minor version) and then
re-deploy shared spack environments on each supported machine.

### Spack

Spack is used to build libraries used by E3SM components and tools that need
system MPI:

- ESMF
- MOAB
- SCORPIO
- Metis
- Parmetis
- Trilinos
- Albany
- PETSc
- Netlib LAPACK

We build one spack environment for tools (e.g. ESMF and MOAB) and another for
libraries.  This allows us to build the tools with one set of compilers and
MPI libraries adn the libraries with another.  This is sometimes necessary,
since ESMF, MOAB and/or their dependencies can't always be built or don't
run correctly with all compiler and MPI combinations.  For example, we have
experienced problems running ESMF built with intel compilers on Perlmutter.
We are also not able to build ESMF or the Eigen dependency of MOAB using
`nvidiagpu` compilers.

When we update the versions of any of these packages in Polaris, we also need
to bump the Polaris version (typically either the major or the minor version)
and then re-deploy shared spack environments on each supported machine.

### Conda

Conda (via conda-forge) is used for python packages and related dependencies
that don’t need system MPI. Conda environments aren’t shared between
developers because the polaris python package you’re developing is part of the
conda environment.

When we update the constraints on conda dependencies, we also need to bump the
Polaris alpha, beta or rc version.  We do not need to re-deploy spack
environments on share machines because they remain unaffected.

## Mache

A brief tour of mache.

### Identifying E3SM machines

Polaris and other packages use mache to identify what machine they’re on (when
you’re on a login node).  This is used when configuring polaris and creating a
conda environment.  Because of this, there is a “bootstrapping” process where
a conda environment is created with mache installed in it, then the machine is
identified and the rest of the polaris setup can continue.

### Config options describing E3SM machines

Mache has config files for each E3SM machine that tell us where E3SM-Unified
is, where to find diagnostics, and much more, see
[machines](https://github.com/E3SM-Project/mache/tree/main/mache/machines).
These config options are shared across packages including:

- MPAS-Analysis
- E3SM_Diags
- zppy
- polaris
- compass
- E3SM-Unified

Polaris uses these config options to know how to make a job script, where to
find locally cached files in its “databases” and much more.

### Modules, env. variables, etc. for  E3SM machines

Mache keeps its own copy of the E3SM file
[config_machines.xml](https://github.com/E3SM-Project/E3SM/blob/master/cime_config/machines/config_machines.xml)
in the package [here](https://github.com/E3SM-Project/mache/blob/main/mache/cime_machine_config/config_machines.xml).
We try to keep a close eye on E3SM master and update mache when system modules
for machines that mache knows about get updated.  When this happens, we update
mache’s copy of `config_machines.xml` and that tells me which modules to
update in spack, see below.dev_quick_start

### Creating spack environments

Mache has templates for making spack environments on some of the E3SM supported
machines.  See [spack](https://github.com/E3SM-Project/mache/tree/main/mache/spack).
It also has functions for building the spack environments with these templates
using E3SM’s fork of spack (see below).

## Updating spack from polaris with mache from a remote branch

If you haven’t cloned polaris and added Xylar's fork, here’s the process:

```bash
mkdir polaris
cd polaris/
git clone git@github.com:E3SM-Project/polaris.git main
cd main/
git remote add xylar/polaris git@github.com:xylar/polaris.git
```

Now, we need to set up polaris and build spack packages making use of the
updated mache.  This involves changing the mache version in a couple of places
in polaris and updating the version of polaris itself to a new alpha, beta or
rc.  As an example, we will use the branch
[simplify_local_mache](https://github.com/xylar/polaris/tree/simplify_local_mache).

Often, we will need to test with a `mache` branch that has changes needed
by polaris.  Here, we will use `<fork>` as a stand-in for the fork of mache
to use (e.g. `E3SM-Project/mache`) and `<branch>` as the stand-in for a branch on
that fork (e.g. `main`).

We also need to make sure there is a spack branch for the version of Polaris.
The spack branch is a branch off of the develop branch on
[E3SM’s spack repo](https://github.com/E3SM-Project/spack) that has any
uupdates to packages required for this version of mache.  The remote branch
is named after the release version of mache (omitting any alpha, beta or rc
suffix because it is intended to be the spack branch we will use once the
``mache`` release happens).  In this example, we will work with the branch
[spack_for_mache_1.12.0](https://github.com/E3SM-Project/spack/tree/spack_for_mache_1.12.0).
The local clone is instead named after the Polaris version (again any omitting
alpha, beta or rc) plus the compiler and MPI library because we have discovered
two users cannot make modifications to the same git clone.  Giving each clone
of the spack branch a unique name ensures that they are independent.

Here's how to get a branch of polaris we're testing (`simplify_local_mache`
in this case) as a local worktree:

```bash
# get my branch
git fetch --all -p
# make a worktree for checking out my branch
git worktree add ../simplify_local_mache -b simplify_local_mache \
    --checkout xylar/polaris/simplify_local_mache
cd ../simplify_local_mache/
```

You will also need a local installation of
[Miniforge3](https://github.com/conda-forge/miniforge#miniforge3).
Polaris can do this for you if you haven't already installed it.  If you want
to download it manually, use the Linux x86_64 version for all our supported
machines.

:::{note}
We have found that an existing Miniconda3 installation **does not** always
work well for polaris, so please start with Miniforge3 instead.
:::

:::{note}
You definitely need your own local Miniforge3 installation -- you can’t use
a system version or a shared one like E3SM-Unified.
:::

Define a location where Miniforge3 is installed or where you want to install
it:

```bash
# change to your conda installation
export CONDA_BASE=${HOME}/miniforge3
```

Okay, we're finally ready to do a test spack build for polaris.
To do this, we call the `configure_polaris_env.py` script using
`--mache_fork`, `--mache_branch`, `--update_spack`, `--spack` and
`--tmpdir`. Here is an example appropriate for Anvil or Chrysalis:

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --mache_fork <fork> \
    --mache_branch <branch> \
    --update_spack \
    --spack /lcrc/group/e3sm/${USER}/spack_test \
    --tmpdir ${TMPDIR} \
    --compiler intel intel gnu \
    --mpi openmpi impi openmpi \
    --recreate \
    --verbose
```

The directory you point to with `--conda` either doesn't exist or contains
your existing installation of Miniforge3.

When you supply `--mache_fork` and `--mache_branch`, polaris will clone
a fork of the `mache` repo and check out the requested branch, then install
that version of mache into both the polaris installation conda environment and
the final polaris environment.

`mache` gets installed twice because the deployment tools need `mache` to
even know how to install polaris and build the spack environment on supported
machines.  The "prebootstrap" step in deployment is creating the installation
conda environment.  The "bootstrap" step is creating the conda environment that
polaris will actually use and (in this case with `--update_spack`) building
spack packages, then creating the "load" or "activation" script that you will
need to build MPAS components and run polaris.

For testing, you want to point to a different location for installing spack
using `--spack`.

On many machines, the `/tmp` directory is not a safe place to build spack
packages.  Use `--tmpdir` to point to another place, e.g., your scratch
space.

The `--recreate` flag may not be strictly necessary but it’s a good idea.
This will make sure both the bootstrapping conda environment (the one that
installs mache to identify the machine) and the polaris conda environment are
created fresh.

The `--compiler` flag is a list of one or more compilers to build for and the
`--mpi` flag is the corresponding list of MPI libraries.  To see what is
supported on each machine, take a look at {ref}`dev-supported-machines`.

Be aware that not all compilers and MPI libraries support Albany and PETSc, as
discussed below.

### Testing spack with PETSc (and Netlib LAPACK)

If you want to build PETSc (and Netlib LAPACK), use the `--with_petsc` flag.
Currently, this only works with some
compilers, but that may be more that I was trying to limit the amount of work
for the polaris support team.  There is a file,
[petsc_supported.txt](https://github.com/E3SM-Project/polaris/blob/main/deploy/petsc_supported.txt),
that lists supported compilers and MPI libraries on each machine.

Here is an example:

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --mache_fork <fork> \
    --mache_branch <branch> \
    --update_spack \
    --spack /lcrc/group/e3sm/${USER}/spack_test \
    --tmpdir ${TMPDIR} \
    --compiler intel gnu \
    --mpi openmpi \
    --with_petsc \
    --recreate \
    --verbose
```

### Testing spack with Albany

If you also want to build Albany, use the `--with_albany` flag.  Currently,
this only works with Gnu compilers.  There is a file,
[albany_support.txt](https://github.com/E3SM-Project/polaris/blob/main/deploy/albany_supported.txt),
that lists supported compilers and MPI libraries on each machine.

Here is an example:

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --mache_fork <fork> \
    --mache_branch <branch> \
    --update_spack \
    --spack /lcrc/group/e3sm/${USER}/spack_test \
    --tmpdir ${TMPDIR} \
    --compiler gnu \
    --mpi openmpi \
    --with_albany \
    --recreate \
    --verbose
```

### Troubleshooting spack

If you encounter an error like:
```
==>   spack env activate dev_polaris_0_2_0_gnu_mpich
==> Error: Package 'armpl' not found.
You may need to run 'spack clean -m'.
```
during the attempt to build spack, you will first need to find the path to
`setup-env.sh` (see `polaris/build_*/build*.sh`) and source that script to
get the `spack` command, e.g.:

```bash
source ${PSCRATCH}/spack_test/dev_polaris_0_2_0_gnu_mpich/share/spack/setup-env.sh
```

Then run the suggested command:

```bash
spack clean -m
```

After that, re-running `./configure_polaris_envs.py` should work correctly.

This issue seems to be related to switching between spack v0.18 and v0.19 (used by different versions of polaris).

## Testing polaris

### Testing MPAS-Ocean without PETSc

Please use the E3SM-Project submodule in polaris for testing, rather than
E3SM’s master branch.  The submodule is the version we know works with polaris
and serves as kind of a baseline for other testing.

```bash
# source whichever load script is appropriate
source load_dev_polaris_0.2.0_chrysalis_intel_openmpi.sh
git submodule update --init --recursive
cd E3SM-Project/components/mpas-ocean
# this will build with PIO and OpenMP
make ifort
polaris suite -c ocean -t pr -p . \
    -w /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/ocean_pr_chrys_intel_openmpi
cd /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/ocean_pr_chrys_intel_openmpi
sbatch job_script.pr.bash
```

You can make other worktrees of E3SM-Project for testing other compilers if
that’s helpful.  It also might be good to open a fresh terminal to source a
new load script.  This isn’t required but you’ll get some warnings.

```bash
source load_dev_polaris_0.2.0_chrysalis_gnu_openmpi.sh
cd E3SM-Project
git worktree add ../e3sm_chrys_gnu_openmpi
cd ../e3sm_chrys_gnu_openmpi
git submodule update --init --recursive
cd components/mpas-ocean
make gfortran
polaris suite -c ocean -t pr -p . \
    -w /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/ocean_pr_chrys_gnu_openmpi
cd /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/ocean_pr_chrys_gnu_openmpi
sbatch job_script.pr.bash
```

You can also explore the utility in
[utils/matrix](https://github.com/E3SM-Project/polaris/tree/main/utils/matrix) to
test on several compilers automatically.

### Testing MALI with Albany

Please use the MALI-Dev submodule in polaris for testing, rather than MALI-Dev
develop branch.  The submodule is the version we know works with polaris and
serves as kind of a baseline for other testing.

```bash
# source whichever load script is appropriate
source load_dev_polaris_0.2.0_chrysalis_gnu_openmpi_albany.sh
git submodule update --init --recursive
cd MALI-Dev/components/mpas-albany-landice
# you need to tell it to build with Albany
make ALBANY=true gfortran
polaris suite -c landice -t full_integration -p . \
    -w /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/landice_full_chrys_gnu_openmpi
cd /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/landice_full_chrys_gnu_openmpi
sbatch job_script.full_integration.bash
```

### Testing MPAS-Ocean with PETSc

The tests for PETSc use nonhydrostatic capabilities not yet integrated into
E3SM.  So you can’t use the E3SM-Project submodule.  You need to use Sara
Calandrini’s [nonhydro](https://github.com/scalandr/E3SM/tree/ocean/nonhydro)
branch.

```bash
# source whichever load script is appropriate
source load_dev_polaris_0.2.0_chrysalis_intel_openmpi_petsc.sh
git submodule update --init
cd E3SM-Project
git remote add scalandr/E3SM git@github.com:scalandr/E3SM.git
git worktree add ../nonhydro_chrys_intel_openmpi -b nonhydro_chrys_intel_openmpi \
    --checkout scalandr/E3SM/ocean/nonhydro
cd ../nonhydro_chrys_intel_openmpi
git submodule update --init --recursive
cd components/mpas-ocean
# this will build with PIO, Netlib LAPACK and PETSc
make ifort
polaris list | grep nonhydro
# update these numbers for the 2 nonhydro tasks
polaris setup -n 245 246 -p . \
    -w /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/nonhydro_chrys_intel_openmpi
cd /lcrc/group/e3sm/ac.xylar/polaris/test_20230202/nonhydro_chrys_intel_openmpi
sbatch job_script.custom.bash
```

As with non-PETSc MPAS-Ocean and MALI, you can have different worktrees with
Sara’s nonhydro branch for building with different compilers or use
[utils/matrix](https://github.com/E3SM-Project/polaris/tree/main/utils/matrix) to
build (and run).

## Deploying shared spack environments

:::{note}
Be careful about deploying shared spack environments, as changes you make
can affect other polaris users.
:::

Once polaris has been tested with the spack builds in a temporary location, it
is time to deploy the shared spack environments for all developers to use.
A `mache` developer will make a `mache` release (if needed) before this
step begins.  So there is no need to build mache from a remote branch anymore.

Polaris knows where to deploy spack on each machine because of the `spack`
config option specified in the `[deploy]` section of each machine's config
file, see the [machine configs](https://github.com/E3SM-Project/polaris/tree/main/polaris/machines).

It is best to update the remote polaris branch in case of changes:

```bash
cd simplify_local_mache
# get any changes
git fetch --all -p
# hard reset if there are changes
git reset –hard xylar/polaris/simplify_local_mache
```

### Deploy spack for polaris without Albany or PETSc

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --update_spack \
    --tmpdir ${TMPDIR} \
    --compiler intel intel gnu \
    --mpi openmpi impi openmpi \
    --recreate \
    --verbose
```

### Deploying spack with Albany

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --update_spack \
    --tmpdir ${TMPDIR} \
    --compiler gnu \
    --mpi openmpi \
    --with_albany \
    --recreate \
    --verbose
```

### Deploying spack with PETSc (and Netlib LAPACK)

```bash
export TMPDIR=/lcrc/group/e3sm/${USER}/spack_temp
./configure_polaris_envs.py \
    --conda ${CONDA_BASE} \
    --update_spack \
    --tmpdir ${TMPDIR} \
    --compiler intel gnu \
    --mpi openmpi \
    --with_petsc \
    --recreate \
    --verbose
```
