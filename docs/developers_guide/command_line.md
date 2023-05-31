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

The `polaris list` command is used to list test cases, test suites, and
supported machines.  The command-line options are:

```none
polaris list [-h] [-t TEST] [-n NUMBER] [--machines] [--suites] [-v]
```

By default, all test cases are listed:

```none
$ polaris list
Testcases:
   0: examples/example_compact/1km/test1
   1: examples/example_compact/1km/test2
...
```

The number of each test case is displayed, followed by the relative path that
will be used for the test case in the work directory.

The `-h` or `--help` options will display the help message describing the
command-line options.

The `-t` or `--test_expr` flag can be used to supply a substring or regular
expression that can be used to list a subset of the tests.  Think of this as
as search expression within the default list of test-case relative paths.

The flags `-n` or `--number` are used to list the name (relative path) of
a single test case with the given number.

Instead of listing test cases, you can list all the supported machines that can
be passed to the `polaris setup` and `polaris suite` by using the
`--machines` flag.

Similarly, you can list all the available test suites for all 
{ref}`dev-components` by using the `--suites` flag.  The result are the flags 
that would be passed  to `polaris suite` as part of setting up this test suite.

The `-v` or `--verbose` flag lists more detail about each test case,
including its description, short name, core, configuration, subdirectory within
the configuration and the names of its steps:

```none
$ polaris list -n 0 -v
path:          examples/example_compact/1km/test1
description:   Tempate 1km test1
name:          test1
core:          examples
configuration: example_compact
subdir:        1km/test1
steps:
 - step1
 - step2
```

See {ref}`dev-list` for more about the underlying framework.

(dev-polaris-setup)=

## polaris setup

The `polaris setup` command is used to set up one or more test cases.

:::{note}
You must have built the executable for the standalone MPAS component you
want to run before setting up a polaris test case.
:::

The command-line options are:

```none
polaris setup [-h] -w PATH [-t PATH] [-n NUM [NUM ...]] [-f FILE] [-m MACH]
               [-b PATH] [-p PATH] [--suite_name SUITE]
```

The `-h` or `--help` options will display the help message describing the
command-line options.

The test cases to set up can be specified either by relative path or by number.
The `-t` or `--test` flag is used to pass the relative path of the test
case within the resulting work directory.  The is the path given by
{ref}`dev-polaris-list`.  Only one test case at a time can be supplied to
`polaris setup` this way.

Alternatively, you can supply the test numbers of any number of test cases to
the `-n` or `--case_number` flag.  Multiple test numbers are separated by
spaces.  These are the test numbers  given by {ref}`dev-polaris-list`.

`polaris setup` requires a few basic pieces of information to be able to set
up a test case.  These include places to download and cache some data files
used in the test cases and the location where you built the MPAS model.  There
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
is the base path where the test case(s) should be set up.  It is required that 
you supply a work directory, and we recommend not using the polaris repo itself
but instead use a temp or scratch directory to avoid confusing the polaris code
with test cases setups and output within the branch.

To compare test cases with a previous run of the same test cases, use the
`-b` or `--baseline_dir` flag to point to the work directory of the
previous run.  Many test cases validate variables to make sure they are
identical between runs, compare timers to see how much performance has changed,
or both.  See {ref}`dev-validation`.

The test cases will be included in a "custom" test suite in the order they are
named or numbered.  You can give this suite a name with `--suite_name` or
leave it with the default name `custom`.  You can run this test suite with
`polaris serial [suite_name]` as with the predefined test suites (see
{ref}`dev-polaris-suite`).

Test cases within the custom suite are run in the order they are supplied to
`polaris setup`, so keep this in mind when providing the list.  Any test
cases that depend on the output of other test cases must run after their
dependencies.

See {ref}`dev-setup` for more about the underlying framework.

(dev-polaris-suite)=

## polaris suite

The `polaris suite` command is used to set up a test suite. The command-line
options are:

```none
polaris suite [-h] -c COMPONENT -t SUITE -w PATH [-f FILE] [-v]
              [-m MACH] [-b PATH] [-p PATH]
```

The `-h` or `--help` options will display the help message describing the
command-line options.

