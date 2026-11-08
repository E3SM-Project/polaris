# Adding a First Task

In this section, we'll add the first actual task to our new category, following
the structure of the `overflow` default test. We'll create a
`default` task that sets up the mesh for now but will eventually also create
an initial condition, runs a short forward integration, and generates a plot
for quick inspection.

## Adding a `default` Task

We'll add a task called `default` to `my_overflow` by making a
`default` package within `polaris/tasks/ocean/my_overflow`. First,
create the directory and an empty `__init__.py` file:

```bash
$ mkdir polaris/tasks/ocean/my_overflow/default
$ touch polaris/tasks/ocean/my_overflow/default/__init__.py
```

Now, let's create the `Default` class in this file. This class should inherit
from `polaris.Task` and add the necessary steps (`init` for now, more to come
later in the tutorial). The constructor should take `component` and any shared
steps (`init` in this case).  It is frequently useful to include other
parameters like a directory the task will live in (`indir`) and any other
parameters (like the grid `resolution`) that may distinguish different
versions of the task from one another.  Here's our example:

```python
from polaris import Task as Task


class Default(Task):
    """
    The default "my overflow" test case simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.
    """

    def __init__(self, component, indir, init):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.ocean.my_overflow.init.Init
            A shared step for creating the initial state
        """
        task_name = 'default'
        super().__init__(component=component, name=task_name, indir=indir)

        self.add_step(init, symlink='init')
```

## Adding the Task to the Component

Update your `add_my_overflow_tasks()` function in
`polaris/tasks/ocean/my_overflow/__init__.py` to create and add the
`Default` task for each supported resolution, similar to how it is done in
`overflow`:

```{code-block} python
:emphasize-lines: 2, 21-24
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.my_overflow.default import Default as Default
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

    default = Default(component=component, indir=indir, init=init_step)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)
```

---

← [Back to *Adding a Shared Step*](adding_shared_step.md)

→ [Continue to *Testing the First Task and Step*](testing_first_task.md)
