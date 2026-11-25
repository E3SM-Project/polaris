# Adding a Shared Step

In Polaris, **shared steps** are a powerful way to avoid redundant computation
and ensure consistency across related tasks. Rather than each task duplicating
the same setup or preprocessing work, a shared step can be created once and
then referenced by multiple tasks that need it. This is especially useful
when many tasks require identical inputs or initial conditions. For more on
the concept and implementation of shared steps, see the
{ref}`dev-shared-steps`.

The `init` step in `overflow` (which we will mimic in
`my_overflow`) represents a common example. Many tasks use the same
mesh and initial condition for a given resolution, so it makes sense to define
a single `init` step and share it among all relevant tasks. This approach saves
compute time and ensures that all tasks are using exactly the same initial
state.

In this section, we'll walk through how to create a shared `init` step for your
new category of tasks, following the established pattern in Polairs.

This step is involved enough that it divided into several pages, each
covering a different part of the process.  We'll start out by just setting
up some basic infrastructure, and making sure it's wired together right.

## Adding the `init` Step

In polaris, steps are defined in python modules by classes that descend
from the {py:class}`polaris.Step` base class.  The modules can be defined
within the task package (if they are unique to the task) or in the
category of tasks (if they are shared among several tasks).  In this example,
we have only added one task (`default`) so far but we anticipate
adding more.  All tasks will require a similar `init` step, so
it makes sense for the `init.py` module to be located in the test
group's package to promote {ref}`dev-code-sharing`.

The `init` step will create the MPAS mesh and initial condition for
the task.  To start with, we'll just create a new `Init` class.  In this
example, we will have `Init` descend from `Step`.  (In the `overflow` version,
it descends from `OceanIOStep` so add some functionality for writing out files
either in Omega or MPAS-Ocean format, just so you're not surprised by the
difference.) Here's the beginnings of the `Init` step:

```bash
$ vim polaris/tasks/ocean/my_overflow/init.py
```
```python
from polaris import Step


class Init(Step):
    """
    A step for creating a mesh and initial condition for "my overflow" test
    cases.
    """

    def __init__(self, component, name, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        indir : str
            The name of the directory the task will be set up in
        """
        super().__init__(component=component, name=name, indir=indir)
```

The step takes the component it belongs to as an input to its constructor,
and passes that along to the superclass' version of the constructor, along with
the name of the step and the directory that the step should go in wihtin a
subdirectory that's the same as `name`.  An alternative would be to provide
`subdir` argument if we want to specify the full subdirectory of the step
withing the component without using `name` as the final subdirectory.

## Create a Shared Step Object

Update your `add_my_overflow_tasks()` function in
`polaris/tasks/ocean/my_overflow/__init__.py` to create and add the shared
`Init` step:

```{code-block} python
:emphasize-lines: 1-3, 12
from polaris.tasks.ocean.my_overflow.init import Init as Init


def add_my_overflow_tasks(component):
    """
    Add a task following the "my overflow" test case of Petersen et al. (2015)
    doi:10.1016/j.ocemod.2014.12.004

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    init_step = Init(component=component, name='init', indir=indir)

```
This will place the `init` step in a subdirectory `planar/my_overflow/init`
within the `ocean` component.  It will also define a shared config file at
`planar/my_overflow/my_overflow.cfg` that will have the config options for
`my_overflow` tasks and steps generally and `init` in particular.

## Test Things Out Again

There's still not much to test but it doesn't hurt to rerun:

``` bash
polaris list
```

Again, if you get import errors, something isn't quite hooked up right. It's
still to early to see anything new in the list of tasks.

## Adding a Config File

To set default config options (see {ref}`config-files`) that are shared across
all the tasks and steps of a category of tasks, we typically add them to to a
config file with the same name as the category of tasks (e.g.
`my_overflow.cfg`). Having a shared config file means fewer places that a user
has to edit the config options. (But for this same reason it's improtant that
the config options really can be shared between steps and tasks -- if the
same config option should have different values for different tasks, it
obviously doesn't make sense to try to use a config file shared between these
tasks.)

In this case, we know that these config options are going to be used across
many tasks so it makes sense to put them directly in the
`my_overflow` subdirectory:

