(dev-components)=

# Components

Currently, there are two components, `landice`, which has tasks for
MALI, and `ocean`, which encompasses all the tasks for MPAS-Ocean and 
OMEGA.

From a developer's perspective, a component is a package within polaris
that has four major pieces:

1. A class that descends from the {py:class}`polaris.Component` base class.
   The class is defined in `__init__.py` and its `__init__()` method
   calls the {py:meth}`polaris.Component.add_test_group()` method to add each
   test group to the component.
2. A `tasks` package, which contains packages for each
   test group, each of which contains various packages and modules for
   tasks and their steps.
3. An `<component>.cfg` config file containing any default config options
   that are universal to all test groups of the component.
4. Additional "framework" packages and modules shared between test groups.

The core's framework is a mix of shared code and other files (config files,
namelists, streams files, etc.) that is expected to be used only by modules
and packages within the core, not by other cores or the main polaris
{ref}`dev-framework`.

The constructor (`__init__()` method) for a child class of
{py:class}`polaris.Component` simply calls the parent class' version
of the constructor with `super().__init__()`, passing the name of the MPAS
core.  Then, it creates objects for each test group and adds them to itself, as
in this example from {py:class}`polaris.ocean.Ocean`:

```python
from polaris import Component
from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannel
from polaris.ocean.tasks.global_ocean import GlobalOcean
from polaris.ocean.tasks.ice_shelf_2d import IceShelf2d
from polaris.ocean.tasks.ziso import Ziso


class Ocean(Component):
   """
   The collection of all task for the MPAS-Ocean core
   """

   def __init__(self):
      """
      Construct the collection of MPAS-Ocean tasks
      """
      super().__init__(name='ocean')

      self.add_test_group(BaroclinicChannel(component=self))
      self.add_test_group(GlobalOcean(component=self))
      self.add_test_group(IceShelf2d(component=self))
      self.add_test_group(Ziso(component=self))
```

The object `self` is always passed to the constructor for each test group
so test groups are aware of which component they belong to.  This is necessary,
for example, in order to create the path for each test group, task and
step in the work directory.

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
