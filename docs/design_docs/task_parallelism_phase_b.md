# Task Parallelism Phase B: Concurrency

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Phase B makes Polaris run independent steps at the same time.

Phase A gave Polaris the ability to confine a step to part of its allocation.
Phase B adds the parts that decide what to run and when: a graph of which
steps depend on which, a record of which resources are in use, and an
executor that runs each step in its own process.

MPI steps and Python steps are treated the same way. This is worth stating
plainly because earlier designs staged them separately, running Python work
concurrently while MPI steps waited their turn. That separation existed
because we could not confine an MPI step to part of the allocation. Phase A
removes that reason, and with it the need for a barrier between the two kinds
of work, the machinery to switch between modes, and the cost of switching.

Each step runs in its own operating-system process. Polaris already knows how
to do this: `polaris serial` can run a single step in a fresh process from
its pickle file, and that is the unit the scheduler dispatches. Running a step
in its own process means it cannot disturb another step by changing the
working directory, setting a module-level default or writing to a global
logger -- all of which Polaris steps legitimately do today.

This is where the regression-suite speedup arrives. On a recent `omega_pr`
run on Chrysalis, three nodes, 12:26 total: the MPI work amounts to roughly
236 s of core-time on 192 cores, against a dependency floor of about 106 s,
so something in the range of 2.5-3x is the expectation on the same
allocation. That number is an estimate from one run's timings and should be
treated as a target to measure against, not a promise.

Success in Phase B means a suite's independent steps run together, results
match serial execution exactly, a failure stops only the work that depended
on it, and reruns still skip completed steps.

## Requirements

### Requirement: A Concurrent Execution Path

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall provide a way to run a suite, task or step with concurrency,
alongside the existing `polaris serial`.

`polaris serial` shall remain available and unchanged. Setup shall provide an
opt-in way to generate job scripts that use the concurrent path; the serial
path shall remain the default until the concurrent one has been used enough
to trust.

### Requirement: Scheduling from Declared Dependencies

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall decide what may run from explicitly declared step
dependencies and from declared input and output files, not from the order in
which steps happen to be listed.

If a suite relies on listed order without declaring a real dependency, it is
acceptable for the concurrent path to expose that as a failure. Invalid
graphs -- cycles, or an input no selected step produces and which does not
already exist -- shall be rejected before anything runs, rather than
discovered partway through.

Steps shared between tasks shall be recognized as one step and run once.

### Requirement: Resource-Aware Scheduling

Date last modified: 2026/09/08

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall run as many ready steps as the allocation's resources allow,
and no more.

Cores, GPUs, nodes and memory shall all be accounted for. A step whose
minimum requirements cannot be met by the whole allocation shall be reported
as impossible before the run starts.

The memory a node is credited with shall be what that node reports, not what
its machine's configuration estimates. Phase A requires the allocation's
nodes to be read at the start of a run, because a configured figure is an
estimate of a machine while the scheduler is packing particular nodes, and
over-admitting memory is the failure that kills a job rather than the one
that slows it. Nodes shall be tracked individually rather than as so many
copies of one node, which costs nothing if they turn out to be identical and
is the only correct answer if they are not.

This was written before any machine was known to be heterogeneous, on the
argument that the configured figure is the weaker source of truth in every
case and that reading the nodes removes a whole class of error -- a stale
configuration, a machine that has changed, a job that is not on the machine
it was thought to be -- without requiring any of them to be anticipated.
That argument still stands on its own.

It no longer has to. Aurora is heterogeneous, from a survey of all 10,624 of
its nodes: about one in nine holds roughly 1007 GiB where the majority holds
1135, so a figure taken from the majority would over-admit by about 13%
whenever a step landed on a small node. A run that packs against what its
own nodes report cannot make that mistake; a run that packs against one
number per machine can only avoid it by using the smallest, and thereby
wasting the difference everywhere else.

A step that has not said its resources may span nodes shall have its cores
and its GPUs drawn from a single node. This is a packing constraint rather
than a total: an allocation with cores free on several nodes and none of
them holding enough may be unable to start such a step while showing plenty
free, and the pool has to be able to say so rather than deadlocking or
overcommitting. The same applies to GPUs, and a step needing both must find
both on one node rather than each somewhere. A step that may span is bounded
only by what the allocation holds.

