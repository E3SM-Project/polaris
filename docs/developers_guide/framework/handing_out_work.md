(dev-handing-out-work)=

# Handing out a step's work

A step whose work is a loop over independent items -- a plot for each month,
a map for each field, a file for each region -- can hand out each item as a
*piece* that runs on a core of its own.  The pieces can run on any node of
the job's allocation, which is how Python work reaches beyond one node: a
step's own process, and anything it starts itself, stays on the node it runs
on.

## Writing a step that hands out work

Override {py:meth}`polaris.Step.run_pieces()` in place of `run()`.  It is
given a {py:class}`polaris.run.pieces.Pieces`, whose `map()` works like the
built-in `map`: it calls a function once for each item, with one item from
each of the iterables it is given, and returns what each call returned, in
the order of the items.

```python
from polaris import Step


def plot_month(climatology_filename, month, image_filename):
    ...
    return image_filename


class PlotMonths(Step):
    def __init__(self, component, indir):
        super().__init__(
            component=component,
            name='plot_months',
            indir=indir,
            cores=12,
            min_cores=1,
        )

    def run_pieces(self, pieces):
        months = list(range(1, 13))
        climatology = self.work_path('climatology.nc')
        images = [self.work_path(f'month_{month:02d}.png') for month in months]
        pieces.map(plot_month, [climatology] * len(months), months, images)
```

The iterables must all be the same length, rather than being cut to the
shortest as the built-in `map` would cut them.  At most `pieces.cores`
pieces run at once, one to a core, and the next item starts as soon as a
core comes free.  `run_pieces()` can call `map()` as often as it needs to,
and can do work of its own between calls, such as combining what one call
returned before handing out the next.

The step's own process -- the one running `run_pieces()` -- runs on the
node `polaris parallel` or `polaris serial` itself runs on, and is given no
core of its own: its cores are for its pieces.  It should do only light
work itself: working out what each piece needs to be told, handing the
pieces out, and gathering what comes back.

## What a piece has, and what it does not

Each piece runs in a process of its own, forked for it by a *resident*: a
process the run starts on every node, which imports Polaris once so that
each piece starts with it already imported.  A piece is not forked from the
step's own process, so it has nothing the step did there -- no objects the
step built, no config it read, no logger.  What a piece needs has to travel
with it, as its arguments, or be read from a file.

That has three consequences for the function a step hands out:

- **It must be a function a module defines.**  Functions are pickled by
  reference, by their module and name, and found again in the resident.  A
  lambda or a nested function is refused with a `TypeError` when it is
  handed out, rather than being pickled together with whatever it closed
  over, which is often the whole step.
- **Its arguments, and what it returns, must be picklable and should be
  small.**  File names, indices and small arrays travel well.  A large array
  should be written to a file in the step's work directory and its name
  passed instead, and a piece that makes a file should return the file's
  name rather than its contents.
- **It cannot rely on state set up in the step's process.**  A piece that
  needs config options is passed their values; one that needs a mesh opens
  it.  Opening the same input in every piece is the cost of working this
  way, and a piece that spends most of its time on setup it repeats is a
  sign that the items should be bigger.

A piece runs with the step's work directory as its working directory, on the
one core it was given.  It should not start threads or processes of its
own, since that core is all it has.  The rules in {ref}`dev-task-parallelism`
apply to a piece as they do to a step.

Forking a piece, running it and hearing back from it costs about 20 ms, so
a piece should take at least a second or so.  Items much shorter than that
are better handed out in batches.

## What a step declares

`cores` is how many pieces the step would like to run at once, and
`min_cores` the fewest it will accept, as for any step without MPI tasks.
A step that hands out work may take its cores from more than one node, so
`may_span_nodes` is `True` for it unless the step says otherwise.  When the
step starts, the scheduler reserves its cores on as few nodes as will hold
them, and gives them back when the step ends.

`memory`, if the step declares it, is what its pieces hold at once: what one
piece holds at its peak, with a margin, times `cores`.  It is charged to the
nodes the cores come from, in proportion to the cores on each.  A step that
declares nothing is charged one core's share of a node's memory for each of
its cores, as any step is.  That suits pieces that need no more than that;
pieces that need more have to say so, since nothing else tells the
scheduler.

A step that hands out work cannot also have a command in `args`, which
would be a second way of running it, and cannot yet ask for GPUs.

