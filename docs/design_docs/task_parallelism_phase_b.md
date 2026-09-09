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
executor that runs each step in a forked child process.

MPI steps and Python steps are treated the same way. Earlier designs staged
them separately because an MPI step could not be confined to part of the
allocation. Phase A removes that reason, and with it the barrier between the
two kinds of work and the cost of switching between them.

Each step runs in a process of its own, forked from the scheduler. The two
halves of that are separate decisions and the difference decides the phase.
*Isolation* is required: Polaris steps change the working directory, set
library defaults and use `pyplot` globals, so two steps sharing a process
would race. *Forking* is how the process is made, and it matters because the
alternative was measured and does not work. A step started as a fresh
`polaris serial` subprocess spends about 35 s importing Python before it
does any work, and paying that once per step consumed the whole speedup: on
`omega_pr` the concurrent run took 13:04 against a serial baseline of 12:15.
A forked child inherits the modules the scheduler has already imported and
the live `Step` object it already holds, so it pays neither. Measured on
four `omega_pr` steps, forking saved about 48 s per step.

This is where the regression-suite speedup arrives. On a recent `omega_pr`
run on Chrysalis, three nodes, 12:26 total: the MPI work amounts to roughly
236 s of core-time on 192 cores, against a dependency floor of about 106 s,
so something in the range of 2.5-3x is the expectation on the same
allocation. That is an estimate from one run's timings, to measure against
rather than a promise.

Success in Phase B means a suite's independent steps run together, results
match serial execution exactly, a failure stops only the work that depended
on it, and reruns still skip completed steps.

## Open Questions

### What target and minimum threads should a JIGSAW step declare?

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

JIGSAW is the only consumer of thread parallelism in Polaris's own Python
work, and it is not configured the way the rest of the framework is: the
binary links `libgomp` and calls `omp_set_num_threads`, but it takes its
count from `NUMTHREAD` in its own job-config file, which `jigsawpy` exposes
as `opts.numthread`. So `OMP_NUM_THREADS` does not reach it. Polaris never
sets it, which means the two steps that shell out to it -- the
quasi-uniform and unified spherical base meshes -- run at whatever thread
count the machine offers. Those meshes are therefore not reproducible across
machines or allocation shapes today, independently of task parallelism.

The agreed shape of the fix is that those steps declare
`cpus_per_task`/`min_cpus_per_task` -- a true statement about *cores*, which
is what the pool reserves and the child is bound to -- and pass the number
they were assigned to `opts.numthread`. The step choosing one thread per
core is the step's business rather than the framework's, so this needs no
new resource vocabulary.

What is open is the number. JIGSAW should want many cores for a large mesh
and few for a small one, so a single figure on the base class may be the
wrong shape and the declaration may have to vary with resolution or be
derived from the cell count the step already computes. This shall be
measured rather than guessed: a quasi-uniform mesh at high resolution and at
factors of four or eight coarser, each at several thread counts, with
`numthread` set explicitly.

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

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall run as many ready steps as the allocation's resources allow,
and no more.

Cores, GPUs, nodes and memory shall all be accounted for. A step whose
minimum requirements cannot be met by the whole allocation shall be reported
as impossible before the run starts.

The memory a node is credited with shall be what that node reports, not what
its machine's configuration estimates, and nodes shall be tracked
individually rather than as copies of one node. Aurora is heterogeneous: a
survey of all 10,624 of its nodes found about one in nine holding roughly
1007 GiB where the majority holds 1135, so a figure taken from the majority
over-admits by about 13% whenever a step lands on a small node.
Over-admitting memory kills a job rather than slowing it.

A step that has not said its resources may span nodes shall have its cores
and its GPUs drawn from a single node. This is a packing constraint rather
than a total: an allocation with cores free on several nodes and none
holding enough shall report that such a step cannot start, rather than
deadlocking or overcommitting. A step needing both cores and GPUs shall find
both on one node. A step that may span is bounded only by what the
allocation holds.

