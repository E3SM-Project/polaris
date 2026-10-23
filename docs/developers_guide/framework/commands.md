(dev-command-mods)=

# Modules for polaris commands

(dev-list)=

## list module

The {py:func}`polaris.list.list_cases()`, {py:func}`polaris.list.list_machines()`
and {py:func}`polaris.list.list_suites()` functions are used by the
`polaris list` command to list tasks, supported machines and test
suites, respectively.  These functions are not currently used anywhere else
in polaris.

(dev-setup)=

## setup module

The {py:func}`polaris.setup.setup_tasks()` and {py:func}`polaris.setup.setup_task()`
functions are used by `polaris setup` and `polaris suite` to set up a list
of tasks and a single task, respectively, in a work directory.
Subdirectories will be created for each task and its steps; input,
namelist and streams files will be downloaded, symlinked and/or generated
in the setup process. A [pickle file](https://docs.python.org/3/library/pickle.html)
called `task.pickle` will be written to each task directory
containing the task object for later use in calls to `polaris serial`.
Similarly, a file `step.pickle` containing the step object
will be written to each step directory, allowing the step to be run
on its own with `polaris serial`.  In contrast to {ref}`config-files`, these
pickle files are not intended for users (or developers) to read or modify.
Properties of the task and step objects are not intended to change between
setting up and running a suite, task or step.

A pickle holds the task or step itself, the config it uses and, for a step,
the dependencies it was given.  It does not hold the component's `tasks`,
`steps` and `configs` dictionaries, nor the `tasks` a config has been shared
with.  Those four describe how a component was assembled during setup and
nothing reads them afterwards, but every task and step in them points back at
the component, so pickling them would make each step's pickle a copy of the
whole component.  They come back from a pickle empty, so anything that needs
them has to run during setup.

(dev-suite)=

## suite module

The {py:func}`polaris.suite.setup_suite()` function is used by `polaris suite`
to set up a suite in a work directory.  Setting up a suite includes setting up
the tasks (see {ref}`dev-setup`), writing out a {ref}`dev-provenance` file, and
saving a pickle file containing a python dictionary that defines the suite for
later use by `polaris serial`.  The "target" and "minimum" number of cores
required for running the suite are displayed.  The "target" is determined
based on the maximum product of the `ntasks` and `cpus_per_task`
attributes of each step in the suite.  This is the number of cores to run
on to complete the suite as quickly as possible, with the
caveat that many cores may sit idle for some fraction of the runtime.  The
"minimum" number of cores is the maximum of the product of the `min_tasks`
and `min_cpus_per_task` attribute for all steps in the suite, indicating the
fewest cores that the test may be run with before at least some steps in the
suite will fail.

A suite is defined by `polaris/<component>/suites/<suite_name>.txt`, which
lists the tasks in the suite.  A suite may also provide an optional
`polaris/<component>/suites/<suite_name>.cfg` alongside it with config options
that apply to the whole suite.  This is the natural place for options that
describe the suite rather than any one task, such as the `[job]` options used
to build the job script:

```cfg
# Config options related to creating a job script
[job]

# wall-clock time
wall_time = 00:30:00

# use this machine's debug target, whether it provides one as a partition, a
# QOS or a queue
scheduler_target = debug
```

These options are added after the machine config options and before the
component's, so a suite can override a machine default while a user config
file (`-f`) still overrides the suite.  Config options belonging to an
individual task are still set by that task and take precedence over the
suite's.  See {ref}`scheduler-targets` for what the `[job]` options mean and
what happens when a machine cannot satisfy the requested scheduler target.

(dev-run)=

## run.serial module

The function {py:func}`polaris.run.serial.run_tasks()` is used to run a
suite or task and {py:func}`polaris.run.serial.run_single_step()` is
used to run a single step using `polaris serial`.  `run_tasks()` performs
setup operations like creating a log file and figuring out the number of tasks
and CPUs per task for each step, then it calls each step's `run()` method.

Suites run from the base work directory with a pickle file starting with the
suite name, or `custom.pickle` if a suite name was not given. Tasks or
steps run from their respective subdirectories with a `task.pickle` or
`step.pickle` file in them. Both of these functions reads the local pickle
file to retrieve information about the suite, task and/or step that
was stored during setup.

If {py:func}`polaris.run.serial.run_tasks()` is used for a suite, it will
run each task in the suite in the order that they are given in the
text file defining the suite (`polaris/<component>/suites/<suite_name>.txt`).
Output from tasks and their steps are stored in log files in the
`case_outputs` subdirectory of the base work directory. If the function is
used for a single task, it will run the steps of that task, writing
output for each step to a log file starting with the step's name. In either
case (suite or individual test), it displays a `SUCCESS` or `ERROR` message for
the execution of each step, indicates whether baseline comparisons `PASS` or
`FAIL` for any steps that include them (and if a baseline was provided),
and finally indicates if the overall task execution was `SUCCESS` or `ERROR`.
Execution times are provided for individual steps, tasks and the suite as a
whole.

Because every step runs in the same process, each step also reports the
memory that process used: its peak during the step, what it still held
afterward and, if the step started the largest subprocess so far, that
subprocess's peak.  Memory that keeps growing from one step to the next is
memory that earlier steps left behind.  The numbers come from
{py:func}`polaris.run.memory.read_process_memory()`, and the peak is reset
before each step with {py:func}`polaris.run.memory.reset_peak_memory()` where
the system allows it (Linux).  The log also records the size of each
dependency's pickle as the step loads it, since a dependency is unpickled
whole into the process.

`run_tasks()` also writes a machine-readable results file,
`<suite_name>_results.json` (or `task_results.json` for a single task), next
to the pickle file. Each task's outcome is held in a
{py:class}`polaris.run.results.TaskResult` and the file is written by
{py:func}`polaris.run.results.write_suite_results()`. The file is written
before the first task runs and again after each task, so it is there even if
the job is killed. Downstream tools should read this file rather than parsing
the log files. Its format is described in {ref}`suites-results`. Each write
goes to a temporary file that is renamed into place, so a reader never sees a
partial file, and non-finite norms are written as strings (`NaN`,
`Infinity`, `-Infinity`) to keep the file strict JSON. If you remove a field
or change its meaning, increment `SCHEMA_VERSION` in `polaris.run.results`;
adding a field does not need a new version.

{py:func}`polaris.run.serial.run_single_step()` runs only the selected step
from a given task, skipping any others, displaying the output in the terminal
window rather than a log file.

(dev-run-parallel)=

## run.parallel module

{py:func}`polaris.run.parallel.run_tasks()` runs a suite or task with its
steps at the same time, and is what `polaris parallel` calls.  It shares the
step lifecycle with the serial path -- the checks on a step's inputs and
outputs, loading what it depends on, `runtime_setup()`, `run()`, the
completion markers and the baseline comparisons all live in
`polaris.run.lifecycle` and are the same either way.  What differs is
deciding *which* step runs and what it is given.

Four pieces do that work, and they are worth knowing apart:

- {py:func}`polaris.run.graph.build_step_graph()` turns the selected steps
  into a graph, from the dependencies a step declares and the files one step
  produces that another consumes.  It rejects a graph that cannot be run --
  a cycle, or an input nothing produces and which does not already exist --
  before any step starts.
- {py:func}`polaris.run.allocation.read_allocation()` asks the allocation's
  nodes what they actually hold, rather than trusting the machine's
  configured figure, because a node can offer less than its specification
  says and over-crediting memory kills a job.
- {py:class}`polaris.run.pool.ResourcePool` decides what may start: it hands
  out cores, GPUs and a memory budget, and refuses a step that would not fit
  rather than overcommitting the machine.
- {py:func}`polaris.run.executor.start_step()` forks a child for a step and
  {py:func}`polaris.run.executor.next_event()` waits for whichever finishes
  next.  The child inherits the scheduler's memory, so it imports nothing and
  reads no pickle of its own.

Because the scheduler forks, it must hold no thread but its own -- only the
forking thread survives a fork, and a lock held by any other one at that
moment is held forever in the child.  That is why `polaris/__init__.py` pins
the numerical thread pools before numpy can raise one thread per core, and
why the scheduler reaps in its own loop rather than giving each running step
a thread to wait on it.

A run with a step that hands out pieces of its work starts a resident on
each node to fork the pieces (see {ref}`dev-handing-out-work`).  A run on
more than one node starts them, too, once a step that launches nothing is
waiting for room on the scheduler's node, so that a resident on a node
with room can fork it there.
{py:class}`polaris.run.residents.Residents` starts them, with one launch
across the allocation, and stops them when the run ends.  The scheduler
hears from them in the same loop in which it reaps its children -- a
resident saying hello, one going away, or a step it forked ending -- so
that it never waits on one while another has something to say.
{py:func}`polaris.run.executor.start_remote_step` has a resident fork a
step, which then runs through the same lifecycle as one the scheduler
forks.  A step that hands out work does so through
{py:class}`polaris.run.pieces.Pieces`, which connects to the residents
directly.

Each step's output goes to its own log under `case_outputs`, since steps no
longer take turns and cannot share a stream.  The scheduler also writes an
event stream, `<suite>_events.jsonl`, recording what started when and what
each step held; {py:func}`polaris.run.events.read_events()` reads it back.

(dev-cache)=

## cache module

The {py:func}`polaris.cache.update_cache()` function is used by
`polaris cache` to copy step outputs to the `polaris_cache` database on
the LCRC server and to update `<component>_cached_files.json` files that
contain a mapping between these cached files and the original outputs.  This
functionality enables running steps with {ref}`dev-step-cached-output`, which
can be used to skip time-consuming initialization steps for faster development
and debugging.
