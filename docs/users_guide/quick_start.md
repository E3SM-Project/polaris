(quick-start)=

# Quick Start for Users

:::{admonition} Quick Start for Users is not yet valid
There has not yet been a release of polaris.  We will update this
documentation as soon as there is one.  Until then please refer to the
{ref}`dev-quick-start`.
:::

(conda-env)=

## Loading polaris conda and spack environments

### E3SM supported machines

For each polaris release, we maintain a
[conda environment](https://docs.conda.io/en/latest/). that includes the
`polaris` package as well as all of its dependencies and some libraries
(currently [ESMF](https://earthsystemmodeling.org/),
[MOAB](https://sigma.mcs.anl.gov/moab-library/) and
[SCORPIO](https://e3sm.org/scorpio-parallel-io-library/)) built with system
MPI using [spack](https://spack.io/) on our standard machines (Anvil, Chicoma,
Chrysalis, Compy, and  Perlmutter).  Once there is a polaris release,
these will be the commands to load the environments and set you up for building
the desired E3SM component (MPAS-Ocean, MALI or Omega):

- Anvil (Blues):

```bash
source /lcrc/soft/climate/polaris/anvil/load_latest_polaris.sh
```

- Chicoma (CPU nodes):

```bash
source /usr/projects/climate/SHARED_CLIMATE/polaris/chicoma-cpu/load_latest_polaris.sh
```

- Chrysalis:

```bash
source /lcrc/soft/climate/polaris/chrysalis/load_latest_polaris.sh
```

- Compy:

```bash
source /share/apps/E3SM/conda_envs/polaris/load_latest_polaris.sh
```

- Perlmutter (CPU nodes):

```bash
source /global/cfs/cdirs/e3sm/software/polaris/pm-cpu/load_latest_polaris.sh
```

These same paths (minus `load_latest_polaris.sh`) also will have load scripts
for  the latest version of polaris with all the supported compiler and MPI
combinations.  For example, on Anvil, you will be able to get an environment
appropriate for building E3SM components with Gnu compilers and OpenMPI using:

```bash
source /lcrc/soft/climate/polaris/anvil/load_latest_polaris_gnu_openmpi.sh
```

### Other machines

Once it is released, you will be able to install polaris from a conda package.
To install your own polaris conda environment on non-E3SM-supported machines,
first, install [Miniforge3](https://github.com/conda-forge/miniforge#miniforge3)
if you don't already have it.  Then, create a new conda environment (called
`polaris` in this example) as follows:

```bash
conda create -n polaris -c conda-forge -c e3sm/label/polaris python=3.11 \
    "polaris=*=mpi_mpich*"
```

This will install the version of the package with MPI from conda-forge's MPICH
package.  If you want OpenMPI, use `"polaris=*=mpi_openmpi*"` instead.  If
you do not want MPI from conda-forge (e.g. because you are working with a
system with its own MPI), use `"polaris=*=nompi*"`

To get a specific version of polaris, you can instead run:

```bash
conda create -n polaris -c conda-forge -c e3sm/label/polaris python=3.11 \
    "polaris=1.0.0=mpi_mpich*"
```

That is, you will replace `polaris=*` with `polaris=1.0.0`.

Then, you will need to create a load script to activate the conda environment
and set some environment variables. In a directory where you want to store the
script, run:

```bash
conda activate polaris
create_polaris_load_script
```

From then on, each time you want to set up tasks or suites with polaris
or build MPAS components, you will need to source that load script, for
example:

```bash
source load_polaris_1.0.0_mpich.sh
```

When you set up tasks, a link called `load_polaris_env.sh` will be added to
each task or suite work directory.  To run the tasks, you may find it
more convenient to source that link instead of finding the path to the original
load script.

(build-components)=

## Building supported E3SM components as standalone models

You will need to check out a branch of E3SM to build one of the supported
components.

Typically, for MPAS-Ocean, you will clone
[E3SM](https://github.com/E3SM-Project/E3SM), for Omega, you will clone
[Omega](https://github.com/E3SM-Project/Omega), and for MALI, you will clone
[MALI-Dev](https://github.com/MALI-Dev/E3SM).

To build MPAS-Ocean, first source the appropriate load script (see
{ref}`conda-env`) then run:

```bash
cd components/mpas-ocean
git submodule update --init --recursive
make <mpas_make_target>
```

Omega is still in the early stages of development to the appropriate commands
have not yet been determined for building it.

MALI can be compiled with or without the Albany library that contains the
first-order velocity solver.  The Albany first-order velocity solver is the
only velocity option that is scientifically validated, but the Albany library
is only available with Gnu compilers.  In some situations it is
desirable to compile without Albany to run basic tasks.  This basic mode for
MALI can be compiled similarly to MPAS-Ocean.  Again, first source the
appropriate load script (see {ref}`conda-env`) then run:

```bash
cd components/mpas-albany-landice
git submodule update --init --recursive
make [ALBANY=true] <mpas_make_target>
```

where `ALBANY=true` is included if you want to compile with Albany support
and excluded if you do not.  Some more information on building and running
MALI is available at
[https://github.com/MALI-Dev/E3SM/wiki](https://github.com/MALI-Dev/E3SM/wiki).

See the last column of the table in {ref}`dev-supported-machines` for the right
`<mpas_make_target>` command for each machine and compiler.

(setup-overview)=

## Setting up tasks

Before you set up a task with polaris, you will need to build the
MPAS component you wish to test with, see {ref}`build-components` above.

If you have not already done so, you will need to source the appropriate load
script, see {ref}`conda-env`.

To see all available tasks you can set up in polaris, run:

```bash
polaris list
```

and you get output like this:

```none
0: landice/circular_shelf/decomposition_test
1: landice/dome/2000m/sia_smoke_test
2: landice/dome/2000m/sia_decomposition_test
3: landice/dome/2000m/sia_restart_test
4: landice/dome/2000m/fo_smoke_test
5: landice/dome/2000m/fo_decomposition_test
6: landice/dome/2000m/fo_restart_test
7: landice/dome/variable_resolution/sia_smoke_test
8: landice/dome/variable_resolution/sia_decomposition_test
9: landice/dome/variable_resolution/sia_restart_test
...
```

The list is long, so it will likely be useful to `grep` for particular
content:

```bash
polaris list | grep baroclinic_channel
```

```none
32: ocean/baroclinic_channel/1km/rpe
33: ocean/baroclinic_channel/4km/rpe
34: ocean/baroclinic_channel/10km/rpe
35: ocean/baroclinic_channel/10km/decomp
36: ocean/baroclinic_channel/10km/default
37: ocean/baroclinic_channel/10km/restart
38: ocean/baroclinic_channel/10km/threads
```

See {ref}`dev-polaris-list` for more information.

To set up a particular task, you can either use the full path of the
task:

```bash
polaris setup -t ocean/global_ocean/QU240/mesh -w <workdir> -p <component_path>
```

or you can replace the `-t` flag with the simple shortcut: `-n 15`.  You
can set up several tasks at once by passing test numbers separated by
spaces: `-n 15 16 17`.  See {ref}`dev-polaris-setup` for more details.

Here, `<workdir>` is a path, usually to your scratch space. For example, on
Chrysalis at LCRC, you might use:

```bash
-w /lcrc/group/e3sm/$USER/runs/210131_test_new_branch
```

The placeholder `<component_path>` is the relative or absolute path where the
E3SM  component has been built (the directory, not the executable itself; see
{ref}`machines`).  You will typically want to provide a path either with `-p`
or in a config file (see below) because the default paths are only useful for
developers running out of the polaris repository.

You can explicitly specify a supported machine with `-m <machine>`. You can
run:

```bash
polaris list --machines
```

to see what machines are currently supported. If you omit the `-m` flag,
polaris will try to automatically detect if you are running on a supported
machine and will fall back to a default configuration if no supported machine
is detected.

You may point to a config file with `-f`:

```bash
polaris setup -t ocean/global_ocean/QU240/mesh -f my_config.cfg -w <workdir>
```

to specify config options that override the defaults from polaris as a
whole, individual testcases, or machines.  If you are working on a supported
machine and you used `-p` to point to the MPAS build you want to use, you do
not need a config file.

If you are not on one of the supported machines, you will need to create a
config file like in this example. See also
[this example](https://github.com/E3SM-Project/polaris/blob/main/example.cfg)
in the repository.

```cfg
# This file contains some common config options for machines that polaris
# doesn't recognize automatically

# The paths section describes paths where files are automatically downloaded
[paths]

# A root directory where data for polaris tasks can be downloaded. This
# data will be cached for future reuse.
database_root = </path/to/root>/polaris/data

# The parallel section describes options related to running tasks in parallel
[parallel]

# parallel system of execution: slurm or single_node
system = single_node

# whether to use mpirun or srun to run the model
parallel_executable = mpirun -host localhost

# total cores on the machine (or cores on one node if it is a multinode
# machine), detected automatically by default
# cores_per_node = 4
```

The `database_root` directory can point to a location where you would like to
download data for MALI, MPAS-Seaice, MPAS-Ocean and Omega.  This data is
downloaded  only once and cached for the next time you call `polaris setup` or
`polaris suite` (see below).

The `cores_per_node` config option will default to the number of CPUs on your
computer.  You can set this to a smaller number if you want polaris to
use fewer cores.

In order to run regression testing that compares the output of the current run
with that from a previous polaris run, use `-b <previous_workdir>` to specify
a "baseline".

When you set up one or more tasks, they will also be included in a custom
suite, which is called `custom` by default.  (You can give it another
name with the `--suite_name` flag.)  You can run all the tasks in
sequence with one command as described in {ref}`suite-overview` or run them
one at a time as follows.

If you want to copy the MPAS executable over to the work directory, you can
use the `--copy_executable` flag or set the config option
`copy_executable = True` in the `[setup]` section of your user config
file.  One use of this capability for polaris simulations that are used in
a paper.  In that case, it would be better to have a copy of the executable
that will not be changed even if the E3SM branch is modified, recompiled or
deleted.  Another use might be to maintain a long-lived baseline test.
Again, it is safer to have the executable used to produce the baseline
preserved.

## Running a task

After compiling the code and setting up a task, you can log into an
interactive node (see {ref}`supported-machines`), load the required conda
environment and modules, and then

```bash
cd <workdir>/<test_subdir>
source load_polaris_env.sh
polaris serial
```

The `<workdir>` is the same path provided to the `-w` flag above.  The
sequence of subdirectories (`<test_subdir>`) is the same as given when you
list the tasks.  If the task was set up properly, the directory
should contain a file `task.pickle` that contains the information
polaris needs to run the task.  The load script
`load_polaris_env.sh` is a link to whatever load script you sourced before
setting up the task (see {ref}`conda-env`).

## Running with a job script

Alternatively, on supported machines, you can run the task or suite with
a job script generated automatically during setup, for example:

```bash
cd <workdir>/<test_subdir>
sbatch job_script.sh
```

You can edit the job script to change the wall-clock time (1 hour by default)
or the number of nodes (scaled according to the number of cores require by the
tasks by default).

```bash
#!/bin/bash
#SBATCH  --job-name=polaris
#SBATCH  --account=condo
#SBATCH  --nodes=5
#SBATCH  --output=polaris.o%j
#SBATCH  --exclusive
#SBATCH  --time=1:00:00
#SBATCH  --qos=regular
#SBATCH  --partition=acme-small


source load_polaris_env.sh
polaris serial
```

You can also use config options, passed to `polaris suite` or
`polaris setup` with `-f` in a user config file to control the job script.
The following are the config options that are relevant to job scripts:

```cfg
# The parallel section describes options related to running jobs in parallel
[parallel]

# account for running diagnostics jobs
account = condo

# Config options related to creating a job script
[job]

# the name of the parallel job
job_name = polaris

# wall-clock time
wall_time = 1:00:00

# The job partition to use, by default, taken from the first partition (if any)
# provided for the machine by mache
partition = acme-small

# The job quality of service (QOS) to use, by default, taken from the first
# qos (if any) provided for the machine by mache
qos = regular

# The job constraint to use, by default, taken from the first constraint (if
# any) provided for the  machine by mache
constraint =
```

(suite-overview)=

## Suites

Polaris includes several suites of tasks for code regressions and
bit-for-bit testing, as well as simply to make it easier to run several test
cases in one call. They can be listed with:

```bash
polaris list --suites
```

The output is:

```none
Suites:
  -c landice -t fo_integration
  -c landice -t full_integration
  -c landice -t sia_integration
  -c ocean -t cosine_bell_cached_init
  -c ocean -t ec30to60
  -c ocean -t ecwisc30to60
  -c ocean -t nightly
  -c ocean -t pr
  -c ocean -t qu240_for_e3sm
  -c ocean -t quwisc240
  -c ocean -t quwisc240_for_e3sm
  -c ocean -t sowisc12to60
  -c ocean -t wc14
```

You can set up a suite as follows:

```bash
polaris suite -c ocean -t nightly -w <workdir> -p <component_path>
```

where the details are similar to setting up a case. You can use the same
config file (e.g. `-f ocean.cfg`) and you can specify a "baseline" with
`-b <previous_workdir>` for regression testing of the output compared with a
previous run of the `nightly` suite. See {ref}`dev-polaris-suite` for more
on this command.

To run the regression suite, log into an interactive node, load your modules,
and

```bash
cd <workdir>
source load_polaris_env.sh
polaris serial [nightly]
```

In this case, you can specify the name of the suite to run.  This is required
if there are multiple suites in the same `<workdir>`.  You can optionally
specify a suite like `polaris serial [suitename].pickle`, which is convenient
for tab completion on the command line. The load script
`load_polaris_env.sh` is a link to whatever load script you sourced before
setting up the task (see {ref}`conda-env`).
