# Task Parallelism Phase C: Python Worker Pool

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Phase B forks a child per step, from the scheduler, on the scheduler's node.
Phase C puts a resident Polaris process on every node of the allocation, so
that the same cheap fork is available everywhere and work can be distributed
across nodes.

**Crossing nodes is what this phase is for.** Phase B's mechanism is not too
slow -- forking a child costs about a tenth of a second, which is nothing
beside a five-second task. It is confined: a process can only fork on the
node it runs on, so all of Phase B's non-MPI work lands on one node. That is
the same single-node ceiling MPAS-Analysis has, reached by the same route,
and lifting it is the point.

Two capabilities follow from one mechanism. A resident process on a node can
fork a whole step, which lifts Phase B's bound without a second executor.
And it can host a pool of workers for work too fine-grained to track
individually, which is what an analysis step submitting hundreds of tasks
needs.

The motivating workload is analysis. Polaris is to gain analysis capability
equivalent to MPAS-Analysis, which already parallelizes this kind of work
with Python's `multiprocessing` -- bounded to one node. At high resolution,
which is Omega's target, one node is not enough.

Phase C stands on Phase A and Phase B. The residents occupy a defined part
of the allocation, so ordinary steps continue to run in the rest; the
scheduler from Phase B accounts for that share as it would any other
reservation. Making the share change as the amount of Python work changes is
Phase D.

### What the measurement showed

Whether a pool is needed at all was an empirical question, and it has been
answered. A high-resolution MPAS-Analysis run was instrumented for per-task
duration, peak memory and dependency-graph width, and run cold on one node:
1231 tasks, none failed, 7h29m.

The question this phase turned on was whether analysis work is coarse --
minutes each, tens of them, in which case Phase B already handles it -- or
fine-grained, in which case a pool is needed. It is fine-grained. The median
task is 5.2 seconds and 49% run in under five, at the resolution that
matters. This document proceeds as written.

Two of that measurement's headline numbers should not be carried into this
design without their qualification, and the qualification is the same for
both.

**The measured ceiling on what more nodes could buy was 1.29x, and it is a
statement about three particular tasks.** The run's critical path was 5h49m
of a 7h29m makespan, and a single transect-remapping task was 82% of it;
three such tasks are the whole tail. They are known not to be written for
high resolution, and they are among the things Polaris would reimplement
rather than inherit. Taking the reported figures at face value, and assuming
the three are independent rather than chained, removing the largest raises
the ceiling from about 6.5x to about 11x and removing all three to about
36x. Those are arithmetic on someone else's summary rather than a
reanalysis, so they should be read as an order of magnitude. The conclusion
that survives is directional and sufficient: the measured headroom is a
lower bound taken on the least favorable available version of the workload,
not an estimate of what task parallelism is worth.

**The reported narrowing of the dependency graph with resolution is the same
finding again, not a second one.** Mean graph width, as reported, is
arithmetically serial work divided by critical path -- which is the speedup
ceiling. Both runs confirm it: 2255 minutes over 349 gives 6.46 against a
reported width of 6.5, and the low-resolution run gives 30.4 against a
reported 30. So "the graph got narrower as resolution rose" restates the
serial tail and inherits its fragility. The structural comparison is peak
width, which went from 251 to 170 -- a modest narrowing rather than a
collapse. This matters because an intrinsically narrow graph would be a real
argument against this phase, and the evidence does not support one.

### What the measurement showed about memory, and one correction

Every task in that run inherited 7.85 GiB by forking. Measured directly, the
baseline splits into **0.40 GiB of Python imports and 7.45 GiB of data
loaded before forking**. The import half is identical at both resolutions;
the data half scales with the problem, which is what identifies it.

