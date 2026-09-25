(suites)=

# Suites

In polaris, suites are simply lists of tasks to be run together
in one operation.  One common reason for running a suite is to check for
changes in performance or output data compared with a previous run of the
same suite.  This type of
[regression testing](https://en.wikipedia.org/wiki/Regression_testing) is one
of the primary reasons that polaris exists. Another reason to define a test
suite is simply to make it easier to run a sequence of tasks that are often run
together.

Suites are defined by their MPAS core and name.  As you can see by
running:

```bash
polaris list --suites
```

the current set of available suites is:

```none
Suites:
  -c ocean -t cosine_bell
  -c ocean -t cosine_bell_cached_init
  -c ocean -t nightly
  -c ocean -t pr
```

As an example, the ocean `nightly` suite includes the tasks used
for regression testing of MPAS-Ocean.  Here are the tasks included:

```none
ocean/planar/baroclinic_channel/10km/threads
ocean/planar/baroclinic_channel/10km/decomp
ocean/planar/baroclinic_channel/10km/restart
ocean/planar/inertial_gravity_wave
```

:::{note}
Some tasks have "cached" steps, meaning those steps (or the entire test
case if no specific steps are listed) aren't run but instead the results
of a previous run are simply downloaded.  This is used to skip steps that
are prohibitively time-consuming during regression testing, but where the
results are needed to run subsequent tasks.  An example in the 
`cosine_bell_cached_init` suite listed above is the
`spherical/icos/cosine_bell` and `spherical/qu/cosine_bell` 
tasks from the `ocean` component.  These tasks take several minutes to
create their meshes and initial conditions, so to speed things up we sometimes
run with cached meshes and initial conditions.
:::

Including the `-v` verbose argument to `polaris list --suites` will
print the tasks belonging to each given suite.

(suites-results)=

## Results

When you run a suite with `polaris serial`, a line for each task is written to
the terminal and output from each task goes to a log file in `case_outputs`.
Polaris also writes `<suite_name>_results.json` in the base work directory,
for scripts and dashboards to read. Running a single task from its work
directory writes `task_results.json` there instead.

The file lists every task in the order they run, with:

- `status`: `pass`, `fail`, or `pending` if the task has not finished
- `execution`: whether the steps ran without error (`pass` or `fail`)
- `baseline`: `pass` or `fail`, or `null` if there was no baseline comparison
- `elapsed_seconds`: the task's wall-clock time
- `steps_to_run`: the steps the task ran
- `log`: the task's log file, relative to the base work directory
- `baseline_diffs`: the largest l1, l2 and l_infinity norms of the difference
  from the baseline for each variable that was compared

It also has a `summary` with the number of tasks that passed, failed or are
pending, the total `elapsed_seconds`, and `provenance` such as the Polaris
version, machine, compiler and build directory.

The file is rewritten after each task. `complete` is `false` until the suite
has finished, so if a job runs out of time, tasks that did not finish are
still listed as `pending`. `schema_version` changes if a field is removed or
its meaning changes.
