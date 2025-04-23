(dev-components)=

# Components

Currently, there are three components: `mesh`, which includes tasks and steps
for making MPAS meshes; `ocean`, which encompasses all the tasks
for MPAS-Ocean and Omega; and `seaice`, which implements tasks for MPAS-Seaice.

From a developer's perspective, a component is a package within polaris
that has three major pieces:

1. A `polaris.tasks.<component>` package, which contains packages for
   individual tasks and their steps, possibly within subpackages that help to
   organize them into broader categories.
2. A `polaris.<component>` package, which contains shared framework code and
   other files (e.g., config files, YAML files for model config options) that
   are expected to be used only by modules and packages within the component,
   not by other components or the main polaris {ref}`dev-framework`.
3. Optionally, a `<component>.cfg` config file containing default config
   options that are universal to all tasks of the component.

Each component object is either an instance of the
{py:class}`polaris.Component` class or of a child class that descends from this
class.

## Adding Tasks to a Component

Tasks are added to a component using the `polaris.tasks.add_tasks` module.
Each component has an `add_<component>_tasks()` function in this module that
adds the tasks to the component. This approach avoids circular imports in
Python. For example, the `add_ocean_tasks()` function for the `ocean` component
might look like this:

```python
from polaris.tasks.ocean.baroclinic_channel import add_baroclinic_channel_tasks
from polaris.tasks.ocean.cosine_bell import add_cosine_bell_tasks
from polaris.tasks.ocean.inertial_gravity_wave import (
    add_inertial_gravity_wave_tasks,
)
from polaris.tasks.ocean.manufactured_solution import (
    add_manufactured_solution_tasks,
)
from polaris.tasks.ocean.single_column import add_single_column_tasks


def add_ocean_tasks(component):
    """
    Add tasks to the ocean component.

    component : polaris.Component
        The ocean component to which tasks will be added.
    """
    # please keep these in alphabetical order
    add_baroclinic_channel_tasks(component=component)
    add_cosine_bell_tasks(component=component)
    add_inertial_gravity_wave_tasks(component=component)
    add_manufactured_solution_tasks(component=component)
    add_single_column_tasks(component=component)
```

The `add_<component>_tasks()` must then be added, along with the component
itself, to `polaris/tasks/__init__.py`:
```python
from typing import List

from polaris import Component

# import new components here
from polaris.tasks.mesh import mesh
from polaris.tasks.mesh.add_tasks import add_mesh_tasks
from polaris.tasks.ocean import ocean
from polaris.tasks.ocean.add_tasks import add_ocean_tasks
from polaris.tasks.seaice import seaice
from polaris.tasks.seaice.add_tasks import add_seaice_tasks

# Add new components alphabetically to this list
_components: List[Component] = [
    mesh,
    ocean,
    seaice,
]

_tasks_added = False


def get_components():
    """
    Add all tasks to the Polaris components
    """
    global _tasks_added
    if not _tasks_added:
        # add tasks to each component
        add_mesh_tasks(component=mesh)
        add_ocean_tasks(component=ocean)
        add_seaice_tasks(component=seaice)

        _tasks_added = True

    return _components
```

## Config File

A `<component>.cfg` config file is optional. If present, it typically defines
default paths and options for the component. For example, it might define the
default path to the component's executable and the default namelist and streams
files for "forward mode" (and, for MPAS-Ocean, "init mode"):

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
# the landice model. Change these in a custom config file if you need a different
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
# executables are provided for use by specific tasks. Most tools that
# polaris needs should be in the conda environment, so this is only the path
# to the MALI executable by default.
[executables]
component = ${paths:component_path}/landice_model
```