## When a piece fails

A piece that raises an exception, exits or is killed fails the call that
handed it out.  `map()` stops every other piece of the call that is still
running and raises {py:class}`polaris.run.pieces.PieceFailed`, saying which
piece failed -- its index, the call with its arguments, and the core and
node it ran on -- and why, with the piece's traceback if it raised one.
Nothing is retried.  Left uncaught, the exception fails the step, exactly as
one raised from `run()` would.

What a piece prints or logs goes to a log of its own,
`pieces/piece_NNNN.log` in the step's work directory, numbered from zero in
the order the pieces were handed out.  A log nothing was written to is
removed, so the logs that are left belong to the pieces that had something
to say, including any that failed.

## Computing with Dask across nodes

A step whose arrays are too big for one node can compute with Dask on its
cores instead of handing out pieces.  Inside `run_pieces()`, it opens
`pieces.dask()`, whose value is a `distributed.Client`:

```python
def run_pieces(self, pieces):
    with pieces.dask():
        ds = xr.open_dataset(self.work_path('output.nc'), chunks={'Time': 1})
        mean = ds.temperature.mean('Time').compute()
    mean.to_netcdf(self.work_path('mean.nc'))
```

The resident on each node the step's cores are on forks one Dask worker
there, bound to those cores, with a thread for each core and the node's
share of the step's memory as its limit.  The scheduler runs in the step's
own process.  The workers start when the `with` block is entered and stop
when it is left, and `map()` cannot be used while they hold the cores.
Starting them takes a second or two, so this is for a step that needs
Dask's arrays across nodes, not a replacement for `map()` over a loop.

A worker runs many tasks at once in one process, in its threads, so tasks
must not change the working directory, set library defaults or write
outside the step's work directory, as {ref}`dev-task-parallelism`
describes.

A worker that dies fails the step.  A task that was running on it raises
Dask's `KilledWorker`, and leaving the `with` block raises
{py:class}`polaris.run.dask_workers.WorkerLost`, naming the node, even if
Dask finished the work on another worker.  Nothing restarts a worker or
retries its tasks.  What each worker says goes to `dask/worker_<node>.log`
in the step's work directory.

## How a run starts the residents

`polaris parallel` starts one resident on each node of the allocation when
the run has a step that hands out work, or is on more than one node and has
a step that launches nothing, which a resident can fork on its node when the
scheduler's is full.  It stops them when the run ends, however it ends.  Starting them takes as long as importing Polaris on a
compute node, typically some tens of seconds.  The run starts other steps
in the meantime, and a step that hands out work waits until every resident
is ready.  `polaris serial` starts them before its first step, if any of
its steps hands out work, and stops them when it finishes.  What the
residents themselves print goes to `case_outputs/residents.log`.

Two config options in the `[residents]` section control them:

```cfg
# Options for the resident processes a run starts on each node for steps that
# hand out pieces of their work
[residents]

# The network interface residents listen on and steps reach them over, such
# as ib0.  Left empty, it is the interface a node's hostname resolves to,
# which on some machines is a slow management network.
interface =

# How long to wait, in seconds, for every resident to say hello.  Residents
# spend nearly all of it importing Polaris, once per node and in parallel.
start_timeout = 1800
```

A machine whose hostnames resolve to a slow network sets `interface` in its
machine config; Chrysalis uses `ib0`.  Only a process holding the run's key
can connect to a resident, and the key is made afresh for every run.

## What a run reports

Each step that handed out work writes `polaris_pieces.json` in its work
directory, saying how many pieces it handed out, how many failed, on which
nodes they ran, and how long its cores were busy.  `polaris parallel` adds
these up at the end of the run:

```none
Handed-out work: 200 piece(s) from 2 step(s) on 2 node(s); their cores were busy 82% of the time they were reserved.
```

The share of time the cores were busy is the cost of reserving cores for a
step: they are idle while the step reads its inputs, between its calls to
`map()`, and while its last pieces finish.  Cores Dask workers hold count as
busy.  The run also says how many Dask workers steps started and how long
they took to start, and how long the residents took to be ready and to
stop.

A piece that was allowed more than the core it was given is reported in
`polaris_placement_mismatch.log` in the step's work directory, as a step
that ran somewhere other than its placement is.
