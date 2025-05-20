(machine-compy)=

# CompyMcNodeFace

## config options

Here are the default config options added when CompyMcNodeFace is automatically
detected or when you choose `-m compy` when setting up tasks or a test
suite:

```cfg
# The paths section describes paths for data and environments
[paths]

# A shared root directory where polaris data can be found
database_root = /compyfs/polaris

# the path to the base conda environment where polaris environments have
# been created
polaris_envs = /share/apps/E3SM/polaris/conda/base


# Options related to deploying a polaris conda and spack environments
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = intel

# the system MPI library to use for intel compiler
mpi_intel = impi

# the system MPI library to use for gnu compiler
mpi_gnu = openmpi

# the base path for spack environments used by polaris
spack = /share/apps/E3SM/polaris/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
#
# We don't use them on Compy because hdf5 and netcdf were build without MPI
use_e3sm_hdf5_netcdf = False
```

Additionally, some relevant config options come from the
[mache](https://github.com/E3SM-Project/mache/) package:

```cfg
# The parallel section describes options related to running jobs in parallel
[parallel]

# parallel system of execution: slurm, cobalt or single_node
system = slurm

# whether to use mpirun or srun to run a task
parallel_executable = srun --mpi=pmi2

# cores per node on the machine
cores_per_node = 40

# account for running diagnostics jobs
account = e3sm

# available partition(s) (default is the first)
partitions = slurm

# quality of service (default is the first)
qos = regular
```

## Loading and running Polaris on CompyMcNodeFace

Follow the developer's guide at {ref}`dev-machines` to get set up.  There are
currently no plans to support a different deployment strategy (e.g. a shared
environoment) for users.
