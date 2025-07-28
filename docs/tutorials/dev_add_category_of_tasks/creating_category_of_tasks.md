# Making a New Category of Tasks

This page walks you through creating a new category of tasks in Polaris, using
the ocean component as an example. In Polaris, a "category of tasks" is simply
a set of related tasks grouped in a Python package (subdirectory) within a
component's `tasks` directory.

Use any method you like for editing code. If you haven't settled on a method
and are working on your own laptop or desktop, you may want to try an
integrated development environment ([VS Code](https://code.visualstudio.com/)
is a really nice one). These tools help ensure your code adheres to the style
required for Polaris (see {ref}`dev-style`). `vim` or a similar tool will work
fine on supercomputers (though VS Code can also be used via ssh).

To create a new category of tasks, start by making a new subdirectory under the
appropriate component's `tasks` directory. For example, to create a new group
called `my_overflow` for the ocean component, create the following
directory:

```bash
$ mkdir polaris/tasks/ocean/my_overflow
$ touch polaris/tasks/ocean/my_overflow/__init__.py
```

Next, add a function to `__init__.py` that will be used to add all the tasks
in this category to the component. This function should be named
`add_<my_category>_tasks()` and take the component as an argument. For now, it
can just `pass` since we haven't created any tasks yet:

```python
def add_my_overflow_tasks(component):
    """
    Add a task following the "my overflow" test case of Petersen et al. (2015)
    doi:10.1016/j.ocemod.2014.12.004

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    pass
```

Later, as you add tasks, you will update this function to instantiate and add
each task to the component using `component.add_task()`.

This function needs to be called from the component's `add_tasks.py` module to
register all tasks in this category.

```{code-block} python
:emphasize-lines: 5, 21

...
from polaris.tasks.ocean.manufactured_solution import (
    add_manufactured_solution_tasks as add_manufactured_solution_tasks,
)
from polaris.tasks.ocean.my_overflow import add_my_overflow_tasks
from polaris.tasks.ocean.overflow import add_overflow_tasks
...

def add_ocean_tasks(component):
    """
    Add all ocean-related tasks to the ocean component.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which tasks will be added.
    """
    # planar tasks
    ...
    add_manufactured_solution_tasks(component=component)
    add_my_overflow_tasks(component=component)
    add_overflow_tasks(component=component)
    ...

```
We keep categories of tasks sorted first by planar, single column or
spherical mesh types, then alphabetically within these categories.

Naming conventions in Python are that we use
[CamelCase](https://en.wikipedia.org/wiki/Camel_case) for classes (which always
start with a capital letter), and all lowercase, possibly with underscores,
for variable, module, package, function, and method names. We avoid all-caps
like `MPAS`, even though this might seem preferable. (We use `E3SM` in a few
places because `E3sm` looks really awkward.)

You are encouraged to add docstrings (enclosed in `"""`) to briefly document
classes, methods, and functions as you write them. We use the
[numpydoc](https://numpydoc.readthedocs.io/en/latest/format.html) style
conventions, as described in {ref}`dev-docstrings`.

That's all you need to do to set up a new category of tasks! In the next
steps, you'll add actual task classes and update your
`add_my_overflow_tasks()` function to register them with the
component.


## Test it out

There's not too much to test so far, but you can make sure you can run:

``` bash
polaris list
```

If you don't have access to the `polaris` command, you probably need to source
the load script, something like:
``` bash
source load_dev_polaris_0.1.0-alpha.3_chrysalis_intel_openmpi.sh
```

If `polaris list` gives you import errors, something isn't quite hooked up
right.  You shouldn't expect to see anything new yet because we haven't added
a task yet.

## Commit the Changes

It is a good idea to commit frequently during development.  You can always
use `git rebase` later to clean things up and consolidate commits that belong
together.  One advantage of committing frequently is that your code will be
linted and formatted using several tools such as `ruff check`, `ruff format`
and `mypy` as you go.  These tools help to keep a consistent style throughout
Polaris and catch many types of errors before you run the code. See
{ref}`dev-polaris-style`.

---

← [Back to *Getting Started*](getting_started.md)

→ [Continue to *Adding a Shared Step*](adding_shared_step.md)
