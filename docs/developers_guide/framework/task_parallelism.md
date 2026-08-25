(dev-task-parallelism)=

# Writing task-parallel-safe steps

Polaris runs one step at a time today, and a step that changes the process
working directory or mutates a module-level global is correct under that
assumption.  It stops being correct as soon as two steps run concurrently in
one process, and the failure is timing-dependent: it shows up as intermittent
wrong answers rather than as a clean error.

Polaris is adding task parallelism so that analysis steps, which are heavily
Python and are the workload that most needs to run concurrently, can be
scheduled together and across nodes.  The rules below are what a step must
satisfy to be scheduled that way.  They are cheap to follow when a step is
first written and expensive to retrofit, so **new analysis steps should follow
them from the start**.  Existing steps are being converted only where they are
shared building blocks; see {ref}`dev-task-parallelism-status`.

The reasoning behind the rules, and the scheduler work they support, is in the
{ref}`design documents <design-docs>`, under
"Task-Parallel-Safe Analysis Steps in Polaris".

## What Polaris already guarantees

Several properties a distributed executor would otherwise have to demand are
already true, so a step does not have to do anything special about them:

- **Steps are already serializable.**  `polaris setup` pickles each step to
  `step.pickle` in its work directory and `polaris serial` unpickles it in a
  different process.  A step holding an open file handle or a live connection
  would already fail today.
- **Config options already come from a file.**  Each step's config file is
  written into its work directory at setup and re-read immediately before the
  step runs, so a step run in a fresh process sees the same config.
- **Declared inputs and outputs are already absolute.**
  `Step.process_inputs_and_outputs()` resolves the `filename` arguments to
  `add_input_file()` and `add_output_file()` against the step's work directory
  at setup, so `self.inputs` and `self.outputs` do not depend on the process
  working directory.
- **Every step already has its own work directory and its own logger.**

## The rules

### Address files through the step, not the working directory

Polaris changes the process working directory to the step's work directory
before calling `run()`, so a bare relative filename works today.  The working
directory is process-global, so it cannot stay pointed at your step once
another step is running beside you.

Build paths with {py:meth}`polaris.Step.work_path()` instead:

```python
class Viz(Step):
    def run(self):
        with xr.open_dataset(self.work_path('output.nc')) as ds:
            ...
        fig.savefig(self.work_path('comparison.png'))
```

This applies to paths handed to subprocesses and to third-party libraries as
well, since those inherit or resolve against the same working directory.  The
`filename` arguments to `add_input_file()` and `add_output_file()` are
unaffected -- they are relative by design and already resolved at setup.

### Do not mutate process-global state

A step must not change anything shared by the whole process: the working
directory, environment variables, module-level configuration in libraries such
as `mpas_tools.io`, or global plotting state.  In particular:

- Do not assign to `plt.rcParams` or call `plt.style.use()`.  Use the
  {py:func}`polaris.viz.mplstyle_context()` context manager, which applies the
  Polaris style (and an optional `dpi`) for the duration of a `with` block and
  restores the previous settings afterwards.
- Do not call `plt.switch_backend()`.  Matplotlib already selects a
  non-interactive backend where Polaris steps run, and the object-oriented
  figure API does not consult the backend at all.

### Use the object-oriented figure API

`pyplot`'s "current figure" is process-global.  `plt.figure()`,
`plt.subplot()`, `plt.title()`, `plt.colorbar()` and `plt.savefig()` all act on
whichever figure `pyplot` made most recently, so two steps plotting at the same
time draw into each other's figures.  Build the figure explicitly instead:

```python
from matplotlib.figure import Figure

from polaris.viz import mplstyle_context

with mplstyle_context():
    fig = Figure(figsize=(8, 4.5))
    ax = fig.add_subplot(111)
    ax.plot(x, y)
    ax.set_title('...')
    fig.colorbar(handle, ax=ax)
    fig.savefig(self.work_path('my_plot.png'))
```

A figure built this way is never registered with `pyplot`, so there is also
nothing to `plt.close()`.

### Keep temporary files in the step's work directory

Write scratch files under the step's own work directory rather than in `/tmp`
or the base work directory, so that two concurrent steps cannot choose the same
path.  A step must also not write into another step's work directory, and must
not read a file that a concurrently running step is still writing.

### Log through the step's logger

Emit output with `self.logger`, never with `print()` or by writing to `stdout`,
`stderr` or the root logger.  Output written to shared streams interleaves once
several steps run at once, and the resulting log cannot be attributed to a
step.  Pass `self.logger` to any helper function or subprocess that produces
output; see {ref}`dev-logging`.

### Declare the resources you need

A step must declare the resources it needs so that the scheduler can decide how
many steps may run at once.  Memory is the field that distinguishes analysis
steps from most existing Polaris steps: at high resolution an analysis step may
need a large fraction of a node, and a scheduler that packs by cores alone will
oversubscribe memory.

### Size internal parallelism from what you were given

A step that starts its own pool of processes or threads must size it from the
resources the step was given, not from the machine.  A pool sized to
`os.cpu_count()` oversubscribes the node as soon as a second step runs beside
it.  Use `self.cpus_per_task`:

```python
n_workers = min(self.cpus_per_task, len(work_items))
```

(dev-task-parallelism-status)=

## Current status

The framework support exists -- {py:meth}`polaris.Step.work_path()`,
{py:func}`polaris.viz.mplstyle_context()`, and the object-oriented figure API
in `polaris.viz` -- and the shared building blocks have been converted:
`polaris.viz`, `polaris.mesh.spherical`, and
`polaris.ocean.convergence.analysis`.

Most task-level analysis and visualization steps have **not** been converted;
they still open files by bare relative name and use the `pyplot` current
figure.  That is correct under today's one-step-at-a-time execution and will be
addressed as the analysis capability is built out.  Do not copy those steps as
a template for new work.
