(dev-categories-of-tasks)=

# Categories of tasks

There is no formal requirement that tasks be grouped together but it is
typically convenient to do so to keep things organized. Typically, tasks 
are placed in a shared subdirectory when they share some conceptual link, serve
a similar purpose or are variants on one another. Often, they have a common 
topography and initial condition, perhaps with different mesh resolutions, 
parameters, or both.  It is common for tasks with a subdirectory to share 
"framework" modules (but contents within a subdirectory of `tasks` should
not be used outside of that subdirectory -- framework used more broadly should
belong to the component or polaris as a whole).  Each component will typically 
include a mix of "idealized" tasks (e.g. {ref}`dev-ocean-baroclinic-channel` 
or {ref}`dev-landice-dome`) and "realistic"domains (e.g. 
{ref}`dev-landice-greenland` and {ref}`dev-ocean-global-ocean`).

Categories of tasks can be grouped in a python package (subdirectory) within 
the component's `tasks` package.  Often, this subdirectory will include a 
shared config file, with a set of default config options that are the starting 
point for all its tasks.  As an example, here is the config file for the `dome`
test cases in the `landice` core:

```cfg
# config options for dome tasks
[dome]

# sizes (in cells) for the 2000m uniform mesh
nx = 30
ny = 34

# resolution (in m) for the 2000m uniform mesh
dc = 2000.0

# number of levels in the mesh
levels = 10

# the dome type ('halfar' or 'cism')
dome_type = halfar

# Whether to center the dome in the center of the cell that is closest to the
# center of the domain
put_origin_on_a_cell = True

# whether to add a small shelf to the test
shelf = False

# whether to add hydrology to the initial condition
hydro = False

# config options related to visualization for dome tasks
[dome_viz]

# which time index to visualize
time_slice = 0

# whether to save image files
save_images = True

# whether to hide figures (typically when save_images = True)
hide_figs = True
```

Sometimes these config options are for functionality provided by the component
framework (as is the case for the `[vertical_grid]` config section used by many
task in the `ocean` component).  But most shared config options will typically 
go into a section that describes the tasks, as in the `[dome]` example above. 
Config options that are specific to a particular step might go into a section 
with another name, like the `[dome_viz]` section above.  There is not a
config file specific to a step -- all steps in a task share the same config
file.

Typically, in the subdirectory for tasks in a common category, the 
`__init__.py` file will be used to define a helper function to add the tasks
to the component.  This helps to keep the constructor of the component itself
from getting too cluttered. As an example, here is a function for adding `dome`
tasks to the `landice` component:

```python
from polaris.landice.tasks.dome.smoke_test import SmokeTest
from polaris.landice.tasks.dome.decomposition_test import DecompositionTest
from polaris.landice.tasks.dome.restart_test import RestartTest


def add_dome_tasks(component):
    """
    Add tasks that define Dome test cases
    
    component : polaris.landice.Landice
        the component that to add the tasks to
    """
    for mesh_type in ['2000m', 'variable_resolution']:
        component.add_task(
            SmokeTest(component=component, mesh_type=mesh_type))
        component.add_task(
            DecompositionTest(component=component, mesh_type=mesh_type))
        component.add_task(
            RestartTest(component=component, mesh_type=mesh_type))
```

As in this example, it may be useful to make several
versions of a task by passing different parameters.  In the example, we
create versions of `SmokeTest`, `DecompositionTest` and `RestartTest`
with each of two mesh types (`2000m` and `variable_resolution`).  We will
explore this further when we talk about {ref}`dev-tasks` and
{ref}`dev-steps` below.

It is also sometimes useful to define a common parent task that the tasks in
this category will descend from.  The parent task take cares of setting any 
additional config options and other pieces (like common steps) that apply
across all tasks, reducing code redundancy.

As with components and the main `polaris` package, tasks in a common 
subdirectory can also have a shared "framework" of packages, modules, config 
files, namelists, streams, and YAML files that is shared among tasks and steps.