An earlier reading of this design called the 7.45 GiB an artifact of one
program's structure that a reimplementation would not inherit. That was
wrong in a way worth correcting: it is a mechanism, and this phase should
use it deliberately. Copy-on-write sharing was measured on Chrysalis at
Phase B scale -- 24 forked children held 347 MiB between them against a
parent of 322 MiB, where naive resident-set accounting reports 7,700 MiB. A
node's resident process can load a large read-only input once and fork
workers that share it, which is the distributed equivalent of what
MPAS-Analysis gets for free, and it is the difference between a node
supporting a few workers and supporting one per core.

Two things follow that the design has to state rather than assume.

Sharing must be asked for. This environment runs Python 3.14, where
`multiprocessing`'s default start method on Linux is `forkserver` rather
than `fork`; a forkserver child is forked from a clean server that never
loaded the parent's data, so it inherits nothing. A pool written today
without saying so would not reproduce the behaviour described above.

Asking for it means forking from a process that may be multi-threaded, which
is what CPython changed the default to avoid. Phase B's rule applies
unchanged and for the same reason: hold thread pools to one before importing,
and check the count from `/proc` rather than from `threading.enumerate()`,
which reported one thread where the kernel reported 129.

The per-task memory figures from that run exclude the inherited inputs, so
they are not what a worker holding its own inputs would need. What a worker
needs is imports, plus whatever of the shared inputs its work touches, plus
its own data -- and the middle term was never measured because forking made
it free.

### Sizing a pool, and what not to assume while doing it

The question that sizes a pool is therefore **how much read-only input a
step needs resident**, and it is deliberately phrased that way rather than
in terms of any particular kind of input. If steps can work on subsets,
memory stops binding and a pool is limited by cores. If each step needs all
of it, the same node supports far fewer workers than it has cores. Polaris
can measure this as soon as it has one real step of the kind, and should,
before choosing a pool size.

Two things follow that are easy to get wrong in opposite directions.

**The pool must not be designed around a shared dataset.** Analysis happens
to be a workload where many tasks read from one large input, and it is
tempting to build for that. Most Polaris workflows have no such thing, and a
pool that assumes one -- in how it starts workers, in how it accounts for
their memory, or in what it expects a task to be given -- would be a pool
that serves one purpose well and the general case badly. Task parallelism is
the general facility; analysis is its first demanding customer, not its
specification.

**But a worker's memory should not be assumed private either.** Where many
tasks on a node do read the same large input, holding one copy per node
rather than one per worker is the distributed equivalent of what forking
gives for free, and the difference is large enough to change how many
workers fit. This is worth leaving room for and is not worth building now:
nothing has been measured that needs it, and the measurement that would
justify it is the one described above. It is recorded here so that it is not
rediscovered late, and so that nothing in the pool's design forecloses it.

### A task larger than one node

Nothing here restricts a step to a single node, and the design should not
acquire that restriction by accident.

Polaris already runs steps that span nodes: every MPI model run does. What
is bounded to one node is a non-MPI step running in its own process, which
is a property of processes rather than a decision Polaris made. A step that
hands its work to the pool is not in that category.

Phase A provides the property this turns on: a step declares whether its
resources may be drawn from more than one node, defaulting to no. A step
using the pool declares that they may, and this phase is where anything
first does. Its cores are then a reservation rather than a placement:
Polaris launches the step's driver, which needs about one core, and accounts
the rest against the pool's share.

The property covers GPUs on the same terms. A pool whose workers use GPUs
draws them from the nodes those workers are on, so a step's GPU count is a
claim against the pool exactly as its core count is. `gpus` is already a
per-step total, but the pool has to account for it, and a step that
distributes GPU work should not have GPUs reserved on the node its driver
sits on.

This phase is where a limitation carried harmlessly through Phase A and
Phase B stops being harmless. On PBS with PALS, a launch needing no GPUs is
given an empty vendor visibility variable, and the runtime reads an empty
value as "no mask", meaning every device. That splits into two cases and
only one works: a worker assigned *some* devices is confined, and a worker
assigned *none* is not confined at all. A pool mixing GPU and CPU-only
workers on one node therefore isolates the GPU workers and not the CPU-only
ones, which is the opposite of the intuition that asking for nothing is
safe.

