# Task Parallelism Phase A: Placement

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Today, when Polaris runs a step that uses MPI, it launches it across the
whole allocation. That is correct when only one step runs at a time, and it
is the single largest obstacle to ever running two steps at once: two steps
that each believe they own the machine will either collide or, more often,
queue behind one another.

Phase A gives Polaris the ability to run a step on a **named part** of its
allocation -- these nodes, these cores, these GPUs -- and gives steps a way
to describe what they need, in terms the batch system can act on.

Phase A does not run anything concurrently. At the end of it, Polaris still
executes one step at a time and produces identical results. What changes is
that the machinery for saying "run this here" exists and is known to work on
every machine Polaris supports.

Most of the work is not in Polaris. Polaris does not build the command that
launches parallel work; `mache` does, through its `ParallelSystem` classes.
`mache` is a contract shared with other software, so the launcher change must
land there first. That change has its own design document in the `mache`
repository; this document describes what Polaris needs from it and what
changes on the Polaris side.

Success in Phase A means Polaris can construct a correct launch command for a
step confined to a given subset of the allocation, on Slurm and on PBS, for
CPU-only and GPU steps, and that `polaris serial` behaves exactly as before.

## Requirements

### Requirement: Confine a Step to Part of the Allocation

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Polaris shall be able to launch a step so that it runs on a specified subset
of the allocation's nodes and cores, rather than on all of them.

The subset shall be expressible in terms Polaris already understands: which
nodes, how many cores, and how many GPUs. Polaris shall not need to know
machine-specific syntax in order to express it.

### Requirement: Isolation Enforced by the Batch System

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

When two steps are confined to non-overlapping subsets, the batch system
shall be what keeps them apart, not Polaris.

We prototyped an alternative in which Polaris pinned processes itself using
CPU affinity masks. It works, but it is a weaker guarantee: a step that
ignores its mask is not prevented from doing so, and the mechanism differs
per machine. Measurements showed the batch system can do this properly on
every supported machine, so it should.

The exception is machines running Slurm older than 20.11, such as Chrysalis,
where the necessary options do not exist. There, Polaris shall fall back to
explicit CPU binding, and shall record that it has done so.

### Requirement: A Step's GPU Need Is Always Stated Explicitly

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A Polaris step uses no GPUs unless it declares otherwise. That premise does
not change, and most steps will continue to declare nothing.

What must change is that Polaris shall state a step's GPU need to the
launcher in every case, **including when it is zero**. Passing nothing is
not the same as passing zero: the batch system treats an unstated GPU
requirement as a claim on the node's GPUs and reserves all of them, which
prevents any other step from starting. Because most Polaris steps use no
GPUs, explicitly requesting none is the ordinary case rather than a special
one.

A step that does want GPUs shall declare how many **the step** needs, not
how many each MPI rank needs. This differs from how CPU resources are
described today, where `ntasks` and `cpus_per_task` are per-rank
quantities, and the difference is not cosmetic: measurements on both GPU
machines showed the per-rank form does not confine a step at all, while a
per-step total does.

### Requirement: Steps Declare Memory

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A step shall be able to declare how much memory it needs, as a target and a
minimum, in the same style as its existing CPU requirements.

Memory is unlike cores and GPUs in that the batch system will not keep it
for us. Asking a launch for a share of the node's memory was measured to
change nothing, so a memory figure passed to the launcher would reserve
nothing and prevent nothing. Memory is therefore a budget Polaris keeps
itself: the only way one step's memory is protected from another's is that
Polaris declines to start the second step. That decision is Phase B's, and
so is the accounting behind it.

What Phase A shall provide is the declaration, its default, and its
visibility to the step. A step that declares nothing shall be treated as
needing memory in proportion to the cores it asked for -- the node's memory
divided by its cores, times the step's cores. This is deliberately the value
that makes memory-aware packing arithmetically identical to packing on cores
alone, so that introducing memory can never make Phase B schedule worse than
it would have without it, and so that no per-step number has to be invented
for the steps that exist today. Steps that have been measured, which is
mostly the analysis work in Phase C, override the default with a real
figure and are then scheduled on it.

Because a step's memory need is not enforced anywhere, an under-declaring
step running beside others is a real failure mode, and one that did not
exist when Polaris ran a step at a time. Phase B addresses it.

