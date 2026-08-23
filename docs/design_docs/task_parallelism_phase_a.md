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

Phase A only requires that the declaration exist and be carried through to
the launcher. Using it to decide how many steps may run at once belongs to
Phase B. Memory matters most for the analysis work in Phase C, where a
single step may need a large fraction of a node.

### Requirement: Resource Views Describe What a Step Can Use

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The resource information given to a step shall describe the resources that
step can actually use.

A step confined to one node shall be told about one node's resources. A
non-MPI Python step cannot use cores on other nodes without a distributed
launcher, so telling it the allocation-wide core count invites it to size
itself wrongly. Any resources withheld from a step shall be genuinely
withheld, not merely subtracted from a number.

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
passed to the launcher on their behalf. Memory should be added the same
way.

Non-MPI steps are worth calling out. A single-process Python step has no
meaningful "number of ranks"; what it has is a number of cores it can use
and an amount of memory it needs. Expressing that through MPI-shaped fields
is how Polaris ends up telling a Python step it has 192 cores across three
nodes. Non-MPI steps should describe cores and memory directly.

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
is: Polaris testing confirms the rendering works, `mache` merges and
releases, Polaris pins the released version, and only then does Phase A
land. Anything built on Phase A in the meantime is developed against a
moving dependency and should expect to be rebased.

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

- `Step` gains `gpus` and `min_gpus` as per-step totals, and `memory` and
  `min_memory`. The existing `gpus_per_task` should be deprecated in favor
  of the total, since it does not do what its name suggests when steps run
  concurrently.
- `Step` gains a way to say how many cores and how much memory a non-MPI
  step needs, without going through MPI task counts.
- The code that builds a step's parallel command passes a placement through
  to `mache` when one has been assigned, and passes none when it has not,
  preserving today's behavior.
- The resource information handed to a step is built from its placement, so
  that a confined step sees only what it was given.

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

### Testing and Validation: No Regression

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A representative suite shall be run with `polaris serial` and compared
against a baseline, to confirm that adding the placement machinery has not
changed behavior when placement is not used. Since Phase A adds no
concurrency, any difference in results is a bug rather than a trade-off.