A candidate fix is to name an out-of-range device rather than an empty
value. It is untested and should be tested: the runtime may equally refuse
it, warn, or fall back to every device.

One further thing is unestablished and matters more here than anywhere else.
That machine's configuration describes twelve GPUs per node, which are
tiles, while the runtime presents six cards; a mask naming three tiles
yielded two devices, which is consistent. What has not been tried is a mask
naming a *single* tile, which is the unit a scheduler handing out twelve
would assign. Whether two workers masked to different tiles of the same card
are isolated, or merely both see that card, is the question this phase rests
on.

For the pool, a computation whose data exceed one node's memory is not a
separate problem needing separate machinery. Working in chunks and spreading
those chunks across the workers' combined memory are the same facility, and
the distributed-array layer that provides it sits on the same pool.

The cost is not zero: moving data between nodes is slower than staying
within one, the work has to be written in terms of array operations the
framework can partition, and diagnosing a distributed computation is harder.
So this should not be the assumed shape of every analysis step, and no step
should be written to span nodes before measurement shows it needs to. But it
should be available, and the requirements below are written so that it is.

That nothing has yet demanded it carries less weight than it appears to. The
instrumented analysis run contained no Python task needing more than a node
-- the largest held 53.9 GiB where the node had 251 -- but the program
measured had no way to express such a task, since its parallelism is
fork-based and confined to one node. A tool produces no examples of what it
cannot express.

The case that stays hard is a computation that cannot be partitioned at all,
needing global random access to a single array larger than a node. Neither
chunking nor distribution helps, and the answer is to restructure the
computation. Analysis work is mostly reductions over dimensions that
partition cleanly, so this should be rare.

Success in Phase C means a Python step can distribute work across more than
one node, that this is faster than the same work on one node, and that
results are unchanged.

## Requirements

### Requirement: Python Work Across More Than One Node

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

A step shall be able to distribute Python work across workers on more than
one node of the allocation.

This is the requirement that distinguishes Phase C from what MPAS-Analysis
can already do. A capability limited to a single node would not address the
problem that motivates the phase.

A non-MPI step shall also be able to run on a node other than the
scheduler's, which is the bound Phase B accepted and this phase lifts.

This covers two things that should not be conflated: many independent pieces
of work running at once on different nodes, and a single computation whose
data are spread across the memory of several nodes. Both shall be possible.
The second is not expected to be common, but designing it out would be a
mistake, and it comes without additional machinery from the same framework
that provides the first.

### Requirement: The Pool Occupies a Known Share

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The pool shall be confined to a defined set of resources, and the scheduler
shall know about that reservation.

An earlier attempt launched a worker pool without bounding it, which claimed
the whole allocation and prevented model runs from starting at all. With
Phase A the pool is placed like anything else, and the scheduler simply sees
fewer free resources while it exists.

### Requirement: Steps Ask for Workers Explicitly

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

A step shall have to opt in to using the pool, and shall declare how many
workers it wants and needs.

Ordinary steps shall continue to run as a forked child, as in Phase B, and
adding this phase shall not change how any existing step runs. A step forked
by a node's resident rather than by the scheduler shall behave identically:
same lifecycle entry point, same log, same completion markers. Phase B
specifies that entry point so that this costs nothing here.

### Requirement: Work Sent to the Pool Must Be Safe to Run There

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Work dispatched to a worker shall not depend on process state that the worker
does not have, and shall not disturb state that other work in the same worker
relies on.

A worker process runs many pieces of work over its lifetime, possibly
several at once, and never ran the setup that a fresh Polaris process runs.
Work that changes the working directory, sets a library-level default or
writes to a shared path is unsafe there in a way it is not unsafe in its own
process.

The properties this requires are set out in
[Task-Parallel-Safe Analysis Steps in Polaris](task_parallel_analysis_steps.md),
which should be adopted before analysis steps are written, and are written
up for step authors under {ref}`dev-task-parallelism`. Phase C depends on
those rules being followed; it cannot enforce them after the fact.

