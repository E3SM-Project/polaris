(dev-imports)=

# Imports and start-up time

What a `polaris` command costs is mostly the Python modules it imports, so
Polaris imports only what a command needs.  `import polaris` imports only the
standard library and `tranche`, `polaris list` imports no tasks, and
`polaris setup` imports only the task groups of the tasks it sets up.

(dev-deferred-imports)=

## Deferred imports

A module that uses a third-party package only inside functions defers it with
{py:func}`polaris.lazy.lazy_module()` or {py:func}`polaris.lazy.lazy_attr()`.
The real import stays under `if TYPE_CHECKING:`, so mypy and IDEs still see
it:

```python
from typing import TYPE_CHECKING

from polaris.lazy import lazy_attr, lazy_module

if TYPE_CHECKING:
    import numpy as np
    import xarray as xr
    from mpas_tools.io import write_netcdf
else:
    np = lazy_module('numpy')
    xr = lazy_module('xarray')
    write_netcdf = lazy_attr('mpas_tools.io', 'write_netcdf')
```

The package is imported the first time the name is used, and from then on the
name is the real module or function.

An import made only for its side effects, such as `import cmocean` to register
its colormaps, uses {py:func}`polaris.lazy.lazy_side_effect()`, which imports
it when any other deferred name in the module is first used:

```python
if TYPE_CHECKING:
    import cmocean  # noqa: F401
    import matplotlib.pyplot as plt
else:
    lazy_side_effect('cmocean')
    plt = lazy_module('matplotlib.pyplot')
```

An import stays eager when its name is used while the module is imported: as
a base class, a decorator, a default argument, or in a module-level constant.
Where it is easy, move that use into a function instead, or use `math`
rather than `numpy` for a constant.

You don't need to write these blocks by hand.  Write ordinary imports, then
run the conversion script from the root of the branch:

```bash
python utils/defer_imports/defer_imports.py polaris
pre-commit run --all-files
```

It only changes modules with eager third-party imports that can be deferred,
and `--check` lists them without changing anything.  When rebasing a branch
whose imports conflict with converted ones, take the branch's version of the
import block and run the script again.

`polaris parallel` calls {py:func}`polaris.lazy.load_all()` before it starts
any steps, so each package is imported once rather than once in every step it
forks.

(dev-task-manifest)=

## The task manifest

`polaris list` and `polaris setup` read the tasks from
`polaris/task_manifest.json` rather than building them.  It records each
task's path, name, component, subdirectory and steps, and the task group that
adds it (see {ref}`dev-components`).  Git ignores the file.

The manifest is rebuilt automatically whenever any `.py`, `.cfg` or `.yaml`
file in the `polaris` package has changed, so a new or changed task appears in
`polaris list` straight away.  The first command after a change pays for the
rebuild, which builds every task.

`polaris setup` and `polaris suite` look up the task group of each task they
set up and build only those groups.  This requires that a task group gives the
same tasks and steps whether or not other task groups have been built.  In
particular, a step shared between task groups must not depend on which of them
creates it.  Steps created with
{py:meth}`polaris.Component.get_or_create_shared_step()` always write the
pickle that dependent steps read, for this reason.
