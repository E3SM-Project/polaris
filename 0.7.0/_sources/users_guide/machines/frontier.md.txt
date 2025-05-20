# Frontier

login: `ssh <username>@frontier.olcf.ornl.gov`

interactive login:

```bash
# for CPU:
salloc -A cli115 --partition=batch --nodes=1 --time=30:00 -C cpu

# for GPU:
salloc -A cli115 --partition=batch --nodes=1 --time=30:00 -C gpu
```

Here is a link to the
[Frontier User Guide](https://docs.olcf.ornl.gov/systems/frontier_user_guide.html)

## config options

Here are the default config options added when you have configured Poaris on
a Frontier login node (or specified `./configure_polaris_envs.py -m frontier`):

```cfg
# The paths section describes paths for data and environments
[paths]

# A shared root directory where polaris data can be found
database_root = /lustre/orion/cli115/world-shared/polaris

# the path to the base conda environment where polaris environments have
# been created
polaris_envs = /ccs/proj/cli115/software/polaris/frontier/conda/base


# Options related to deploying a polaris conda and spack environments
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = gnu

# the compiler to use to build software (e.g. ESMF and MOAB) with spack
software_compiler = gnu

# the system MPI library to use for gnu compiler
mpi_gnu = mpich

# the system MPI library to use for gnugpu compiler
mpi_gnugpu = mpich

# the system MPI library to use for crayclang compiler
mpi_crayclang = mpich

# the system MPI library to use for crayclanggpu compiler
mpi_crayclanggpu = mpich

# the base path for spack environments used by polaris
spack = /ccs/proj/cli115/software/polaris/frontier/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
use_e3sm_hdf5_netcdf = True

# The parallel section describes options related to running jobs in parallel.
# Most options in this section come from mache so here we just add or override
# some defaults
[parallel]

# cores per node on the machine
cores_per_node = 64

# threads per core (set to 1 because hyperthreading requires extra sbatch
# flag --threads-per-core that polaris doesn't yet support)
threads_per_core = 1
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
cores_per_node = 64

# account for running diagnostics jobs
account = cli115

# available partition(s) (default is the first)
partitions = batch


# Config options related to spack environments
[spack]

# whether to load modules from the spack yaml file before loading the spack
# environment
modules_before = False

# whether to load modules from the spack yaml file after loading the spack
# environment
modules_after = False

# whether the machine uses cray compilers
cray_compilers = True
```

## Loading and running Polaris on Frontier

Follow the developer's guide at {ref}`dev-machines` to get set up.  There are
currently no plans to support a different deployment strategy (e.g. a shared
environoment) for users.

