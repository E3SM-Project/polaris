# Import performance

Creation date: 2026/09/10

Contributors: Xylar Asay-Davis, Claude

## Summary

What a `polaris` command costs is the number of Python modules it imports,
and today every command imports nearly all of them.  `polaris list` imports
2,839 modules; setting up one ocean task imports 2,647, because building any
ocean task builds all 193.  On a loaded Chrysalis login node both take about
21 s, and on an idle compute node 16 to 18 s.  Polaris' own 353 modules are
9% of that; the rest is the scientific Python stack, pulled in by Polaris'
module-scope imports.

This design has each command import only what it names.  `polaris list`
reads a cached manifest and imports nothing.  `polaris setup` imports one
task group.  The framework core imports only the standard library.  A
prototype that reproduces `polaris list -v` byte for byte gives, on the same
loaded login node:

| | today | with this design |
| --- | --- | --- |
| `polaris list` | 21.1 s | 0.05 s |
| set up one ocean task | 21.8 s | 1.0 s |
| `import polaris` | 4.0 s | 0.09 s |

Deferring an import need not cost readability.  Under
`if TYPE_CHECKING: import numpy as np` with `np = lazy_module('numpy')` in
the `else`, the name, its source and its type all stay visible: mypy still
checks calls against real numpy, and IDE navigation still resolves.  That
cost is what made deferral unattractive, and it is avoidable.

Separately, `import numpy` starts one BLAS thread per core and burns about
15 s of CPU, including inside a one-core Slurm job step.  The entry point
pins the thread count before numpy loads.

## Requirements

### Requirement: `polaris list` returns immediately.

### Requirement: Setting up a task builds only that task.

### Requirement: Starting Polaris is cheap.

`import polaris` should cost about what starting Python costs.

### Requirement: Polaris does not claim CPU it will not use.

## Implementation

### Implementation: Deferred imports keep their declarations.

`polaris/lazy.py` provides `lazy_module` and `lazy_attr`.  A module that
uses a heavy third-party package at run time but not at import time binds it
through the helper, with the real import under `if TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING

from polaris.lazy import lazy_attr, lazy_module

if TYPE_CHECKING:
    import numpy as np
    import xarray as xr
    from mpas_tools.ocean.viz.transect import compute_transect
else:
    np = lazy_module('numpy')
    xr = lazy_module('xarray')
    compute_transect = lazy_attr(
        'mpas_tools.ocean.viz.transect', 'compute_transect'
    )
```

This applies to 152 of Polaris' 354 modules, 95 of them under
`polaris/tasks/`.  The conversion is mechanical and was done by an AST
script for the prototype; it should land as a scripted commit, reviewed as a
whole rather than file by file.

A module that uses one of these names at module scope keeps its eager
import, or moves the work into a function.  `polaris/viz/helper.py` builds
its `projections` dict from `cartopy.crs` attributes while importing, so it
gains nothing from a proxy until that dict is built on demand.

> **Rationale.**  This is what removes matplotlib, cartopy, cmocean,
> networkx, igraph, dask and jigsawpy from the task tree entirely.  The
> ocean component falls from 2,647 modules to 1,434, and one ocean task
> group from 2,647 to 467.  mypy still reports `Module has no attribute` for
> a misspelled numpy name under the `TYPE_CHECKING` form.

### Implementation: Setting up a task builds only that task group.

The registry has two levels.  `polaris/tasks/__init__.py` maps each
component name to the module that defines it and the module that adds its
tasks, and imports neither.  Each component's `add_tasks.py` maps each task
group name to its module and registration function.  `get_components` and
`add_<component>_tasks` both take an optional list of names and build only
those.

The manifest below records which task group produced each task path, so
`polaris setup -t <path>` and `polaris setup -n <number>` resolve to a task
group without importing anything.  `polaris suite` builds the union of the
groups its suite file names.

The mapping has to come from the manifest rather than from the path.  A task
group's name is not a prefix of the paths it produces: the ocean
`single_column` group produces `ocean/column/ekman` and five siblings, and
`ocean/column/` also holds four tasks from the `horiz_press_grad` group.

