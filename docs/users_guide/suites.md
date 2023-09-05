(suites)=

# Suites

In polaris, suites are simply lists of tasks to be run together
in one operation.  One common reason for running a suite is to check for
changes in performance or output data compared with a previous run of the
same suite.  This type of
[regression testing](https://en.wikipedia.org/wiki/Regression_testing) is one
of the primary reasons that polaris exists. Another reason to define a test
suite is simply to make it easier to run a sequence of tasks (e.g. from
the same test group) that are often run together.

Suites are defined by their MPAS core and name.  As you can see by
running:

```bash
polaris list --suites
```

the current set of available suites is:

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

As an example, the ocean `nightly` suite includes the tasks used
for regression testing of MPAS-Ocean.  Here are the tasks included:

```none
ocean/baroclinic_channel/10km/threads
ocean/baroclinic_channel/10km/decomp
ocean/baroclinic_channel/10km/restart
ocean/inertial_gravity_wave/convergence

```

:::{note}
Some tasks have "cached" steps, meaning those steps (or the entire test
case if no specific steps are listed) aren't run but instead the results
of a previous run are simply downloaded.  This is used to skip steps that
are prohibitively time-consuming during regression testing, but where the
results are needed to run subsequent tasks.  An example above is the
`mesh` and `PHC/init` tasks from the `ocean/global_ocean/`
test group on the `QUwISC240` mesh.  These tasks take several minutes to
run, which is longer than we wish to take for a quick performance test,
so they are cached instead.
:::

Including the `-v` verbose argument to `polaris list --suites` will
print the tasks belonging to each given suite.