Memory accounting is admission control and nothing more. Cores, GPUs and
nodes are handed to the launcher, which keeps steps off each other's; memory
is not, because nothing below Polaris acts on it. A step that starts and
then exceeds what it declared is not stopped. So the accounting is only as
good as the declarations, and this design claims no more than that.

A step that declares no memory is taken to want its proportional share of a
node, so a run in which nothing declares memory packs exactly as it would
with no memory accounting at all. Memory accounting can only ever remove a
schedule that a measured declaration says would not have fit.

A step's resources shall be decided from the whole allocation, exactly as
`polaris serial` decides them, and the scheduler shall wait until that much
is free rather than starting the step on less.

Width must not become a packing lever. A step handed whatever happened to be
free when its turn came has a width that depends on scheduling timing, and
for an MPI model step the width is the decomposition -- so the same suite on
the same allocation would produce different outputs on different runs, which
contradicts *Results Match Serial Execution*. A step's memory budget, being
proportional to its cores, stops moving for the same reason.

This costs packing: a wide step waits for room a narrower version would not
have needed. If that cost proves large, the way to buy it back is to let a
step declare that its results do not depend on its width, which is true of
most steps that are not model runs.

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

### Requirement: Starting a Step Shall Cost Almost Nothing

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The cost of starting a step shall not depend on how many steps the run
contains, and shall be small beside the work the step does.

Running a suite concurrently must not be slower than running it serially.
That is not a performance target but a correctness-of-purpose one: a
concurrent path that loses to the serial path has no reason to exist.

The first Phase B implementation started each step as a fresh `polaris
serial` subprocess and failed this. Measured on `omega_pr`, three Chrysalis
nodes, 115 steps: 5807 s of measured step time against 1668 s of actual
work, so 71% of it was startup, 36.6 s per step. Both kinds of step pay it
-- 34.6 s median for 1-core Python steps and 37.6 s for MPI steps, because
an MPI step's driver is itself a full Polaris process before it reaches
`srun`. The result was a concurrent run of 13:04 against a serial baseline
of 12:15.

The asymmetry is what makes this fatal rather than merely wasteful. A serial
run imports once for the whole suite; a per-step subprocess imports once per
step. So the cost is one the concurrent path introduces against a baseline
that does not pay it, and it grows with the node count: more concurrency
shrinks the science and leaves the startup untouched.

Reducing the constant does not satisfy this requirement. The startup is
about 2,880 module imports from a parallel filesystem, and deferring the
component imports in `polaris/tasks/__init__.py` was tried and measured --
2,880 modules to 2,868, because unpickling a step needs the same set anyway.
Import cost is worth reducing on its own merits and does not change that it
would be paid once per step.

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

### Requirement: Nothing Outlives the Scheduler

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

A scheduler that stops shall stop the steps it started, whether it is
finishing, interrupted or failing.

A forked child is a direct child of the scheduler. One left behind holds
cores with nothing watching it and, for an MPI step, a model still running
behind it; one never reaped is a zombie for as long as the scheduler lives.
Inside a batch job the allocation ending hides both, which is why the first
implementation could go without this and nobody notice until a suite was run
interactively.

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

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

Where the machine can hold a launch to a memory figure, Polaris shall do so
for a step that declared one, and shall not for a step that did not.

Polaris shall not rely on enforcement in place of its own accounting.
Admission control works on every machine; capping does not.

This is possible on newer Slurm and not on older: a launch allowed 1024 MB
and told to take 4 GB is killed at 960 MB on Perlmutter GPU and on Frontier,
and runs to completion on Chrysalis. PALS offers no per-launch memory size,
so Aurora is expected not to enforce. Enforcement is therefore uneven across
machines, which is accepted: it reaches only steps whose authors opted in by
declaring, and replaces silent divergence with loud.

