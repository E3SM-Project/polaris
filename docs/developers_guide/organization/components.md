(dev-components)=

# Components

Currently, there are two components, `ocean`, which encompasses all the tasks 
for MPAS-Ocean and OMEGA, and `seaice`, which implements tasks for MPAS-Seaice.

From a developer's perspective, a component is a package within polaris
that has four major pieces:

1. A class that descends from the {py:class}`polaris.Component` base class.
   The class is defined in `__init__.py` and its `__init__()` method
   calls the {py:meth}`polaris.Component.add_tasks()` method (or helper 
   functions that, in turn, call this method) to add tasks to the component.
2. A `tasks` package, which contains packages for individual tasks and their 
   steps, possibly within packages that help to sort them into broader 
   categories.
3. An `<component>.cfg` config file containing any default config options
   that are universal to all tasks of the component.
4. Additional "framework" packages and modules shared broadly between tasks.

The component's framework is a mix of shared code and other files (config 
files, YAML files for model config options, etc.) that is expected to be used 
only by modules and packages within the component, not by other components or 
the main polaris {ref}`dev-framework`.

## Constructor

The constructor (`__init__()` method) for a child class of
{py:class}`polaris.Component` simply calls the parent class' version
of the constructor with `super().__init__()`, passing the name of the 
component.  Then, it calls helper functions to add tasks to the component, as
in this example from {py:class}`polaris.ocean.Ocean`:

```python
from polaris import Component
from polaris.ocean.tasks.baroclinic_channel import add_baroclinic_channel_tasks
from polaris.ocean.tasks.cosine_bell import add_cosine_bell_tasks
from polaris.ocean.tasks.inertial_gravity_wave import (
    add_inertial_gravity_wave_tasks,
)
from polaris.ocean.tasks.manufactured_solution import (
    add_manufactured_solution_tasks,
)
from polaris.ocean.tasks.single_column import add_single_column_tasks


class Ocean(Component):
    """
    The collection of all test case for the MPAS-Ocean core
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')

        # please keep these in alphabetical order
        add_baroclinic_channel_tasks(component=self)
        add_cosine_bell_tasks(component=self)
        add_inertial_gravity_wave_tasks(component=self)
        add_manufactured_solution_tasks(component=self)
        add_single_column_tasks(component=self)
```

The object `self` is always passed as the `component` argument to the helper
function so it can, in turn, be used both to add the task to the component and
to identify which component the task belongs to in its constructor.

An example of a helper function that adds tasks for baroclinic channel test 
cases is:
```python
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.baroclinic_channel.decomp import Decomp
from polaris.ocean.tasks.baroclinic_channel.default import Default
from polaris.ocean.tasks.baroclinic_channel.init import Init
from polaris.ocean.tasks.baroclinic_channel.restart import Restart
from polaris.ocean.tasks.baroclinic_channel.rpe import Rpe
from polaris.ocean.tasks.baroclinic_channel.threads import Threads


def add_baroclinic_channel_tasks(component):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [10., 4., 1.]:
        resdir = resolution_to_subdir(resolution)
        resdir = f'planar/baroclinic_channel/{resdir}'

        init = Init(component=component, resolution=resolution, indir=resdir)

        component.add_task(
            Default(component=component, resolution=resolution,
                    indir=resdir, init=init))

        if resolution == 10.:
            component.add_task(
                Decomp(component=component, resolution=resolution,
                       indir=resdir, init=init))

            component.add_task(
                Restart(component=component, resolution=resolution,
                        indir=resdir, init=init))

            component.add_task(
                Threads(component=component, resolution=resolution,
                        indir=resdir, init=init))

        component.add_task(
            Rpe(component=component, resolution=resolution,
                indir=resdir, init=init))
```

## Config file

The config file for the component should, at the very least, define the
default value for the `component_path` path in the `[paths]` section.  This
path should point to the path within the appropriate E3SM submodule where the
standalone component can be built.  This is the path to the directory where the
E3SM component's executable will be built, not to the executable itself.

Typically, the config file will also define the paths to the component 
executable  and the default namelist and streams files for "forward mode" (and,
for  MPAS-Ocean, "init mode"):

```cfg
# This config file has default config options for the landice core

# The paths section points polaris to external paths
[paths]

# the relative or absolute path to the root of a branch where MALI has been
# built
component_path = e3sm_submodules/MALI-Dev/components/mpas-albany-landice

# The namelists section defines paths to example_compact namelists that will be used
# to generate specific namelists. By default, these point to the forward and
# init namelists in the default_inputs directory after a successful build of
# the landice model.  Change these in a custom config file if you need a different
# example_compact.
[namelists]
forward = ${paths:component_path}/default_inputs/namelist.landice

# The streams section defines paths to example_compact streams files that will be used
# to generate specific streams files. By default, these point to the forward and
# init streams files in the default_inputs directory after a successful build of
# the landice model. Change these in a custom config file if you need a different
# example_compact.
[streams]
forward = ${paths:component_path}/default_inputs/streams.landice


# The executables section defines paths to required executables. These
# executables are provided for use by specific tasks.  Most tools that
# polaris needs should be in the conda environment, so this is only the path
# to the MALI executable by default.
[executables]
component = ${paths:component_path}/landice_model
```
