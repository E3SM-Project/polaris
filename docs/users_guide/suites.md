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

(debug-suites)=

## Suites that default to the debug queue

Pull-request review is time-sensitive, so a few suites default to the machine's
**debug** queue, partition, or QOS (whichever the machine provides) to get
faster turnaround.  By default these are the `omega_pr` and `mpaso_pr` suites,
controlled by the `debug_suites` option in the `[job]` config section:

```cfg
[job]

# a comma-separated list of suites that default to the machine's debug
# queue/partition/qos (if it has one) for fast PR-review turnaround; jobs too
# large for the debug node limit fall back to the machine's normal default
debug_suites = omega_pr, mpaso_pr
```

When you set up one of these suites on a machine that has a debug
queue/partition/qos, the suite's job script (`job_script.<suite>.sh`) is written
to use it, and its wall time is capped to the debug limit.  If the suite needs
more nodes than the debug queue allows, it automatically falls back to the
machine's normal default queue.  Machines without a debug queue are unaffected.

You can add your own suites to this list (or remove the defaults) by overriding
`debug_suites` in a user config file passed to `polaris suite`.