Memory is accounted for differently from the rest, and the difference should
be understood rather than smoothed over. Cores, GPUs and nodes are handed to
the launcher, which keeps steps off each other's; memory is not, because
nothing below Polaris will act on it. The pool's memory accounting is
therefore admission control and nothing more: it decides what may start, and
a step that starts and then uses more than it declared is not stopped by
anything. This is the correct amount of mechanism, since the alternative --
a step killed part-way through for exceeding a figure someone estimated --
trades a rare failure for a routine one. But it means memory accounting is
only as good as the declarations, and the design should say so rather than
imply a guarantee it does not have.

Since a step that declares no memory is taken to want its proportional share
of the node, a run in which nothing declares memory packs exactly as it
would with no memory accounting at all -- the two constraints reduce to the
same inequality. Memory accounting can therefore only ever remove a
schedule that a measured declaration says would not have fit.

A step's resources shall be decided from the whole allocation, exactly as
`polaris serial` decides them, and the scheduler shall wait until that much
is free rather than starting the step on less.

The target-and-minimum rule keeps the job it already has: it fits a step to
the machine once, at the start of a run, and a step whose minimum the
allocation cannot meet is reported as impossible. What it must not also
become is a packing lever. A step handed whatever happened to be free when
its turn came is a step whose width depends on scheduling timing, and for an
MPI model step the width is the decomposition, so the same suite on the same
allocation would produce different outputs on different runs. That is not a
trade against the requirement that results match serial execution; it
contradicts it. A pleasant consequence is that a step's memory budget, being
proportional to its cores, stops moving too.

This does cost packing. A wide step waits for room that a narrower version of
it would not have needed, and the allocation can sit partly idle while it
waits. It is still the right trade, because the alternative is not slower but
wrong. If the cost proves large, the way to buy it back is to let a step say
that its results do not depend on its width -- which is true of most steps
that are not model runs -- rather than to make every step's width a
scheduling accident.

### Requirement: Each Step in Its Own Process

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Each step shall run in its own process, isolated from other running steps.

Polaris steps mutate process-wide state as a matter of course: the framework
changes the working directory into each step's work directory, and sets
library-level defaults for NetCDF output. These are correct today and would
be races if two steps shared a process. Process isolation makes them
harmless without requiring every existing step to be rewritten.

### Requirement: Deterministic Ordering

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When several steps could run, the choice among them shall be repeatable.

Two runs of the same work with the same resources should make the same
choices. The chosen order need not match what `polaris serial` did, but it
must not vary from run to run, or debugging a concurrent run becomes
guesswork.

### Requirement: Failure Isolation and Restart

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A step that fails shall prevent the steps that depend on it from running, and
shall not prevent unrelated work from continuing.

Completed steps shall still be skipped on rerun, cached steps shall still be
honored, and a rerun after a failure shall resume from what succeeded.

### Requirement: A Step Killed by the Node Is Reported as Such

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Running steps concurrently introduces a failure that serial Polaris does not
have. Memory is not enforced by anything, so a step that uses more than it
declared exhausts the node, and the operating system then kills whichever
process it chooses. The step that dies need not be the step at fault, and a
step that was correct in isolation can fail because of a neighbor.

Polaris shall recognize this case rather than presenting it as an ordinary
step failure. A step terminated by a signal rather than by its own exit
shall be reported as terminated, and the report shall name every step that
was resident on the same node at the time, together with what each of them
had declared.

Naming the co-resident set is the most that can honestly be said, and saying
it is the point: the victim is identifiable and the culprit is not, so a
report that blames only the victim sends whoever reads it to the wrong step.
The list of neighbors and their declarations is what turns an inexplicable
failure into a short investigation, and, in the common case where one
neighbor's declaration is obviously too small, into an obvious fix.

### Requirement: A Declared Memory Figure May Be Enforced

Date last modified: 2026/08/24

Contributors:

- Xylar Asay-Davis
- Claude

Where the machine can hold a launch to a memory figure, Polaris shall do so
for a step that declared one, and shall not for a step that did not.

