(dev-tutorial-add-test-group)=

# Developer Tutorial: Adding a new test group

This tutorial presents a step-by-step guide to adding a new test group to the
polaris python package (see the {ref}`glossary` for definitions of these
terms).  In this tutorial, I will use the {ref}`dev-ocean-baroclinic-channel`
as an example.  This test group was actually ported from {ref}`compass` but we
will use it to describe the process for creating a test group from scratch.

(dev-tutorial-add-test-group-getting-started)=

## Getting started

To begin with, you will need to check out the polaris repo and create a new
branch from `main` for developing the new test group.  For this purpose, we
will stick with the simpler approach in {ref}`dev-polaris-repo` here, but feel
free to use the `git worktree` approach from {ref}`dev-polaris-repo-advanced`
instead if you are comfortable with it.

```bash
git clone git@github.com:E3SM-Project/polaris.git add-yet-another-channel
cd add-yet-another-channel
git checkout -b add-yet-another-channel
```

Now, you will need to create a conda environment for developing polaris, as
described in {ref}`dev-conda-env`.  We will assume a simple situation where
you are working on a "supported" machine and using the default compilers and
MPI libraries, but consult the documentation to make an environment to suit
your needs.

```bash
# this one will take a while the first time
./configure_polaris_envs.py --conda $HOME/miniforge3
```

If you don't already have [miniforge3](https://github.com/conda-forge/miniforge#miniforge3)
installed in the directory pointed to by `--conda`, it will be installed
automatically for you.

```{note}
If you have [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
installed already, you can use that, too.  But we don't recommend installing
that if you haven't already.  Miniforge3 comes with some important tools and
config options already set the way we need them.
```

If all goes well, you will have a file named `load_dev_polaris_*.sh`,
where the details of the `*` depend on your current version of polaris, the
machine and compilers.  For example, on Chrysalis, you might have
`load_dev_polaris_0.1.0-alpha.3_chrysalis_intel_openmpi.sh`, which will be the
example used here:

```bash
source load_dev_polaris_0.1.0-alpha.3_chrysalis_intel_openmpi.sh
```

Now, we're ready to get the MPAS-Ocean source code from the E3SM repository:

```bash
# Get the E3SM code -- this one takes a while every time
git submodule update --init --recursive
```

If your test group will require development in E3SM in addition to polaris,
you will want to create a branch (possibly with `git worktree`) for your
development there as well:

```bash
cd e3sm_submodules/E3SM-Project
git fetch --all -p
git branch xylar/mpas-ocean/add-yet-another-channel origin/main
git switch xylar/mpas-ocean/add-yet-another-channel
cd ../
```

```{note}
E3SM has some pretty strict requirements on branch names.  If you are using
your own fork of E3SM, you should start your branch name with the component
you are developing (in this case `mpas-ocean`).  If you wish to push your
branch to the E3SM repo, you need to begin the branch name with your GitHub
username (`xylar` in this example), followed by the component name.  In
either case, the branch name needs to be all lowercase, separated by
hyphens, and to describe the work to be done.
```

Next, we're ready to build the MPAS-Ocean executable:

```bash
cd E3SM-Project/components/mpas-ocean/
make ifort
cd ../../..
```

The make target will be different depending on the machine and compilers, see
{ref}`dev-supported-machines` or {ref}`dev-other-machines` for the right one
for your machine.

Now, we're ready to start developing!

(dev-tutorial-add-test-group-make-test-group)=

## Making a new test group

Use any method you like for editing code.  If you haven't settled on a method
and are working on your own laptop or desktop, you may want to try an
integrated development environment ([PyCharm](https://www.jetbrains.com/pycharm/)
is a really nice one).  They have features to make sure your code adheres to
the style required for polaris (see {ref}`dev-style`).  `vim` or a similar
tool will work fine on supercomputers.

Your new test group will be a new python package within an existing component
(`ocean` here).  For this example, we create a new test group modeled on
`baroclinic_channel` called `yet_another_channel`. We create a new
`yet_another_channel` directory in `polaris/ocean/tasks`.  In that directory,
we will make a new  file called `__init__.py` that will initially be empty.
That's all it takes  to make `yet_another_channel` a new package in `polaris`.

Each test group in `polaris` is a class that descends from the
{py:class}`polaris.TestGroup` class.  Let's make a new class for the
`yet_another_channel` test group in `__init__.py`:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/__init__.py
```
```python
from polaris import TestGroup


class YetAnotherChannel(TestGroup):
    """
    A test group for "yet another channel" tasks
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component, name='yet_another_channel')
```

The method (a function for a class) called `__init__()` is the constructor
used to make an instance (an object) representing the test group.  It needs
to know what component it belongs to so that is passed in as the `component`
argument.  The only thing that happens so far is that the constructor for the
base class `TestGroup` gets called.  In the process, we give the test group
the name `yet_another_channel`.  You can take a look at the base class
{py:class}`polaris.TestGroup` in
[polaris/testgroup.py](https://github.com/E3SM-Project/polaris/blob/main/polaris/testgroup.py)
if you want.  That's not necessary for the tutorial, but some new developers
have found reading the base class code (particularly for
{py:class}`polaris.Task` and {py:class}`polaris.Step`) to be highly
instructive.

Naming conventions in python are that we use
[CamelCase](https://en.wikipedia.org/wiki/Camel_case) for classes, which
always start with a capital letter, and all lowercase, possibly with
underscores, for variable, module, package, function and method names.  We
avoid all-caps like `MPAS`, even though this might seem preferable. (We use
`E3SM` in a few places because `E3sm` looks really awkward.)

You are encouraged to add docstrings (enclosed in `"""`) to briefly document
classes, methods and functions as you write them.  We use the
[numpydoc](https://numpydoc.readthedocs.io/en/latest/format.html) style
conventions, as described in {ref}`dev-docstrings`.

Our new `YetAnotherChannel` class defines the test group, but so far it
doesn't have any tasks in it.  We'll come back and add them later in the
tutorial.  Before we add a task, let's make `polaris` aware that the
test group exists. To do that, we need to open
[polaris/ocean/\_\_init\_\_.py](https://github.com/E3SM-Project/polaris/blob/main/polaris/ocean/__init__.py),
add an import for the new test group, and add an instance of the test group to the list of test
groups in the ocean core:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/__init__.py
```
```{code-block} python
:emphasize-lines: 4, 21

from polaris import Component
from polaris.ocean.tasks.baroclinic_channel import BaroclinicChannel
from polaris.ocean.tasks.global_convergence import GlobalConvergence
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannel


class Ocean(Component):
    """
    The collection of all task for the MPAS-Ocean core
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean tasks
        """
        super().__init__(name='ocean')

        # please keep these in alphabetical order
        self.add_test_group(BaroclinicChannel(component=self))
        self.add_test_group(GlobalConvergence(component=self))
        self.add_test_group(YetAnotherChannel(component=self))
```

We make an instance of the `YetAnotherChannel` class and we immediately add
it to the `Ocean` core's list of test groups.  That's all we need to do.  Now
`polaris` knows about the test group.

(dev-tutorial-add-test-group-add-default)=

## Adding a "default" task

We'll add a task called `default` to `yet_another_channel` by making a
`default` package within `polaris/ocean/tasks/yet_another_channel`.  First,
we make the directory `polaris/ocean/tasks/yet_another_channel/default`, then
we add an empty `__init__.py` file into it. As a starting point, we'll create
a new `Default` class in this file that descends from the
{py:class}`polaris.Task` base class (take a look at
`polaris/task.py` if you want to see the contents of `Task` if
you're interested).

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```python
from polaris import Task


class Default(Task):
    """
    The default task for the "yet another channel" test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
    """

    def __init__(self, test_group):
        """
        Create the task

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to
        """
        name = 'default'
        super().__init__(test_group=test_group, name=name)
```

As a starting point, we just pass along the test group (`YetAnotherChannel`)
this task belongs to on to the base class's constructor
(`super().__init__()`) and give the task a name, `default`.

And let's add the `Default` task to the test group:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/__init__.py
```
```{code-block} python
:emphasize-lines: 1, 16-18

from polaris.ocean.tasks.yet_another_channel.default import Default
from polaris import TestGroup


class YetAnotherChannel(TestGroup):
    """
    A test group for "yet another channel" tasks
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component,
                         name='yet_another_channel')

        self.add_test_case(
            Default(test_group=self))
```

Even though this task doesn't do anything, we can list the tasks and make
sure your new one shows up:

```bash
$ polaris list
     Testcases:
     ...
        9: ocean/yet_another_channel/default
```

If they don't show up, you probably missed a step (adding the test group to the
component or the task to the test group).  If you get import errors or
syntax errors, you'll need to fix those first.

(dev-tutorial-add-test-group-vary-res)=

## Varying resolution and other parameters

For "yet another channel" tasks, we know that we want each test to be at a
single resolution but let's suppose that we want multiple versions of the
`yet_another_channel` test for different resolutions.

We also want a lot of flexibility in determining
the resolution, so it's easy to add new ones in the future.  At the same time,
we want it to be easy to set up and run tasks and the supported resolutions
without users having to specify the resolution (e.g. in a config option). We
have found that a convenient way to handle this situation is to passing the
resolution as a parameter when we create a version of the task.  This way,
we can easily create several versions of the task at different resolutions
just by passing different values for the resolution.  The same could apply for
many other parameters, such as the horizontal viscosity in the model, the type
of vertical coordinate, or whether or not a task includes a type of
forcing (e.g. tides).  There is little restriction on what types of parameters
can be used to create variants of a task. We'll see what this looks like
in the next few sections.

There are also types of tasks where a single parameter is varied *within*
the task (e.g. with different steps each performing a simulation with its
own parameter value, and then a step analyzing the behavior as the parameter
varies).  The "yet another channel" test group includes the RPE (reference
potential energy) task that explores the behavior of the task at
different horizontal viscosities in this way.  In this situation, it is more
convenient for the parameter values to come from config options than to be
hard-coded when the task is created.  This allows users who want to
explore non-default parameter values to change the config options before
running the task.  We'll see in more detail what that looks like later in
the tutorial.

Let's say you want to support 3 resolutions in `yet_another_channel` tasks:
1, 4 and 10 km.  We'll add resolution in km as a float parameter and attribute
to the `default` task:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```{code-block} python
:emphasize-lines: 1, 12-15, 18, 27-28, 31-38

import os

from polaris import Task


class Default(Task):
    """
    The default task for the "yet another channel" test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, test_group, resolution):
        """
        Create the task

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to

        resolution : float
            The resolution of the task in km
        """
        name = 'default'
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)
```

We store the `resolution` as an attribute of the task object itself
(`self.resolution`). Later on in the task in other methods, we will access
the resolution with `self.resolution` whenever we need it.  We also indicate
that the work directory should include a subdirectory for resolution (taking
care to support the possibility that we might want sub-km resolutions in the
future) as well as the name of the task. We add resolution to the
docstring for both the class (where we describe the `resolution` attribute) and
the constructor (where we describe the `resolution` argument or parameter).

The `default` task still doesn't do anything yet because we haven't added
any steps, change how we add ti to the `yet_another_channel` test group so we
can see how the resolution will be specified.  We update `YetAnotherChannel`
to add a loop over resolutions as follows:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/__init__.py
```
```{code-block} python
:emphasize-lines: 17-19

from polaris.ocean.tasks.yet_another_channel.default import Default
from polaris import TestGroup


class YetAnotherChannel(TestGroup):
    """
    A test group for "yet another channel" tasks
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component,
                         name='yet_another_channel')

        for resolution in [1., 4., 10.]:
            self.add_test_case(
                Default(test_group=self, resolution=resolution))
```

