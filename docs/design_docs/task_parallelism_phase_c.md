# Task Parallelism Phase C: Python Worker Pool

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Phase B runs each step in its own process. That is the right unit for a
Polaris step, which typically does minutes of work. It is the wrong unit for
work made of many small pieces: if a piece takes two seconds, spending a
second starting a process for it wastes half the machine.

Phase C adds a second executor for that case: a pool of worker processes,
spread across the allocation's nodes, that a step can send many small pieces
of work to.

The motivating workload is analysis. Polaris is to gain analysis capability
equivalent to MPAS-Analysis, and MPAS-Analysis already does this kind of
work in parallel -- but with Python's `multiprocessing`, which cannot reach
beyond one node. At high resolution, which is Omega's target, one node is not
enough. Lifting that ceiling is the point of this phase.

Phase C stands on Phase A and Phase B. The pool occupies a defined part of
the allocation, so ordinary steps continue to run in the rest; the
scheduler from Phase B accounts for the pool's share as it would any other
reservation. Making that share change as the amount of Python work changes is
Phase D.

### This phase may turn out to be unnecessary in its current form

Whether a pool is needed at all is an empirical question, and the measurement
is not yet in. We are instrumenting a high-resolution MPAS-Analysis run for
per-task duration, peak memory and dependency-graph width.

If that shows analysis tasks are coarse -- minutes each, tens of them -- then
Phase B already handles them and Phase C reduces to writing analysis steps
that declare their resources properly. If it shows they are fine-grained --
seconds each, hundreds or thousands -- then a pool is necessary and this
phase proceeds as written.

This document is written for the second case because it is the one the
existing evidence points at, but the numbers that would size the pool are
deliberately left unset. They should come from measurement.

### A task larger than one node

Nothing here restricts a step to a single node, and the design should not
acquire that restriction by accident.

Polaris already runs steps that span nodes: every MPI model run does. What
is bounded to one node is a **non-MPI step running in its own process**, as
in Phase B -- that is a property of processes, not a decision Polaris made.

For the pool, a computation whose data exceed one node's memory is not a
separate problem needing separate machinery. Working in chunks and spreading
those chunks across the workers' combined memory are the same facility, and
the distributed-array layer that provides it sits on the same pool. A step
that needs more memory than one node has can take a lease spanning several
and work across their combined memory.

The cost is not zero: moving data between nodes is slower than staying
within one, the work has to be written in terms of array operations the
framework can partition rather than as monolithic in-memory arrays, and
diagnosing a distributed computation is harder than a local one. So this
should not be the assumed shape of every analysis step, and no step should
be written to span nodes before measurement shows it needs to. But it should
be available, and the requirements below are written so that it is.

The case that genuinely stays hard is a computation that cannot be
partitioned at all -- one needing global, random access to a single array
larger than a node. Neither chunking nor distribution helps there, and the
answer is to restructure the computation. Analysis work is mostly reductions
over dimensions that partition cleanly, so this should be rare; if the
measurement turns one up, it is worth examining on its own rather than
treating as a requirement on the framework.

Success in Phase C means a Python step can distribute work across more than
one node, that this is faster than the same work on one node, and that
results are unchanged.

## Requirements

### Requirement: Python Work Across More Than One Node

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A step shall be able to distribute Python work across workers on more than
one node of the allocation.

This is the requirement that distinguishes Phase C from what MPAS-Analysis
can already do. A capability limited to a single node would not address the
problem that motivates the phase.

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

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A step shall have to opt in to using the pool, and shall declare how many
workers it wants and needs.

Ordinary steps shall continue to run as their own process, as in Phase B.
Adding a pool shall not change how any existing step runs.

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
`docs/design_docs/task_parallel_analysis_steps.md`, which should be adopted
before analysis steps are written. Phase C depends on those rules being
followed; it cannot enforce them after the fact.

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

### Algorithm Design: What the Pool Is

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The pool is a set of worker processes, at least one per node it spans, started
once and reused. A step that opts in is given a handle to it and a lease
saying how many workers it may use, submits pieces of work, and collects
results.

Starting the pool is a single launch, confined by Phase A placement. That is
important for two reasons: it is one launch rather than one per piece of
work, which is the whole point of pooling; and being confined means the rest
of the allocation stays usable.

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
-- depend on the analysis measurement described above.

### Algorithm Design: Two Executors, One Scheduler

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler from Phase B does not change shape. It still decides what may
run and what resources each thing gets. What changes is that a step may be
executed in one of two ways: as its own process, or, if it opted in, by being
given the pool.

Keeping the decision "what runs next" separate from "how it is executed" is
what prevents the scheduler from acquiring the mode-switching complexity that
made the earlier attempt hard to reason about.

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
finding, and it should be recorded rather than worked around. The measurement
that decides this is the same instrumented MPAS-Analysis run that sizes the
pool.
