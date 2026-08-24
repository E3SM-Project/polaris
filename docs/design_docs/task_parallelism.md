# Task Parallelism in Polaris

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Polaris runs one step at a time. This document describes adding the ability
to run independent steps at the same time, and maps out four phases of work
to get there.

"Task parallelism" is the historical name for this effort. The unit Polaris
actually schedules is a `Step`, not a `Task`, and steps that run together may
come from one task or from several tasks in a suite.

### Two workloads, not one

Two quite different kinds of work motivate this, and keeping them distinct
is what makes the phasing sensible.

**Regression suites** such as `omega_pr` are dominated by many small MPI
model runs. On a recent `omega_pr` run on Chrysalis, 79% of the time in
steps was MPI forward runs and 21% was everything else. The whole suite took
12:26 while its longest single task took 106 s, so the work is there: it is
simply run one step after another. Running independent steps together should
give roughly a 2.5-3x improvement on the same three-node allocation, limited
by the total core-seconds of MPI work rather than by dependencies.

**Analysis** is the larger long-term need. Polaris is to gain analysis
capability equivalent to MPAS-Analysis, for Omega and possibly MPAS-Ocean.
That workload is heavily Python. MPAS-Analysis already has task parallelism,
but it is built on `multiprocessing`, which cannot span nodes, and that
single-node ceiling is a known choke point at high resolution -- exactly
Omega's target. What this workload needs is not just concurrency but
concurrency **across nodes**.

Neither is optional, and the phases below deliver them in an order chosen for
what each one unblocks rather than for which matters more.

### What we already established

Before designing anything, we measured whether the machines Polaris targets
can actually run several placed pieces of work at once inside a single
allocation. They can, all five of them. The measurements were made in
August 2026 with throwaway scripts; the results are recorded here because
this document is where they need to survive.

In each test, four pieces of work were launched at once inside one
allocation, each asking to be confined to its own cores and, where
relevant, its own GPUs. Each reported back which cores and GPUs it could
actually see and when it ran, so that genuine overlap could be told from
work that merely queued.

| machine | batch system | what confines a launch | cores | GPUs |
| --- | --- | --- | --- | --- |
| Chrysalis | Slurm 20.02 | explicit CPU binding | disjoint | n/a |
| Perlmutter CPU | Slurm 25.11 | resource request | disjoint | n/a |
| Perlmutter GPU | Slurm 25.11 | request + GPU total | disjoint | disjoint |
| Frontier | Slurm 25.11 | request + GPU total | disjoint | disjoint |
| Aurora | PBS with PALS | host list + core list | disjoint | disjoint |

All five ran all four launches concurrently.

The GPU machines were also tested at MPI width -- four concurrent two-rank
MPI launches -- and partitioned cleanly there too. On Frontier the four
launches received GPUs 4,5 / 6,7 / 0,1 / 2,3.

The conclusions that shape this design are:

- **Launching work is cheap.** Measured sequentially: roughly 60 per minute
  on Perlmutter GPU and Aurora, 150 on Perlmutter CPU, 500-600 on Frontier
  and Chrysalis. A long-standing suspicion that Perlmutter throttles
  launches to about one a minute turned out to describe a different problem
  -- concurrent launches queueing, not launches being rate limited.

  Two caveats worth carrying. The tail is heavy: Frontier showed two of ten
  launches near two seconds against a median of 0.11 s on an otherwise idle
  system. And all of this was measured off-peak, so a busy weekday has not
  been ruled out. If a future run finds launching unexpectedly slow, this is
  the first thing to re-measure rather than the last.
- **The scheduler will keep concurrent work apart, if asked properly.** Each
  piece of work gets its own cores, and its own GPUs, enforced by the batch
  system rather than by Polaris. This is a stronger guarantee than we
  expected to get.
- **Silence about GPUs is not neutral at the launcher.** Polaris steps use
  no GPUs unless they say so, and that stays true. But if Polaris passes
  that silence on, the batch system reads it as "give this work the node's
  GPUs" and reserves all of them, which is what stopped concurrency on the
  GPU machines -- not memory or CPU contention. Polaris must therefore state
  a step's GPU need explicitly in every case, **including when it is zero**.
  Since most Polaris steps use no GPUs at all, saying "none" is the common
  path, not the exception.
- **When a step does want GPUs, it must ask for a total, not a count per MPI
  rank.** The per-rank form does not confine a step at all. This is a real
  constraint on how Polaris describes step resources, and it differs from
  how CPU resources are described today.
