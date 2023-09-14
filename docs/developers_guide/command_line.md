(dev-command-line)=

# Command-line interface

The command-line interface for polaris acts essentially like 4 independent
scripts: `polaris list`, `polaris setup`, `polaris suite`, and 
`polaris serial`.  These are the primary user interface to the package, as 
described below.

When the `polaris` package is installed into your conda environment, you can
run these commands as above.  If you are developing polaris from a local
branch off of <https://github.com/E3SM-Project/polaris>, you will need to create a
conda environment appropriate for development (see {ref}`dev-conda-env`).
If you do, polaris will be installed in the environment in "development"
mode, meaning you can make changes to the branch and they will be reflected
when you call the `polaris` command-line tool.

(dev-polaris-list)=

## polaris list

The `polaris list` command is used to list tasks, suites, and
supported machines.  The command-line options are:

```none
$ polaris list --help
usage: polaris list [-h] [-t TASK] [-n NUMBER] [--machines] [--suites] [-v]
```

By default, all tasks are listed:

```none
$ polaris list
Tasks:
   0: ocean/planar/baroclinic_channel/10km/default
   1: ocean/planar/baroclinic_channel/10km/decomp
...
```

The number of each task is displayed, followed by the relative path that
will be used for the task in the work directory.

The `-h` or `--help` options will display the help message describing the
command-line options.

The `-t` or `--task_expr` flag can be used to supply a substring or regular
expression that can be used to list a subset of the tasks.  Think of this as
as search expression within the default list of task relative paths.

The flags `-n` or `--number` are used to list the name (relative path) of
a single task with the given number.

Instead of listing tasks, you can list all the supported machines that can
be passed to the `polaris setup` and `polaris suite` by using the
`--machines` flag.

Similarly, you can list all the available suites for all 
{ref}`dev-components` by using the `--suites` flag.  The result are the flags 
that would be passed  to `polaris suite` as part of setting up this suite.

The `-v` or `--verbose` flag lists more detail about each task,
including its description, short name, core, configuration, subdirectory within
the configuration and the names of its steps:

```none
$ polaris list -n 0 -v
path:          ocean/planar/baroclinic_channel/10km/default
name:          default
component:     ocean
subdir:        planar/baroclinic_channel/10km/default
steps:
 - init:    ocean/planar/baroclinic_channel/10km/init
 - forward: ocean/planar/baroclinic_channel/10km/default/forward
 - viz:     ocean/planar/baroclinic_channel/10km/default/viz
```

See {ref}`dev-list` for more about the underlying framework.

(dev-polaris-setup)=

## polaris setup

The `polaris setup` command is used to set up one or more tasks.

:::{note}
You must have built the executable for the standalone MPAS component you
want to run before setting up a polaris task.
:::

The command-line options are:

```none
$ polaris setup --help
usage: polaris setup [-h] [-t PATH] [-n NUM [NUM ...]] [-f FILE] [-m MACH] -w
                     PATH [-b PATH] [-p PATH] [--suite_name SUITE]
                     [--cached STEP [STEP ...]] [--copy_executable] [--clean]

```

The `-h` or `--help` options will display the help message describing the
command-line options.

The tasks to set up can be specified either by relative path or by number.
The `-t` or `--task` flag is used to pass the relative path of the task
within the resulting work directory.  The is the path given by
{ref}`dev-polaris-list`.  Only one task at a time can be supplied to
`polaris setup` this way.

Alternatively, you can supply the task numbers of any number of tasks to
the `-n` or `--task_number` flag.  Multiple test numbers are separated by
spaces.  These are the test numbers  given by {ref}`dev-polaris-list`.

`polaris setup` requires a few basic pieces of information to be able to set
up a task.  These include places to download and cache some data files
used in the tasks and the location where you built the MPAS model.  There
are a few ways to to supply these.  The `-m` -r `--machine` option is used
to tell `polaris setup` which supported machine you're running on (leave this
off if you're working on an "unknown" machine).  See {ref}`dev-polaris-list`
above for how to list the supported machines.

You can supply the directory where you have built the MPAS component with the
`-p` or `--component_path` flag.  This can be a relative or absolute path.  The
default for the `landice` component is 
`e3sm_submodules/MALI-Dev/components/mpas-albany-landice`
and the default for the `ocean` component depends on whether you are using
MPAS-Ocean or OMEGA.  For MPAS-Ocean, it is
`e3sm_submodules/E3SM-Project/components/mpas-ocean`.  For OMEGA, it is
`e3sm_submodules/Omega/components/omega`

