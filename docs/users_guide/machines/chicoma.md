(machine-chicoma)=

# Chicoma

[LANL IC overview and search](https://int.lanl.gov/hpc/institutional-computing/index.shtml)

[DST Calendar](http://hpccalendar.lanl.gov/) (within LANL network)

Information about Slurm:

- [Introduction to Slurm at LANL](https://hpc.lanl.gov/job-scheduling/index.html#JobScheduling-IntroductiontoSlurm)
- [Basic Slurm Guide for LANL HPC Users](https://hpc.lanl.gov/job-scheduling/basic-slurm-guide-for-lanl-hpc-users.html)
- [Slurm Command Summary](https://hpc.lanl.gov/job-scheduling/slurm-commands.html)
- [Slurm: Running Jobs on HPC Platforms](https://hpc.lanl.gov/job-scheduling/slurm-commands.html#SlurmCommands-SlurmJobSubmission)
- [example of batch scripts](https://hpc.lanl.gov/job-scheduling/basic-slurm-guide-for-lanl-hpc-users.html#BasicSlurmGuideforLANLHPCUsers-BatchScriptGenerator)

Machine specifications: [chicoma](https://hpc.lanl.gov/platforms/chicoma/index.html)
[turquoise network](https://hpc.lanl.gov/networks/turquoise-network/index.html)

login: `ssh -t <username>@wtrw.lanl.gov ssh ch-fe`

File locations:

- small home directory, for start-up scripts only: `/users/<username>`
- home directory, backed up: `/usr/projects/climate/<username>`
- scratch space, not backed up: `/lustre/scratch4/turquoise/<username>` or
  `scratch5`

Check compute time:

- `sacctmgr list assoc user=<username> format=Cluster,Account%18,Partition,QOS%45`
- Which is my default account? `sacctmgr list user <username>`
- `sshare -a | head -2; sshare -a | grep $ACCOUNT | head -1`
- `sreport -t Hours cluster AccountUtilizationByUser start=2019-12-02 | grep $ACCOUNT`
- check job priority: `sshare -a | head -2; sshare -a | grep $ACCOUNT`
- [LANL Cluster Usage Overview](https://hpcinfo.lanl.gov) (within LANL yellow)

Check disk usage:

- your home space: `chkhome`
- total disk usage in Petabytes: `df -BP |head -n 1; df -BP|grep climate; df -BP |grep scratch`

Archiving

- [turquoise HPSS archive](https://hpc.lanl.gov/data/filesystems-and-storage-on-hpc-clusters/hpss-data-archive/index.html)
- archive front end: `ssh -t <username>@wtrw.lanl.gov ssh ar-tn`
- storage available at: `cd /archive/<project_name>`
- you can just copy files directly into here for a particular project.

LANL uses slurm. To obtain an interactive node:

```bash
salloc -N 1 -t 2:0:0 --qos=interactive
```

Use `--account=ACCOUNT_NAME` to change to a particular account.

## Chicoma-CPU

Chicoma's CPU and GPU nodes have different configuration options and compilers.
We only support Chicoma-CPU at this time.

### config options

Here are the default config options added when you choose `-m chicoma-cpu`
when setting up tasks or a suite:

```cfg
# The paths section describes paths for data and environments
[paths]

# A shared root directory where polaris data can be found
database_root = /usr/projects/e3sm/polaris/

# the path to the base conda environment where polaris environments have
# been created
polaris_envs = /usr/projects/e3sm/polaris/chicoma-cpu/conda/base


# Options related to deploying a polaris conda and spack environments
[deploy]

# the compiler set to use for system libraries and MPAS builds
compiler = gnu

# the compiler to use to build software (e.g. ESMF and MOAB) with spack
software_compiler = gnu

# the system MPI library to use for gnu compiler
mpi_gnu = mpich

# the system MPI library to use for nvidia compiler
mpi_nvidia = mpich

# the base path for spack environments used by polaris
spack = /usr/projects/e3sm/polaris/chicoma-cpu/spack

# whether to use the same modules for hdf5, netcdf-c, netcdf-fortran and
# pnetcdf as E3SM (spack modules are used otherwise)
use_e3sm_hdf5_netcdf = True

# location of a spack mirror for polaris to use
spack_mirror = /usr/projects/e3sm/polaris/chicoma-cpu/spack/spack_mirror


# The parallel section describes options related to running jobs in parallel
[parallel]

# account for running diagnostics jobs
account =

# cores per node on the machine
cores_per_node = 128

# threads per core (set to 1 because trying to hyperthread seems to be causing
# hanging on perlmutter)
threads_per_core = 1

# quality of service
# overriding mache because the debug qos also requires --reservaiton debug,
# which polaris doesn't currently support
qos = standard


# Config options related to creating a job script
[job]

# The job partition to use
partition = standard

# The job quality of service (QOS) to use
qos = standard
```

Additionally, some relevant config options come from the
[mache](https://github.com/E3SM-Project/mache/) package:

```cfg
# The parallel section describes options related to running jobs in parallel
[parallel]

# parallel system of execution: slurm, pbs or single_node
system = slurm

# whether to use mpirun or srun to run a task
parallel_executable = srun

# cores per node on the machine
cores_per_node = 256

# available partition(s) (default is the first)
partitions = standard, gpu

# quality of service (default is the first)
qos = standard, debug


# Config options related to spack environments
[spack]

# whether to load modules from the spack yaml file before loading the spack
# environment
modules_before = False

# whether to load modules from the spack yaml file after loading the spack
# environment
modules_after = False
```

## Loading and running Polaris on Chicoma

Follow the developer's guide at {ref}`dev-machines` to get set up.  There are
currently no plans to support a different deployment strategy (e.g. a shared
environoment) for users.
