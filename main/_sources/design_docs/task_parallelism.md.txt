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

### What the rendered commands did

The table above was produced with commands written by hand. That establishes
what the machines can do, not that the commands Polaris and `mache` build
between them do it, which is a different claim and the one that gates the
`mache` change. It was checked separately, in August 2026, on all five
machines, by constructing disjoint placements, rendering each through
`mache` and launching them together:

| machine | placement | GPUs | note |
| --- | --- | --- | --- |
| Chrysalis | exact cores | n/a | clean first time |
| Frontier | honored | disjoint, 0,1 / 2,3 / 4,5 / 6,7 | clean first time |
| Perlmutter GPU | honored | disjoint, 0 / 1 / 2 / 3 | clean after a fix |
| Aurora | exact cores | disjoint masks | clean after a fix |
| Perlmutter CPU | honored | n/a | clean first time |

Two defects were found this way and both were fixed in `mache` rather than
worked around. On Aurora, `--env-remove` is not an option the PALS
`mpiexec` accepts, and it rejected the whole command, so every placed launch
failed to start. On Perlmutter GPU, a `gpu_bind` of `none` carried from the
machine config alongside an explicit GPU request, and under concurrency
three of four launches silently received no GPU at all and exited zero --
the same class of failure as silently losing placement, and the reason this
verification was worth doing separately from the hand-written one.

The Aurora result carried one limit, and asking about it turned up a real
defect. On Slurm the GPUs a launch can see are read from the scheduler's own
variables, so the verdict is independent evidence. On PALS nothing assigns
GPUs, so `mache` renders the indices the caller chose and the check reads
that same value back -- confirming the plumbing, not the runtime.

Asked properly, by enumerating what the runtime can see, the answer is that
**an empty `ZE_AFFINITY_MASK` hides nothing**. Level Zero reads an empty
value as "no mask", meaning every device: six cards visible with the
variable unset, and the same six with it set and empty. The explicit "no
GPUs" `mache` renders on PALS is a no-op.

Two controls make that a finding rather than a guess. The variable arrived
*set and empty* rather than dropped, which separates Level Zero's semantics
from a plumbing bug; and a mask naming a subset did confine the launch,
which rules out the mask being inert. Two enumerators agreed, one reaching
Level Zero with no SYCL layer between.

Nothing on PALS reserves GPUs, so a step seeing hardware it declined costs
only tidiness, and neither Phase A nor Phase B is affected. It becomes an
isolation question in Phase C, where it is recorded.

### What the measurements concluded

**A harness built to answer a question is not part of the deliverable, its
findings belong in the design document, and it does not merge.** Anything
from such a harness that deserves to keep running -- a regression test, a
standing check -- has to move somewhere permanent before the harness goes.
An earlier version of these documents pointed at a README on a branch that
was never going to merge, and the evidence would have gone with it.

The conclusions that shape this design are:

- **Launching work is cheap.** Measured sequentially: roughly 60 per minute
  on Perlmutter GPU and Aurora, 150 on Perlmutter CPU, 500-600 on Frontier
  and Chrysalis. A long-standing suspicion that Perlmutter throttles
  launches to about one a minute turned out to describe a different problem
  -- concurrent launches queueing, not launches being rate limited.

  Two caveats. The tail is heavy: Frontier showed two of ten launches near
  two seconds against a median of 0.11 s on an idle system. And all of it was
  measured off-peak. If a future run finds launching slow, re-measure this
  first.
- **The scheduler will keep concurrent work apart, if asked properly.** Each
  piece of work gets its own cores and its own GPUs, enforced by the batch
  system rather than by Polaris.
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

  Silence about memory does not repeat the trap that silence about GPUs
  sets. Four concurrent launches that said nothing about memory all started
  within 40 ms of each other and ran their full duration on both machines
  that enforce. Aurora and Perlmutter CPU are unmeasured on this point.

- **Starting a step is not free, and how it is started decides whether
  concurrency pays.** A fresh `polaris serial` subprocess spends about 35 s
  importing Python before it does any work -- 11.5 s to import `polaris` and
  17.3 s for the first unpickle of a step, which is itself import time. Paid
  once per step, that was 71% of the measured step time on `omega_pr` and
  made the concurrent run slower than the serial one. Forking from the
  scheduler removes both costs, because a child inherits the modules and the
  step objects the scheduler already holds; measured on four steps, it saved
  about 48 s each.

  Two properties come with forking and had to be measured rather than
  assumed. Sharing is nearly complete -- 24 children cost 347 MiB between
  them against a parent of 322 MiB. And Polaris is multi-threaded on import
  without looking it: `import polaris` leaves 129 OS threads, 128 of them an
  OpenBLAS pool, where `threading.enumerate()` reports one. Only the forking
  thread survives a fork, so the scheduler holds its thread pools to one
  before importing anything.

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
is merged and released as `mache` 3.12.0, which Polaris requires; while it
was unreleased Phase A was developed against the branch.

### Phase B -- Concurrency

[Task Parallelism Phase B: Concurrency](task_parallelism_phase_b.md)

Build the dependency graph, the resource pool and an executor that runs each
step in a child forked from the scheduler. Run independent steps at the same
time -- MPI and non-MPI alike, since with Phase A in place there is no reason
to stage one behind the other.

Forking is what makes this pay. A step started as a fresh `polaris serial`
subprocess spends about 35 s importing Python first, and paying that once
per step cost more than concurrency saved; a forked child inherits the
scheduler's imports and its live `Step` objects and pays neither. Non-MPI
steps run on the scheduler's node, which bounds Python concurrency at one
node and is the bound Phase C lifts.

This is where the regression-suite speedup lands.

### Phase C -- Python worker pool

[Task Parallelism Phase C: Python Worker Pool](task_parallelism_phase_c.md)

Add a resident process on each node of the allocation, which forks children
for work and hosts a pool of workers for Python work too fine-grained to be
given a process of its own. This is what lifts the single-node ceiling that
constrains MPAS-Analysis today, and it is the phase the analysis capability
depends on. It also lifts Phase B's bound on where a non-MPI step runs,
using the same mechanism rather than a second one.

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
  [Task-Parallel-Safe Analysis Steps in Polaris](task_parallel_analysis_steps.md),
  which is worth adopting before analysis steps are written rather than
  after. Its rules are also written up for step authors in the developer
  guide, under {ref}`dev-task-parallelism`.

## What success looks like

Polaris can run a suite's independent steps at the same time, on any
supported machine, with the batch system keeping them from treading on each
other, producing the same results as running them one at a time; and Python
analysis work can spread across more than one node.