Let's run `polaris list` and see that our new tasks appear:
```
$ polaris list
...
  10: ocean/yet_another_channel/1km/default
  11: ocean/yet_another_channel/4km/default
  12: ocean/yet_another_channel/10km/default
```

In the long run, the `default` task and most other tasks in this
test group will be for regression testing and will only be run at the coarsest
resolution, 10 km.  But we will put in several resolutions to show how they
are supported.  If we have done our job especially well, we should be able to
add new, non-standard resolutions and the tasks should still work.

(dev-tutorial-add-test-group-add-init)=

## Adding the init step

In polaris, steps are defined in python modules by classes that descend
from the {py:class}`polaris.Step` base class.  The modules can be defined
within the task package (if they are unique to the task) or in the
test group (if they are shared among several tasks).  In this example,
we have only added one task (`default`) so far but we anticipate
adding more.  All tasks will require a similar `init` step, so
it makes sense for the `init.py` module to be located in the test
group's package to promote {ref}`dev-code-sharing`.

The `init` step will create the MPAS mesh and initial condition for
the task.  To start with, we'll just create a new `Init` class
that descends from `Step`:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```python
from polaris import Step


class Init(Step):
    """
    A step for creating a mesh and initial condition for "yet another channel"
    tasks

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """
    def __init__(self, task, resolution):
        """
        Create the step

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to

        resolution : float
            The resolution of the task in km
        """
        super().__init__(task=task, name='init')
        self.resolution = resolution
```

This pattern is probably starting to look familiar.  The step takes the test
case it belongs to as an input to its constructor, and passes that along to
the superclass' version of the constructor, along with the name of the step.
By default, the subdirectory for the step is the same as the step name, but
just like for a task, you can give the step a more complicated
subdirectory name, possibly with multiple levels of directories.  This is
particularly important for parameter studies, an example of which can be seen
in the {ref}`dev-ocean-cosine-bell` task.

### Creating a horizontal mesh

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
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```{code-block} python
:emphasize-lines: 1-4, 6, 13-40

from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny


class Init(Step):

    ...

    def run(self):
        """
        Run this step of the task
        """
        logger = self.logger
        config = self.config

        section = config['yet_another_channel']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
                                       nonperiodic_x=False,
                                       nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')
```