### Requirement: Failures Are Attributable

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When work sent to the pool fails, it shall be clear which piece of work
failed and why, and the failure shall be reported as a failure of the step
that submitted it.

A worker that dies shall not silently reduce the pool. Losing workers
quietly turns a crash into a mysterious slowdown.

### Requirement: The Pool's Cost Is Visible

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The time spent starting and stopping the pool, and the resources it held
while idle, shall be recorded.

A pool is only worth having if the work it enables outweighs what it costs.
Earlier measurements found a worker pool spending around 9% of a suite's wall
time on its own lifecycle, which is the sort of thing that must be visible
rather than inferred.

## Algorithm Design

### Algorithm Design: What the Resident Process Is

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

Each node the pool spans carries one resident Polaris process, started once
and reused. It imports Polaris once, which is the cost Phase B pays in the
scheduler and this phase pays once per node, in parallel.

A resident serves two kinds of request. It forks a child to run a whole
step, which is Phase B's mechanism made available on a node that is not the
scheduler's. And it hosts worker processes that run many small pieces of
work submitted by a step, which is what an analysis step needs.

The two share their expensive part. A resident that has imported Polaris and
loaded a read-only input can fork either a step or a worker, and both
inherit that state at copy-on-write cost. Building one mechanism rather than
two is the reason this phase absorbs Phase B's single-node bound instead of
leaving it.

A step that opts in is given a handle to the pool and a lease saying how
many workers it may use, submits pieces of work, and collects results.

Starting the residents is one launch per node, confined by Phase A
placement, so the rest of the allocation stays usable.

Dask Distributed is the natural implementation. What matters for Polaris is
that its core is a **general task scheduler**, not an array library: a step
submits arbitrary Python callables and collects results, and can say which
workers a piece of work may run on and what resources it needs. Distributed
arrays are one thing built on top of that scheduler, available when a step
wants them, and irrelevant when it does not. The primary use here is the
general form -- many independent analysis tasks -- and the design should be
read that way.

Earlier Polaris work established that such a pool can be started across an
allocation's nodes. The design should not depend on the choice of framework:
what a step sees should be "submit work, get results", so the underlying
mechanism can be replaced.

### Algorithm Design: Where a Pool Disappoints

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The risks in adopting a pool are operational rather than conceptual, and are
worth naming so they are designed for rather than discovered.

**Worker memory is managed by the pool, not by the batch system.** Workers
spill, pause and eventually restart themselves when they approach their
memory limit. If a step's tasks are memory-hungry and the limits are set
wrongly, the symptom is workers dying and work silently retrying, which
reads as a mysterious slowdown. Worker memory limits must be derived from
the resources the pool was actually given, and worker restarts must be
reported, not absorbed.

This is the case the memory declaration introduced in Phase A exists for.
The pool's memory is the memory its steps declared, divided among its
workers, and it must be taken from the declaration rather than inferred from
the worker count: the analysis steps this phase is for are the ones whose
memory bears no fixed relation to their cores, and deriving one from the
other gets them wrong in the direction that hurts. Steps that reach this
phase should be carrying measured figures rather than the proportional
default. What a step declares is what it will hold resident -- its own data
and whatever of its inputs it keeps -- and not what an equivalent forking
program would have needed, which is smaller for the reason given above.

**Large results should not travel back through the pool.** Analysis tasks
that produce files should write them and return paths. Returning large
arrays moves them across the network and through the process that
coordinates the pool, which is the classic way to turn a fast distributed
computation into a slow one.

**Pure-Python work needs separate processes, not threads.** A worker that
runs several tasks as threads will serialize anything holding Python's
global interpreter lock. Work that is numerical and releases the lock is
fine; work that is Python-level loops is not. The pool's shape -- how many
worker processes, how many threads each -- must follow from what the tasks
actually do.