Device memory needs no declaration of its own. GPUs are never divided
between steps, so a step given a GPU is given that GPU's memory with it, and
the GPU count already accounts for it.

Host memory on a GPU machine is the case where the proportional default is
most likely to be wrong, and a step author should expect to declare rather
than rely on it. A step that wants every GPU on a node and only a handful of
cores to drive them gets, by the proportional rule, only that handful's
share of the node's memory -- which is unlikely to be what it needs to stage
data for the devices. Making the default depend on GPUs as well would
destroy the property that makes it safe, since it is exactly its being
proportional to cores that makes memory-aware packing reduce to packing on
cores. The default is a floor for steps nobody has measured, not an estimate
anyone should trust for a step whose memory has nothing to do with its core
count.

### Requirement: Resource Views Describe What a Step Can Use

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The resource information given to a step shall describe the resources that
step can actually use.

A step confined to one node shall be told about one node's resources, and a
step whose work may span nodes shall be told about all of the resources it
was given. Telling a step that runs its work in its own process about cores
on nodes it will never reach invites it to size itself wrongly; telling a
step that distributes its work about one node's worth understates what it
has. The view shall describe how a step's resources are distributed, not
only how many there are, since that is the part a step sizing itself needs
and the part a single number cannot carry.

Any resources withheld from a step shall be genuinely withheld, not merely
subtracted from a number.

Memory shall be part of that view. It is the one resource where the number a
step is told is the only thing standing between it and the node's limit,
because nothing below Polaris will stop it, and it is the number a step that
sizes something for itself -- a worker pool, a chunk size -- has to size
against. A step told its cores and its memory can do that; a step told only
its cores cannot, and the natural mistake is to derive memory from cores,
which is wrong in exactly the case that matters.

### Requirement: A Step Says Whether Its Resources May Span Nodes

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Whether a step's resources may be drawn from more than one node shall be a
property the step declares, and shall not be inferred from whether the step
uses MPI.

This covers cores and GPUs together, as one property rather than two. A step
that reaches other nodes reaches them by one mechanism, and that mechanism
carries whatever the work needs; a step that cannot reach them cannot reach
either. No case has been identified that wants the two to differ, and
splitting them would invite a step to claim GPUs on nodes its cores cannot
reach.

MPI and spanning are not the same question, and treating them as the same is
what this requirement exists to prevent. An MPI step spans nodes because its
launcher spreads its ranks. A single-process Python step that does its work
in its own threads cannot span nodes, because there is no mechanism by which
it would reach them. A single-process Python step that hands its work to a
distributed worker pool spans nodes perfectly well -- the pool is exactly
the mechanism the thread-based step lacks -- and it does so while remaining
one process asking for one task. "Not MPI" covers the last two cases, which
want opposite answers.

Such a step's workers may use GPUs as readily as cores, and when they do,
the GPUs come from the nodes the workers are on rather than from the node
the step's own process happens to occupy. Nothing about a step being
single-process confines its GPUs to one node once its work is somewhere
else.

Steps that do not say shall be treated as confined to a node, which is what
every non-MPI step in Polaris is today. This is also the safe direction: a
request that a node can satisfy is satisfiable on any allocation that could
have satisfied a larger one.

Where a step cannot be given what it asked for, the existing
target-and-minimum rule shall decide what happens, with the node boundary
as one more thing that can make a request unsatisfiable. A step confined to
a node may be reduced silently towards its target, exactly as it may be
today, because a step that names a minimum has said in advance which
reductions are acceptable. A step whose *minimum* cannot be met within a
node shall be an error when the run is set up, naming what it needs, what a
node holds, and the property that would let it span -- not quietly reduced
to what fits. This applies to a step asking for more GPUs than a node has
exactly as it applies to cores.

This is deliberately the rule Polaris already follows, extended rather than
replaced, and it leaves today's steps alone. The two steps that currently
ask for more cores than some machines have per node both name a minimum of
one, so they are reduced as they always were. What changes is only that the
bound is the allocation for a step that may span, and that a step that may
not span and cannot fit says so instead of shrinking in silence.

### Requirement: Portability Across Supported Machines

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Placement shall work on all machines Polaris supports for parallel work:
Slurm systems both older and newer than the 20.11 change in how job steps
reserve resources, and PBS systems using the PALS launcher.

