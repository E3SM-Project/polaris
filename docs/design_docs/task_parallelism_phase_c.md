# Task Parallelism Phase C: Python Work Across Nodes

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
Analysis in Polaris will be many small Python steps, as MPAS-Analysis is
many small tasks, so this is the capability it depends on most. And a
resident can fork a child for each piece of work a step loops over inside
itself -- seasons, elevations, regions -- so that a step's own loop can use
other nodes too. That is MPAS-Analysis's own model, a child per subtask,
carried across nodes. Dask is kept for the one thing a child per piece
cannot do: a computation whose arrays are spread over several nodes.

The motivating workload is analysis. Polaris is to gain analysis capability
equivalent to MPAS-Analysis, which already parallelizes this kind of work
with Python's `multiprocessing` -- bounded to one node. At high resolution,
which is Omega's target, one node is not enough.

Phase C stands on Phase A and Phase B. A step that hands out work reserves
the cores its pieces run on, as any step that spans nodes reserves its
cores, and gives them back when it ends; the rest of the allocation stays
with ordinary steps. Since nothing holds cores beyond the step using them,
there is no share for Phase D to resize.

### What the measurement showed

How fine-grained analysis work is was an empirical question, and it has been
answered. A high-resolution MPAS-Analysis run was instrumented for per-task
duration, peak memory and dependency-graph width, and run cold on one node:
1231 tasks, none failed, 7h29m.

The work is fine-grained. The median task is 5.2 seconds and 49% run in
under five, at the resolution that matters. So whatever a resident starts --
a step, or a piece of one -- has to start in a small fraction of a second,
which forking from a process that has already imported Polaris does.

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
children that share it, which is the distributed equivalent of what
MPAS-Analysis gets for free, and it is the difference between a node
supporting a few children and supporting one per core.

Two things follow that the design has to state rather than assume.

Sharing must be asked for. This environment runs Python 3.14, where
`multiprocessing`'s default start method on Linux is `forkserver` rather
than `fork`; a forkserver child is forked from a clean server that never
loaded the parent's data, so it inherits nothing. Code that starts processes
without saying so would not reproduce the behavior described above.

Asking for it means forking from a process that may be multi-threaded, which
is what CPython changed the default to avoid. Phase B's rule applies
unchanged and for the same reason: hold thread pools to one before importing,
and check the count from `/proc` rather than from `threading.enumerate()`,
which reported one thread where the kernel reported 129.

The per-task memory figures from that run exclude the inherited inputs, so
they are not what a child holding its own inputs would need. What a child
needs is imports, plus whatever of the shared inputs its work touches, plus
its own data -- and the middle term was never measured because forking made
it free.

### Sizing a step's work, and what not to assume while doing it

The question that sizes a step's work is therefore **how much read-only
input each piece needs resident**, and it is deliberately phrased that way
rather than in terms of any particular kind of input. If pieces can work on
subsets, memory stops binding and a step is limited by cores. If each piece
needs all of it, the same node supports far fewer pieces at once than it has
cores. Polaris can measure this as soon as it has one real step of the kind,
and should, before steps declare their figures.

Two things follow that are easy to get wrong in opposite directions.

**Handing out work must not be designed around a shared dataset.** Analysis
happens to be a workload where many tasks read from one large input, and it
is tempting to build for that. Most Polaris workflows have no such thing,
and a mechanism that assumes one -- in how it starts children, in how it
accounts for their memory, or in what it expects a piece of work to be given
-- would serve one purpose well and the general case badly. Task parallelism
is the general facility; analysis is its first demanding customer, not its
specification.

**But a child's memory should not be assumed private either.** Where many
pieces on a node do read the same large input, holding one copy per node
rather than one per child is the distributed equivalent of what forking
gives for free, and the difference is large enough to change how many
pieces fit. This is worth leaving room for and is not worth building now:
nothing has been measured that needs it, and the measurement that would
justify it is the one described above. It is recorded here so that it is
not rediscovered late, and so that nothing in the design forecloses it.

### A task larger than one node

Nothing here restricts a step to a single node, and the design should not
acquire that restriction by accident.

Polaris already runs steps that span nodes: every MPI model run does. What
is bounded to one node is a non-MPI step running in its own process, which
is a property of processes rather than a decision Polaris made. A step that
hands its work out is not in that category.

Phase A provides the property this turns on: a step declares whether its
resources may be drawn from more than one node, defaulting to no for a step
with one task. A step that hands out work declares that they may, and this
phase is where anything first does. Its cores are then a reservation rather
than a placement: the step's own process needs about one core, and the rest
are where its pieces of work are forked.