An unenforced declaration is invisible when it is wrong. It makes the
scheduler's accounting a fiction, and surfaces much later as an exhausted
node, or never surfaces while costing throughput. A step that stated a
number is making a claim and can fairly be held to it.

A step that said nothing takes the proportional default, which is a rough
guess and is known to be poor where memory has little to do with core count.
Capping a step at the framework's own estimate would not improve the
estimate; it would require every step to carry a measured figure before it
could run, and arrive as a wave of failures in steps nobody had touched.

One question that could have reshaped this was answered and did not.
Placement on newer Slurm asks for exactly what a step needs, so a placed
step might have received a memory ceiling nobody set. It does not: on
Perlmutter CPU and Frontier, a placed single-core launch and an unplaced
control, neither mentioning memory, both allocated twice a single core's
proportional share and neither was touched. That bounds rather than settles
-- no ceiling below the amount tried, and Perlmutter GPU untested -- but it
removes the mechanism that would have forced Polaris's hand.

### Requirement: Results Match Serial Execution

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

For deterministic workflows, running concurrently shall produce the same
final outputs as running serially.

### Requirement: The Run Can Be Understood Afterwards

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

A concurrent run shall record enough to reconstruct what happened: which
steps ran when, what resources each held, what each was waiting for, and how
the total compares with running serially.

Where the run reports how much work it did, the figure shall be the steps'
own work and shall exclude the cost of starting them. The first
implementation summed the time from starting a step's process to reaping it,
and reported `omega_pr` as doing 7.2x the work of a serial run on a run that
was slower than serial -- because 4,200 s of Python imports counted as work.
A metric that reports health while the wall clock says otherwise is worse
than none.

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

### Algorithm Design: Running a Step in a Forked Child

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler forks a child for each step it starts, and waits for it.

The child inherits the parent's address space, which is what makes this both
correct and fast. It is a private copy, so the step may change the working
directory, set library defaults and use `pyplot` globals exactly as it does
today. It already holds every module the scheduler imported and the live
`Step` object the scheduler selected, so it imports nothing and unpickles
nothing -- the two costs that made a per-step subprocess unaffordable.

Measured on Chrysalis, four `omega_pr` steps run both ways in the same
allocation, 32 trials, all of which exited cleanly:

| step | cores | forked | subprocess |
| --- | --- | --- | --- |
| `column/inertial/analysis` | 1 | 3.7 s | 56.3 s |
| `column/thermo/conservation_summary` | 1 | 0.1 s | 46.8 s |
| `manufactured_solution/.../del4/analysis` | 1 | 1.9 s | 46.2 s |
| `baroclinic_channel/10km/restart/full_run` | 4 | 2.4 s | 51.4 s |

Forking saved 48.2 s per step. The subprocess column is almost entirely
startup: `conservation_summary` reports its own runtime as under a second,
so the 46.8 s bought nothing. A forked child produced output identical to
the subprocess digit for digit.

Sharing is nearly complete. Twenty-four concurrent children held 347 MiB
between them against the parent's own 322 MiB, where naive resident-set
accounting reports 7,700 MiB and would size a node wrongly by a factor of
twenty.

A forked child shall, before running the step: restore the default
disposition of the signals the scheduler handles, change to the step's work
directory, redirect its own file descriptors 1 and 2 to the step's log, run
the shared step lifecycle, and end with `_exit` so that it never runs the
scheduler's exit handlers or flushes buffers the scheduler still owns. The
redirection is by file descriptor rather than by reassigning Python's
streams, so that output from a model an MPI step launches lands in the log
too. The parent shall flush its own streams before forking, or a child
inherits the buffer and the output is written twice.

The same mechanism serves MPI and non-MPI steps. An MPI step's child goes on
to launch its model through the parallel command; a Python step's child
simply runs Python. The scheduler needs no second executor and no barrier
between them. A forked child reaching `srun` and returning was measured, not
assumed.