Where a machine cannot support placement, Polaris shall detect this and say
so, rather than silently running steps on the whole allocation.

### Requirement: No Change to Existing Behavior

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

`polaris serial` shall behave exactly as it does today. A step that does not
ask to be confined shall be launched as it is now.

Two of the requirements above change what a step is told or permitted rather
than how it is launched, and both are constructed to leave existing steps
where they are: the memory default reproduces core-only packing exactly, and
the node-span rule reduces to today's target-and-minimum behavior for every
step now in Polaris. Neither should show up as a difference in a run.

This requirement is also what the migration of existing non-MPI steps onto
the new fields is checked against. A step restated in different words shall
receive the same resources and produce the same outputs, and any step for
which that is not true has been restated wrongly.

## Algorithm Design

### Algorithm Design: What Placement Means to the Launcher

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The launcher should accept an optional description of where a step is to
run, alongside the existing task and CPU counts. In substance that
description is:

- the nodes the step may use;
- how many cores it may use on each;
- how many GPUs it needs in total, which is normally none.

All three are always present. There is no "unspecified" for GPUs, because
an unspecified GPU requirement is what the batch system reads as a claim on
all of them.

Each supported system can express all three, though they say it differently.
On newer Slurm it is a matter of asking for exactly the resources requested
rather than inheriting the job's; on PBS with PALS it is a host list plus an
explicit core list; on older Slurm, where the modern options do not exist, it
is an explicit CPU mask, which is the fallback noted above.

The important design point is that Polaris should describe the *placement*,
never the flags. Which flags implement it is the launcher's business, and
they differ enough between machines -- and between Slurm versions on the same
kind of machine -- that leaking them into Polaris would spread
machine-specific knowledge through the scheduler.

### Algorithm Design: Describing Step Resources

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Polaris steps today describe CPU needs per MPI rank: `ntasks` how many ranks,
`cpus_per_task` how many cores each, with `min_tasks` and `min_cpus_per_task`
giving the scheduler room to run a step smaller when resources are tight.
That target-and-minimum pattern is a good one and should be kept.

GPUs should be added as a per-step total with a matching minimum, for the
reason given in the requirements, defaulting to none so that the great
majority of steps need say nothing and still get an explicit "no GPUs"
passed to the launcher on their behalf.

Memory follows the same target-and-minimum pattern but does not follow the
same path afterwards. GPUs go to the launcher because the launcher acts on
them; memory goes to the scheduler and to the step, because those are the
only two things that act on it. It is worth being explicit that this is not
an omission: a memory figure rendered into a launch command would be
decoration, and worse than decoration, because it would suggest an
enforcement that does not happen.

Memory's default differs from the GPU default in kind. "No GPUs" is a true
statement about a step that uses no GPUs. There is no equivalent true
statement about memory -- every step uses some -- so the default has to be
an assumption, and the assumption chosen is the step's proportional share of
the node: cores requested, times the node's memory divided by the node's
cores. Its merit is not that it is accurate for any particular step; it is
that a run in which every step defaults packs exactly as a run with no
memory accounting at all, so the mechanism is inert until someone supplies a
measured number.

An alternative was considered and rejected: converting memory into an
equivalent number of cores and packing on cores alone, so that a step
needing a large fraction of the node's memory reserves a matching fraction
of its cores. It has the appeal of resting on the one resource the batch
system does enforce. But it over-reserves whenever a step's ratio of memory
to cores differs from the node's, and it does so worst for steps that want
much memory and few cores, which is precisely the analysis work that
motivated declaring memory at all. It would also hand such a step *more*
cores than it asked for, so a step that sizes a worker pool from its cores
would respond to needing more memory by creating more workers with less
memory each. Tracking memory as its own quantity avoids both, and is
consistent with the decision already made for GPUs, which this design
likewise declines to express in CPU-shaped terms.

GPUs need no separate treatment for non-MPI steps, and it is worth saying so
rather than leaving it to be inferred. A per-step total is already the shape
a single-process step wants, so the same `gpus` and `min_gpus` serve both
kinds of step and nothing further is required. The measurement that forced
GPUs into that shape -- a per-rank count does not confine a launch -- happens
to have put them where a step with no ranks can use them. Cores are the
exception rather than GPUs being an omission: they are described per rank
for historical reasons, and are the one resource a non-MPI step therefore
cannot state.

