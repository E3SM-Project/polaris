(dev-parallel)=

# Parallel

Polaris now uses `mache.parallel` for parallel-system selection, resource
discovery and launcher command construction.

Within Polaris, a component stores a `mache.parallel.ParallelSystem`
instance with {py:meth}`polaris.Component.set_parallel_system`, then uses it
for:

- resource queries through {py:meth}`polaris.Component.get_available_resources`
- command execution through
  {py:meth}`polaris.Component.run_parallel_command`

This change adds stronger GPU support, supports compiler-specific parallel
sections (`[parallel.<compiler>]`) and avoids modifying config options during
runtime.

## Public API

The key APIs are now:

- {py:func}`mache.parallel.get_parallel_system`
- {py:class}`mache.parallel.ParallelSystem`
- {py:meth}`polaris.Component.set_parallel_system`
- {py:meth}`polaris.Component.get_available_resources`
- {py:meth}`polaris.Component.run_parallel_command`

`ParallelSystem.get_parallel_command()` supports both CPU and GPU resources
through `cpus_per_task` and `gpus_per_task`.

## Placement

A step can be confined to a **named part** of the allocation -- these nodes,
these cores on each, this many GPUs -- rather than being launched across all
of it.  That is what makes it possible to run two steps at once without them
colliding or queueing behind one another.

The description is machine independent.  Polaris says *where*, and `mache`
decides which flags express it, because those differ between machines and
even between Slurm versions on the same machine:

```python
from mache.parallel import ResourcePlacement

step.placement = ResourcePlacement(
    nodes=('nid001234',), cores=tuple(range(8)), gpus=0
)
```

`Step.placement` is `None` by default, and a step with no placement produces
exactly the command Polaris has always produced.  **Nothing assigns a
placement yet.**  Deciding which subset a step should get needs a scheduler,
which is a later phase; the only caller today is the serial path, which
assigns none.

Two consequences are worth knowing about:

- A placement always states GPUs, including when the answer is zero.  A
  launch that says nothing about GPUs is read by the batch system as a claim
  on every GPU on the node, which stops any other step from starting.
- {py:meth}`polaris.Component.get_available_resources` takes an optional
  placement and, when given one, describes that subset rather than the whole
  allocation.  A step confined to one node has to be told about one node:
  resources withheld from a step have to be genuinely withheld, not merely
  subtracted from a number.

Not every machine can confine a launch.  `mache` reports which mechanism a
machine has through `ParallelSystem.placement_support`, decided at run time
from the launcher that is actually installed rather than from configuration.

## Compiler-specific parallel configs

`mache.parallel` combines options in `[parallel]` with
`[parallel.<compiler>]` (if present), where `<compiler>` comes from
`[build] compiler`.

This lets machine configs specify different launcher flags and resource options
for different compiler toolchains without requiring a single machine-wide
parallel configuration.

## GPU resources

Polaris step resources include GPU requirements in addition to CPU
requirements. Resource constraints use both CPU and GPU availability when
determining whether a step can run.

A step states its GPU need as `gpus` and `min_gpus`, which are totals for
the **step**, not counts per MPI task. A step that needs no GPUs leaves them
at zero, which is the common case. The distinction matters once steps run at
the same time: measurements on both GPU machines showed that asking for a
number of GPUs per task does not confine a step to those GPUs, while asking
for a total does.

`gpus_per_task` and `min_gpus_per_task` still work and are translated into a
total, but they are deprecated and raise a `DeprecationWarning`.

For ocean model steps with dynamic sizing, Omega runs on GPU-capable compiler
configs use:

- `goal_cells_per_gpu` (target; default 8000)
- `max_cells_per_gpu` (minimum required resources; default 80000)

## Supported Parallel Systems

The active system is still selected from `[parallel] system` and environment
context (`slurm`, `pbs`, `single_node`, `login`) but implementation is in
`mache.parallel`:

- {py:class}`mache.parallel.SingleNodeSystem`
- {py:class}`mache.parallel.LoginSystem`
- {py:class}`mache.parallel.SlurmSystem`
- {py:class}`mache.parallel.PbsSystem`

## Notes

- Polaris no longer provides a `polaris.parallel` module.
- Runtime no longer rewrites `cores_per_node` in config files.
- Machine and compiler config should provide the desired parallel options.