We use {py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()` to compute the
number of grid cells in x and y from the physical sizes and the resolution.

We will continue with the `run()` method below, but first it is worth
discussing how to set the config options used to generate the horizontal mesh.

### Adding a config file

We need a way to get the physical extent of the mesh `lx` and `ly` in km.
We could hard-code these in the task directly but this has several
disadvantages.  First and foremost, it hides these physical values in a way
that isn't accessible to users.  They become "magic numbers" in the code.
Second, by making them available to users, they should be easy to alter so a
user can explore the effects of modifying them if they choose to.  Finally,
the config options are available to each step in the tasks so it is easy
to look them up again later (e.g. during plotting) if they are needed.

To set default config options (see {ref}`config-files`) for the task, we
typically add them to to a config file with the same name as the test group
or task (or both).  Polaris will automatically look for config files with
these names when it sets up the tasks.  All the steps of a task
share the same config file because it isn't very convenient for a user to have
to edit a different config file for each step.  (Even editing config files for
individual tasks is kind of a pain, so it can be more convenient to set
config options in a "user" {ref}`config-files` before setting up the test
case.)

In this case, we know that these config options are going to be used across
many tasks so it makes sense to put them directly in the
`yet_another_channel` test group.  If we put them in a file called
`yet_another_channel.cfg`, they will automatically get read in and added to
the config file for each task as part of setup:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/yet_another_channel.cfg
```
```cfg
# config options for "yet another channel" testcases
[yet_another_channel]

# the size of the domain in km in the x and y directions
lx = 160.0
ly = 500.0
```

There is another way to get define default config options.  The "yet another
channel" task doesn't use this but we can also define them in the code in
a `configure()` method of the task.  These config options will also show
up in the config file in the task's work directory.  There is no
`configure()` method for individual steps because it is not a good idea to
change config options within a step, since other steps may be affected in
potentially unexpected ways.  You can see an example of this in the
[cosine_bell task](https://github.com/E3SM-Project/polaris/blob/main/polaris/ocean/tasks/global_convergence/cosine_bell/__init__.py#L55-L62).


(dev-tutorial-add-test-group-adding-a-step)=

### Adding the step to the task

Returning to the `default` task, we are now ready to add
`init`.

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```{code-block} python
:emphasize-lines: 4, 11-12

import os

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.init import Init


class Default(Task):
    def __init__(self, test_group, resolution):
        ...

        self.add_step(
            Init(task=self, resolution=resolution))
```

Now we have created a step, `init`, that does something, creating a
mesh. We can first check that the step exists:

```bash
$ polaris list -v

  ...

  12: path:          ocean/yet_another_channel/10km/default
      name:          default
      component:     ocean
      test group:    yet_another_channel
      subdir:        10km/default
      steps:
       - init
```

Then we can set up the task:

```bash
$ polaris setup -t ocean/yet_another_channel/10km/default \
    -p ${PATH_TO_MPAS_OCEAN} -w ${PATH_TO_WORKING_DIR}

     Setting up tasks:
       ocean/yet_another_channel/10km/default
     target cores: 1
     minimum cores: 1
```

and run it:

```bash
$ cd ${PATH_TO_WORKING_DIR}/ocean/yet_another_channel/10km/default
$ sbatch job_script.sh
$ cat polaris.o${SLURM_JOBID}

     Loading conda environment
     Done.

     Loading Spack environment...
     Done.

     ocean/yet_another_channel/10km/default
     polaris calling: polaris.run.serial._run_test()
       in /gpfs/fs1/home/ac.cbegeman/polaris-repo/main/polaris/run/serial.py

     Running steps: init
       * step: init

     polaris calling: polaris.ocean.tasks.yet_another_channel.default.Default.validate()
       inherited from: polaris.task.Task.validate()
       in /gpfs/fs1/home/ac.cbegeman/polaris-repo/main/polaris/task.py

       test execution:      SUCCESS
       test runtime:        00:00
     Test Runtimes:
     00:00 PASS ocean/yet_another_channel/10km/default
     Total runtime 00:01
     PASS: All passed successfully!
```

### Creating a vertical coordinate

Ocean tasks typically need to define a vertical coordinate as we will
discuss here.  Land ice tasks use a different approach to creating
vertical coordinates, so this section will not apply to those tasks.
Returning to the `run()` method in the `init` step, the code
snippet below is an example of how to make use of the
{ref}`dev-ocean-framework-vertical` to create the vertical coordinate:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```{code-block} python
:emphasize-lines: 1, 7, 17-26

import xarray as xr

...

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):
    def run(self):

        ...

        write_netcdf(ds_mesh, 'culled_mesh.nc')

        ds = ds_mesh.copy()
        x_cell = ds.xCell
        y_cell = ds.yCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)

        init_vertical_coord(config, ds)
```

This part of the step, too, relies on config options, this time from the
`vertical_grid` section (see {ref}`dev-ocean-framework-vertical` for more on
this):

Now we add a new section to the config file:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/yet_another_channel.cfg
```
```cfg # Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 20

# Depth of the bottom of the ocean
bottom_depth = 1000.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1

...
```

What we're doing here is defining a z-star coordinate with 20 uniform vertical
levels, a bottom depth of 1000 m (so each layer is 50 m thick) and without
partial cells.  We also define the `bottomDepth` field to be a constant with
the value of the `bottom_depth` config option everywhere, so there is no
topography.  The sea surface height (`ssh`) is set to zero everywhere (this
will nearly always be the case for any tasks that don't include ice-shelf
cavities, where the SSH is depressed by the weight of the overlying ice).
{py:func}`polaris.ocean.vertical.init_vertical_coord()` takes are of most of
the details for us once we have defined `bottomDepth` and `ssh`, adding the
following fields to `ds`:

* `minLevelCell` - the index of the top valid layer
* `maxLevelCell` - the index of the bottom valid layer
* `cellMask` - a mask of where cells are valid
* `layerThickness` - the thickness of each layer
* `restingThickness` - the thickness of each layer stretched as if `ssh = 0`
* `zMid` - the elevation of the midpoint of each layer
* `refTopDepth` - the positive-down depth of the top of each ref. level
* `refZMid` - the positive-down depth of the middle of each ref. level
* `refBottomDepth` - the positive-down depth of the bottom of each ref. level
* `refInterfaces` - the positive-down depth of the interfaces between ref.
  levels (with `nVertLevels` + 1 elements).
* `vertCoordMovementWeights` - the weights (all ones) for coordinate movement

### Creating an initial condition

The next part of the `run()` method in the `init` step is to
define the initial condition:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```{code-block} python
:emphasize-lines: 1, 14-88

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step


class Init(Step):
    def run(self):

        ...
        init_vertical_coord(config, ds)

        section = config['yet_another_channel']
        use_distances = section.getboolean('use_distances')
        gradient_width_dist = section.getfloat('gradient_width_dist')
        gradient_width_frac = section.getfloat('gradient_width_frac')
        bottom_temperature = section.getfloat('bottom_temperature')
        surface_temperature = section.getfloat('surface_temperature')
        temperature_difference = section.getfloat('temperature_difference')
        salinity = section.getfloat('salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

        x_min = x_cell.min().values
        x_max = x_cell.max().values
        y_min = y_cell.min().values
        y_max = y_cell.max().values

        y_mid = 0.5 * (y_min + y_max)
        x_perturb_min = x_min + 4.0 * (x_max - x_min) / 6.0
        x_perturb_max = x_min + 5.0 * (x_max - x_min) / 6.0

        if use_distances:
            perturb_width = gradient_width_dist
        else:
            perturb_width = (y_max - y_min) * gradient_width_frac

        y_offset = perturb_width * np.sin(
            6.0 * np.pi * (x_cell - x_min) / (x_max - x_min))

        temp_vert = (bottom_temperature +
                     (surface_temperature - bottom_temperature) *
                     ((ds.refZMid + bottom_depth) / bottom_depth))

        frac = xr.where(y_cell < y_mid - y_offset, 1., 0.)

        mask = np.logical_and(y_cell >= y_mid - y_offset,
                              y_cell < y_mid - y_offset + perturb_width)
        frac = xr.where(mask,
                        1. - (y_cell - (y_mid - y_offset)) / perturb_width,
                        frac)

        temperature = temp_vert - temperature_difference * frac
        temperature = temperature.transpose('nCells', 'nVertLevels')

        # Determine y_offset for 3rd crest in sin wave
        y_offset = 0.5 * perturb_width * np.sin(
            np.pi * (x_cell - x_perturb_min) / (x_perturb_max - x_perturb_min))

        mask = np.logical_and(
            np.logical_and(y_cell >= y_mid - y_offset - 0.5 * perturb_width,
                           y_cell <= y_mid - y_offset + 0.5 * perturb_width),
            np.logical_and(x_cell >= x_perturb_min,
                           x_cell <= x_perturb_max))

        temperature = (temperature +
                       mask * 0.3 * (1. - ((y_cell - (y_mid - y_offset)) /
                                           (0.5 * perturb_width))))

        temperature = temperature.expand_dims(dim='Time', axis=0)

        normal_velocity = xr.zeros_like(ds.xEdge)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)

        ds['temperature'] = temperature
        ds['salinity'] = salinity * xr.ones_like(temperature)
        ds['normalVelocity'] = normal_velocity
        ds['fCell'] = coriolis_parameter * xr.ones_like(x_cell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        write_netcdf(ds, 'init.nc')
```

The details aren't critical for the purpose of this tutorial, though you may
find this example to be useful for developing other tasks, particularly
those for the `ocean` component.  The point is mostly to show how config
options are used to define the initial condition. Again, we use config options
from `yet_another_channel.cfg`, this time in a section specific to the test
group that we therefore call `yet_another_channel`:

```cfg
# config options for "yet another channel" testcases
[yet_another_channel]

...

# Logical flag that determines if locations of features are defined by distance
# or fractions. False means fractions.
use_distances = False

# Temperature of the surface in the northern half of the domain.
surface_temperature = 13.1

# Temperature of the bottom in the northern half of the domain.
bottom_temperature = 10.1

# Difference in the temperature field between the northern and southern halves
# of the domain.
temperature_difference = 1.2

# Fraction of domain in Y direction the temperature gradient should be linear
# over. Used when use_distances = False.
gradient_width_frac = 0.08

# Width of the temperature gradient around the center sin wave. Default value
# is relative to a 500km domain in Y. Used when use_distances = True.
gradient_width_dist = 40e3

# Salinity of the water in the entire domain.
salinity = 35.0

# Coriolis parameter for entire domain.
coriolis_parameter = -1.2e-4
```

Again, the idea is that we make these config options rather than hard-coding
them in the task so that users can more easily alter the task and
also to provide a relatively obvious place to document these parameters.

```{figure} ../developers_guide/framework/images/baroclinic_channel_cell_patches.png
---
align: right
width: 250 px
---
Temperature
```

### Adding plots


It is helpful to make some plots of a few variables from the initial condition
as a sanity check.  We do this using the visualization for
{ref}`dev-visualization-planar`.

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```{code-block} python
:emphasize-lines: 1, 6, 19-23

import cmocean  # noqa: F401

...

from polaris import Step
from polaris.viz import plot_horiz_field


class Init(Step):

    ...

    def run(self):

        ...

        write_netcdf(ds, 'init.nc')

        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'initial_temperature.png')
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'initial_normal_velocity.png', cmap='cmo.balance',
                         show_patch_edges=True)
```

Here, we add plots of temperature and the normal component of the velocity at
model edges.  You pass in the data set and the name of the field to plot as
well as a mesh dataset (which could be the same `ds`, since it has the same
mesh variables in this case, but we pass `ds_mesh` in this example).  You
can specify the colormap (the default is the matplotlib default `viridis`) and
optionally you can plot the edges of the patches (cells or edges).

### Adding step outputs

Now that we've written the full `run()` method for the step, we know what
the output files will be.  It is a very good idea to define the outputs
explicitly.  For one, polaris will check to make sure they are created as
expected and raise an error if not.  For another, we anticipate that defining
outputs will be a requirement for future work on task parallelism in which
the connection between tasks and steps will be determined based on their
inputs and outputs.  For this step, we add the following outputs in the
constructor:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/init.py
```
```{code-block} python
:emphasize-lines: 11-13

...

class Init(Step):
    ...

    def __init__(self, task, resolution):

        ...

        self.resolution = resolution

        for file in ['base_mesh.nc', 'culled_mesh.nc', 'initial_state.nc']:
            self.add_output_file(file)
```

Only `initial_state.nc` and `culled_graph.info` are strictly necessary, as
these are used as inputs to the `forward` and `analysis` steps that we will
define below, but explicitly including other outputs is not a problem.

(dev-tutorial-add-test-group-adding-validation)=

### Adding validation

One of the main purposes of having tasks is to validate changes to the
code.  You can use polaris' validation code to compare the output of different
steps to one another (or files within a single step), but a very common type
of validation is to check if the contents of files exactly match the contents
of the same files from a "baseline" run (performed with a different branch of
E3SM and/or polaris).

Validation happens at the task level so that steps can be compared with
one another.  Well add baseline validation for both the initial state and
forward runs:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```{code-block} python
:emphasize-lines: 3, 10-19

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.init import Init
from polaris.validate import compare_variables


class Default(Task):

    ...

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, and ``layerThickness`` in the
        ``init`` step with a baseline if one was provided.
        """
        super().validate()

        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')
```
We check salinity, temperature and layer thickness in the initial state step.
Since we only provide `filename1` in the call to
{py:func}`polaris.validate.compare_variables()`, we will only do this
validation if a user has set up the task with a baseline, see
{ref}`dev-validation`.

(dev-tutorial-add-test-group-testing-a-step)=

### Test things out!

It's a good idea to test things out after adding each step to a task.
Before we add any more steps or tasks, we'll run `default` and make sure
we can create the initial condition.  It would be good to make sure what we've
done so far works well before we move on.

The first way to test things out is just to list the tasks and make sure your
new ones show up:

```bash
$ polaris list

Testcases:
   0: ocean/baroclinic_channel/10km/default
   1: ocean/baroclinic_channel/10km/decomp
   2: ocean/baroclinic_channel/10km/restart
   3: ocean/baroclinic_channel/10km/threads
   4: ocean/baroclinic_channel/1km/rpe
   5: ocean/baroclinic_channel/4km/rpe
   6: ocean/baroclinic_channel/10km/rpe
   7: ocean/global_convergence/qu/cosine_bell
   8: ocean/global_convergence/icos/cosine_bell
   9: ocean/yet_another_channel/1km/default
   10: ocean/yet_another_channel/4km/default
   11: ocean/yet_another_channel/10km/default
```

If they don't show up, you probably missed a step (adding the test group to the
component or the task to the test group).  If you get import errors or
syntax errors, you'll need to fix those first.