```bash
$ vim polaris/tasks/ocean/my_overflow/my_overflow.cfg
```
```cfg
# Options related to the "my overflow" case
[my_overflow]

```
We'll flesh out the config options as we need them below.

There is another way to get define default config options.  The `my_overflow`
tasks don't use this but we can also define them in the code in
a `configure()` method of the task.  These config options will also show
up in the config file in the task's work directory.  There is no
`configure()` method for individual steps because it is not a good idea to
change config options within a step, since other steps may be affected in
potentially unexpected ways.  You can see an example of this in the
[cosine_bell task](https://github.com/E3SM-Project/polaris/blob/6a541bb778751985191138be4d4a64887c05c18b/polaris/tasks/ocean/cosine_bell/__init__.py#L268-L282).


## Add a Shared Config File to the Step

Here's what you need to add in ``polaris/tasks/ocean/my_overflow/__init__.py`
to create a shared config file and add it to your `init` step:

```{code-block} python
:emphasize-lines: 1, 14-16, 19
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.my_overflow.init import Init as Init


def add_my_overflow_tasks(component):
    """
    Add a task following the "my overflow" test case of Petersen et al. (2015)
    doi:10.1016/j.ocemod.2014.12.004

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    indir = 'planar/my_overflow'
    config_filename = 'my_overflow.cfg'
    config = PolarisConfigParser(filepath=f'{indir}/{config_filename}')
    config.add_from_package('polaris.tasks.ocean.my_overflow', config_filename)

    init_step = Init(component=component, name='init', indir=indir)
    init_step.set_shared_config(config, link=config_filename)
```

The config file will live within the `ocean` component in a work directory
at `planar/my_overflow/my_overflow.cfg`. Later, we'll add it to the tasks
within `my_overflow` as well.

## Creating a Horizontal Mesh

The `run()` method of the `init` step does the actual work of
creating a mesh and initial condition. Below, We will present the method in 3
pieces.  Please browse the code yourself to see the complete method.

First, we create a regular, planar, hexagonal mesh that is periodic in the x
direction but not in y. The number of cells in mesh are based on the physical
sizes of the mesh in x and y, which come from config options `lx` and `ly`
discussed below.  The distance between grid-cell centers `dc` is just the
resolution converted from km to m.  Then, we "cull" (remove) the the top and
bottom row of cells in the y direction so the mesh is no longer periodic in
that direction (`nonperiodic_y=True`).

```bash
$ vim polaris/tasks/ocean/my_overflow/init.py
```
```{code-block} python
:emphasize-lines: 1-4, 6, 13-36

from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny


class Init(Step):

    ...

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger

        section = config['my_overflow']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=False
        )
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        write_netcdf(ds_mesh, 'culled_mesh.nc')
```

We use {py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()` to compute the
number of grid cells in x and y from the physical sizes and the resolution.

We will continue with the `run()` method as we move through the tutorial, but
first it is worth discussing how to set the config options used to generate
the horizontal mesh.

## Adding a the Config Options to the Config File

We need a way to get the physical extent of the mesh `lx` and `ly` in km and
the `resolution` (in km) of the cells. We could hard-code these in the task
directly and sometimes we do but this can also have several disadvantages.
First and foremost, unless they are explicitly given as part of the name of
the task or step, this it hides these physical values in a way that isn't
accessible to users.  They become "magic numbers" in the code. Second, by
making them available to users, they should be easy to alter so a user can
explore the effects of modifying them if they choose to.  Finally, the config
options are available to each step in the tasks so it is easy to look them up
again later (e.g. during plotting) if they are needed.

```bash
$ vim polaris/ocean/tasks/my_overflow/my_overflow.cfg
```
```{code-block} cfg
:emphasize-lines: 4-11
# Options related to the "my overflow" case
[my_overflow]

# The width of the domain in the across-slope dimension (km)
ly = 40

# The length of the domain in the along-slope dimension (km)
lx = 200

# Distance from two cell centers (km)
resolution = 2.0
```

## Test Things One More Time

Give it one more test:

``` bash
polaris list
```

Import errors, missing files, and such will tell you something's missing or
not hooked up quite right.

---

← [Back to *Making a New Category of Tasks*](creating_category_of_tasks.md)

→ [Continue to *Adding a First Task*](adding_first_task.md)
