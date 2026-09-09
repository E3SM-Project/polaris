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
    nodes=('nid001234',), cores=(tuple(range(8)),), gpus=0
)
```

`cores` is one set of core numbers **per node**, in the same order as
`nodes`, which is why a placement on a single node still nests.  Core numbers
are node-local, so a step spanning two nodes normally asks for the same ones
on both:

```python
step.placement = ResourcePlacement(
    nodes=('nid001234', 'nid001235'),
    cores=(tuple(range(8)), tuple(range(8))),
    gpus=0,
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
  allocation.  A step confined to part of an allocation has to be told about
  that part: resources withheld from a step have to be genuinely withheld,
  not merely subtracted from a number.  The view carries memory beside cores,
  nodes and GPUs, because a step sizing a worker pool or a chunk size has to
  size it against memory, and the natural mistake is to derive memory from
  cores.

A step's placement is decided by whatever is running it.  When steps run one
at a time it is `None`, exactly as it has always been.  When a scheduler runs
them together it forks a child per step, and the child is handed the
placement directly -- it inherits the scheduler's memory, so the placement is
already an object it holds rather than something to be encoded, written into
an environment and read back.

## Capping a step's memory

Some machines will hold a launch to a memory figure and some will not, and
`mache` renders the flag only where it is enforced.  Polaris passes the cap
for a step that **declared** `memory` and never for one carrying only the
framework's `memory_budget`:

```python
self.component.run_parallel_command(
    args=args,
    cpus_per_task=self.cpus_per_task,
    ntasks=self.ntasks,
    openmp_threads=self.openmp_threads,
    logger=self.logger,
    gpus=self.gpus,
    placement=self.placement,
    memory_cap=self.memory,
)
```

The framework does this for a step that runs its model through `args`, which
is every {py:class}`polaris.ModelStep`.  A step that calls
`run_parallel_command()` itself should pass `memory_cap=self.memory` as
above; `self.memory` is `None` for a step that declared nothing, which
renders no cap at all, so the line is correct whether or not the step has
been measured.

The reason it is only for a declared figure is that a step which stated a
number has made a claim and can fairly be held to it, while a step that said
nothing is being estimated by the framework, and killing it for exceeding the
framework's own guess would make every step carry a measured number before it
could run.

Not every machine can confine a launch.  `mache` reports which mechanism a
machine has through `ParallelSystem.placement_support`, decided at run time
from the launcher that is actually installed rather than from configuration.

Placement needs a `mache` that gives a placement one set of cores per node,
which the deployment pins.  The release that first brought placement
expressed a launch's cores as one flat set instead, which cannot describe a
launch spanning nodes wherever the launcher binds cores explicitly: it
required the numbers to be unique, and node-local numbering means two nodes
normally use the same ones.

Setup refuses to go any further against a `mache` that cannot place, rather
than letting a run fail partway through with a `TypeError` from inside the
launcher.  It tests capabilities rather than comparing version numbers,
because the capability is the thing that matters and a version is only a
proxy for it: it asks whether this `mache` accepts a placement at all, and
then whether it accepts one core set per node, by building two nodes that
both offer core 0.

## How a step says what it needs

A step describes its resources in one of two shapes, depending on whether it
has MPI ranks.

An **MPI step** says `ntasks` ranks of `cpus_per_task` cores each, with
`min_tasks` and `min_cpus_per_task` saying how far it can be reduced.  That
is unchanged.

A **non-MPI step** says `cores` and `min_cores` directly.  A step with no
ranks has no meaningful `cpus_per_task`, and "one task of two hundred CPUs"
is a sentence no launcher can act on.  For a step that does speak in ranks,
`cores` is simply the product, so anything wanting a step's core count can
ask for it directly either way.

GPUs need no second spelling: `gpus` and `min_gpus` are already per-step
totals, which is the shape a step with no ranks needs.  `gpus_per_task` is
deprecated and is the only GPU field a non-MPI step cannot use.

## Whether a step may span nodes

`may_span_nodes` says whether a step's cores **and GPUs** may be drawn from
more than one node.

This is deliberately not the same question as whether a step uses MPI.  A
single process that hands its work to a distributed pool spans nodes
perfectly well; one that does its work in its own threads cannot; both are
"not MPI".  Polaris cannot tell them apart, so the step says.

It defaults to whether the step has more than one task, which is the only
mechanism Polaris has today for reaching another node.  Nothing sets it
otherwise yet -- it exists so that the worker pool in a later phase has
something to turn on rather than a rule to remove.

`cpus_per_task` is held to one node whatever the step says, because one
process cannot be given cores on a node it is not running on.  The span
property bounds the step's *total*.

Where a step cannot be given what it asked for, the usual target-and-minimum
rule decides, with the node boundary as one more thing that can make a
request unsatisfiable.  A step held to a node may be reduced towards its
target silently, exactly as it may be today.  A step whose **minimum** cannot
be met within a node is an error, naming what it needs, what a node holds,
and the property that would let it span -- a step that names a minimum has
said which reductions it will accept, and shrinking below it is not one.

## Memory

A step says how much memory it needs as `memory` and `min_memory`, both in
MB.

**A declared figure is a ceiling as well as a claim.** Asking a launch for a
share of the node's memory was measured to be enforced on Perlmutter and
Frontier -- a step allowed 1 GB and told to take 4 GB is killed -- and not
enforced on Chrysalis. So a step that declares memory should declare a
**peak with margin**, not a typical value: on a machine that enforces, the
number it gives is the number it dies at.

Polaris does not yet pass a memory figure to the launcher, and that is a
consequence of where the work has got to rather than a decision that it
never should.  `mache` accepts an optional cap alongside a placement, and
Polaris will pass it for a step that *declared* a figure once there is a
scheduler to admit steps -- which is a later phase.  Today nothing is
admitted and nothing is capped.

What the launcher does not do, on any machine, is *reserve* memory or say
whether a step fits.  That stays Polaris's own accounting: the only thing
protecting one step's memory from another's is Polaris declining to start
the second.  Enforcement and scheduling are separate, and only enforcement
is something a launcher offers.

A step that declares nothing is given **its proportional share of a node**
as its `memory_budget`, leaving `memory` as `None`: its cores times the
node's memory per core, rounded down.

The two are kept apart on purpose. `memory` is what the step declared and is
the only figure that may be enforced as a cap; `memory_budget` is what to
account for, declared or defaulted. Capping a step at the framework's own
rough guess would make every step carry a measured number before it could
run, which is the burden the default exists to avoid -- while leaving a
declared figure unenforced makes it invisible when wrong, which is worse
than a failure.  The default is
chosen for a property rather than for accuracy.  A set of steps that fits on
cores always fits in memory, so a run in which every step defaults packs
exactly as it would have with no memory accounting at all, and introducing
memory can never schedule an existing suite worse than before.  A step that
has been measured says what it needs and is scheduled on that instead.

That default is weakest on a GPU machine, where a step wanting every GPU on a
node and four cores to drive them gets four cores' share of the memory.  The
answer is for such a step to declare, not to make the default depend on GPUs
-- it is exactly the default's being core-proportional that makes it safe.

The per-node figure comes from `memory_per_node` in `mache`'s `[parallel]`
config, beside `cores_per_node` and `gpus_per_node`.  A machine that does not
set it leaves memory undeclared rather than guessed at, since a wrong figure
there would propagate into every step's default.

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