The property covers GPUs on the same terms. A piece of work that uses GPUs
draws them from the node it is forked on, so a step's GPUs are reserved
where its pieces run, exactly as its cores are, and not on the node its own
process sits on.

This phase is where a limitation carried harmlessly through Phase A and
Phase B stops being harmless. On PBS with PALS, a launch needing no GPUs is
given an empty vendor visibility variable, and the runtime reads an empty
value as "no mask", meaning every device. That splits into two cases and
only one works: a child assigned *some* devices is confined, and a child
assigned *none* is not confined at all. Mixing GPU and CPU-only children on
one node therefore isolates the GPU children and not the CPU-only ones,
which is the opposite of the intuition that asking for nothing is safe.

A candidate fix is to name an out-of-range device rather than an empty
value. It is untested and should be tested: the runtime may equally refuse
it, warn, or fall back to every device.

One further thing is unestablished and matters more here than anywhere else.
That machine's configuration describes twelve GPUs per node, which are
tiles, while the runtime presents six cards; a mask naming three tiles
yielded two devices, which is consistent. What has not been tried is a mask
naming a *single* tile, which is the unit a scheduler handing out twelve
would assign. Whether two children masked to different tiles of the same
card are isolated, or merely both see that card, is the question this phase
rests on.

A computation whose data exceed one node's memory needs processes that hold
their chunks for as long as it runs, which a child per piece of work does
not provide. That is what Dask's distributed arrays are for, and it is the
one place this phase keeps Dask: a step that needs it gets Dask workers,
forked by the residents on the cores reserved for it, for as long as it
runs.

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

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A step shall be able to distribute Python work across more than one node of
the allocation.

This is the requirement that distinguishes Phase C from what MPAS-Analysis
can already do. A capability limited to a single node would not address the
problem that motivates the phase.

A step that launches nothing shall also be able to run on a node other than
the scheduler's, which is the bound Phase B accepted and this phase lifts.

This covers two things that should not be conflated: many independent pieces
of work running at once on different nodes, and a single computation whose
data are spread across the memory of several nodes. Both shall be possible.
The second is not expected to be common, but designing it out would be a
mistake.

### Requirement: Work Runs on Cores Reserved for It

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

The pieces of work a step hands out shall run only on resources the
scheduler reserved for that step, and those resources shall be returned when
the step ends.

An earlier attempt launched a worker pool without bounding it, which claimed
the whole allocation and prevented model runs from starting at all.

### Requirement: Steps Ask Explicitly for Cores for Their Work

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A step shall have to opt in to handing out work, and shall declare how many
cores its work wants and needs.

Ordinary steps shall continue to run as a forked child, as in Phase B, and
adding this phase shall not change how any existing step runs. A step forked
by a node's resident rather than by the scheduler shall behave identically:
same lifecycle entry point, same log, same completion markers. Phase B
specifies that entry point so that this costs nothing here.

### Requirement: Work Handed Out Must Be Safe to Run There

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

Work a step hands out shall not depend on process state that the process
running it does not have. Work handed to Dask workers shall also not disturb
state that other work in the same worker relies on.

A piece of work runs in a child of a resident, which never ran the step's
own setup. A child per piece means one piece cannot disturb the next, but a
piece can still depend on state it was never given. A Dask worker runs many
pieces over its lifetime, possibly several at once, so there work that
changes the working directory, sets a library-level default or writes to a
shared path is unsafe in a way it is not in a process of its own.

The properties this requires are set out in
[Task-Parallel-Safe Analysis Steps in Polaris](task_parallel_analysis_steps.md),
which should be adopted before analysis steps are written, and are written
up for step authors under {ref}`dev-task-parallelism`. Phase C depends on
those rules being followed; it cannot enforce them after the fact.

### Requirement: Failures Are Attributable

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

When a piece of work fails, it shall be clear which piece failed and why,
and the failure shall be reported as a failure of the step that handed it
out.

A child or worker that dies shall be reported as the failure of what it was
running, and nothing shall be retried silently. Absorbing a crash quietly
turns it into a mysterious slowdown.

### Requirement: The Cost Is Visible

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

The time spent starting and stopping the residents, and the cores a step
held while none of its work was running on them, shall be recorded.

Handing out work is only worth it if what it enables outweighs what it
costs. Earlier measurements found a worker pool spending around 9% of a
suite's wall time on its own lifecycle, which is the sort of thing that must
be visible rather than inferred.

## Algorithm Design

### Algorithm Design: What the Resident Process Is

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

Each node carries one resident Polaris process, started once and reused. It
imports Polaris once, which is the cost Phase B pays in the scheduler and
this phase pays once per node, in parallel.