You can also supply a config file with config options pointing to the
directories for cached data files, the location of the MPAS component, and much
more (see {ref}`config-files` and {ref}`setup-overview`).  Point to your config
file using the `-f` or `--config_file` flag.

The `-w` or `--work_dir` flags point to a relative or absolute path that
is the base path where the task(s) should be set up.  It is required that 
you supply a work directory, and we recommend not using the polaris repo itself
but instead use a temp or scratch directory to avoid confusing the polaris code
with tasks setups and output within the branch.

To compare tasks with a previous run of the same tasks, use the
`-b` or `--baseline_dir` flag to point to the work directory of the
previous run.  Many tasks validate variables to make sure they are
identical between runs, compare timers to see how much performance has changed,
or both.  See {ref}`dev-validation`.

The tasks will be included in a "custom" suite in the order they are
named or numbered.  You can give this suite a name with `--suite_name` or
leave it with the default name `custom`.  You can run this suite with
`polaris serial [suite_name]` as with the predefined suites (see
{ref}`dev-polaris-suite`).

Tasks within the custom suite are run in the order they are supplied to
`polaris setup`, so keep this in mind when providing the list.  Any test
cases that depend on the output of other tasks must run after their
dependencies.

You can uses `--cached` to specify steps of a test case to download from
pre-generated files if they are available (see {ref}`dev-polaris-cache`.)

If you specify `--copy_executable`, the model executable will be copied to the 
work directory rather than just symlinked.  This is useful if wish to run
the tasks again later but anticipate that you may have removed (or replaced)
the model code.

Finally, if you specify `--clean`. The base work directory pointed to with the
`-w` flag will be deleted before setting up the tasks.  This is useful if you
want to do a fresh run, since polaris will not rerun steps that have already
been run.

See {ref}`dev-setup` for more about the underlying framework.

(dev-polaris-suite)=

## polaris suite

The `polaris suite` command is used to set up a suite. The command-line
options are:

```none
$ polaris suite --help
usage: polaris suite [-h] -c COMPONENT -t SUITE [-f FILE] [-m MACH] [-b PATH]
                     -w PATH [-p PATH] [--copy_executable] [--clean]
```

The `-h` or `--help` options will display the help message describing the
command-line options.

The required argument are `-c` or `--component`, one of the {ref}`dev-components`,
where the suite and its tasks reside; and `-t` or `--test_suite`,
the name of the suite.  These are the options listed when you run
`polaris list --suites`. As with {ref}`dev-polaris-setup`, you must supply a 
work directory with `-w` or `--work_dir`.

As in {ref}`dev-polaris-setup`, you can supply one or more of: a supported
machine with `-m` or `--machine`; a path where you build MPAS model via
`-p` or `--mpas_model`; and a config file containing config options to
override the defaults with `-f` or `--config_file`.  As with
{ref}`dev-polaris-setup`, you may optionally supply a baseline directory for 
comparison with `-b` or `--baseline_dir`.  If supplied, each task in the 
suite that includes {ref}`dev-validation` will be validated against the 
previous run in the baseline.

The flags `--copy_executable`and `--clean` are the same as in 
{ref}`dev-polaris-setup`.

See {ref}`dev-suite` for more about the underlying framework.

(dev-polaris-run)=

## polaris serial

The `polaris serial` command is used to run (in sequence, as opposed to in task
parallel) a suite, task or step  that has been set up in the current
directory:

```none
$ polaris serial --help
usage: polaris serial [-h] [--steps STEPS [STEPS ...]]
                      [--skip_steps SKIP_STEPS [SKIP_STEPS ...]] [-q]
                      [--step_is_subprocess]
                      [suite]
```

Whereas other `polaris` commands are typically run in the local clone of the
polaris repo, `polaris serial` needs to be run in the appropriate work
directory. If you are running a suite, you may need to provide the name
of the suite if more than one suite has been set up in the same work
directory.  You can provide either just the suite name or
`<suite_name>.pickle` (the latter is convenient for tab completion).  If you
are in the work directory for a task or step, you do not need to provide
any arguments.

If you want to explicitly select which steps in a task you want to run,
you have two options.  You can either edit the `steps_to_run` config options
in the config file:

```cfg
[task]
steps_to_run = init full_run restart_run
```

Or you can use `--steps` to supply a list of steps to run, or `--skip_steps`
to supply a list of steps you do not want to run (from the defaults given in
the config file).  For example,

```none
polaris serial --steps init full_run
```

or

```none
polaris serial --skip_steps restart_run
```

Would both accomplish the same thing in this example -- skipping the
`restart_run` step of the task.

