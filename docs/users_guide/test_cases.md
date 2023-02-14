(test-cases)=

# Test Cases

Polaris supports test cases for two main components, {ref}`ocean`
([MPAS-Ocean](https://mpas-dev.github.io/ocean/ocean.html)) and
{ref}`landice` ([MALI](https://mpas-dev.github.io/land_ice/land_ice.html)).
Test cases are grouped under these components and then into "test groups",
which are groups of test cases that have some common purpose or concept.
Land-ice test groups include "idealized" setups like {ref}`landice-dome` and
{ref}`landice-hydro-radial` as well as "realistic" domains as in
{ref}`landice-greenland`.  The same is true for the ocean, with "idealized"
test groups like {ref}`ocean-baroclinic-channel` and {ref}`ocean-ziso`, and
a "realistic" test group in {ref}`ocean-global-ocean`.

Idealized test groups typically use analytic functions to define their
topography, initial conditions and forcing data (i.e. boundary conditions),
whereas realistic test groups most often use data files for all for these.

Polaris test cases are made up of one or more steps.  These are the
smallest units of work in polaris. You can run an individual step on its own if
you like.  Currently, the steps in a test case run in sequence but there are
plans to allow steps that don't depend on one another to run in parallel in the
future.  Also, there is no requirement that all steps defined in a test case
must run when that test case is run.  Some steps may be disabled depending on
config options (see {ref}`config-files`) that you choose.  Other steps, such
as plotting or other forms of analysis, may be intended for you to run them
manually if you want to see the plots.

In polaris, test cases are identified by their subdirectory relative to a base
work directory that you choose during `polaris setup`.  For example, the
default test case from the {ref}`ocean-baroclinic-channel` configuration at
10-km resolution is identified as:

```none
ocean/baroclinic_channel/10km/default
```

When you list test cases:

```bash
polaris list
```

you will see these relative paths.
