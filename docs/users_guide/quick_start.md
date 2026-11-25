(quick-start)=

# Quick Start for Users

There are two ways to get Polaris:

- **Install it from conda-forge** to set up and run tasks with a model you
  have already built, and to run tasks that need no model, such as building
  meshes and analyzing output.  This is described below.
- **Deploy it from a clone of the repository** with `./deploy.py` when you
  need to build MPAS-Ocean, Omega, MALI or MPAS-Seaice, or to change Polaris
  itself.  See {ref}`dev-quick-start`.

Polaris runs on Linux and macOS.

(conda-env)=

## Installing from conda-forge

The conda package is called `e3sm-polaris`.  The Python package and the
command it installs are both called `polaris`:

```bash
conda create -n polaris -c conda-forge e3sm-polaris
conda activate polaris
polaris --help
```

:::{note}
The conda-forge package named `polaris` is a different project, the client
for the Polaris Hub.  Both install a Python package called `polaris`, so they
cannot be installed in the same environment.
:::

(install-jigsaw)=

### JIGSAW, for tasks that build meshes

Tasks that build a mesh with [JIGSAW](https://github.com/dengwirda/jigsaw)
need JIGSAW and JIGSAW-Python.  They are not dependencies of `e3sm-polaris`,
because Polaris needs newer versions than conda-forge provides.  Instead,
[mache](https://docs.e3sm.org/mache/) builds them from source and installs
them into the active environment.

With your Polaris environment active, clone JIGSAW-Python at the version this
release of Polaris uses, then run `mache jigsaw install` from the directory
that contains the clone:

```bash
git clone https://github.com/dengwirda/jigsaw-python.git
git -C jigsaw-python checkout 46a26d38b27fcdd28be723c923ce677159d2b766
mache jigsaw install
```

Without JIGSAW, every other task still works.  A task that builds a JIGSAW
mesh fails when it runs, saying that JIGSAW needs to be installed.

(setup-overview)=

## Setting up tasks

To see the tasks you can set up, run:

```bash
polaris list
```

The list is long, so you will likely want to `grep` it:

```bash
polaris list | grep baroclinic_channel/10km
```

```none
  85: ocean/planar/baroclinic_channel/10km/default
  86: ocean/planar/baroclinic_channel/10km/decomp
  87: ocean/planar/baroclinic_channel/10km/restart
  88: ocean/planar/baroclinic_channel/10km/threads
  89: ocean/planar/baroclinic_channel/10km/rpe
```

See {ref}`dev-polaris-list` for more.  To set up a task, give its path (or
its number with `-n`), a work directory, and the directory where the model was
built:

```bash
polaris setup -t ocean/planar/baroclinic_channel/10km/default \
    -w <workdir> -p <component_path> --model mpas-ocean
```

`<workdir>` is usually in your scratch space.  `<component_path>` is the
directory where the model was built, not the executable itself.  For ocean
tasks, `--model` chooses between `mpas-ocean` and `omega`.  An environment
installed from conda-forge cannot build a model, so if Polaris finds no model
in `<component_path>`, setup stops and says so.  See {ref}`dev-polaris-setup`
for all the options.

On a supported machine (see {ref}`machines`), Polaris recognizes the machine
by itself, or you can name it with `-m <machine>`.  Elsewhere, give Polaris
a config file with `-f`:

```bash
polaris setup -t ocean/planar/baroclinic_channel/10km/default \
    -w <workdir> -p <component_path> --model mpas-ocean -f my_config.cfg
```

where `my_config.cfg` has at least:

```cfg
# The paths section describes paths where files are automatically downloaded
[paths]

# A root directory where data for polaris tasks can be downloaded. This
# data will be cached for future reuse.
database_root = </path/to/root>/polaris/data

# The parallel section describes options related to running tasks in parallel
[parallel]

# parallel system of execution: slurm, pbs or single_node
system = single_node

# whether to use mpirun or srun to run the model
parallel_executable = mpirun -host localhost

# total cores on the machine (or cores on one node if it is a multinode
# machine), detected automatically by default
# cores_per_node = 4
```

A config file can also override any config option of Polaris, a task or a
machine; see {ref}`config-files`.  To compare results with an earlier run,
give its work directory as a baseline with `-b <baseline_workdir>`.

(run-overview)=

## Running tasks

With your Polaris environment active, go to the task's work directory and
run it:

```bash
cd <workdir>/<task_subdir>
polaris serial
```

`polaris serial` runs the steps one after another.  `polaris parallel` runs
the steps that do not depend on each other at the same time, within the
cores and nodes you have; see {ref}`dev-polaris-serial` and
{ref}`dev-polaris-parallel`.

On machines with Slurm or PBS, setup also writes `job_script.sh`, which you
can submit (for example with `sbatch job_script.sh`) instead.  Options for the
job script, such as the account and wall-clock time, go in the `[parallel]`
and `[job]` sections of your config file.

(suite-overview)=

## Suites

Polaris has suites of tasks for regression and bit-for-bit testing.  To list
them:

```bash
polaris list --suites
```

To set up a suite, give its component (`-c`) and name (`-t`), with the same
other flags as for a task:

```bash
polaris suite -c ocean -t omega_pr -w <workdir> -p <component_path> \
    --model omega
```

Then run it from the work directory, naming the suite if there is more than
one there:

```bash
cd <workdir>
polaris serial omega_pr
```

See {ref}`dev-polaris-suite` for more.