If listing works out, it's time to set up one of your tasks.  Probably start
with one that's pretty light weight and fast to run.  In this case, that's the
10 km `default` (test number 11):

```bash
$ polaris setup -n 11 -p <E3SM_component> -w <work_dir>
```
See {ref}`dev-polaris-setup` for the details.  If that works, you're ready to
do a test run.  If you get errors during setup, you have some debugging to do.

You can run the test with a job script or an interactive node.  For debugging,
the interactive node is usually more efficient.  To run the task, open a
new terminal, go to the work directory, start an interactive session on
however many nodes you need (most often 1 when you're just debugging something
small) and for a long enough time that your debugging doesn't get interrupted,
e.g. on Chrysalis:
```bash
$ cd <work_dir>
$ source load_polaris_env.sh
$ srun -N 1 -t 2:00:00 --pty bash
```

Let's navigate into the task directory and see what it looks like:
```
$ cd ocean/yet_another_channel/10km/default
$ ls
default.cfg  load_polaris_env.sh   init  job_script.sh      task.pickle
```
If we open up `default.cfg` we can see that it contains our newly added
`yet_another_channel` section along with a bunch of other sections. Let's go to
the `task` section, where you will see `steps_to_run = init`.
This means that when we run our case, the initial condition should be generated
if we didn't make any mistakes in setting up the step (fingers crossed!).

Then, on the interactive node, source the local link the load script and run:
```bash
$ source load_polaris_env.sh
$ polaris serial
```

Now let's see what's in the `init` directory:
```
$ cd init
$ ls
base_mesh.nc               default.cfg                initial_state.nc
culled_graph.info          initial_normalVelocity.png initial_temperature.png
culled_mesh.nc             initial_salinity.png       step.pickle
```
Our `initial_state.nc` file is there for use in running MPAS-Ocean in the next
step. Let's also take a look at the image files and make sure our initial
condition looks as expected.

(Later on, there will be a `polaris run` command that runs in task parallel,
and this should be the default way you run, but for now you can only run in
task-serial mode, where your tasks and steps run one after the other.)

One important aspect of this testing will be to change config options in the
work directory and make sure the task is modified in the expected way.  If
you change `lx` and `ly`, does the domain size change in the plots as expected?
What happens to the initial condition when you change the physical parameters?
How is the time step and simulation duration changed when you modify
`dt_per_km` and `btr_dt_per_km`? Obviously, these are only example of things
you might try to stress-test your own task.

## Adding the forward step

Now that we know that the first step seems to be working, we're ready to add
another. We will add a `forward` step for running the MPAS-Ocean model forward
in time from the initial condition created in `init`.  `forward`
will be a little more complicated than `init` as we get started.
We're going to start from the {py:class}`polaris.ocean.model.OceanModelStep`
subclass that descends from {py:class}`polaris.ModelStep`, which in turn
descends from `Step`.  `ModelStep` adds quite a bit of useful functionality
for steps that run E3SM model components (MALI, MPAS-Ocean or Omega) and
`OceanModelStep` adds on to that with some functionality specific to the ocean.
We'll explore some aspects of the functionality that each of these subclasses
brings in here, but there may be other capabilities that we don't cover here
that will be important for your tasks so it likely will be useful to have
a look at the general {ref}`dev-model` section and potentially the
ocean-specific {ref}`dev-ocean-model` section as well.  MALI steps will
likely descend from `ModelStep`, though there may be advantages in defining
a `LandiceModelStep` class in the future.