The required argument are `-c` or `--component`, one of the {ref}`dev-components`,
where the test suite and its test cases reside; and `-t` or `--test_suite`,
the name of the test suite.  These are the options listed when you run
`polaris list --suites`. As with {ref}`dev-polaris-setup`, you must supply a 
work directory with `-w` or `--work_dir`.

As in {ref}`dev-polaris-setup`, you can supply one or more of: a supported
machine with `-m` or `--machine`; a path where you build MPAS model via
`-p` or `--mpas_model`; and a config file containing config options to
override the defaults with `-f` or `--config_file`.  As with
{ref}`dev-polaris-setup`, you may optionally supply a baseline directory for 
comparison with `-b` or `--baseline_dir`.  If supplied, each test case in the 
suite that includes {ref}`dev-validation` will be validated against the 
previous run in the baseline.

See {ref}`dev-suite` for more about the underlying framework.

(dev-polaris-run)=

## polaris serial

The `polaris serial` command is used to run (in sequence, as opposed to in task
parallel) a test suite, test case or step  that has been set up in the current
directory:

```none
polaris serial [-h] [--steps STEPS [STEPS ...]]
                 [--skip_steps SKIP_STEPS [SKIP_STEPS ...]]
                 [suite]
```

Whereas other `polaris` commands are typically run in the local clone of the
polaris repo, `polaris serial` needs to be run in the appropriate work
directory. If you are running a test suite, you may need to provide the name
of the test suite if more than one suite has been set up in the same work
directory.  You can provide either just the suite name or
`<suite_name>.pickle` (the latter is convenient for tab completion).  If you
are in the work directory for a test case or step, you do not need to provide
any arguments.

If you want to explicitly select which steps in a test case you want to run,
you have two options.  You can either edit the `steps_to_run` config options
in the config file:

```cfg
[test_case]
steps_to_run = initial_state full_run restart_run
```

Or you can use `--steps` to supply a list of steps to run, or `--skip_steps`
to supply a list of steps you do not want to run (from the defaults given in
the config file).  For example,

```none
polaris serial --steps initial_state full_run
```

or

```none
polaris serial --skip_steps restart_run
```

Would both accomplish the same thing in this example -- skipping the
`restart_run` step of the test case.

:::{note}
If changes are made to `steps_to_run` in the config file and `--steps`
is provided on the command line, the command-line flags take precedence
over the config option.
:::

To see which steps are are available in a given test case, you need to run
{ref}`dev-polaris-list` with the `-v` or `--verbose` flag.

See {ref}`dev-run` for more about the underlying framework.

(dev-polaris-cache)=

## polaris cache

`polaris` supports caching outputs from any step in a special database
called `polaris_cache` (see {ref}`dev-step-input-download`). Files in this
database have a directory structure similar to the work directory (but without
the component subdirectory, which is redundant). The files include a date stamp
so that new revisions can be added without removing older ones (supported by
older polaris versions).  See {ref}`dev-step-cached-output` for more details.

A new command, `polaris cache` has been added to aid in updating the file
`cached_files.json` within a component.  This command is only available on
Anvil and Chrysalis, since developers can only copy files from a polaris work
directory onto the LCRC server from these two machines.  Developers run
`polaris cache` from the base work directory, giving the relative paths of
the step whose outputs should be cached:

```bash
polaris cache -i ocean/global_ocean/QU240/mesh/mesh \
    ocean/global_ocean/QU240/PHC/init/initial_state
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
    "ocean/global_ocean/QU240/mesh/mesh/culled_mesh.nc": "global_ocean/QU240/mesh/mesh/culled_mesh.210803.nc",
    "ocean/global_ocean/QU240/mesh/mesh/culled_graph.info": "global_ocean/QU240/mesh/mesh/culled_graph.210803.info",
    "ocean/global_ocean/QU240/mesh/mesh/critical_passages_mask_final.nc": "global_ocean/QU240/mesh/mesh/critical_passages_mask_final.210803.nc",
    "ocean/global_ocean/QU240/PHC/init/initial_state/initial_state.nc": "global_ocean/QU240/PHC/init/initial_state/initial_state.210803.nc",
    "ocean/global_ocean/QU240/PHC/init/initial_state/init_mode_forcing_data.nc": "global_ocean/QU240/PHC/init/initial_state/init_mode_forcing_data.210803.nc"
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
when the test case is configured for MPAS-Ocean.