What the two do not share is how they are confined. An MPI step's placement
reaches a launcher, which puts the work on the nodes and cores it names. A
non-MPI step does its work in the child itself, and nothing between the
scheduler and that child acts on a placement, so the child sets its own
affinity -- which it can only do on the node it is running on. A step that
is not launched shall therefore be given cores on the scheduler's own node.

That puts a ceiling on Python concurrency at one node's worth of cores. It
is the ceiling Phase C lifts. It costs little in the suites this phase
targets: `omega_pr`'s 85 one-core steps hold about 979 core-seconds of work
between them, which is some 15 s on one 64-core node against a suite of
twelve minutes.

Every step has a child on the scheduler's node for as long as it runs, MPI
steps included, and those are not reserved. A child blocked waiting for its
model consumes no core, so reserving one each would cost more concurrency
than the children cost the node. The point at which that stops being true is
a child that does real work while its model runs.


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

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The per-step lifecycle -- runtime input checks, dependency loading,
`runtime_setup()`, `run()`, output checks, validation, completion markers --
currently lives inside `polaris/run/serial.py`. It should be moved into a
shared module that both the serial and concurrent paths call, with no change
in behavior. This is a pure refactor and should land as its own change,
ahead of the scheduler.

What runs in a forked child shall be one entry point, taking a `Step` and
producing a step's log, outputs and completion markers indistinguishable
from the serial path's. This is the seam Phase C reuses: a child forked by a
resident process on another node differs only in where its `Step` came from,
so the child-side code should not know which forked it. Log parity is part
of the contract and is easy to lose -- a first attempt called the lifecycle
directly and produced correct results with a log missing its `Running step:`
preamble and its `execution: SUCCESS` footer.

### Implementation: How Many Threads a Step's Process Uses

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The numerical thread pools shall be held to one on both paths, and shall be
held there before anything imports numpy.

Three paths disagreed. `polaris serial` ran unconfined and got one OpenBLAS
thread per core on the node -- 128 on Chrysalis. A per-step subprocess bound
to its placement before importing numpy got one per placed core. A forked
child inherits the scheduler's count whatever its own placement.

Polaris asks nothing of a threaded BLAS in return: every `np.linalg` call in
the framework is a vector norm over a one-dimensional array, `polyfit` runs
on a handful of convergence points, and the one `matmul` is a stack of tiny
per-point matrices. What the pool costs is reproducibility, since a threaded
reduction sums in an order that depends on the thread count. Pinning both
paths is what lets them agree by construction, as *Results Match Serial
Execution* requires, and it is also what makes the scheduler safe to fork
from. Baselines shift once against this, which is what regenerating them
from `main` is for.

It shall be set in `polaris/__init__.py`, above that package's own imports,
and not in the command-line entry point. OpenBLAS sizes its pool when numpy
is first imported and nothing resizes it afterwards without `threadpoolctl`,
which Polaris does not depend on; importing `polaris.__main__` imports the
package first, so a process that pins there already holds 129 threads. A
test shall ask for that placement specifically, since the mistake looks
correct.

It says nothing about a model's threading. `run_parallel_command()` sets
`OMP_NUM_THREADS` from a step's `openmp_threads` for a launched command,
which overrides this, and JIGSAW takes its count from its own config file.
An explicitly chosen value is left alone, so a job script may still say
otherwise.

### Implementation: The Scheduler Must Be Safe to Fork From

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler process shall hold no thread but its own at the moment it
forks, and shall verify this rather than assume it.

Only the forking thread survives a fork. A lock held by any other thread at
that moment is held forever in the child, and the symptom is a step that
hangs rather than one that fails.

Polaris is multi-threaded on import and does not look it. Measured on
Chrysalis, `import polaris` leaves the process with **129 OS threads** --
128 from the OpenBLAS pool numpy brings up, one thread per visible core, and
one from the allocator. `threading.enumerate()` reports one, because it sees
Python threads only. Any check shall read `/proc/self/status`, which is
also what CPython's own fork warning uses.

