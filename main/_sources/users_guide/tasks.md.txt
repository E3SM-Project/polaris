(tasks)=

# Tasks

Polaris currently supports tasks for the {ref}`mesh`, {ref}`e3sm-init`,
{ref}`ocean` ([MPAS-Ocean](https://mpas-dev.github.io/ocean/ocean.html)) and
{ref}`seaice`
([MPAS-Seaice](https://mpas-dev.github.io/sea_ice/sea_ice.html)) components.
Land-ice support is planned but has not yet been migrated.
Tasks are grouped under these components and then into common categories for
convenience and shared framework.  These groupings of tasks have some common
purpose or concept. For ocean, this includes "idealized" tasks like
{ref}`ocean-baroclinic-channel` and {ref}`ocean-overflow`.

Idealized tasks typically use analytic functions to define their
topography, initial conditions and forcing data (i.e. boundary conditions),
whereas realistic tasks most often use data files for all for these.

Polaris tasks are made up of one or more steps.  These are the
smallest units of work in polaris. You can run an individual step on its own if
you like.  Currently, the steps in a task run in sequence but there are
plans to allow steps that don't depend on one another to run in parallel in the
future.  Also, there is no requirement that all steps defined in a task
must run when that task is run.  Some steps may be disabled depending on
config options (see {ref}`config-files`) that you choose.  Other steps, such
as plotting or other forms of analysis, may be intended for you to run them
manually if you want to see the plots.

In polaris, tasks are identified by their subdirectory relative to a base
work directory that you choose during `polaris setup`.  For example, the
default task from the {ref}`ocean-baroclinic-channel` configuration at
10-km resolution is identified as:

```none
ocean/planar/baroclinic_channel/10km/default
```

When you list tasks:

```bash
polaris list
```

you will see these relative paths.