We start with a `Forward` class that descends from `OceanModelStep` and a
constructor with the name of the step.  This time, we also supply the target
number of MPI tasks (`ntasks`), minimum number of MPI tasks (`min_tasks`), and
number of threads (the `init` used the default of 1 task, 1 CPU per
task and 1 thread):

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.py
```
```python
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of "yet another
    channel" tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """
    def __init__(self, task, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1):
        """
        Create a new task

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to

        resolution : km
            The resolution of the task in km

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use
        """
        self.resolution = resolution
        super().__init__(task=task, name=name, subdir=subdir,
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

```

By default, the number of MPI tasks `ntasks` isn't specified yet, nor is the
minimum number of MPI tasks `min_tasks`.  If they aren't specified explicitly,
they will be computed algorithmically later on based on the number of cells in
the mesh, as well discuss below. There are also 3 parameters that are specific
to the functionality we anticipate adding to this step:
* `resolution` - the resolution of the step in km as we already discussed.

Next, we add inputs that are outputs from the `init` task:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.py
```
```{code-block} python
:emphasize-lines: 10-15

...

class Forward(OceanModelStep):

    ...

    def __init__(self, task, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1):

        ...

        self.add_input_file(filename='initial_state.nc',
                            target='../init/initial_state.nc')

        self.add_output_file(filename='output.nc')
```

(dev-tutorial-add-test-group-model-config-and-streams)=

### Defining model config options and streams

The E3SM components supported by polaris require both model config options
and streams definitions (namelist and streams files for MPAS components, and
yaml files for Omega, see {ref}`dev-model-yaml-namelists-and-streams`) to work
properly.  An important part of polaris' functionality is that it takes the
default model config options and E3SM component and modifies only those options
that are specific to the task to produce the final model config files used to
run the model.

In polaris, there are two main ways to set model config options and we will
demonstrate both in this task.  First, you can define a namelist or yaml
file with the desired values.  This is useful for model config options that are
always the same for this task and can't be changed based on config options
from the polaris config file.

In the ocean component, we want the same tasks to work with either Omega
or MPAS-Ocean.  We have decided to define model config options using the new
yaml file format that Omega will use, whereas the landice component of polaris
will use the namelist and streams files that MPAS components use.  This
tutorial will focus on the yaml format but the concepts will not be hugely
different for namelist and streams files.

Here is the `forward.yaml` file from the `baroclinic_channel` test group. We'll just copy it into our `yet_another_channel` test group:

```bash
$ cp ${POLARIS_HEAD}/polaris/ocean/tasks/baroclinic_channel/forward.yaml \
     ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/.
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.yaml
```
```yaml
mpas-ocean:
  time_management:
    config_run_duration: 00:15:00
  time_integration:
    config_dt: 00:05:00
  split_explicit_ts:
    config_btr_dt: 00:00:15
  io:
    config_write_output_on_startup: false
  hmix_del2:
    config_use_mom_del2: true
    config_mom_del2: 10.0
  bottom_drag:
    config_implicit_bottom_drag_coeff: 0.01
  cvmix:
    config_cvmix_background_diffusion: 0.0
    config_cvmix_background_viscosity: 0.0001
  streams:
    mesh:
      filename_template: initial_state.nc
    input:
      filename_template: initial_state.nc
    restart: {}
    output:
      type: output
      filename_template: output.nc
      output_interval: 0000_00:00:01
      clobber_mode: truncate
      contents:
      - tracers
      - xtime
      - normalVelocity
      - layerThickness
```

````{note}
For comparison, here is a typical landice namelist file:
```none
config_dt = '0001-00-00_00:00:00'
config_run_duration = '0002-00-00_00:00:00'
config_block_decomp_file_prefix = 'graph.info.part.'
```

And a streams file:
```xml
<streams>

<immutable_stream name="input"
                  filename_template="landice_grid.nc"/>

<immutable_stream name="restart"
                  type="input;output"
                  filename_template="rst.$Y.nc"
                  filename_interval="output_interval"
                  output_interval="0100-00-00_00:00:00"
                  clobber_mode="truncate"
                  precision="double"
                  input_interval="initial_only"/>

<stream name="output"
        type="output"
        filename_template="output.nc"
        output_interval="0001-00-00_00:00:00"
        clobber_mode="truncate">

    <stream name="basicmesh"/>
    <var name="xtime"/>
    <var name="normalVelocity"/>
    <var name="thickness"/>
    <var name="daysSinceStart"/>
    <var name="surfaceSpeed"/>
    <var name="temperature"/>
    <var name="lowerSurface"/>
    <var name="upperSurface"/>
    <var name="uReconstructX"/>
    <var name="uReconstructY"/>

</stream>


</streams>
```
````

There is also a shared `output.yaml` file for ocean tasks that makes sure
we get double-precision output (the default is single precision, which saves a
lot of space but isn't great for regression testing):

```yaml
mpas-ocean:
  streams:
    output:
      type: output
      precision: double
```


In the `forward` step, we add these namelists as follows:

```{code-block} python
:emphasize-lines: 9-12

...

class Forward(OceanModelStep):
    def __init__(self, task, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1):
        ...

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_yaml_file('polaris.ocean.tasks.yet_another_channel',
                           'forward.yaml')
```

The first argument to {py:meth}`polaris.ModelStep.add_yaml_file()` is the
python package where the namelist file can be found, and the second is the
file name.  Files within the polaris package can't be referenced directly
with a file path but rather with a package like in these examples.

The model config options will start with the default set for the E3SM
component, provided along with the model executable at the end of compilation.
For MPAS-Ocean and MALI, this will be in
`default_inputs/namelist.<component>.forward`.  (For Omega, this has yet to
be determined.)  Each time a yaml or namelist file is added to a step, the
model config options changed in that file will override the previous values.
So the order of the files may matter if the same model config options are
changed in multiple files in polaris.

Streams are handled a little differently.  Again, the starting point is a set
of defaults from the E3SM components, such as
`default_inputs/streams.<component>.forward`.  But in this case, streams are
only included in the step if they are referenced in one of the yaml or streams
files added to it.  If you want the default definition of a stream, referring
to it is enough:

```yaml
mpas-ocean:
  streams:
    restart: {}
```

If you want to change one of its attributes but not its contents, you can do
that:
```yaml
mpas-ocean:
  streams:
    input:
      filename_template: initial_state.nc
```
Other attributes will remain as they are in the defaults.  You can
change the contents (the variables or arrays) of a stream in addition to the
attributes.  In this case, the contents you provide will replace the default
contents:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.yaml
```
```yaml
mpas-ocean:
  ...
  streams:
    output:
      type: output
      filename_template: output.nc
      output_interval: 0000_00:00:01
      clobber_mode: truncate
      contents:
      - tracers
      - xtime
      - normalVelocity
      - layerThickness
```
Finally, you can add completely new streams that don't exist in the default
model config files to a step by defining all of the relevant streams attributes
and contents.  We don't demonstrate that in this tutorial.

### Adding the `forward` step to the task

Returning to the `default` task, we are now ready to add
`initial_state` and `forward` steps to the task.  In
`polaris/ocean/tasks/yet_another_channel/default/__init__.py`, we add:

```{code-block} python
:emphasize-lines: 2, 13-15

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.forward import Forward
from polaris.ocean.tasks.yet_another_channel.init import Init


class Default(Task):
    def __init__(self, test_group, resolution):
        ...

        self.add_step(
            Init(task=self, resolution=resolution))

        self.add_step(
            Forward(task=self, ntasks=4, min_tasks=4, openmp_threads=1,
                    resolution=resolution))
```

We hard-code the `forward` task to run on 4 cores and 1 thread, and do
not pass a viscosity (meaning it will use the default value from
`forward.yaml`).

### Adding more validation

Just as we did with the initial state in {ref}``,
we want to add validation of the result of the forward run:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```python
from polaris import Task
from polaris.validate import compare_variables


class Default(Task):
    def validate(self):
        """
        Compare ``temperature``, ``salinity`` and ``layerThickness`` in
        both ``init`` and ``forward`` steps, and ``normalVelocity``
        in the ``forward`` step with a baseline if one was provided.
        """
        super().validate()

        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')

        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='forward/output.nc')
```
We check salinity, temperature,  layer thickness and normal velocity in the
forward step.  Again, we only provide `filename1` in each call to
{py:func}`polaris.validate.compare_variables()` so validation will only be
performed if a user has set up the task with a baseline.

### Test the task again!

We're ready to run some more tests just like we did in
{ref}`dev-tutorial-add-test-group-testing-a-step`.  Again, we'll start with
`polaris list` to make sure that works fine and the tasks still show
up.  Then, we'll set up the task with `polaris setup` as before.  Next,
we will go to the task's work directory and use `polaris serial`
(likely on an interactive node) to make sure the task runs both steps
we've added so far.

## Adding a visualization step

We'll add one more step to make some plots after the forward run has finished.
Here is the contents of `viz.py`:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/viz.py
```
```python
import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.viz import plot_horiz_field


class Viz(Step):
    """
    A step for plotting the results of a series of RPE runs in the "yet another
    channel" test group
    """
    def __init__(self, task):
        """
        Create the step

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to
        """
        super().__init__(task=task, name='viz')
        self.add_input_file(
            filename='initial_state.nc',
            target='../init/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            target='../forward/output.nc')

    def run(self):
        """
        Run this step of the task
        """
        ds_mesh = xr.load_dataset('initial_state.nc')
        ds = xr.load_dataset('output.nc')
        t_index = ds.sizes['Time'] - 1
        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'final_temperature.png', t_index=t_index)
        max_velocity = np.max(np.abs(ds.normalVelocity.values))
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'final_normalVelocity.png',
                         t_index=t_index,
                         vmin=-max_velocity, vmax=max_velocity,
                         cmap='cmo.balance', show_patch_edges=True)
```

It makes images of the final temperature and normal velocity from a forward
step.  Since all the pieces of this step have been covered in the other 2
steps, we won't describe this step in any more detail.

### Adding the `viz` step to the task

We're now ready to add the `viz` step to the `default` task:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/default/__init__.py
```
```{code-block} python
:emphasize-lines: 4, 18-19

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.forward import Forward
from polaris.ocean.tasks.yet_another_channel.init import Init
from polaris.ocean.tasks.yet_another_channel.viz import Viz


class Default(Task):
    def __init__(self, test_group, resolution):
        ...

        self.add_step(
            Init(task=self, resolution=resolution))

        self.add_step(
            Forward(task=self, ntasks=4, min_tasks=4, openmp_threads=1,
                    resolution=resolution))

        self.add_step(
            Viz(task=self))
```

### Test the task one more time!

And it's time to test things out one more time, now with all 3 steps. Again,
follow the procedure as in
{ref}`dev-tutorial-add-test-group-testing-a-step`:
* `polaris list` to make sure you can list the tasks
* `polaris setup` to set them up again (maybe in a fresh work directory)
* go to the task's work directory
* on an interactive node, run `polaris serial`.

(dev-tutorial-add-test-group-adding-second-test)=

## Adding a second task

Let's add one more task to see how that goes.  This will be a quick one.

The decomposition test we present here is pretty similar to the default test.
It starts with the same initial condition and does a forward run exactly like
`default`.

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/decomp/__init__.py
```

```python
import os

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.init import Init


class Decomp(Task):
    """
    A decomposition task for the baroclinic channel test group, which
    makes sure the model produces identical results on 1 and 4 cores.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, test_group, resolution):
        """
        Create the task

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to

        resolution : float
            The resolution of the task in km
        """
        name = 'decomp'
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)
        self.add_step(
            Init(task=self, resolution=resolution))
```

But then it does a second forward run on 8 cores instead of 4 and compares the
results to make sure they are identical.  Each of these runs is performed in
its own step.

```python
from polaris import Task
from polaris.ocean.tasks.yet_another_channel.forward import Forward

...


class Decomp(Task):
    def __init__(self, test_group, resolution):
        ...

        for procs in [4, 8]:
            name = f'{procs}proc'

            self.add_step(Forward(
                task=self, name=name, subdir=name, ntasks=procs,
                min_tasks=procs, openmp_threads=1,
                resolution=resolution))
```

Then, we validate temperature, salinity, layer thickness and normal velocity
to make sure they area all identical between the 4 and 8 core runs:

```python
from polaris import Task
from polaris.validate import compare_variables


class Decomp(Task):

    ...

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``4proc`` and ``8proc`` steps with each other
        and with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='4proc/output.nc',
                          filename2='8proc/output.nc')
```

Note that, unlike in the `default` task, we provide the `filename2`
parameter here so validation is performed even if we don't provide a baseline.
(If we do provide a baseline, both the 4 core and 8 core results will be
validated against their equivalents in the baseline as well.)

Finally, we add the new task to the test group:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/__init__.py
```

```python

from polaris.ocean.tasks.yet_another_channel.decomp import Decomp
from polaris.ocean.tasks.yet_another_channel.default import Default
from polaris import TestGroup


class YetAnotherChannel(TestGroup):
    """
    A test group for "yet another channel" tasks
    """

    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component,
                         name='yet_another_channel')

        for resolution in [1., 4., 10.]:
            self.add_test_case(
                Default(test_group=self, resolution=resolution))
            self.add_test_case(
                Decomp(test_group=self, resolution=resolution))
