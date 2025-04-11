(machine-anvil)=

# Anvil

Anvil is a set of nodes used by E3SM and its "ecosystem" projects on
`blues` at [LCRC](https://www.lcrc.anl.gov/).  To gain access to the
machine, you will need access to E3SM's confluence pages or the equivalent for
your ecosystem project.

## config options

Here are the default config options added when Anvil is automatically detected
or when you choose `-m anvil` when setting up tasks or a suite:

```cfg
# The paths section describes paths for data and environments
[paths]

# A shared root directory where polaris data can be found
database_root = /lcrc/group/e3sm/public_html/polaris

# the path to the base conda environment where polars environments have
# been created
polaris_envs = /lcrc/soft/climate/polaris/anvil/base


# Options related to deploying a polaris conda and spack environments
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = intel

# the system MPI library to use for intel compiler
mpi_intel = impi

# the system MPI library to use for gnu compiler
mpi_gnu = openmpi

# the base path for spack environments used by polaris
spack = /lcrc/soft/climate/polaris/anvil/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
use_e3sm_hdf5_netcdf = True
```

Additionally, some relevant config options come from the
[mache](https://github.com/E3SM-Project/mache/) package:

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
account = condo

# available partition(s) (default is the first)
partitions = acme-small, acme-medium, acme-large

# quality of service (default is the first)
qos = regular, acme_high
```

## Loading and running Polaris on Anvil

Follow the developer's guide at {ref}`dev-machines` to get set up.  There are
currently no plans to support a different deployment strategy (e.g. a shared
environoment) for users.