A resident serves three kinds of request, and each is a fork. It forks a
child to run a whole step, which is Phase B's mechanism made available on a
node that is not the scheduler's, and which is what many small analysis
steps need. It forks a child for each piece of work a step hands out from
its own loops, so that a step can spread a loop over other nodes. And for a
step whose arrays are spread over several nodes, it forks the Dask workers
that hold them.

All three share their expensive part. A resident that has imported Polaris
and loaded a read-only input forks children that inherit that state at
copy-on-write cost. Building one mechanism rather than two is the reason
this phase absorbs Phase B's single-node bound instead of leaving it.

A step that opts in is given a handle, submits pieces of work, and collects
results. The pieces run on the cores reserved for the step, one per core at
a time.

Starting the residents is one launch per node, confined by Phase A
placement, so the rest of the allocation stays usable. *Implementation:
Launching the Residents* says what that launch allows their children. A run
starts them when it first needs them: at once if a step hands out work, and
otherwise when a step that launches nothing first waits for room on the
scheduler's node. Started at once, they were ready after 62 to 95 s in
`omega_pr` and `mpaso_pr` on three Chrysalis nodes, and forked nothing.

A child per piece of work, rather than long-lived workers, is a tentative
decision made on measured cost and revisited in *Decision: Warm Workers for
a Step's Work*. What a step sees is "submit work, get results", so the
mechanism underneath can change without changing any step.

### Algorithm Design: Where Handing Out Work Disappoints

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

The risks are operational rather than conceptual, and are worth naming so
they are designed for rather than discovered.

**Memory is Polaris's to account for, not the batch system's.** A step that
hands out work is charged memory as any step is: what it declares, or one
core's share of a node for each of its cores if it declares nothing, so that
each piece has one core's share. Measuring every step's memory would be
laborious, so that default has to serve most steps, and it does serve pieces
that fit in a core's share. A step whose pieces need more -- the analysis
steps this phase is for can be ones whose memory bears no fixed relation to
their cores -- declares what they hold at once: what one piece holds
resident, its own data and whatever of its inputs it keeps, times its cores.
That is not what an equivalent forking program would have needed, which is
smaller for the reason given above. A Dask worker's memory limit comes from
the same figure, and a worker that reaches it is reported rather than
restarted.

**Large results should not travel back.** Work that produces files should
write them and return paths. Returning large arrays moves them across the
network and through the resident and the step, which is the classic way to
turn a fast distributed computation into a slow one.

**A fresh child repeats its setup.** A piece of work that opens the mesh or
builds a plotting descriptor does so in every child, where a warm worker
could have kept it. Loading a read-only input in the parent before forking
avoids that, as the memory section above describes. What this costs on a
real analysis step is the measurement that decides whether warm workers are
worth having.

**There is a floor on useful task size.** Forking a piece of work, running
it and answering costs about 18 ms, measured on Chrysalis. That is noise
beside a five-second task, and it is why work far shorter than a second
should be handed out in batches rather than item by item.

### Algorithm Design: Sizing a Step's Work

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A step's work is sized from what the step declares, not from the
allocation: the cores it wants and needs, and the memory its pieces hold if
a core's share is not enough.
The cores are decided once from the whole allocation, as Phase B decides
every step's width, and the scheduler waits until that many are free rather
than starting the step on fewer. They may come from several nodes, and they
go back when the step ends.

Each reserved core runs one piece at a time. Once a step has fewer pieces
left than cores, the spare cores sit idle until its last piece finishes, a
tail of about one piece's length. That is what not holding a shared pool
costs; *Decision: A Shared Pool Held for the Run* says when the trade would
go the other way.

The numbers that make this concrete -- how many cores, how much memory each
piece -- follow from how much read-only input a piece needs resident, which
is the open question stated above and which Polaris can answer with one real
step of the kind. Until it is answered, a step relies on the default unless
its pieces are known to need more, and the run records what each step
reserved.

### Algorithm Design: Where a Step's Child Is Forked

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

The scheduler from Phase B does not change shape. It still decides what may
run and what resources each thing gets. What changes is where a step's child
is forked -- by the scheduler, or by the resident on the node its cores are
on -- and whether a step that opted in is also given a way to hand out work.

Polaris requires a step to launch only through its command, never from
`run()`. So a step whose `args` is `None` launches nothing, and its child
can be forked by any resident, with its cores drawn from any node that has
room. A step with a command -- even an empty one, which some steps fill in
at run time -- is forked by the scheduler as in Phase B. Its child launches,
and launching from inside a resident's own launch is what Phase B set aside.

