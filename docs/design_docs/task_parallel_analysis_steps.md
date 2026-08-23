# Task-Parallel-Safe Analysis Steps in Polaris

Creation date: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Polaris is adding task parallelism. The near-term driver is building
analysis capability in Polaris equivalent to MPAS-Analysis, for Omega and
possibly MPAS-Ocean. That work is heavily Python, and it is the workload
that most needs to run concurrently: MPAS-Analysis implements task
parallelism with `multiprocessing.Process`, which cannot span nodes, and
that single-node ceiling is a known choke point at high resolution --
exactly Omega's target.

Whether Polaris can run analysis steps concurrently is only partly a
property of the scheduler. It is equally a property of the steps. A step
that changes the working directory, mutates module-level configuration or
writes to a shared path cannot safely run beside another step in the same
process, and cannot be dispatched to a worker on another node at all.

This document sets out the properties an analysis step must have in order to
be scheduled concurrently, and proposes adopting them as groundrules now,
while the analysis capability is still being designed. The cost of adopting
them up front is close to zero; the cost of retrofitting them later is
rewriting every analysis step already written.

These rules are deliberately written so that a conforming step does not need
to know which executor runs it. The same step should be runnable in the
scheduler process, in a subprocess, or in a distributed worker on another
node, without modification.

Existing Polaris code does not follow these rules today, and this document
does not require it to. The framework itself does `os.chdir(step.work_dir)`
around each step, sets `mpas_tools.io.default_format` and
`default_engine` as process globals, and `polaris.viz` assigns
`plt.rcParams['savefig.dpi']`. Those are safe under today's one-step-at-a-time
execution and are called out here because they are the concrete patterns new
analysis steps must avoid, and because the framework will have to offer
alternatives before it can require them.

Success means a newly written analysis step, following these rules, can be
run concurrently with other steps -- including on a different node -- with no
change to the step, no interference between steps, and identical results to
running it alone.

## Requirements

### Requirement: No Process-Global State Mutation

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall not mutate state that is shared by the whole process.

This includes the current working directory, environment variables,
module-level configuration in third-party libraries, and global
plotting state. Any of
these makes two steps running in one process interfere with each other, and
the interference is timing-dependent, so it surfaces as intermittent wrong
answers rather than as a clean failure.

Where a step needs behavior that is conventionally set globally, the
framework shall provide a scoped alternative.

### Requirement: Explicit Configuration

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall obtain all of its configuration through objects
passed to it, and shall not depend on configuration having been applied to
the process by some earlier step or by the framework's startup.

A step dispatched to a worker on another node begins in a process that never
ran that startup, so any dependence on it is a latent failure that appears
only once the step is scheduled remotely.

### Requirement: Working-Directory Independence

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall address every file by an explicit path and shall not
depend on the process's working directory being its own work directory.

The step shall continue to be given a work directory, and relative paths
within the step's own definition of its inputs and outputs remain the normal
way to describe them; the requirement is that resolution to an absolute path
happen through the step rather than through `os.getcwd()`.

### Requirement: Isolated Outputs and Temporary Files

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall write only within its own work directory, and shall
place temporary files there rather than in a shared location.

Two concurrent steps must not be able to choose the same temporary path.
Steps shall not write into another step's work directory, and shall not
depend on being able to read a file that a concurrently running step is
still writing.

### Requirement: Logging Through the Step's Logger

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall emit output through the logger it is given, and shall
not write to `stdout`, `stderr` or the root logger directly.

When several steps run at once, output written to shared streams interleaves,
and the resulting log cannot be attributed to a step. This requirement is
what makes per-step logs remain readable under concurrency.

### Requirement: Declared Resources

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall declare the resources it needs, including CPU cores
and memory, so that the scheduler can decide how many steps may run at once.

Memory is the requirement that distinguishes analysis steps from most
existing Polaris steps. At high resolution an analysis step may need a large
fraction of a node, and a scheduler that packs by cores alone will
oversubscribe memory and fail. A step that cannot fit in a node's memory
shall be reported as infeasible rather than attempted.

### Requirement: Dispatchable to a Remote Worker

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall be able to be sent to a worker process, potentially
on another node, and run there.

Whatever the framework must transfer in order to do this shall be
transferable. In practice this means a step shall not hold open file
handles, live network connections, database handles or other unserializable
state across the boundary between being defined and being run.

### Requirement: Restartable and Idempotent

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Rerunning an analysis step that has already completed shall be safe, and
shall produce the same result.

Under concurrency a run is more likely to be interrupted partway, because
more work is in flight when a failure or a wall-clock limit arrives. Steps
shall not accumulate state by appending to existing outputs, and shall
tolerate the presence of outputs from a previous partial run.

### Requirement: Bounded Process Launching

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

An analysis step shall not launch more parallel work than it declared.

A step that internally starts its own pool of processes or threads sized to
the whole machine will oversubscribe the node as soon as a second step runs
beside it. Any internal parallelism shall be sized from the resources the
step was given, not from the machine.

## Algorithm Design

