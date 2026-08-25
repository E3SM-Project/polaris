# Task Parallelism Phase D: Coexistence and Elasticity

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Phase C gives the worker pool a fixed share of the allocation for the life of
the run. That is simple, and it is wrong in one specific way: once the Python
work is finished, the pool goes on holding its share, and those nodes sit
idle while model runs queue for resources that are right there.

Phase D makes the pool's share change with the work. When Python work is
ready, the pool grows; when it drains, the pool gives nodes back and ordinary
steps use them.

This is the phase that makes a mixed suite -- model runs and analysis in the
same job -- use the machine properly. It is also the phase most likely to be
unnecessary, and that should be tested before it is built: if suites in
practice do their analysis at the end, after the model runs are done, then a
pool that appears late and holds resources until the job ends costs nothing,
and Phase D is optimisation without a problem to solve.

Success in Phase D means a suite mixing model runs and analysis finishes in
close to the time the work itself requires, with no long stretch where part
of the allocation is reserved but idle.

## Requirements

### Requirement: The Pool Gives Resources Back

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When there is less ready Python work than the pool is sized for, the pool
shall shrink and the freed resources shall become available to other steps.

When the Python work is finished entirely, the pool shall release everything.

### Requirement: The Pool Grows When Needed

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When ready Python work exceeds what the current pool can handle, and
resources are free, the pool shall grow.

Growing shall not take resources from steps that are already running.

### Requirement: Changes Are Not Constant

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The pool shall not resize continuously in response to small fluctuations.

Adding and removing workers is not free. An earlier design that switched
execution modes at every opportunity spent a significant fraction of its
wall time doing so. The scheduler shall require a change to be worth making
before making it.

### Requirement: A Rule for Competing Work

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When ready model steps and ready Python work both want the same free
resources, Polaris shall apply a stated rule rather than whichever the loop
happens to reach first.

The rule shall be simple enough to explain in a sentence and shall be
recorded in the run's event stream when it is applied, so that a schedule
that looks wrong can be understood.

### Requirement: Resizing Is Safe

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Shrinking the pool shall not interrupt work already running on the workers
being removed.

A worker shall be allowed to finish what it holds before it is stopped, and
the resources it occupied shall not be offered to another step until it has
actually gone.

### Requirement: Elasticity Is Visible

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Every resize shall be recorded, with what triggered it and what it cost, and
the run summary shall report how much of the allocation was idle and for how
long.

Idle time is the quantity this phase exists to reduce, so it must be
measurable before and after.

## Algorithm Design

### Algorithm Design: Deciding the Size

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler already holds the dependency graph, so it knows not only what
Python work is ready now but how much is still to come. The pool's target
size should be the number of workers the ready Python work can actually use,
capped by what the allocation can spare.

Resizing should happen in whole nodes. A pool spanning three nodes releasing
"half a node" leaves a fragment too small to run a model step in, which is
the shape of free resource that looks available and is useless.

Two guards keep this from thrashing. A change should have to be worth more
than it costs -- the cost being one launch per node added, which measurement
puts at a fraction of a second to a second -- and a resize should not be
followed immediately by its opposite.

### Algorithm Design: When Both Kinds of Work Are Waiting

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The rule proposed is: **prefer the work on the critical path, and break ties
in favour of model steps.**

Model steps tend to be longer and to have more work depending on them, so
starting one late delays more. Python work tends to be shorter and more
plentiful, which makes it good for filling gaps. The scheduler can estimate
the critical path from the graph, so this is not guesswork.

This is a proposal, not a conclusion. It should be revisited once there is a
real mixed suite to measure, and the alternative -- simple first-ready
ordering -- should be measured against it rather than assumed worse.

### Algorithm Design: Shrinking Without Interrupting

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Shrinking should be cooperative: mark the workers to be removed as accepting
no new work, wait for what they hold to finish, then stop them and return
their resources to the pool. The scheduler must not count those resources as
free until the workers have actually exited, or it will place a step on top
of one still shutting down.

## Implementation

### Implementation: What Changes

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Phase D changes the pool module from Phase C and the scheduler loop from
Phase B, and adds nothing structurally new:

- the pool gains grow and drain operations, and a notion of workers that are
  finishing but not yet gone;
- the resource pool distinguishes resources that are free from resources that
  will be free shortly;
- the scheduler consults a target pool size each time round the loop, and
  applies the competing-work rule when both kinds are ready.

### Implementation: Order of Work

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Shrinking should be implemented before growing. Shrinking is what recovers
the idle resources that motivate the phase; growing is an optimisation on top
of it, and a pool that only ever shrinks is still correct.

## Testing

### Testing and Validation: Resize Behavior

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Tests with synthetic work shall cover: Python work draining to nothing, and
the pool releasing everything; Python work appearing when the pool is at zero;
a burst of work followed immediately by a lull, which shall not produce a
resize followed by its opposite; and a shrink while work is still running,
which shall wait for it.

### Testing and Validation: Idle Time

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A mixed synthetic suite -- model-like steps and Python-like work,
interleaved so that a fixed pool would clearly waste resources -- shall be run
with a fixed pool and with an elastic one. Total allocation-seconds idle
shall fall, and results shall be identical.

This test is also what decides whether Phase D is worth building at all. It
should be written first, run against Phase C, and the answer recorded.

### Testing and Validation: Real Mixed Workload

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Once a real suite exists that mixes model runs and analysis, it shall be run
with a fixed and an elastic pool and the wall times compared, on at least one
Slurm and one PBS machine.