- **The batch system will not schedule memory for us, but on newer Slurm it
  will enforce it.** These are different things and the difference decides
  how memory is handled. Asking a launch for a share of the node's memory
  did not fix the serialization -- silence about GPUs did that -- and it
  reserved nothing that any measurement could see. But a later measurement
  on the same machines showed a memory request is not inert: a launch
  allowed 1024 MB and told to take 4 GB is killed at 960 MB on Perlmutter
  GPU and on Frontier, and runs to completion on Chrysalis, whose Slurm
  predates the 20.11 change.

  So the launcher will not tell Polaris what fits, and deciding that remains
  a budget Polaris keeps itself, in the scheduler in Phase B. What the
  launcher will do, on some machines, is hold a launch to a number it was
  given. That makes a memory figure passed to a launcher a **cap** rather
  than a reservation, which is a thing worth doing deliberately for a step
  that stated its own number and not worth doing to a step the framework
  guessed at.

  One worry this raised does not materialize. Silence about memory does not
  repeat the trap that silence about GPUs sets: four concurrent launches
  that said nothing about memory all started within 40 ms of each other and
  ran their full duration on both machines that enforce. An unstated memory
  requirement is not read as a claim on the node's memory. Aurora and
  Perlmutter CPU are unmeasured on this point.

One more result is worth recording because it cost a round of testing: on
CUDA machines the visible-device variable is renumbered for each launch, so
four launches on four different GPUs all report device `0`. Anything
verifying GPU placement must use the scheduler's global identifiers
instead.

Two approaches were tried and rejected. Allowing launches to overlap without
constraining them gives concurrency but every launch then shares every core
and GPU, which is oversubscription rather than scheduling. Constraining a
launch and *also* pinning it with an explicit CPU mask fails outright on
newer Slurm, because the two contradict each other; explicit masks remain
the only mechanism on Slurm older than 20.11, where they work.

The practical consequence is that no new dependency is needed. We considered
adopting Flux, a nested scheduler that would sidestep the batch system
entirely, and it is not necessary.

## The phases

Each phase is a separate design document and is intended to be independently
useful.

### Phase A -- Placement

[Task Parallelism Phase A: Placement](task_parallelism_phase_a.md)

Give Polaris the ability to run a step on a **named part** of its allocation
rather than on all of it, and give steps a way to say what they need,
including GPUs as a per-step total and memory. Still one step at a time.
Memory is declared here and shown to the step, but it is not something the
launcher is asked to enforce; deciding what fits is Phase B's job.

This is a prerequisite for everything else, and most of the work is in
`mache`, which owns how Polaris launches parallel work. That `mache` change
exists as pull request #470 and is not yet merged or released, so Phase A
is developed against a branch rather than a released version for now.

### Phase B -- Concurrency

[Task Parallelism Phase B: Concurrency](task_parallelism_phase_b.md)

Build the dependency graph, the resource pool and an executor that runs each
step in its own process. Run independent steps at the same time -- MPI and
non-MPI alike, since with Phase A in place there is no reason to stage one
behind the other.

This is where the regression-suite speedup lands.

### Phase C -- Python worker pool

[Task Parallelism Phase C: Python Worker Pool](task_parallelism_phase_c.md)

Add a second executor: a pool of workers spread across the allocation's
nodes, for Python work that is too fine-grained to give a process of its
own. This is what lifts the single-node ceiling that constrains
MPAS-Analysis today, and it is the phase the analysis capability depends on.

Measurement has since confirmed the premise: a high-resolution analysis run
is fine-grained, with a median task of about five seconds and half of them
shorter. Phase C records what else that run showed, including two of its
headline numbers that do not mean what they appear to. It is worth stating
here that analysis is the pool's first demanding customer and not its
specification -- most Polaris workflows share no single large input, and a
pool built around one would serve the general case badly.

### Phase D -- Coexistence and elasticity

[Task Parallelism Phase D: Coexistence and Elasticity](task_parallelism_phase_d.md)

Let the worker pool and ordinary steps share an allocation, and let the pool
grow and shrink as the amount of ready Python work changes, so that it does
not hold nodes idle once that work drains.

## Scope and non-goals

- `polaris serial` **stays**, unchanged, as the compatibility baseline. The
  new capability arrives on a separate path. There is no plan in these
  documents to remove `polaris serial`; that can be revisited once the new
  path has been used in anger.
- Polaris will not request larger allocations by default just because it can
  now use them. Allocation sizing stays as it is; users asking for more
  nodes is a deliberate act.
- These documents do not cover writing the analysis capability itself. The
  properties an analysis step needs in order to be safely run concurrently
  are a separate document,
  *Task-Parallel-Safe Analysis Steps in Polaris*, which is worth adopting
  before analysis steps are written rather than after. That document is
  being prepared on its own branch and should land alongside these; once it
  does, this should become a link to it.

## What success looks like

Polaris can run a suite's independent steps at the same time, on any
supported machine, with the batch system keeping them from treading on each
other, producing the same results as running them one at a time; and Python
analysis work can spread across more than one node.