### Algorithm Design: Scoped Alternatives to Global State

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The framework should offer a scoped replacement for each global that steps
currently rely on, so that following the rules is easier than breaking them.

For NetCDF output format and engine, the framework should provide the values
through the step rather than through `mpas_tools.io` module globals, and
should pass them explicitly at each write. Setting the module globals inside
a worker, as the Phase 1 task-parallel work had to do, is a workaround that
only holds while one step runs per worker.

For plotting, the framework should offer a context manager that applies
Matplotlib settings for the duration of a plot and restores them afterwards,
rather than steps assigning to `plt.rcParams`. Matplotlib's own
`plt.rc_context` is sufficient. Steps should also use the object-oriented
Figure API rather than the implicit `pyplot` current-figure state, which is
process-global.

For temporary files, the framework should provide a helper that creates them
under the step's work directory, so that the natural thing to write is also
the isolated thing.

### Algorithm Design: Resource Declaration for Analysis Steps

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Analysis steps should express CPU needs the way non-MPI work actually uses
them -- as a core count for the step -- rather than through MPI task counts.
Memory should be expressed as a target and a minimum, in the same style as
the existing target-and-minimum resource fields, so that the scheduler can
run a step in less memory when the allocation is tight and can report a
step as infeasible when even the minimum does not fit.

The measurement needed to set these numbers sensibly is being gathered
separately, by instrumenting a high-resolution MPAS-Analysis run for
per-task duration, peak resident memory and dependency-graph width. Default
values should not be guessed before that data exists.

### Algorithm Design: Making Conformance Checkable

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Rules that are only written down are not adopted. Most of these rules can be
checked mechanically, and should be.

Working-directory independence, global-state mutation and unbounded process
launching can be checked at runtime by running a step with the process
working directory set somewhere unrelated, snapshotting the globals a step is
forbidden to touch, and comparing them afterwards. Dispatchability can be
checked by round-tripping the step through serialization before running it.
Isolation can be checked by comparing the set of files a step wrote against
its declared outputs and its work directory.

These checks are cheap enough to run as part of ordinary testing, and are
most valuable while the analysis capability is small.

## Implementation

### Implementation: Framework Support

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

The framework changes implied by this document are small and independent of
the scheduler work:

- a scoped IO-configuration path that does not depend on
  `mpas_tools.io` module globals;
- a Matplotlib context manager in `polaris.viz`, replacing the
  assignment to `plt.rcParams['savefig.dpi']` in
  `polaris/viz/spherical.py`;
- a step method that returns a temporary directory inside the step's work
  directory;
- memory fields alongside the existing resource fields on `Step`.

None of these require the task-parallel scheduler to exist, and all of them
are useful on their own.

### Implementation: Conformance Checks

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

A conformance helper should run a step under adverse conditions and assert
the rules. In outline:

```python
def check_task_parallel_safe(step):
    """Run a step the way a remote worker would, and check it behaves."""
    before = snapshot_process_state()   # cwd, env, mpas_tools.io, rcParams
    step = round_trip(step)             # must survive serialization
    run_from_unrelated_directory(step)
    after = snapshot_process_state()
    assert before == after
    assert files_written(step) <= allowed_paths(step)
```

Steps that are known not to conform yet should be marked, so the check can
be required of new analysis steps without first fixing every existing step.
This is the same shape as the `task_parallelism_allowed` metadata already
proposed for the scheduler, and the two should use one mechanism rather
than two.

### Implementation: Adoption

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

These rules should apply to new analysis steps from the start. Existing
Polaris steps should not be required to conform until there is a reason:
they run one at a time today and are correct under that assumption.

The order that matters is that the rules exist before the analysis
capability is written. If the analysis steps are written first and the rules
come later, the outcome is a port of Polaris analysis to meet the needs of
task parallelism -- which is the specific outcome this document exists to
avoid.

## Testing

### Testing and Validation: Conformance

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests shall cover the conformance helper itself, using deliberately
non-conforming steps: one that changes the working directory, one that
mutates a forbidden global, one that writes outside its work directory, one
that cannot be serialized and one that launches unbounded parallelism. Each
shall be detected.

Every new analysis step shall have a test that runs it through the
conformance helper.

### Testing and Validation: Concurrent Execution

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Once the scheduler can run steps concurrently, a test shall run a set of
conforming analysis steps both serially and concurrently and compare the
outputs, which shall be identical.

A test shall also run steps concurrently with deliberately interleaved
timing, so that two steps are inside their plotting and IO code at the same
time, since that is where shared global state would otherwise surface.

### Testing and Validation: Resource Declaration

Date last modified: 2026/08/23

Contributors:

- Xylar Asay-Davis
- Claude

Tests shall verify that a step declaring more memory than a node has is
reported as infeasible rather than attempted, and that the scheduler does
not pack steps whose combined declared memory exceeds what is available.

Validation on a real workload shall compare declared memory against measured
peak resident memory, since a declaration that is badly wrong is worse than
no declaration: it will either waste the allocation or oversubscribe it.