Non-MPI steps are worth calling out for that reason. A single-process Python
step has no meaningful "number of ranks"; what it has is a number of cores
it can use and an amount of memory it needs. Expressing that through
MPI-shaped fields is how Polaris ends up telling a Python step it has 192
cores across three nodes. Non-MPI steps should describe cores and memory
directly, and their GPUs through the same per-step total every other step
uses.

That matters more once such a step is allowed to span nodes. A step that
wants two hundred cores from a distributed pool is, in MPI-shaped terms, one
task with two hundred CPUs each -- a sentence no launcher can act on, since
one process cannot be given two hundred cores on a node that has a hundred
and twenty-eight. Written directly, as two hundred cores that may come from
several nodes, it says something true and actionable. The MPI-shaped fields
are not merely awkward here; they cannot express the case at all.

### Algorithm Design: Reservations Are Not Always Placements

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

For most steps, the resources Polaris reserves and the resources it confines
the step to are the same set, described once and used twice. An MPI step
given ninety-six cores is launched on those ninety-six cores; reserving them
and placing them are one act.

Two cases in this design separate them. Memory is reserved and never placed,
because no launcher acts on it. A step that delegates its work to a
distributed pool is the mirror image: what Polaris launches is a driver
process needing about one core, while the cores the step claims -- and the
GPUs, where its workers use them -- are consumed by pool workers, which are
separate launches, started elsewhere, and shared with other steps. Placing
two hundred cores on that driver would confine them to a process that will
not use them, while the workers that will are somewhere else entirely, and
placing GPUs on it would reserve devices on the one node whose work is
smallest.

The distinction to carry forward is that **placement is what the launcher
acts on and a reservation is what the scheduler tracks**. They coincide for
ordinary steps. Where they do not, the scheduler's accounting is the one
that has to be right, because it is what stops the machine being
oversubscribed; the placement is only ever a description of where a
particular launch goes.

Phase A implements no delegation -- there is no pool until Phase C, and no
scheduler until Phase B. What Phase A must not do is build the two ideas as
one thing, because separating them afterwards means revisiting every place
that assumed a step's cores and its launch describe the same set.

### Algorithm Design: Detecting What a Machine Supports

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Placement support is a property of the machine and of the version of its
batch system, and it must be decided at run time rather than baked into
configuration, because the same machine can change underneath us.

The launcher should determine, once per run, which placement mechanism
applies, and report it. Three outcomes matter: full placement with batch-system
enforcement; placement by explicit CPU binding, on older Slurm; and no
placement, which Polaris should treat as "concurrency is not available here"
rather than as an error.

## Implementation

### Implementation: The mache Side

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

`mache.parallel.ParallelSystem.get_parallel_command()` gains an optional
placement argument, and each subclass renders it appropriately. This is the
contract change, and it must land in `mache` before Polaris can depend on
it. Its design is *Design Document: parallel placement*, at
`docs/design/parallel_placement.md` in the `mache` repository. It is a
separate repository, so this cannot be a cross-reference.

That work exists: **`mache` pull request #470**, which adds a
`ResourcePlacement` type and the optional argument, renders it for Slurm
both before and after 20.11, for PBS with PALS and for a single node, and
adds a test that renders a placement against every shipped machine config.
It is not merged. Xylar's condition for merging it is that Polaris testing
first confirms the rendered commands behave as intended on real machines,
so Phase A and that pull request unblock each other and should be worked on
together.

Until a released `mache` provides this, Polaris must deploy against the
pull request branch rather than a released version. `deploy.py` already
supports this, so no change to Polaris's deployment machinery is needed:

```
./deploy.py --mache-fork xylar/mache --mache-branch parallel-placement ...
```

`deploy.py` and `deploy/cli_spec.json` are contract files shared with
`mache` and must not be edited in Polaris to accommodate this.

This is a temporary state and should be treated as one. Phase A should not
be merged into Polaris while it depends on an unreleased branch. The order
is: Polaris testing confirms the rendering works and measures each machine's
memory, `mache` takes both -- the confirmation and the corrected memory
figures -- then merges and releases, Polaris pins the released version, and
only then does Phase A land. Folding the memory corrections into the same
release is worth a little care in sequencing, since the alternative is
shipping estimates and correcting them in a second release that nothing
forces anyone to make. Anything built on Phase A in the meantime is
developed against a moving dependency and should expect to be rebased.