The registry records that `mesh` depends on `e3sm/init`, and builds
dependencies first.  `add_mesh_tasks` adds steps to the E3SM-init component,
so building `mesh` first adds the same shared config twice and raises from
`Component.add_config`.

> **Rationale.**  One ocean task group is 467 modules and 1.0 s, against
> 2,647 and 21.8 s for the whole component.  Building groups one at a time
> against a fresh component reproduces the same tasks: `baroclinic_channel`,
> `single_column`, `cosine_bell`, `internal_wave`, `overflow` and `seamount`
> give 9, 6, 16, 4, 21 and 8 tasks in isolation, and the same paths appear
> in `polaris list` today.

### Implementation: `polaris list` reads a task manifest.

The manifest is JSON: for each task, its path, name, component, subdir,
steps and task group.  For the current 274 tasks it is 221 kB.

Its key is a SHA-256 over `(path, mtime, size)` for every `.py`, `.cfg` and
`.yaml` file under `polaris/`, collected with `os.scandir`.  When the key
does not match, Polaris rebuilds the manifest and writes it back, so a
developer who adds a task never sees a stale list.

> **Rationale.**  Reading the manifest costs 2 ms and checking the key costs
> 11 ms once the filesystem metadata is warm, against 21.1 s to build the
> tasks.  A cold check on a loaded login node costs up to 3 s, which is the
> price of the first `polaris list` in a session.  Collecting the same
> information with one `os.stat` per file instead of `os.scandir` costs 1 s
> warm, so the traversal has to be written this way.

### Implementation: Starting Polaris is cheap.

`polaris/__init__.py` and every module reachable from it import only the
standard library and `tranche`.  That covers `component`, `step`, `task`,
`model_step`, `config`, `io`, `yaml`, `streams`, `validate` and `namelist`.
`polaris/__main__.py` maps each command name to a module path and imports
that module after parsing.

> **Rationale.**  One line in `polaris/component.py`,
> `from mpas_tools.io import open_dataset, write_netcdf`, pulls in xarray,
> pandas, pyarrow, netCDF4 and numpy for two names used in one method each.
> `import polaris` falls from 999 modules to 148.

### Implementation: Thread limits are set before numpy loads.

The `polaris` entry point sets `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS` and `NUMEXPR_NUM_THREADS` to 1 when they are unset, before
importing anything else.  A user who exports a different value keeps it.
`Step.openmp_threads` already defaults to 1 and `Component.run_model()`
passes its value in the environment it hands the model, so no model run sees
a change.

> **Rationale.**  `import numpy` on a 128-core node costs 0.12 s of CPU
> pinned and 15.1 s unpinned.  A one-core `srun` step does not restrain it:
> `import polaris` inside `srun -n1 -c1` still burns 14.9 s of CPU.  Under
> task parallelism that CPU comes out of Polaris' own concurrent steps.

### Commit series

1. Defer the heavy imports in the eleven framework modules, and dispatch
   subcommands by module path.
2. Set the thread limits in the entry point.
3. Add `polaris/lazy.py` and the guard test for the framework core.
4. Convert the 152 modules, by script, in one commit.
5. Add the two-level registry and pass names from `setup_tasks` and
   `polaris suite`.
6. Add the manifest, its key and its rebuild path.
7. Document the `TYPE_CHECKING` form in the developer's guide, next to the
   existing import style rule, which needs an exception for it.

## Testing

Three guard tests hold the requirements.  The first imports `polaris` in a
subprocess and asserts the deferred packages are absent from `sys.modules`.
The second imports one task group and asserts that matplotlib, cartopy,
networkx, igraph and dask are absent.  The third touches a task module and
asserts the manifest is rebuilt.

`polaris list` and `polaris list -v` must produce byte-identical output
before and after; the prototype already does, over all 274 tasks and their
steps.  Pre-commit runs mypy over the whole repository, which covers the
`TYPE_CHECKING` blocks.  The `pr` suite for each component covers setup and
run, which is where a name that was only ever resolved lazily would fail.

## Decisions

### Lazy loading through an import hook is rejected.

