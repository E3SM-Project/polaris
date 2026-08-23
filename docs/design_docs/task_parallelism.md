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
allocation. They can, all five of them. The details are recorded in
`utils/launcher_spike/README.md`; the conclusions that shape this design
are:

- **Launching work is cheap.** Between 60 and 670 launches per minute
  depending on machine. A long-standing suspicion that Perlmutter throttles
  launches to about one a minute turned out to describe a different problem.
  (The measurements were taken off-peak, so this is not the last word on a
  busy weekday.)
- **The scheduler will keep concurrent work apart, if asked properly.** Each
  piece of work gets its own cores, and its own GPUs, enforced by the batch
  system rather than by Polaris. This is a stronger guarantee than we
  expected to get.
- **A piece of work claims every GPU on its node unless it says otherwise.**
  This, and not memory or CPU contention, is what prevented concurrency on
  the GPU machines. The fix is for each step to state how many GPUs it
  needs.
- **GPUs must be requested as a total per step, not as a count per MPI
  rank.** The per-rank form does not work. This is a real constraint on how
  Polaris describes step resources, and it differs from how CPU resources
  are described today.

The practical consequence is that no new dependency is needed. We considered
adopting Flux, a nested scheduler that would sidestep the batch system
entirely, and it is not necessary.

## The phases

Each phase is a separate design document and is intended to be independently
useful.

### Phase A -- Placement

`docs/design_docs/task_parallelism_phase_a.md`

Give Polaris the ability to run a step on a **named part** of its allocation
rather than on all of it, and give steps a way to say what they need,
including GPUs as a per-step total and memory. Still one step at a time.

This is a prerequisite for everything else, and most of the work is in
`mache`, which owns how Polaris launches parallel work.

### Phase B -- Concurrency

`docs/design_docs/task_parallelism_phase_b.md`

Build the dependency graph, the resource pool and an executor that runs each
step in its own process. Run independent steps at the same time -- MPI and
non-MPI alike, since with Phase A in place there is no reason to stage one
behind the other.

This is where the regression-suite speedup lands.

### Phase C -- Python worker pool

`docs/design_docs/task_parallelism_phase_c.md`

Add a second executor: a pool of workers spread across the allocation's
nodes, for Python work that is too fine-grained to give a process of its
own. This is what lifts the single-node ceiling that constrains
MPAS-Analysis today, and it is the phase the analysis capability depends on.

### Phase D -- Coexistence and elasticity

`docs/design_docs/task_parallelism_phase_d.md`

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
  `docs/design_docs/task_parallel_analysis_steps.md`, which is worth
  adopting before analysis steps are written rather than after.

## What success looks like

Polaris can run a suite's independent steps at the same time, on any
supported machine, with the batch system keeping them from treading on each
other, producing the same results as running them one at a time; and Python
analysis work can spread across more than one node.