Once a released version exists, Polaris should require at least that
version and should fail clearly, at setup, if an older `mache` is present.
A run that silently loses placement would appear to work while
oversubscribing the machine, which is the worst failure mode available
here: no error, wrong results, and slower than serial.

### Implementation: The Polaris Side

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

- `Step` gains `gpus` and `min_gpus` as per-step totals. The existing
  `gpus_per_task` should be deprecated in favor of the total, since it does
  not do what its name suggests when steps run concurrently.
- `Step` gains `memory` and `min_memory`. `Step` already carries a
  `max_memory` attribute, documented as a placeholder for task parallelism
  and unused by anything. This is that placeholder being redeemed, not a
  second mechanism beside it, and the existing attribute should be
  reconciled rather than left alongside. Its units, megabytes, are worth
  keeping; its name is not, since what a step declares is what it needs and
  not a ceiling it is held to.
- `Step` gains a way to say how many cores and how much memory a non-MPI
  step needs, without going through MPI task counts.
- `Step` gains a property saying whether its resources -- cores and GPUs
  alike -- may be drawn from more than one node, false by default for a
  non-MPI step and true for an MPI one. `constrain_resources()` uses it in
  place of the node-sized cap it applies today: a step that may span is
  bounded by the allocation, and a step that may not and asks for more than
  a node holds is an error rather than a silent reduction. Nothing in
  Polaris sets the property to true in Phase A; it exists so that Phase C
  does not have to remove a rule.
- No non-MPI GPU field is added, because `gpus` and `min_gpus` already are
  one. Deprecating `gpus_per_task` is what completes this: it is the only
  GPU field with a shape a non-MPI step cannot use.
- The non-MPI steps that exist today are moved onto the new fields, as a
  commit of its own at the end of the Phase A series rather than mixed into
  the framework change. Nothing forces this: the two spellings mean the same
  thing for a step confined to a node, and the framework should accept
  either. It is done in Phase A anyway because Phase A is the only phase
  whose acceptance criterion is that behavior does not change, which is
  precisely how a translation of this kind is checked, and because leaving
  both spellings live means the Phase B scheduler is the first thing to meet
  them -- where a misread declaration shows up as a packing bug rather than
  as a wrong number on a page.
- That migration is smaller than it sounds and needs more judgment than it
  sounds. Of the non-model steps that declare resources, most name one core
  and one task, which is the default and can simply go. Four genuinely want
  to state cores directly. The remainder set `ntasks=1` while being MPI
  steps that happen to run at width one -- the WOA23 steps, the topography
  remapping step, and the shared mapping-file step -- and moving those would
  be wrong, since `ntasks` is the field that means what they mean. This has
  to be decided per step rather than swept, and is the reason it is its own
  commit and not a mechanical pass.
- The code that builds a step's parallel command passes a placement through
  to `mache` when one has been assigned, and passes none when it has not,
  preserving today's behavior.
- The resource information handed to a step is built from its placement, so
  that a confined step sees only what it was given, and includes memory
  alongside cores, nodes and GPUs.
- The per-node memory a machine has becomes a `[parallel]` configuration
  option in `mache`, beside the `cores_per_node` and `gpus_per_node` that
  are already there. That is a separate and much smaller change than pull
  request #470: it describes a machine rather than altering an interface,
  and it does not touch `ResourcePlacement`. It should be a configured
  quantity rather than one read from the running node, both because Polaris
  needs it before a compute node is in hand and because what belongs in it
  is the memory a job may actually use, which is not what the operating
  system reports.
- Nothing about memory reaches `mache`'s `ResourcePlacement`. That type
  describes where a launch runs -- which nodes, which cores, which GPUs --
  and every field in it is rendered into the launch command. A memory field
  would render to nothing on every machine Polaris supports. If the
  enforcement question below is answered and some machine does honor a
  memory request, adding the field then is an additive change; adding it
  now would widen an unmerged pull request to carry something no machine
  reads.

