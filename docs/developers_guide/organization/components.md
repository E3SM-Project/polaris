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

Tasks are added to a component in task groups, each of which is a function
that adds related tasks to the component.  Each component has an `add_tasks`
module with a `TASK_GROUPS` dictionary naming the module and function of each
of its task groups.  Nothing is imported until a task group is needed, so
`polaris setup` builds only the task groups of the tasks it sets up (see
{ref}`dev-task-manifest`).  For example, part of the ocean component's
`polaris/tasks/ocean/add_tasks.py` looks like this:

```python
from typing import Dict

from polaris.tasks import TaskGroup, add_task_groups

_OCEAN = 'polaris.tasks.ocean'
TASK_GROUPS: Dict[str, TaskGroup] = {
    # planar tasks
    'baroclinic_channel': TaskGroup(
        f'{_OCEAN}.baroclinic_channel', 'add_baroclinic_channel_tasks'
    ),
    'isomip_plus/planar': TaskGroup(
        f'{_OCEAN}.isomip_plus', 'add_isomip_plus_tasks',
        dict(mesh_type='planar')
    ),
    ...
}


def add_ocean_tasks(component, task_groups=None):
    """
    Add tasks to the ocean component
    """
    add_task_groups(component, task_groups)
```

Task groups are added in the order they appear, which is the order
`polaris list` numbers their tasks in.  The optional third item of a
{py:class}`polaris.tasks.TaskGroup` holds any other keyword arguments to pass
to its function.

A new component is added to `COMPONENTS` in `polaris/tasks/__init__.py`, which
names the module that defines it, the name of the component object and its
`add_<component>_tasks()` function:

```python
COMPONENTS: Dict[str, ComponentEntry] = {
    'e3sm/init': ComponentEntry(
        'polaris.tasks.e3sm.init', 'e3sm_init', 'add_e3sm_init_tasks'
    ),
    'mesh': ComponentEntry('polaris.tasks.mesh', 'mesh', 'add_mesh_tasks'),
    'ocean': ComponentEntry('polaris.tasks.ocean', 'ocean', 'add_ocean_tasks'),
    'seaice': ComponentEntry(
        'polaris.tasks.seaice', 'seaice', 'add_seaice_tasks'
    ),
}
```

Components are kept in alphabetical order, and their task groups are added in
that order too.  This matters when one component's tasks share steps with
another's: the mesh component's coastline tasks share steps with the
`e3sm/init` component's tasks, which are added first.

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
# polaris needs should be in the deployment environment, so this is only the path
# to the MALI executable by default.
[executables]
component = ${paths:component_path}/landice_model
```