Measurement settled that this is possible on newer Slurm and not on older:
a launch allowed 1024 MB and told to take 4 GB is killed at 960 MB on
Perlmutter GPU and on Frontier, and runs to completion on Chrysalis. PALS
appears to offer no per-launch memory size at all, so Aurora is expected not
to enforce either.

The reason to use it is that an unenforced declaration is invisible when it
is wrong. It does not fail; it quietly makes the scheduler's accounting a
fiction, and the error surfaces much later as an exhausted node that someone
has to trace back, or never surfaces while costing throughput the whole
time. Holding a step to its own number turns that into an immediate,
attributable failure, and the fix -- correct the number -- improves packing
on every machine, including the ones that cannot enforce.

The reason to use it only for a declared figure is that most steps will
never declare one. They take the proportional default, which is deliberately
a rough guess and is known to be poor for steps whose memory has little to
do with their core count. Capping a step at the framework's estimate of it
would not produce better estimates; it would require every step to carry a
measured figure before it could run, which is the burden Phase A was built
to avoid, and it would arrive as a wave of failures in steps nobody had
touched. A step that stated a number is making a claim and can fairly be
held to it. A step that said nothing is being guessed at, and the framework
should carry the risk of its own guess.

Enforcement will therefore be uneven across machines, and that is accepted.
It replaces silent divergence with loud divergence, which is the better of
the two, and it reaches only steps whose authors opted in by declaring.

Polaris shall not rely on enforcement in place of its own accounting.
Admission control works on every machine; capping does not, and the
reporting required above is needed regardless.

A question that could have reshaped this has been answered and did not.
Placement on newer Slurm asks for exactly what a step needs rather than the
job's resources, so a placed step might have received a memory ceiling
nobody set -- in which case the choice would not have been whether to cap
but whether Polaris names the number or lets the scheduler pick one it never
reports. It does not: on Perlmutter CPU and on Frontier, a placed
single-core launch and an unplaced control, neither mentioning memory, both
allocated twice what a single core's proportional share would be and neither
was touched. The amount was chosen to be what would bite if placement scaled
memory with cores.

That bounds rather than settles -- it shows no ceiling below the amount
tried, and Perlmutter GPU was not tested on this point -- but it removes the
mechanism that would have forced Polaris's hand.

### Requirement: Results Match Serial Execution

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

For deterministic workflows, running concurrently shall produce the same
final outputs as running serially.

### Requirement: The Run Can Be Understood Afterwards

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A concurrent run shall record enough to reconstruct what happened: which
steps ran when, what resources each held, what each was waiting for, and how
the total compares with running serially.

This is not optional polish. A concurrent run that is slower than expected
is otherwise very hard to diagnose, because the interesting question --
why was nothing running at this moment -- cannot be answered from step logs.

### Requirement: Do Not Poll the Batch System

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall not repeatedly query the batch system to find out how running
steps are getting on.

NERSC asks that jobs keep batch-system queries to one or two a minute in
aggregate, and a scheduler that polls per step per second would breach that
badly at scale. Polaris shall learn that a step has finished from the process
it started, not by asking the queue.

## Algorithm Design

### Algorithm Design: The Scheduling Loop

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The loop is conventional and should stay that way:

1. Mark ready any step whose dependencies have all succeeded.
2. Among ready steps, in a stable order, take each that fits in the
   resources currently free and start it.
3. Wait for any running step to finish.
4. Release its resources, record the outcome, and repeat.

The stable order should come from setup order -- suite, then task, then step
within task -- which is easy to explain and close to what users already
expect. Steps that cannot fit right now are simply skipped over until they
can; there is no need for a more elaborate policy in Phase B, and a simple
one is much easier to reason about when a schedule looks wrong.

The one policy choice worth making deliberately is whether to hold resources
free for a large step that cannot currently fit, rather than filling the gap
with small ones and starving it. Phase B should not do this: it should fill
the gap, and rely on the largest steps being started early by the stable
order. If starvation shows up in practice, that is the point to add a rule,
with evidence for it.

### Algorithm Design: Running a Step in Its Own Process

Date last modified: 2026/09/08

Contributors:

- Xylar Asay-Davis
- Claude