### Implementation: Boundaries

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Nothing in Phase A decides *which* subset a step should get. There is no
scheduler yet; the only caller is the existing serial path, which assigns no
placement. Keeping that boundary makes Phase A reviewable on its own and
means a mistake in it shows up as a wrong command rather than as a wrong
schedule.

## Testing

### Testing and Validation: Command Construction

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests shall check the command built for a given placement on each
supported system, including: a step confined to one node, a step spanning
several, a step needing GPUs, a step needing none, and a step with no
placement at all, which shall produce today's command unchanged.

These tests need no allocation and shall run in ordinary CI.

### Testing and Validation: Real Machines

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The mechanisms Phase A relies on were measured on Chrysalis, Perlmutter (CPU
and GPU), Frontier and Aurora before this design was written; the results
are summarized in [Task Parallelism in Polaris](task_parallelism.md). Those
measurements used commands written by hand. Phase A shall be validated by
showing that the commands `mache` *renders* produce the same behavior on
each of those machines, which is a different claim and the one that gates
merging `mache` pull request #470.

That validation does not require the rest of Phase A. Building placements,
rendering them through `get_parallel_command()` and launching them
concurrently is enough to confirm the rendering, and keeping it separate
means a failure is attributable to `mache` rather than ambiguous between
`mache` and Polaris's placement construction. It should be done first, on
all five machines.

A single confined step shall be run on each machine and shall report that it
sees only the cores and GPUs it was given. This is the check that catches a
placement which is constructed correctly but not honored, and it is worth
keeping as a small standing test rather than a one-off, since it is the
first thing that would break if a site changed its scheduler
configuration.

While those machines are being visited, two further things should be
settled, because both are cheap there and expensive to guess at.
Nothing in this design asks the batch system to limit a step's memory, on
the evidence that requesting memory changed nothing observable. That
evidence shows memory was not the cause of the serialization; it does not
show that a memory request is inert. The test is direct: launch a step with
a small memory allowance, have it allocate several times that, and record
whether it is killed. Two answers matter and both are useful. If nothing
enforces, this design is on the right footing and the co-resident reporting
in Phase B is the whole of the answer. If some machine does enforce, then
two consequences follow at once -- a step could be capped there, and, by the
same argument that applies to GPUs, a step that says nothing about memory
may be read as claiming all of it, which would be the same trap in a second
place.

### Testing and Validation: Measuring Each Machine's Memory

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The per-node memory `mache` reports is a number nobody has been able to
measure. Whoever adds `memory_per_node` to the machine configs is not on
those machines, and the figure that matters -- what a job may actually
allocate -- is not what a vendor specification says, not what site
documentation says, and not what a login node reports. The values that ship
with `mache` will be estimates.

Polaris's validation is the only occasion on which anyone is on all five of
those machines with a reason to look, so measuring the real values is part
of it. For each of Chrysalis, Perlmutter CPU, Perlmutter GPU, Frontier and
Aurora, a job shall record what the batch system says a node has, and the
corrections shall be returned to `mache` as a change to its machine configs.

Two figures are worth recording rather than one, because they answer
different questions. What the scheduler believes a node has is what a
scheduler would pack against, and is what the config option should hold: on
Slurm that is the node's real memory as `scontrol` or `sinfo` reports it,
and on PBS it is the equivalent node attribute. What a process can actually
allocate before it is refused is the figure that decides whether the first
is honest. Where the two disagree, the smaller one is the one Polaris must
not exceed, and the disagreement is itself worth reporting.

Until a machine has been measured its value should be treated as
provisional, and estimates should err low: a figure that is too high costs a
job killed for exhausting a node, while one that is too low costs only work
that could have been packed. Those are not comparable, so the unverified
direction to be wrong in is downwards.

This is a small task with an unusual failure mode: it is easy to omit and
nothing fails when it is. A run with an over-estimated node memory looks
entirely normal until a suite happens to pack tightly enough to exhaust a
node, at which point the failure appears far from its cause and looks like a
step's bug. Recording which machines have been measured, in the `mache`
configs themselves, is what makes the omission visible.

### Testing and Validation: No Regression

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A representative suite shall be run with `polaris serial` and compared
against a baseline, to confirm that adding the placement machinery has not
changed behavior when placement is not used. Since Phase A adds no
concurrency, any difference in results is a bug rather than a trade-off.
