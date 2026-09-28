# Machine-Readable Suite Results

date: 2026/09/25

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

`polaris serial` reports a suite's results only as text: a line per task
on stdout and a `POLARIS TASK: PASS` or `FAIL` line in each task's log in
`case_outputs`. The nightly CDash job scrapes those strings and reports an
execution time of `1.0` for every task because the real times are printed
and then discarded (see
[#771](https://github.com/E3SM-Project/polaris/issues/771)).

This design adds a JSON results file that `polaris serial` writes alongside
the suite's pickle file. It records each task's outcome, elapsed time and
baseline differences, plus the provenance of the run. Downstream tools read
the file instead of the logs, so the log wording is no longer an interface.

Success means that the CDash job can build its test report from this file
alone, with real per-task times, including for a run that was killed before
it finished.

## Requirements

### Requirement: A suite run leaves a machine-readable record of its results.

For each task, the record gives its outcome, the outcome of any baseline
comparison, its elapsed time, the steps it ran and where its log is. For
the run, it gives the Polaris version, machine, compiler and build.

### Requirement: The record is useful when the run does not finish.

A job that hits its wall-clock limit still leaves a record of the tasks that
finished and of those that did not run.

### Requirement: The record carries what the text output discards.

This includes elapsed times and the norms of any baseline differences.

### Requirement: Consumers can detect a change in the format.

## Algorithm Design

### Algorithm Design: A suite run leaves a machine-readable record of its results.

`polaris serial <suite>` writes `<suite>_results.json` in the suite's base
work directory. `polaris serial` in a task's work directory writes
`task_results.json` there. In both cases, the provenance comes from the
`provenance` file in the base work directory.

The file is a JSON object:

```json
{
  "schema_version": 1,
  "suite": "omega_pr",
  "complete": true,
  "start_time": "2026-09-25T10:15:02-05:00",
  "elapsed_seconds": 1834.2,
  "summary": {"total": 12, "passed": 11, "failed": 1, "pending": 0},
  "provenance": {
    "polaris_version": "1.1.0-alpha.6",
    "polaris_git_version": "4b2347b9e",
    "component_git_version": "a1b2c3d",
    "machine": "chrysalis",
    "partition": "compute",
    "compiler": "intel",
    "build_directory": "/path/to/build",
    "build_type": "Release",
    "work_directory": "/path/to/work",
    "baseline_work_directory": "/path/to/baseline"
  },
  "tasks": [
    {
      "path": "ocean/planar/manufactured_solution/convergence_both/default",
      "status": "fail",
      "execution": "pass",
      "baseline": "fail",
      "elapsed_seconds": 95.3,
      "steps_to_run": ["init", "forward"],
      "log": "case_outputs/ocean_planar_manufactured_solution_...log",
      "baseline_diffs": {
        "normalVelocity": {"l1": 1.2e-9, "l2": 3.4e-10, "linf": 5.6e-11}
      }
    }
  ]
}
```

`tasks` lists every task in the suite in the order they run.

- `status` is `pass`, `fail` or `pending`. A task passes if it ran without
  error and no baseline comparison failed, the same criterion as the text
  output.
- `execution` is `pass` or `fail`, and `null` for a pending task.
- `baseline` is `pass` or `fail`, and `null` if no comparison was made.
- `log` is relative to the directory holding the results file. It is `null`
  for a single task, whose steps log separately.
- A provenance value that the `provenance` file does not record is `null`.

### Algorithm Design: The record is useful when the run does not finish.

The file is written before the first task runs, with every task `pending`,
and rewritten after each task finishes. `complete` is `false` until the last
write, which happens before `polaris serial` exits with a failure status.
Each write goes to a temporary file that is renamed into place, so a reader
never sees a partial file.

A consumer that finds `complete: false` after the job has ended reports the
`pending` tasks as not run.

### Algorithm Design: The record carries what the text output discards.

`elapsed_seconds` is wall-clock time, for each task and for the suite so
far. `baseline_diffs` holds the maximum l1, l2 and l_infinity norms of the
differences for each compared variable, merged across a task's steps in the
same way as for `<suite>_output_for_pr.md`. It is empty when no comparison
was made. Non-finite norms are written as the strings `NaN`, `Infinity` and
`-Infinity` so that the file is strict JSON.

### Algorithm Design: Consumers can detect a change in the format.

`schema_version` is an integer. It is incremented when a field is removed
or its meaning changes, not when a field is added.

## Implementation

### Implementation: A suite run leaves a machine-readable record of its results.

A new module, `polaris.run.results`, holds a `TaskResult` record and the
function that writes the file. `polaris.run.serial.run_tasks()` builds a
`TaskResult` per task, replacing the tuple that `_log_and_run_task()`
returns now. It reads provenance with the parser it already uses for
`<suite>_output_for_pr.md`, but from the base work directory, so that a
single task has provenance as well.

The `POLARIS TASK` and `POLARIS BASELINE` log lines and
`<suite>_output_for_pr.md` are unchanged.

### Implementation: The record is useful when the run does not finish.

`run_tasks()` calls the writer once before the loop over tasks, once after
each task and once with `complete=True` before logging the task runtimes,
which is where a failed suite exits.

## Testing

### Testing and Validation: A suite run leaves a machine-readable record of its results.

Unit tests run `run_tasks()` on a mocked suite with a task that passes, one
that raises, and one whose baseline comparison fails, and check the
contents of the file. A run of `omega_pr` against a baseline from `main`
checks the file from a real suite.

### Testing and Validation: The record is useful when the run does not finish.

A unit test checks the file after the first of several tasks, and that the
final file is written when the suite fails.