Polaris already has exactly the right unit. `polaris serial` run inside a
step's work directory loads `step.pickle` and executes that one step, with
configuration, parallel system, resources, logging and completion markers all
handled. The scheduler starts that as a subprocess, with the step's placement
in its environment, and waits for it.

This has a property worth spelling out: the *same* mechanism serves MPI and
non-MPI steps. An MPI step's subprocess goes on to launch its model through
the parallel command; a Python step's subprocess simply runs Python. The
scheduler does not need two executors, two policies or a barrier between
them.

What the two do not share is how they are confined, and saying so matters
because otherwise a placement means nothing for half the steps. An MPI step's
placement reaches a launcher, which puts the work on the nodes and cores it
names. A non-MPI step does its work in the subprocess itself, and nothing
between the scheduler and that process acts on a placement: the executor has
to apply the affinity, and it can only do that on the node it is running on.
So a step that is not launched shall be given cores on the scheduler's own
node and bound to them by the executor.

That puts a ceiling on Python concurrency at one node's worth of cores. It is
the ceiling Phase C exists to lift, and the same one MPAS-Analysis has today.
It is not a ceiling on what Phase B is for: the regression suites this phase
targets are dominated by MPI work, which is placed across the whole
allocation as designed.

The alternative -- launching every step's driver through the launcher, so
that a Python step lands wherever it was placed -- was rejected here because
an MPI step's driver would then start its model from inside a job step, which
needs care on newer Slurm and is a known way to hang. That is a reason to
leave it out of Phase B, not a finding; it is worth revisiting with a
measurement rather than by argument.

One consequence to acknowledge rather than discover: every step has a driver
process on the scheduler's node for as long as it runs, MPI steps included,
and those are not reserved. A driver blocked waiting for its model consumes
no core, so reserving one each would cost more concurrency than the drivers
cost the node. The point at which that stops being true is a driver that does
real work while its model runs, and that is the point to revisit it.

The alternative we considered and rejected was to run steps as functions
inside a pool of worker processes. It is a good fit for fine-grained Python
work -- and Phase C adds exactly that, for exactly that reason -- but it is a
poor fit for whole Polaris steps, which are coarse, mutate process state and
launch their own subprocesses.

### Algorithm Design: Building the Graph

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Edges come from two places: dependencies a step declares directly, and files
one selected step produces that another consumes. Listed order contributes
nothing except as the tie-break for choosing among ready steps.

Steps that are already complete, or cached, participate in validation as
satisfied nodes: their outputs are available for others to depend on, but
they are not run.

The graph should be validated before any step starts. An unsatisfiable input
discovered at minute forty of a suite is much more expensive than the same
error reported at second one.

### Algorithm Design: Knowing When a Step Has Finished

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler waits on the processes it started. When one exits, its exit
status says whether the step succeeded, and Polaris's existing completion
markers confirm it. Nothing asks the batch system anything.

## Implementation

### Implementation: Shared Step Lifecycle

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The per-step lifecycle -- runtime input checks, dependency loading,
`runtime_setup()`, `run()`, output checks, validation, completion markers --
currently lives inside `polaris/run/serial.py`. It should be moved into a
shared module that both the serial and concurrent paths call, with no change
in behavior.

This is worth landing as its own change, ahead of the scheduler, because it
is a pure refactor and reviewable as one. Earlier task-parallel work already
did this and the result was sound; it is the piece of that work most worth
carrying forward.

### Implementation: New Modules

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

- a graph builder, producing the step graph and rejecting invalid ones;
- a resource pool, tracking free nodes, cores, GPUs and memory, and handing
  out and taking back reservations. What it hands out is a reservation, which
  for an ordinary step is also the placement its launch is given, and for the
  cases described in Phase A -- memory, and a step that delegates its work --
  is not. The pool's accounting is what keeps the machine from being
  oversubscribed and must cover everything a step claims, whether or not any
  of it reaches a launcher;
- an executor, starting a step as a subprocess with its placement and
  reporting completion;
- a scheduler, owning the loop above;
- an event stream, recording scheduling decisions as structured records.

These should be small and separately testable. The scheduler in the earlier
attempt grew past three thousand lines, largely because worker-pool lifecycle
and mode-switching policy lived inside it; with a subprocess executor there
is no lifecycle to manage and the loop stays short.