**There is a floor on useful task size.** Each task carries a small
scheduling cost. It is far below the duration of any realistic analysis
task, so it should not matter here, but it is the reason a pool is the wrong
answer for very short work and worth confirming against the measured task
durations rather than assumed.

### Algorithm Design: Sizing the Pool

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The pool should be sized from the work that is ready to run, not from the
allocation. If three analysis steps are ready and together they want twelve
workers, twelve is the number, regardless of how many nodes are free.

Phase C may size the pool once, when the first step that needs it runs, and
keep it until the run ends. That is simple and adequate while Python work is
a small part of a suite. It is also the thing Phase D fixes, because a pool
sized once holds its share even after the Python work is finished.

The numbers that make this concrete -- how many workers, how much memory each
-- follow from how much read-only input a step needs resident, which is the
open question stated above and which Polaris can answer with one real step
of the kind. Until it is answered, a pool should be sized from what its
steps declare and should report what it chose, rather than carrying a
default that would be a guess dressed as a number.

### Algorithm Design: Where a Step's Child Is Forked

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler from Phase B does not change shape. It still decides what may
run and what resources each thing gets. What changes is where a step's child
is forked -- by the scheduler, or by a resident on another node -- and
whether a step that opted in is also handed the pool.

Keeping the decision "what runs next" separate from "how it is executed" is
what prevents the scheduler from acquiring the mode-switching complexity that
made the earlier attempt hard to reason about. A resident is asked to fork;
it does not decide what runs.

## Implementation

### Implementation: Pool Lifecycle

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

- a module owning the pool: starting it with a placement, handing out
  leases, shutting it down, and reporting its cost;
- a step hook -- a separate method from `run()` -- through which a step
  receives the pool and its lease. Keeping it separate means the meaning of
  `run()` is unchanged for every existing step.

The pool must be shut down cleanly at the end of a run, including when the
run fails, or its workers outlive the job.

### Implementation: Worker Environment

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A worker process starts without any of the setup a Polaris process performs.
Anything the work needs must travel with it. Earlier work discovered this the
hard way: NetCDF output settings were configured in the main process, so work
running in workers silently wrote files in a different format, which showed
up as a step taking fifty seconds instead of ten.

Rather than replicating Polaris's startup inside each worker, the work sent
to a worker should carry what it needs. This is the same discipline the
analysis groundrules require, and it is the reason those rules matter more
here than anywhere else.

## Testing

### Testing and Validation: Multi-Node Distribution

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A test shall submit work to the pool and verify from the results which node
each piece ran on, confirming that more than one node was used. This is the
central claim of the phase and should be checked directly rather than
inferred from timing.

### Testing and Validation: Safety of Work Sent to Workers

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Tests shall include work that deliberately violates the rules -- changes the
working directory, mutates a library default, writes outside its work
directory -- and confirm the conformance checks catch it.

A test shall run two pieces of work in one worker at the same time and
confirm that neither affects the other's results.

### Testing and Validation: Failure Handling

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Tests shall cover work that raises, work that exits the worker process
outright, and a worker lost mid-run. In each case the submitting step shall
fail with an attributable error, and the run shall not hang.

### Testing and Validation: Is It Worth It

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Validation shall compare the same analysis workload run three ways: as
ordinary Phase B steps, through the pool on one node, and through the pool on
several. The comparison shall include the pool's own lifecycle cost.

If the pool does not beat Phase B steps on the real workload, that is a
finding, and it should be recorded rather than worked around.

The measurement already in hand does not decide this, and it is worth being
clear about why. It was taken on one program, on one node, using fork, with
a critical path dominated by tasks that would be rewritten before they ever
ran here. It establishes that the work is fine-grained and that a worker's
resident inputs are the quantity to watch. It does not establish what a pool
is worth, because the version of the workload that would run under one does
not exist yet. The comparison has to be made against Polaris's own steps,
and this phase should not claim a speedup it has not measured on them.