Keeping the decision "what runs next" separate from "how it is executed" is
what prevents the scheduler from acquiring the mode-switching complexity that
made the earlier attempt hard to reason about. A resident is asked to fork;
it does not decide what runs.

## Implementation

### Implementation: Residents and the Step Hook

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

- a module owning the residents: starting them with one launch per node,
  connecting to them, stopping them, and reporting what they cost;
- a handle through which a step hands out work: it asks the resident on each
  node of the step's reservation to fork pieces onto the reserved cores, one
  per core at a time, and collects what they return;
- a step hook -- a separate method from `run()` -- through which a step
  receives the handle. Keeping it separate means the meaning of `run()` is
  unchanged for every existing step.

The residents must be stopped at the end of a run, including when the run
fails, or their children outlive the job.

### Implementation: Launching the Residents

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A resident is a single-threaded fork server. It imports Polaris,
`distributed` and the task tree once, starts no thread of its own, and
afterwards only forks: anything that starts threads -- a step, a piece of
work, a Dask worker -- does so in a child. Measured on Chrysalis, a resident
holds 283 MiB and two OS threads, the second being jemalloc's background
thread, which takes its own locks around a fork. It is ready 19 to 61 s
after its launch, almost all of it imports, paid once per node and in
parallel.

There is no Dask Nanny. A Nanny restarts a worker that dies and retries what
it held, which is the absorbed failure the requirements forbid. A resident
reaps its children itself, reports how each ended and restarts nothing, and
Dask's `allowed-failures` is set to zero so that a worker lost under a task
fails that task by name, which was measured to take 20 ms.

What a resident's launch lets its children use depends on how a machine
confines a launch. Chrysalis confines by CPU affinity alone -- Slurm 20.02
with `task/affinity` and `proctrack/pgid`, and no cgroup -- so a resident
launched on one core can bind its children to any core of its node, which
was measured. Where a launch is confined by a cgroup, its children cannot
leave it, so the resident would have to be launched over its whole node and
overlap the launches the scheduler makes. That has to be measured on each
such machine and probably needs a change in `mache`.

Nothing outlives the run. A resident exits when its connection to the
scheduler closes, and the batch system's process tracking is the backstop:
on Chrysalis, a resident killed outright had its children removed within
5 s while the other residents carried on, and stopping the launch left
nothing on any node.

Traffic between the scheduler, the residents and Dask goes over each
machine's fast interface, which is a per-machine setting. Dask otherwise
takes the interface a node's hostname resolves to, which on Chrysalis is
1 GbE: 512 MiB took 5.1 s there and 1.2 s over InfiniBand with TLS. The
channel to each resident also sends small messages at once (`TCP_NODELAY`).
Without that, a reply sent right behind another waited for a delayed
acknowledgement, which added 40 ms to every piece of work.

### Implementation: Who May Connect

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

Every connection the residents and Dask open is authenticated. Dask's TCP is
unauthenticated by default, so on a shared machine anyone who can reach a
worker's port could run code as the person running the suite.

The channels to the residents use a key generated for the run, which a
resident receives through its environment rather than its command line,
since other users on a node can read a process's command line but not its
environment. Dask uses TLS with certificates generated for each step that
starts workers, which needs `cryptography`. Its dashboard is turned off,
being one more open port, but Dask opens an HTTP port on the scheduler and
on each worker regardless, so those listen on their own node only and serve
nothing.

### Implementation: Handing Out Work Under `polaris serial`

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

`polaris serial` is the default path and runs every step, so a step that
hands out work, or computes with Dask across nodes, must run there too.
Before the first such step runs, `polaris serial` starts residents on the
allocation's nodes exactly as `polaris parallel` does -- forking a single one
locally where there is only one node or no allocation -- and the step uses
them the same way. One local resident would not do: a Dask step that needs
more than one node's memory would fail on it. One mechanism on both paths is
also what lets their results agree by construction.

### Implementation: What a Piece of Work Carries

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A child forked by a resident has Polaris imported and none of the setup its
step's own process performed. Anything the work needs must travel with it.
Earlier work discovered this the hard way: NetCDF output settings were
configured in the main process, so work running in workers silently wrote
files in a different format, which showed up as a step taking fifty seconds
instead of ten.

Rather than replicating a step's setup inside each child, the work handed
out should carry what it needs. This is the same discipline the analysis
groundrules require, and it is the reason those rules matter more here than
anywhere else.

## Decisions

Alternatives considered and set aside. Cited from the sections they affect
rather than argued there.

### Decision: Warm Workers for a Step's Work

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