### Implementation: Step Eligibility

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Steps should be eligible for concurrency by default, with a way for a step
author to mark one unsafe -- for shared mutable state outside its work
directory, external side effects, or anything else that makes running beside
another step wrong.

This is the same metadata the analysis conformance checks in
[Task-Parallel-Safe Analysis Steps in Polaris](task_parallel_analysis_steps.md)
needs, and it should be one mechanism, not two. That document has since
landed and its rules are in the developer guide under
{ref}`dev-task-parallelism`; the shared mechanism does not exist yet, and
building it twice is what this is written to prevent.

## Testing

### Testing and Validation: Graph and Scheduling

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests shall cover graph construction from explicit and file
dependencies, shared steps, cycles, unsatisfiable inputs, cached and
completed steps, and the stability of ready-step ordering. These use
synthetic steps and need no allocation.

### Testing and Validation: Resource Accounting

Date last modified: 2026/09/08

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests shall cover packing: steps that all fit, steps where only a subset
fits, a step the allocation reduces from its target towards its minimum, and
a step whose minimum exceeds the allocation, which shall be reported before
the run. The reduction is the allocation's doing and not the pool's, so the
same step is offered the same width whatever else is running.

Memory shall be covered explicitly, including the case where cores are
available but memory is not, and the case where a step declares memory
smaller than its proportional share and is packed on the smaller figure.

The node-span constraint shall be covered too, in particular the cases that
distinguish it from a simple total: enough cores free across the allocation,
not enough on any one node, and a step that may not span; and a step needing
both cores and GPUs where each is available but not together on one node. It
shall wait rather than start, and a step that may span shall start on the
same allocation.

One property is worth testing as a property rather than as a case: a set of
steps that all take the default declaration shall produce exactly the
schedule that packing on cores alone produces. This is the guarantee that
introducing memory cannot degrade an existing suite, and it is cheap to
check against a core-only reference for a range of generated step sets.

Because the co-resident report is what a developer will have to work from
when a node runs out of memory, it shall be tested too: a step killed by a
signal shall be reported as terminated rather than failed, and shall name
the steps that were on its node with what they declared.

### Testing and Validation: Concurrency and Isolation

Date last modified: 2026/09/08

Contributors:

- Xylar Asay-Davis
- Claude

Integration tests shall use synthetic steps that sleep, produce outputs,
consume other steps' outputs and fail deliberately, and shall verify that
independent steps genuinely overlap in time, that a failure blocks only its
dependents, and that a rerun resumes correctly.

A placed step shall check that it received what it was given, and shall say
so when it did not. This is the standing check on real machines that Phase A
could not have: Phase A places nothing, so verifying placement there needed
a harness built for the purpose, while here every step has a placement
already and confirming it costs almost nothing. It runs on every machine on
every run, which is what makes it useful -- the thing it guards against is a
site changing its scheduler configuration underneath us, and that will not
announce itself.

What it reads differs with how the step was confined. A launched step is
asked what its ranks were given; a step bound by the executor is asked for
its own process affinity. Same question, different mechanism, and both are
cheap.

A mismatch shall be reported rather than corrected. A step given fewer cores
than it was promised is running in a way the scheduler's accounting does not
describe, and continuing quietly is how a run ends up oversubscribed and
slower than serial with nothing in the log to say why.

Overlap shall be checked from recorded start and end times, not inferred
from wall time. A test that concludes "it was faster, so it must have run
concurrently" will pass on a machine where nothing overlapped at all.

### Testing and Validation: Equivalence and Speedup

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A representative suite shall be run concurrently and compared against a
serial baseline; outputs shall match.

Wall time shall be recorded and compared, on each supported machine, but no
particular speedup shall be required to declare Phase B correct. Correctness
and isolation are the bar. Speedup below expectation is a reason to look at
the event stream, not a reason to hold the phase.

### Testing and Validation: Cross-Machine

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Validation shall cover Chrysalis, Perlmutter (CPU and GPU), Frontier and
Aurora, since these differ in exactly the way that matters: two eras of Slurm,
a PBS system, and GPU and non-GPU nodes. Each was measured to support what
Phase B needs, as recorded in
[Task Parallelism in Polaris](task_parallelism.md); this validation confirms
Polaris does it.