```

And we're ready to test once again!

(dev-tutorial-add-test-group-docs)=

## Documentation

Make sure to add some documentation of your new test group.  The documentation
is written in the [MyST](https://myst-parser.readthedocs.io/en/latest/syntax/typography.html)
flavor of Markdown, similar to what GitHub uses. See {ref}`dev-docs` for
details.

You need to add all of the public functions, classes and methods to the
{ref}`dev-api` in `docs/developers_guide/<component>/api.md`, following the
examples for other test groups.

You also need to add a file to both the user's guide and the developer's guide
describing the test group and its tasks and steps.

For the user's guide, make a copy of
`docs/users_guide/<component>/test_groups/template.md` called
`docs/users_guide/<component>/test_groups/<test_group>.md`.  In that file, you
should describe the test group and its tasks in a way that would be
relevant for a user wanting to run the task and look at the output.
This file should describe all of the config options relevant the test
group and each task (if it has its own config options), including what
they are used for and whether it is a good idea to modify them.  Add
`<test_group>` in the appropriate place (in alphabetical order) to the list
of test groups in the file `docs/users_guide/<component>/test_groups/index.md`.

For the developer's guide, create a file
`docs/developers_guide/<component>/test_groups/<test_group>.md`. In this file,
you will describe the test group, its tasks and steps in a way that is
relevant to developers who might want to modify the code or use it as an
example for developing their own tasks.  Currently, the descriptions are
brief in part because of the daunting task of documenting a large number of
tasks but should be fleshed out over time.  It would help new developers
if new test groups and tasks were documented well. Add `<test_group>` in
the appropriate place (in alphabetical order) to the list of test groups in
`docs/developers_guide/<component>/test_groups/index.md`.

At this point, you are ready to make a pull request with the new test group!

## Enhancements

This is the "bonus" section of the tutorial with some more advanced
capabilities.  These are still important for you to know about, since they
will give you added flexibility, improve code reuse, and introduce you to
more complex capabilities of polaris.  But they aren't strictly necessary for
you to get started.

### Adding model config options in code

In {ref}`dev-tutorial-add-test-group-model-config-and-streams`, we added
model config options using yaml and namelist files. Another way to set model
config options is to use a python dictionary and to call
{py:meth}`polaris.ModelStep.add_model_config_options()`.  This is the way
to handle namelist options that depend on parameters (such as resolution) that
are not known in advance.  In this case, we use this technique to set the
model config option for the viscosity `config_mom_del2` using a parameter
`nu` passed into the constructor (if it is not `None`, indicating that it was
not set):

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.py
```
```python

from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    def __init__(self, task, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1, nu=None):
        """
        ...
        nu : float, optional
            the viscosity (if different from the default for the test group)
        """
        ...

        if nu is not None:
            # update the viscosity to the requested value
            self.add_model_config_options(options=dict(config_mom_del2=nu))
```

### Adding dynamic model config options

Sometimes, you want to define model config options that should get set during
setup but then get updated at runtime in case config options that affect them
have been updated.  Here, we show example of 2 such "dynamic" model config
options, `dt` and `btr_dt`, the baroclinic and barotropic time steps in the
ocean model.  We also add a `run_time_steps` parameter and attribute to the
step so we can easily set up steps to run for a few time steps instead of a
fixed period of time.

To define dynamic model config options, override the
{py:meth}`polaris.ModelStep.dynamic_model_config()` method. Here, we will use
2 polaris config options, `dt_per_km` and `btr_dt_per_km`, to define the
ocean model time step and the duration of the simulation (if it was specified
as a number of times steps):

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.py
```
```python
import time

from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of "yet another
    channel" tasks.

    Attributes
    ----------
    ...
    dt : float
        The model time step in seconds

    btr_dt : float
        The model barotropic time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
    """
    def __init__(self, task, resolution, name='forward', subdir=None,
                 ntasks=None, min_tasks=None, openmp_threads=1, nu=None,
                 run_time_steps=None):
        """
        run_time_steps : int, optional
            Number of time steps to run for
        """
        ...
        self.run_time_steps = run_time_steps
        self.dt = None
        self.btr_dt = None

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        config = self.config

        options = dict()

        # dt is proportional to resolution: default 30 seconds per km
        dt_per_km = config.getfloat('yet_another_channel', 'dt_per_km')
        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        options['config_dt'] = \
            time.strftime('%H:%M:%S', time.gmtime(dt))

        if self.run_time_steps is not None:
            # default run duration is a few time steps
            run_seconds = self.run_time_steps * dt
            options['config_run_duration'] = \
                time.strftime('%H:%M:%S', time.gmtime(run_seconds))

        # btr_dt is also proportional to resolution: default 1.5 seconds per km
        btr_dt_per_km = config.getfloat('yet_another_channel', 'btr_dt_per_km')
        btr_dt = btr_dt_per_km * self.resolution
        options['config_btr_dt'] = \
            time.strftime('%H:%M:%S', time.gmtime(btr_dt))

        self.dt = dt
        self.btr_dt = btr_dt

        self.add_model_config_options(options=options)
```

The default values for the polaris config options are again found in
`yet_another_channel.cfg`:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/yet_another_channel.cfg
```
```cfg
# config options for "yet another channel" testcases
[yet_another_channel]

# time step per resolution (s/km), since dt is proportional to resolution
dt_per_km = 30

# barotropic time step per resolution (s/km), since btr_dt is proportional to
# resolution
btr_dt_per_km = 1.5
```

We don't do anything differently in `dynamic_model_config()` here whether it's
run at setup or at runtime.  The reason we run it twice is to update the model
config options in case the user modified `dt_per_km` or `btr_dt_per_km` in the
config file in the work directory before running the step.

### Computing the cell count

In the ocean component, we have infrastructure for determining good values
for `ntasks` and `min_tasks` (the reasonable range of MPI tasks that a forward
model step should use).  Using this infrastructure requires overriding the
{py:meth}`polaris.ocean.model.OceanModelStep.compute_cell_count()` method:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/tasks/yet_another_channel/forward.py
```
```python
...

class Forward(OceanModelStep):

    ...

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['yet_another_channel']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count
```
We need to estimate the size of the mesh so we have a good guess at the
resources it will need when we add it to a suite and make a job script for
running it.  Here, we use
{py:func}`polaris.mesh.planar.compute_planar_hex_nx_ny()` to get `nx` and `ny`
(and thus the total cell count) during setup because we have no other way to
get them.  When using task parallelism, we must use this approximation at
runtime, because we cannot rely on any tasks being completed to use as a basis
for computation.

`cell_count` is used in `OceanModelStep` to compute `ntasks` and `min_tasks`
by also using 2 config options:

```bash
$ vi ${POLARIS_HEAD}/polaris/ocean/ocean.cfg
```
```cfg
# Options related the ocean component
[ocean]

# the number of cells per core to aim for
goal_cells_per_core = 200

# the approximate maximum number of cells per core (the test will fail if too
# few cores are available)
max_cells_per_core = 2000

...
```

This method is only used if `ntasks` and `min_tasks` aren't explicitly defined
as parameters to the constructor.

So far, there isn't a equivalent process for MALI, so `ntasks` and `min_tasks`
should be set explicitly either when constructing a task or by overriding
the {py:meth}`polaris.Step.setup()` or
{py:meth}`polaris.Step.constrain_resources()` methods.


(dev-tutorial-add-test-group-add-shared-superclass)=

### Adding a shared "superclass" for tasks

As I started to add other tasks to `yet_another_channel`, it became clear
that there was going to be some redundant code that I copied from one to the
next.  This isn't great for future maintenance and it's kind of counter to
the philosophy of polaris.  So I decided to make a "superclass" with this
common code that all the `yet_another_channel` tasks can descend from.
Later, I removed some of the code from the superclass, so it turned out to not
be as helpful as I originally thought but I think it's still a helpful
demonstration. In general, if you find there are a lot of redundancies between
the different tasks you define, it might be a good idea to use a
superclass to handle that shared functionality in one place.

In this case, the superclass will take care of things like putting the test
case in a subdirectory based on the mesh resolution in km, storing the
resolution as an attribute, adding the initial-condition step, and
validating variables in that initial condition.  All of our tasks will
need these features so it's a little simpler to add them here.

In the file `yet_another_channel_test_case.py` in
`polaris/ocean/tasks/yet_another_channel`, we define the superclass
`YetAnotherChannelTestCase` that descends from {py:class}`polaris.Task`:

```python
import os

from polaris import Task
from polaris.ocean.tasks.yet_another_channel.init import Init
from polaris.validate import compare_variables


class YetAnotherChannelTestCase(Task):
    """
    The superclass for all "yet another channel" tasks with shared
    functionality

    Attributes
    ----------
    resolution : float
        The resolution of the task in km
    """

    def __init__(self, test_group, resolution, name):
        """
        Create the task, including adding the ``init`` step

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to

        resolution : float
            The resolution of the task in km

        name : str
            The name of the task
        """
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        self.add_step(
            Init(task=self, resolution=resolution))

    def validate(self):
        """
        Compare ``temperature``, ``salinity`` and ``layerThickness`` from the
        initial condition with a baseline if one was provided
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')