:::{note}
If changes are made to `steps_to_run` in the config file and `--steps`
is provided on the command line, the command-line flags take precedence
over the config option.
:::

To see which steps are are available in a given task, you need to run
{ref}`dev-polaris-list` with the `-v` or `--verbose` flag.

The `--step_is_subprocess` flag is for internal use by the framework so you
shouldn't need to use that flag.

See {ref}`dev-run` for more about the underlying framework.

(dev-polaris-cache)=

## polaris cache

Polaris supports caching outputs from any step in a special database
called `polaris_cache` (see {ref}`dev-step-input-download`). Files in this
database have a directory structure similar to the work directory (but without
the component subdirectory, which is redundant). The files include a date stamp
so that new revisions can be added without removing older ones (supported by
older polaris versions).  See {ref}`dev-step-cached-output` for more details.

The command `polaris cache` is used to update the file `cached_files.json` 
within a component.  This command is only available on Anvil and Chrysalis, 
since developers can only copy files from a Polaris work directory onto the 
LCRC server from these two machines.
```none
$ polaris cache --help
usage: polaris cache [-h] [-i STEP [STEP ...]] [-d DATE] [-r]
```

Developers run `polaris cache` from the base work directory, giving the 
relative paths of the step whose outputs should be cached:

```bash
polaris cache -i ocean/spherical/*/base_mesh/* \
    ocean/spherical/*/cosine_bell/init/*
```

This will:

1. copy the output files from the steps directories into the appropriate
   `polaris_cache` location on the LCRC server and
2. add these files to a local `ocean_cached_files.json` that can then be
   copied to `polaris/ocean` as part of a PR to add a cached version of a
   step.

The resulting `ocean_cached_files.json` will look something like:

```json
{
    "ocean/spherical/icos/base_mesh/120km/mesh.msh": "spherical/icos/base_mesh/120km/mesh.230914.msh",
    "ocean/spherical/icos/base_mesh/120km/base_mesh.nc": "spherical/icos/base_mesh/120km/base_mesh.230914.nc",
    "ocean/spherical/icos/base_mesh/120km/cellWidthVsLatLon.nc": "spherical/icos/base_mesh/120km/cellWidthVsLatLon.230914.nc",
    "ocean/spherical/icos/base_mesh/120km/graph.info": "spherical/icos/base_mesh/120km/graph.230914.info",
    "ocean/spherical/icos/base_mesh/240km/mesh.msh": "spherical/icos/base_mesh/240km/mesh.230914.msh",
    "ocean/spherical/icos/base_mesh/240km/base_mesh.nc": "spherical/icos/base_mesh/240km/base_mesh.230914.nc",
    "ocean/spherical/icos/base_mesh/240km/cellWidthVsLatLon.nc": "spherical/icos/base_mesh/240km/cellWidthVsLatLon.230914.nc",
    "ocean/spherical/icos/base_mesh/240km/graph.info": "spherical/icos/base_mesh/240km/graph.230914.info",
    "ocean/spherical/qu/cosine_bell/init/210km/initial_state.nc": "spherical/qu/cosine_bell/init/210km/initial_state.230914.nc",
    "ocean/spherical/qu/cosine_bell/init/240km/initial_state.nc": "spherical/qu/cosine_bell/init/240km/initial_state.230914.nc",
    "ocean/spherical/qu/cosine_bell/init/60km/initial_state.nc": "spherical/qu/cosine_bell/init/60km/initial_state.230914.nc",
    "ocean/spherical/qu/cosine_bell/init/90km/initial_state.nc": "spherical/qu/cosine_bell/init/90km/initial_state.230914.nc"
}
```

An optional flag `--date_string` lets the developer set the date string to
a date they choose.  The default is today's date.

The flag `--dry_run` can be used to sanity check the resulting `json` file
and the list of files printed to stdout without actually copying the files to
the LCRC server.

See {ref}`dev-cache` for more about the underlying framework.


(dev-mpas-to-yaml)=

## mpas_to_yaml

For convenience of translating from compass to polaris, we have added an 
`mpas_to_yaml` tool that can be used to convert a namelist and/or streams file 
into a yaml file.  You need to point to a namelist template (e.g. 
`namelist.ocean.forward` from the directory where you have built MPAS-Ocean) 
because the compass namelist files don't include the namelist sections, 
required by the yaml format.  Note that, for the `ocean` component, the `model`
is a keyword that will be added at the top of the yaml file but is ignored when
the yaml file gets parsed, so its value doesn't matter.  We recommend using
`omega` since the yaml file is in OMEGA's format, but it will also be usable
when the task is configured for MPAS-Ocean.
