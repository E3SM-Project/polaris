# Aurora

login: `ssh <username>@aurora.alcf.anl.gov`

interactive login:

```bash
qsub -I -A E3SM_Dec -q debug -l select=1 -l walltime=00:30:00 -l filesystems=home:flare
```

Here is a link to the
[Aurora User Guide](https://docs.alcf.anl.gov/aurora/)

## config options

Here are the default config options added when you have configured Polairs on
a Aurora login node (or specified `./configure_polaris_envs.py -m aurora`):

```cfg
# The paths section describes paths for data and environments
[paths]

# A shared root directory where polaris data can be found
database_root = /lus/flare/projects/E3SM_Dec/polaris

# the path to the base conda environment where polars environments have
# been created
polaris_envs = /lus/flare/projects/E3SM_Dec/soft/polaris/aurora/base


# Options related to deploying a polaris conda and spack environments
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = oneapi-ifx

# the compiler to use to build software (e.g. ESMF and MOAB) with spack
software_compiler = oneapi-ifx

# the system MPI library to use for oneapi-ifx compiler
mpi_oneapi_ifx = mpich

# the base path for spack environments used by polaris
spack = /lus/flare/projects/E3SM_Dec/soft/polaris/aurora/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
use_e3sm_hdf5_netcdf = False


# Config options related to creating a job script
[job]

# the filesystems used for the job
filesystems = home:flare
```

Additionally, some relevant config options come from the
[mache](https://github.com/E3SM-Project/mache/) package:

```cfg
# The parallel section describes options related to running jobs in parallel
[parallel]

# parallel system of execution: slurm, pbs or single_node
system = pbs

# whether to use mpirun or srun to run a task
parallel_executable = mpirun

# cores per node on the machine (with hyperthreading)
cores_per_node = 208

# account for running diagnostics jobs
account = E3SM_Dec

# queues (default is the first)
queues = prod, debug

# Config options related to spack environments
[spack]

# whether to load modules from the spack yaml file before loading the spack
# environment
modules_before = False

# whether to load modules from the spack yaml file after loading the spack
# environment
modules_after = False
```

## Loading and running Polaris on Aurora

Follow the developer's guide at {ref}`dev-machines` to get set up.  There are
currently no plans to support a different deployment strategy (e.g. a shared
environoment) for users.