```

Now, we'll make `Default` descend from `YetAnotherChannelTestCase` and remove
the redundant pieces.  Here's what's left:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase
from polaris.ocean.tasks.yet_another_channel.forward import Forward
from polaris.ocean.tasks.yet_another_channel.viz import Viz
from polaris.validate import compare_variables


class Default(YetAnotherChannelTestCase):
    """
    The default task for the "yet another channel" test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
    """

    def __init__(self, test_group, resolution):
        """
        Create the task

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to

        resolution : float
            The resolution of the task in km
        """
        super().__init__(test_group=test_group, resolution=resolution,
                         name='default')

        self.add_step(
            Forward(task=self, ntasks=4, min_tasks=4, openmp_threads=1,
                    resolution=resolution))

        self.add_step(
            Viz(task=self))

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='forward/output.nc')

```

### Adding a parameter study

The typical structure for a parameter study is to explore each parameter choice
in a separate step (or steps) within a single task. In addition to running
the model for each of these parameter choices, there is typically a separate
step for analyzing the behavior across the parameter set, using the output from
each of the forward steps.

A convergence study is one example of this, where each resolution and time step
combination is run and then an analysis step computes the rate of convergence
from the results. We won't cover this example here, in part because a
resolution study involves both a forward step and an initial condition step for
each resolution in order to generate unique meshes for each step. You may refer
to {ref}`dev-ocean-cosine-bell` for these details. Instead,
we will explore the `rpe` for the `baroclinic_channel` test group, which
only requires unique forward runs for different viscosity values.

