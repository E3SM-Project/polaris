(machines)=

# Machines

Polaris  attempts to be aware of the capabilities of the machine it is running
on.  This is a particular advantage for so-called "supported" machines with a
config file defined for them in the `polaris` package.  But even for "unknown"
machines, it is not difficult to set a few config options in your user config
file to describe your machine.  Then, polaris can use this data to make sure
tasks are configured in a way that is appropriate for your machine.

## config options

The config options typically defined for a machine are:

```cfg
# The paths section describes paths that are used within the ocean core test
# cases.
[paths]

# A shared root directory where MPAS standalone data can be found
database_root = /lcrc/group/e3sm/public_html/mpas_standalonedata

# the path to the base conda environment where polaris environments have
# been created
polaris_envs = /lcrc/soft/climate/polaris/chrysalis/base


# Options related to deploying a polaris conda environment on supported
# machines
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = intel

# the system MPI library to use for intel compiler
mpi_intel = openmpi

# the system MPI library to use for gnu compiler
mpi_gnu = openmpi

# the base path for spack environments used by polaris
spack = /lcrc/soft/climate/polaris/chrysalis/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
use_e3sm_hdf5_netcdf = True
```

The `paths` section provides local paths to the root of the "databases"
(local caches) of data files for each MPAS core.  These are generally in a
shared location for the project to save space.  Similarly, `polaris_envs`
is a location where shared conda environments will be created for polaris
releases for users to share.

The `deploy` section is used to help polaris create development and
release conda environments and activation scripts.  It says which compiler set
is the default, which MPI library is the default for each supported compiler,
and where libraries built with system MPI will be placed.

Some config options come from a package, [mache](https://github.com/E3SM-Project/mache/)
that is a dependency of polaris.  Mache is designed to detect and
provide a machine-specific configuration for E3SM supported machines.  Typical
config options provided by mache that are relevant to polaris are:

```cfg
# The parallel section describes options related to running jobs in parallel
[parallel]

# parallel system of execution: slurm, cobalt or single_node
system = slurm

# whether to use mpirun or srun to run a task
parallel_executable = srun

# cores per node on the machine
cores_per_node = 36

# account for running diagnostics jobs
account = e3sm

# quality of service (default is the first)
qos = regular, interactive
```

The `parallel` section defined properties of the machine, to do with parallel
runs. Currently, machine files are defined for high-performance computing (HPC)
machines with multiple nodes.  These machines all use {ref}`slurm` to submit
parallel jobs.  They also all use the `srun` command to run individual
tasks within a job.  The number of `cores_per_node` vary between machines,
as does the account that typical polaris users will have access to on the
machine.

(slurm)=

## Slurm job queueing

Most HPC systems now use the
[slurm workload manager](https://slurm.schedmd.com/documentation.html).
Here are some basic commands:

```bash
salloc -N 1 -t 2:0:0 # interactive job (see machine specific versions below)
sbatch script # submit a script
squeue # show all jobs
squeue -u <my_username> # show only your jobs
scancel jobID # cancel a job
```

(supported-machines)=

## Supported Machines

On each supported machine, users will be able to source a script to activate
the appropriate polaris environment and compilers.  Most machines support 2
compilers, each with one or more variants of MPI and the required NetCDF,
pNetCDF and SCORPIO libraries.  These scripts will first load the conda
environment for polaris, then it will load modules and set environment
variables that will allow you to build and run the MPAS model.

A table with the full list of supported machines, compilers, MPI variants,
and MPAS-model build commands is found in {ref}`dev-supported-machines` in
the Developer's Guide.  In the links below, we list only the commands needed
to use the default MPI variant for each compiler on each machine.

```{toctree}
:titlesonly: true

anvil
chicoma
chrysalis
compy
frontier
perlmutter
```

(other-machines)=

## Other Machines

If you are working on an "unknown" machine, you will need to define some of
the config options that would normally be in a machine's config file yourself
in your user config file:

```cfg
# This file contains some common config options you might want to set

# The paths section describes paths to databases and shared polaris environments
[paths]

# A root directory where MPAS standalone data can be found
database_root = /home/xylar/data/mpas/mpas_standalonedata

# The parallel section describes options related to running tasks in parallel
[parallel]

# parallel system of execution: slurm or single_node
system = single_node

# whether to use mpirun or srun to run the model
parallel_executable = mpirun -host localhost

# cores per node on the machine, detected automatically by default
# cores_per_node = 4
```

The paths for the MPAS core "databases" can be any emtpy path to begin with.
If the path doesn't exist, polaris will create it.

If you're not working on an HPC machine, you will probably not have multiple
nodes or {ref}`slurm`.  You will probably install
[MPICH](https://www.mpich.org/) or [OpenMPI](https://www.open-mpi.org/),
probably via a
[conda environment](https://docs.conda.io/projects/conda/en/latest/index.html).
In this case, the `parallel_executable` is `mpirun`.

To install the `polaris` package into a conda environment, you will first
need to install [Miniforge3](https://github.com/conda-forge/miniforge#miniforge3)
(if it is not already installed).  Then, you will run one of the following
three commands, depending on how you would like to handle MPI support in the
conda packages.

## MPICH

To create a conda environment called "polaris" with MPI from the `mpich`
package, run:

```bash
conda create -n polaris -c conda-forge -c e3sm/label/polaris python=3.10 "polaris=*=mpi_mpich*"
```

This is the recommended default for single-node Linux and OSX machines.

## OpenMPI

To create a conda environment called "polaris" with MPI from the `openmpi`
package, run:

```bash
conda create -n polaris -c conda-forge -c e3sm/label/polaris python=3.10 "polaris=*=mpi_openmpi*"
```

## No MPI from conda-forge

To create a conda environment called "polaris" without any MPI package from
conda-forge, run:

```bash
conda create -n polaris -c conda-forge -c e3sm/label/polaris python=3.10 "polaris=*=nompi*"
```

This would be the starting point for working with polaris on an unknown
HPC machine.  From there, you would also need to load modules and set
environment variables so that MPAS components can be built with system NetCDF,
pNetCDF and SCORPIO. This will likely require working with an MPAS developer.