Setting `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and `MKL_NUM_THREADS` to
one before anything is imported takes the same process to two threads. The
scheduler does no numerical work, so this costs it nothing.

The scheduler shall also not wait on its children with a thread each. The
first implementation started a daemon thread per running step to wait on it,
which is a reasonable design under `subprocess` and an unsafe one here. It
shall reap children in its own loop instead.

Forking with the OpenBLAS pool present was measured not to hang, over
sixteen trials on four steps. That bounds the risk rather than settling it:
sixteen trials on one machine cannot establish that a lock is never held,
and the mitigation is cheap enough that there is no reason to run without
it.

### Implementation: What a Forked Child Inherits

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler shall not mutate a step's state after the step graph is built.

A subprocess re-read `step.pickle` from disk, which isolated each step from
whatever the scheduler had done to its object in memory. A forked child
inherits the scheduler's objects instead. That is what removes the unpickle
cost, and it means a step's behaviour now depends on what the scheduler
holds at the moment it forks.

Sizing a step's resources is the one mutation that has to happen, and it
already happens in the right place: `constrain_resources()` runs against the
whole allocation once, before the loop starts, which the target-and-minimum
rule requires anyway.

Thread pools are inherited the same way, and not as one would guess. A
forked child keeps the parent's pool size whatever its own affinity: a child
confined to one core, four cores and sixteen cores returned an identical
checksum and the same thread count in each case. Under a subprocess this was
not so -- OpenBLAS sizes itself from the affinity mask at import, so a
placed step bound to one core got one thread while an unconfined serial run
got 128.

That difference is a candidate explanation for the six baseline comparisons
that differed by 0.01-0.02% in the first concurrent `omega_pr` run, since
threaded reductions change summation order. It is a mechanism that fits the
observation, not a demonstration that it caused it; one run of that mesh
step under two thread counts would settle it. Forking removes the mechanism
either way, because every child then shares one thread count.

### Implementation: The mache Side

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

Phase A described a placement as the nodes a step may use and how many cores
it may use *on each*. `mache` 3.12.0 implements it as one flat tuple of
unique core ids, divided into one chunk per rank. For a single node the two
are the same statement; for several they are not, and the difference stops
Phase B from placing a step wider than a node on two of the five machines.

Where the batch system reserves what a job step asks for -- Slurm 20.11 and
newer, so Perlmutter and Frontier -- only the count is used and the ids are
ignored, so a multi-node placement renders correctly today. Where the
launcher binds explicitly -- Chrysalis on Slurm 20.02, Aurora on PALS -- each
chunk becomes a CPU mask for one rank, and those ids are node-local. Since a
placement's ids must be unique, two nodes cannot both use core 0, so a
spanning launch is expressible only while its total cores fit inside one
node's id space.

This is a reading of the 3.12.0 renderers rather than a measured failure. No
multi-node placement has been rendered on any machine, since Phase A's
verification put all four concurrent launches on one node deliberately. The
cross-machine validation below is where it gets tested.

Phase B needs it: the three 64-core Chrysalis nodes `omega_pr` sizes itself
to come from a widest step asking for more than 128 cores. That is
arithmetic on the figure in the summary rather than a measurement of the
suite, and is worth measuring before the pool is built.

So `mache` gains two things, and Polaris develops against the branch until
they are released, as Phase A did:

- **a placement carrying one core list per node**, aligned with the nodes it
  names. This is what the pool naturally produces, and it removes the
  coupling that would require every node of a spanning launch to have the
  same ids free.
- **the allocation's individual nodes**, by name. Polaris cannot build a
  placement without them.

Reading the nodes from the job's environment rather than from the batch
system also keeps *Do Not Poll the Batch System* satisfied. `ParallelSystem`
asks `squeue` or `qstat` for its node count when constructed, which under
the subprocess model happened once per step; forking constructs it once in
the scheduler and every child inherits it, so the pressure is off either
way.

`Component.get_available_resources()` reads a placement's cores as a
per-node set and multiplies by the node count, following Phase A's
description rather than what `mache` renders. Nothing builds a multi-node
placement today, so the disagreement is inert; it stops being inert here.

### Implementation: New Modules

Date last modified: 2026/09/09

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
- an executor, forking a child for a step with its placement, reaping it and
  reporting completion;
- a scheduler, owning the loop above;
- an event stream, recording scheduling decisions as structured records.

These should be small and separately testable. The scheduler in the earlier
attempt grew past three thousand lines, largely because worker-pool lifecycle
and mode-switching policy lived inside it; forking has no lifecycle to
manage and the loop stays short.

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

## Decisions

Alternatives considered and set aside. Cited from the sections they affect
rather than argued there.

### Decision: A Fresh `polaris serial` Subprocess per Step

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

**Superseded.** This is what Phase B first specified and first implemented,
and it reached `main` in `09bc9c60e8`. It was chosen because one mechanism
served MPI and non-MPI steps and each step got a clean process; what it
never accounted for was startup. Measured, that startup was about the size
of the median step's own work, and the concurrent run lost to the serial
one. See *Starting a Step Shall Cost Almost Nothing* for the figures.

The scheduling half of Phase B was unaffected and is carried forward
unchanged: the step graph, the resource pool and admission control, the
allocation reader, placement transport and the standing placement check, the
event stream, and the opt-in concurrent job script. What changed is confined
to how a step is started.

### Decision: Steps as Functions in a Pool of Worker Processes

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

**Rejected for whole steps.** A pool removes the startup cost too, but runs
steps in a shared process, which requires the task-parallel safety that
{ref}`dev-task-parallelism` says most steps do not have. It is a good fit
for fine-grained Python work, and Phase C adds it for exactly that.

### Decision: Launching Every Step's Driver Through the Launcher

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

**Rejected.** It would let a non-MPI step run wherever it was placed rather
than on the scheduler's node. An MPI step's driver would then start its
model from inside a job step, which needs care on newer Slurm and is a known
way to hang. This is a reason to leave it out rather than a finding, and is
worth revisiting with a measurement.

### Decision: A Resident Fork Server on Every Node

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

**Deferred to Phase C.** One long-lived process per node, importing Polaris
once and forking a child per step, would lift the one-node ceiling on
non-MPI steps. It buys about 15 s on `omega_pr`, and costs Phase B a control
channel and a process lifecycle -- the thing this phase is written to keep
out of the scheduler. Phase C needs a resident process per node for its own
reasons, so the mechanism is built once, there.

### Decision: Reducing the Number of Imports

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

**Insufficient on its own.** Importing one ocean init step pulls 2,313
modules, because `polaris.mesh.info` reaches `polaris.mesh.spherical` and a
task module imports its own analysis and viz. Deferring the component
imports in `polaris/tasks/__init__.py` was measured: 2,880 modules to 2,868,
because unpickling a step needs the same set. Worth doing on its own merits;
it does not change that the cost would be paid once per step.

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

### Testing and Validation: Forking

Date last modified: 2026/09/09

Contributors:

- Xylar Asay-Davis
- Claude

A test shall confirm that the scheduler holds no thread but its own before
it forks, reading the count from `/proc/self/status` rather than from
`threading.enumerate()`, which sees Python threads only and reported one
where the kernel reported 129.

A test shall confirm that a forked child's log, outputs and completion
markers match what the same step produces on the serial path. Results
matching while logs differ is the failure mode a first attempt actually
had.

Per-step start cost shall be measured on a real suite and recorded, since
this is the quantity the phase was rebuilt around. It should be small beside
the shortest real step. Measured on Chrysalis it was under 4 s against 46-56
s for a subprocess.

An MPI step shall be included. Its child launches a model, which is the case
that would break first if forking interfered with the launcher, and it is
79% of the work in the suites this phase targets.

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