The `rpe` has been used to show that MPAS-Ocean has lower spurious
dissipation of reference potential energy (RPE) than POP, MOM and MITgcm models
([Petersen et al. 2015](https://doi.org/10.1016/j.ocemod.2014.12.004)).

We want to define the `rpe` at 3 "standard" resolutions that have been
used in previous testing: 1, 4 or 10 km.  The task consists of an
`init` step exactly like the `default` task, 5 variants of the
`forward` step with different values of the viscosity (a parameter study), and
an `analysis` step that is unique to this task (and thus not part of the
"framework" for the test group over all like the `init` and `forward`
steps).  Each `forward` step runs for much longer than in the `default` test
case (20 days, rather than 3 time steps).  This means that `rpe` isn't
appropriate for regression testing, since it is too time consuming to run.
Likewise, the higher resolutions (1 and 4 km) are fairly resource heavy, and
therefore not as well suit to quick testing.  But this task was the
original purpose of the test group as a whole, serving to validate the code in
a specific context.

In analogy to the `default` task, we will start by creating a directory
`rpe` within the `yet_another_channel` directory, adding a new file
`__init__.py`, and adding a class `Rpe` that descends from the
`YetAnotherChannelTestCase` base class:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase


class Rpe(YetAnotherChannelTestCase):
    """
    The reference potential energy (RPE) task for the "yet another channel"
    test group performs a 20-day integration of the model forward in time at
    5 different values of the viscosity at the given resolution.
    """

    def __init__(self, test_group, resolution):
        """
        Create the task

        Parameters
        ----------
        test_group : polaris.ocean.tasks.yet_another_channel.YetAnotherChannel
            The test group that this task belongs to

        resolution : float
            The resolution of the task in km
        """
        super().__init__(test_group=test_group, resolution=resolution,
                         name='rpe')
```

So far, this is identical ot the `default` task except for the name
and docstring changes.

Before we add steps, let's add the `rpe` task to the
`yet_another_channel` test group so we can compare it with the `default`
tet case. We add the following to the file `__init__.py` that defines the
`YetAnotherChannel` test group:

```{code-block} python
:emphasize-lines: 6, 21, 25-27

from polaris import TestGroup
from polaris.ocean.tasks.yet_another_channel.yet_another_channel_test_case import (  # noqa: E501
    YetAnotherChannelTestCase,
)
from polaris.ocean.tasks.yet_another_channel.default import Default
from polaris.ocean.tasks.yet_another_channel.rpe import Rpe


class YetAnotherChannel(TestGroup):
    """
    A test group for "yet another channel" tasks
    """
    def __init__(self, component):
        """
        component : polaris.ocean.Ocean
            the ocean component that this test group belongs to
        """
        super().__init__(component=component,
                         name='yet_another_channel')

        for resolution in [10.]:
            self.add_test_case(
                Default(test_group=self, resolution=resolution))

        for resolution in [1., 4., 10.]:
            self.add_test_case(
                Rpe(test_group=self, resolution=resolution))

```

We switch the `default` task to only support 10 km resolution but now have
the `rpe` task available at 3 resolutions.

#### Adding the steps to the task

The `init` step has already been added to `rpe` because that
happens in the `YetAnotherChannelTestCase` superclass.  Now, we will add the
variants of the `forward` step and the `analysis` step to the task.
Bear with me, as this is where things get a little complicated.

We want there to be a sequence of steps based on a config options
`viscosities`. By default this config options looks like:

```cfg
# config options for "yet another channel" testcases
[yet_another_channel]

...

# Viscosity values to test for rpe task
viscosities = 1, 5, 10, 20, 200
```

We want to set up the sequence of steps using these default values in the
constructor `__init__()`.  But then we want to account for the possibility that
a user has changed these values in a user config file before setting up the
task.  (It is too late to change these config options at runtime because
we need to know the viscosities at setup in order to name the steps.)
We will handle this with the following additions to
`polaris/ocean/tasks/yet_another_channel/rpe/__init__.py`:

```python
from polaris.config import PolarisConfigParser
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase
from polaris.ocean.tasks.yet_another_channel.forward import Forward


class Rpe(YetAnotherChannelTestCase):
    def __init__(self, test_group, resolution):
        super().__init__(test_group=test_group, resolution=resolution,
                         name='rpe')

        self._add_steps()

    def configure(self):
        """
        Modify the configuration options for this task.
        """
        super().configure()
        self._add_steps(config=self.config)

    def _add_steps(self, config=None):
        """ Add the steps in the task either at init or set-up """

        if config is None:
            # get just the default config options for yet_another_channel so
            # we can get the default viscosities
            config = PolarisConfigParser()
            package = 'polaris.ocean.tasks.yet_another_channel'
            config.add_from_package(package, 'yet_another_channel.cfg')

        for step in list(self.steps):
            if step.startswith('rpe') or step == 'analysis':
                # remove previous RPE forward or analysis steps
                self.steps.pop(step)

        resolution = self.resolution

        nus = config.getlist('yet_another_channel', 'viscosities', dtype=float)
        for index, nu in enumerate(nus):
            name = f'rpe_{index + 1}_nu_{int(nu)}'
            step = Forward(
                task=self, name=name, subdir=name,
                ntasks=None, min_tasks=None, openmp_threads=1,
                resolution=resolution, nu=float(nu))

            step.add_yaml_file(
                'polaris.ocean.tasks.yet_another_channel.rpe',
                'forward.yaml')
            self.add_step(step)
```

We use the same private method `_add_steps()` to add steps in `__init__()` and
`configure()` (during setup).  In the first case, we don't have a config file
top pass along.  In the second case, we do.

Breaking the `_add_steps()` method up, we start by reading in the default
config options if this is getting called from `__init__()` so they're not
available yet from `self.config`:

```python
from polaris.config import PolarisConfigParser
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase


class Rpe(YetAnotherChannelTestCase):
    def _add_steps(self, config=None):
        if config is None:
            # get just the default config options for yet_another_channel so
            # we can get the default viscosities
            config = PolarisConfigParser()
            package = 'polaris.ocean.tasks.yet_another_channel'
            config.add_from_package(package, 'yet_another_channel.cfg')
```

This is a kind of unusual circumstance (unique to parameter studies) and the
reason that we go through all this trouble is to make sure we can list the
steps in the task:

```
$ polaris list --verbose
...
   1: path:          ocean/yet_another_channel/1km/rpe
      name:          rpe
      component:     ocean
      test group:    yet_another_channel
      subdir:        1km/rpe
      steps:
       - init
       - rpe_1_nu_1
       - rpe_2_nu_5
       - rpe_3_nu_10
       - rpe_4_nu_20
       - rpe_5_nu_200

```
We only know that there are 5 viscosities for the 5 forward steps `rpe_*`
and what the viscosity values are by reading the config file.

Next, if this is the second time calling `self._setup_steps()` from
`configure()` we need to remove the steps we added before so we can add them
again in case the list of viscosities has changed.  We don't want to remove
the `init` step added by `YetAnotherChannelTestCase` so we will
only remove steps that start with `rpe`.  To remove an item from a
dictionary, you use {py:meth}`dict.pop()`:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase


class Rpe(YetAnotherChannelTestCase):
    def _add_steps(self, config=None):
        for step in list(self.steps):
            if step.startswith('rpe'):
                # remove previous RPE forward steps
                self.steps.pop(step)
```

Okay, now we're ready to actually add the steps:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase
from polaris.ocean.tasks.yet_another_channel.forward import Forward


class Rpe(YetAnotherChannelTestCase):
    def _add_steps(self, config=None):
        ...
        resolution = self.resolution

        nus = config.getlist('yet_another_channel', 'viscosities', dtype=float)
        for index, nu in enumerate(nus):
            name = f'rpe_{index + 1}_nu_{int(nu)}'
            step = Forward(
                task=self, name=name, subdir=name,
                ntasks=None, min_tasks=None, openmp_threads=1,
                resolution=resolution, nu=float(nu))

            step.add_yaml_file(
                'polaris.ocean.tasks.yet_another_channel.rpe',
                'forward.yaml')
            self.add_step(step)
```
The names of the steps and the number of steps are determined by `nus`.

We also add another file with model config options and streams specific to
this task, `rpe/forward.yaml`:
```yaml
ocean:
  time_management:
    config_run_duration: 20_00:00:00
mpas-ocean:
  streams:
    output:
      type: output
      filename_template: output.nc
      output_interval: 0000-00-01_00:00:00
      clobber_mode: truncate
      contents:
      - tracers
      - xtime
      - density
      - daysSinceStartOfSim
      - relativeVorticity
      - layerThickness
```
We want to run each step for 20 days, outputting the list of variables above
every day.

#### Adding the analysis step

The `rpe` includes another step, `analysis` that plots results from
each simulation.  The full analysis step looks like this:

```python
import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris import Step
from polaris.ocean.rpe import compute_rpe


class Analysis(Step):
    """
    A step for plotting the results of a series of RPE runs in the "yet another
    channel" test group

    Attributes
    ----------
    nus : list
        A list of viscosities
    """
    def __init__(self, task, resolution, nus):
        """
        Create the step

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to

        resolution : float
            The resolution of the task in km

        nus : list
            A list of viscosities
        """
        super().__init__(task=task, name='analysis')
        self.nus = nus

        self.add_input_file(
            filename='initial_state.nc',
            target='../init/initial_state.nc')

        for index, nu in enumerate(nus):
            self.add_input_file(
                filename=f'output_{index + 1}.nc',
                target=f'../rpe_{index + 1}_nu_{int(nu)}/output.nc')

        self.add_output_file(
            filename=f'sections_yet_another_channel_{resolution}.png')
        self.add_output_file(filename='rpe_t.png')
        self.add_output_file(filename='rpe.csv')

    def run(self):
        """
        Run this step of the task
        """
        section = self.config['yet_another_channel']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        init_filename = self.inputs[0]
        rpe = compute_rpe(initial_state_file_name=init_filename,
                          output_files=self.inputs[1:])
        with xr.open_dataset(init_filename) as ds_init:
            nx = ds_init.attrs['nx']
            ny = ds_init.attrs['ny']
        _plot(nx, ny, lx, ly, self.outputs[0], self.nus, rpe)


def _plot(nx, ny, lx, ly, filename, nus, rpe):
    """
    Plot section of the "yet another channel" at different viscosities

    Parameters
    ----------
    nx : int
        The number of cells in the x direction

    ny : int
        The number of cells in the y direction (before culling)

    lx : float
        The size of the domain in km in the x direction

    ly : int
        The size of the domain in km in the y direction

    filename : str
        The output file name

    nus : list
        The viscosity values

    rpe : numpy.ndarray
        The reference potential energy with size len(nu) x len(time)
    """

    ...
```
where the details of the `_plot()` function have been left out for
compactness (and because it uses an approach to plotting that is a bit
quick-and-dirty that we don't want other test groups to adopt).  The `_plot()`
function needs the results from each forward step's `output.nc` file as inputs
as well as the size of the domain from the `lx` and `ly` config options and the
number of grid cells `nx` and `ny` from attributes of the initial condition.
It plots the results together in a single image that it writes out.

We add the `analysis` step to the task as follows:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase
from polaris.ocean.tasks.yet_another_channel.rpe.analysis import Analysis


class Rpe(YetAnotherChannelTestCase):
    def _add_steps(self, config=None):
        ...
        for step in list(self.steps):
            if step.startswith('rpe') or step == 'analysis':
                # remove previous RPE forward or analysis steps
                self.steps.pop(step)

        ...
        self.add_step(
            Analysis(task=self, resolution=resolution, nus=nus))
```
Note that we have also taken care to remove the previous version of `analysis`
along with the forward tests before adding new versions if `_add_steps()` is
getting called for the second time from `configure()`.

#### Adding validation

Adding validation to the `rpe` is very similar to `default`.  The only
difference is that we need to do it once for each forward test:

```python
from polaris.ocean.tasks.yet_another_channel import YetAnotherChannelTestCase
from polaris.validate import compare_variables


class Rpe(YetAnotherChannelTestCase):
    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()

        config = self.config
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']

        nus = config.getlist('yet_another_channel', 'viscosities', dtype=float)
        for index, nu in enumerate(nus):
            name = f'rpe_{index + 1}_nu_{int(nu)}'
            compare_variables(task=self, variables=variables,
                              filename1=f'{name}/output.nc')
```

### How to (and how not to) pass data between steps

In developing `yet_another_channel`, we initially used config options to pass
parameters `nx`, `ny`, and `dc` between steps.  They were computed and set in
the shared `YetAnotherChannelTestCase` in its `configure()` method.  This
turned out not to be a good idea and we wanted to share the lessons learned
because they may be useful to other developers.

It turned out to be confusing to set `nx`, `ny`, and `dc` as config options.
First, these were not actually config options that a user should modify.
Instead, they depend on `lx`, `ly`, and `resolution`.  Users can choose `lx`
and `ly` as config options, and `resolution` by selecting different variants
of a task (if we've made multiple resolutions available).  It would be
tricky to communicate this nuance to a user: you can change `lx` and `ly` but
not `nx`, `ny`, and `dc`, which are "fake" config options.

Second, we were computing `nx`, `ny` and `dc` too soon.  By computing them in
`configure()`, we are using the versions of the `lx` and `ly` config options
available at setup, but a user might change them before running the task.
It would be very confusing to them if the changes they made didn't affect `nx`,
`ny` and `dc`.  We could have worked around this by re-computing `nx`, `ny` and
`dc` at runtime but this wasn't worth the trouble because of the first problem:
these aren't really config options.

Instead, the solution turned out to be two-fold.  First, we made a function for
computing `nx` and `ny` for uniform, hexagonal meshes from `lx`, `ly` and
`resolution`.  We decided this should be in the polaris framework rather than
in the test group because it might be useful to others. Second, we stored `nx`,
`ny` and `dc` as global attributes in the initial condition file.  This is
the "proper" way of passing data between steps in polaris: through files.
Third, we changed any parts of the code that were previously getting `nx` and
`ny` from config options to instead either use the new
{py:func}`polaris.mesh.planar.compute_planar_hex_nx_ny()` or to get them from
the attributes of the initial condition file.

Please keep this in mind in your own tasks.  Config options are a good way
to document constants in your task that would otherwise be hard-coded
magic numbers.  They are also a good place to put parameters that you really
do expect a user to want to change.  You should document which are which so
a user knows which are a good idea to change and which are "change at your own
risk".  But you should not put in config options that are overridden in the
code, so that a user changing them actually doesn't do anything.  And you
shouldn't use config options for the primary purpose of passing data between
steps.