**Set aside, tentatively.** Earlier versions of this design ran the pieces
of a step's work on long-lived Dask workers. Measured on two Chrysalis
nodes, a child per piece costs about the same at the size analysis work
has:

| | child per piece | warm Dask worker |
| --- | --- | --- |
| start before the first piece | nothing | 0.2-0.7 s |
| round trip, trivial piece | 17-18 ms | 10.5 ms |
| one plot | 0.082 s | 0.071 s |
| private memory per process | 2.6 MiB | 21 MiB |

At a median task of five seconds, both overheads are a fraction of a
percent. What a child buys is that nothing one piece leaves behind can reach
the next, and that there is no worker to size, keep or restart. What it
gives up is setup a warm worker could keep between pieces. This is to be
revisited once a real analysis suite can show what that setup costs, and
once there are steps that use Dask collections.

### Decision: Workers Started for Each Step

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

**Rejected for ordinary work.** Giving each step that hands out work its own
Dask workers, started when it starts, isolates steps by construction. But
analysis is many small steps, and each would pay the start-up -- 0.2 to
0.7 s, measured -- before its first piece ran. It is kept only for a step
whose arrays span nodes, which is rare and long enough to absorb it.

### Decision: A Shared Pool Held for the Run

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

**Set aside.** Earlier versions of this design reserved a block of the
allocation for handed-out work when the first such step started, kept it
until the run ended, and gave each step a lease within it. With a child per
piece there are no workers to keep warm, so the block buys only one thing:
another step's pieces can fill a step's idle cores while its last pieces
finish. What it costs is a share held after the Python work is done, which
is what Phase D existed to give back. A step reserving its own cores costs a
tail of about one piece's length instead. To be revisited if real testing
shows a shared pool doing better.

## Testing

### Testing and Validation: Multi-Node Distribution

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A test shall hand out work and verify from the results which node each
piece ran on, confirming that more than one node was used. This is the
central claim of the phase and should be checked directly rather than
inferred from timing.

It was done on two Chrysalis nodes in October 2026, under both `polaris
parallel` and `polaris serial`. A step handing out 192 two-second pieces
over 96 cores took 64 on one node and 32 on the other, and every piece
reported its host and a single core. A step computing with Dask had a worker
on each node, with 64 and 32 threads, and each worker's memory limit was
what the scheduler had reserved on its node. Of 100 two-minute steps that
launch nothing, the 64 that fit on the scheduler's node ran there and the
other 36 were forked by the other node's resident. `omega_pr` and `mpaso_pr`
on three nodes matched baselines from `main`, 128 to 0 and 90 to 0.

### Testing and Validation: Safety of Work Handed Out

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

A test shall hand out a piece of work that changes the working directory and
mutates a library default, and confirm that the next piece forked on the
same node sees neither.

Checking that work handed to Dask workers follows the rules -- that it
leaves the working directory and library defaults alone and writes only in
its step's work directory, even with other tasks running beside it in the
same worker -- is deferred until there are steps that use Dask. Those will
show which defaults matter. Until then, a Dask task is trusted to follow the
rules, as a step's own `run()` is.

### Testing and Validation: Failure Handling

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

Tests shall cover a piece of work that raises, one that exits its process
outright, a resident lost mid-run and, for Dask, a worker lost mid-run. In
each case the step that handed the work out shall fail with an attributable
error, and the run shall not hang.

Unit tests cover each case. Chrysalis repeated the ones a test machine
cannot show: a piece that raised failed its step, naming its call, core and
node and giving its traceback; a Dask worker killed under a task failed its
step, naming the node and the worker's log; and interrupting the scheduler
with SIGINT or SIGTERM while pieces, Dask tasks or steps forked by
residents ran left nothing on any node ten seconds later.

### Testing and Validation: Is It Worth It

Date last modified: 2026/10/23

Contributors:

- Xylar Asay-Davis
- Claude

Validation shall compare the same analysis workload run three ways: as
ordinary Phase B steps, as one step handing out its work on one node, and as
the same step on several. The comparison shall include what starting the
residents costs.

If handing out work does not beat Phase B steps on the real workload, that
is a finding, and it should be recorded rather than worked around. The same
comparison is what revisits the two tentative decisions: whether warm
workers, or a shared pool, would have done better.

The measurement already in hand does not decide this, and it is worth being
clear about why. It was taken on one program, on one node, using fork, with
a critical path dominated by tasks that would be rewritten before they ever
ran here. It establishes that the work is fine-grained and that a child's
resident inputs are the quantity to watch. It does not establish what
handing out work is worth, because the version of the workload that would
run that way does not exist yet. The comparison has to be made against Polaris's own steps,
and this phase should not claim a speedup it has not measured on them.