A `sys.meta_path` hook wrapping heavy packages in
`importlib.util.LazyLoader` left the module count unchanged, 2,851 before
and 2,855 after.  It has to be restricted to top-level packages, because
wrapping submodules raises `RecursionError` from `LazyLoader.__delattr__`.
And `from x.y import z`, which is how Polaris imports mpas_tools, scipy,
shapely, pyremap and geometric_features, touches an attribute and forces the
load anyway.  The explicit helper is what makes those cases deferrable.

### Deferring imports without the `TYPE_CHECKING` guard is rejected.

`np = lazy_module('numpy')` alone types `np` as the proxy, so mypy checks
nothing about numpy calls and IDE navigation stops at the helper.  The guard
costs three lines per module and keeps both.

### Converting only the framework, not the task tree, is rejected.

Converting `polaris/ocean`, `polaris/mesh`, `polaris/viz` and the rest of
the framework leaves one ocean task group at 2,072 modules, because the step
modules import matplotlib, cmocean and `mpas_tools.ocean.viz.transect`
themselves.  Converting the task tree as well brings it to 467.

### Repackaging the Python environment is rejected.

Bundling site-packages into a zip, or staging it on node-local disk, would
cut the per-module I/O wait.  Both are deployment changes belonging to
`mache` and `deploy.py`, neither reduces what Polaris imports, and the
problem is not only I/O: `polaris list` spends 7.2 s of pure CPU executing
modules on an idle compute node.

### Reporting the mpas_tools imports upstream is separate work.

`mpas_tools/ocean/__init__.py`, `mpas_tools/mesh/mask.py` and
`mpas_tools/vector/reconstruct.py` pull in networkx, igraph and dask for
callers that need none of them, about 14 s of `polaris list` today.  This
design routes around it, so Polaris does not have to wait for a fix, but the
fix would help every mpas_tools caller.

## Measurements

Chrysalis, Python 3.14, best of three runs, times in seconds.  Wall is
elapsed; CPU is summed over threads, so it exceeds wall when BLAS starts one
thread per core.  The login node carried a load average near 22, from an
unrelated Omega build; the compute node was idle and exclusive.  The design
column is pinned; both columns are the same prototype trees under
`/lcrc/group/e3sm/ac.xylar/import_bench`.

| | login, today | login, design | compute, today | compute, design |
| --- | --- | --- | --- | --- |
| `python -c pass` | 0.03 | 0.03 | 0.03 | 0.03 |
| `import polaris` | 4.04 | **0.09** | 0.80 | **0.08** |
| `polaris list` | 21.11 | **0.05** | 18.03 | **0.05** |
| set up one ocean task | 21.83 | **1.00** | 15.76 | **0.36** |
| build the ocean component | 21.83 | 11.07 | 15.76 | 5.56 |
| `polaris list` without the manifest | 21.11 | 12.99 | 18.03 | 7.78 |

Inside `srun -n1 -c1` on the same compute node the figures match the whole
node to within 0.1 s, and today's `import polaris` still costs 14.93 s
of CPU.

Modules imported, which is what the times follow:

| | today | with this design |
| --- | --- | --- |
| `import polaris` | 999 | 148 |
| one ocean task group | 2,647 | 467 |
| the ocean component | 2,647 | 1,434 |
| all four components | 2,839 | 1,620 |
| `polaris list` | 2,839 | 0 |

Where the time goes today in `polaris list`, by `python -X importtime` self
time, 2,839 modules totalling 71.4 s on a heavily loaded login node:

| package | share | modules | reached through |
| --- | --- | --- | --- |
| scipy | 17% | 530 | pyremap, `polaris.ocean.vertical` |
| pandas | 14% | 298 | xarray |
| polaris | 9% | 340 | |
| networkx | 9% | 287 | `mpas_tools.ocean` |
| numpy | 6% | 148 | everywhere |
| pyarrow | 5% | 11 | pandas |
| dask | 4% | 30 | `mpas_tools.vector.reconstruct` |
| matplotlib | 3% | 96 | cmocean, `polaris.viz` |
| igraph | 2% | 72 | `mpas_tools.mesh.mask` |
