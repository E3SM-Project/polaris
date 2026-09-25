import json
import math
import numbers
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = 1
""" The version of the results file format, incremented when a field is
removed or its meaning changes """


@dataclass
class TaskResult:
    """
    The outcome of running a task as part of a suite

    Attributes
    ----------
    path : str
        The path of the task within the component, which is also its name
        in the suite

    steps_to_run : list of str, optional
        The steps the task was set to run, or ``None`` if the task has not
        been run yet

    log : str, optional
        The path of the task's log file, relative to the suite's base work
        directory, or ``None`` if the task does not have a single log file

    execution_passed : bool, optional
        Whether the steps of the task ran without error, or ``None`` if the
        task has not been run yet

    baseline_passed : bool, optional
        Whether the baseline comparisons passed, or ``None`` if none were
        made

    elapsed_seconds : float, optional
        The wall-clock time the task took to run, or ``None`` if the task
        has not been run yet

    baseline_diffs : dict
        The maximum l1, l2 and l_infinity norms of the difference from the
        baseline, keyed by variable name, as merged by
        :py:func:`polaris.validate.merge_diff_summary()`
    """

    path: str
    steps_to_run: Optional[List[str]] = None
    log: Optional[str] = None
    execution_passed: Optional[bool] = None
    baseline_passed: Optional[bool] = None
    elapsed_seconds: Optional[float] = None
    baseline_diffs: Dict = field(default_factory=dict)

    @property
    def pending(self) -> bool:
        """Whether the task has not been run yet"""
        return self.execution_passed is None

    @property
    def success(self) -> bool:
        """
        Whether the task ran without error and no baseline comparison
        failed
        """
        return self.execution_passed is True and (
            self.baseline_passed is not False
        )

    @property
    def status(self) -> str:
        """The task's status: ``pending``, ``pass`` or ``fail``"""
        if self.pending:
            return 'pending'
        return 'pass' if self.success else 'fail'

    def to_dict(self) -> Dict[str, Any]:
        """
        The task's entry in the results file

        Returns
        -------
        entry : dict
            The task's result in the form it is written to the results file
        """
        return {
            'path': self.path,
            'status': self.status,
            'execution': _pass_fail(self.execution_passed),
            'baseline': _pass_fail(self.baseline_passed),
            'elapsed_seconds': self.elapsed_seconds,
            'steps_to_run': self.steps_to_run,
            'log': self.log,
            'baseline_diffs': _json_safe(self.baseline_diffs),
        }


def write_suite_results(
    filename: str,
    suite_name: str,
    provenance: Dict[str, Optional[str]],
    start_time: datetime,
    elapsed_seconds: float,
    task_results: Iterable[TaskResult],
    complete: bool,
) -> None:
    """
    Write the machine-readable results of a suite run

    The file is written to a temporary file and renamed into place, so a
    reader never sees a partial file.

    Parameters
    ----------
    filename : str
        The results file to write

    suite_name : str
        The name of the suite, or ``task`` for a single task

    provenance : dict
        Metadata about the run, such as the machine and compiler, with
        ``None`` for anything that is not known

    start_time : datetime.datetime
        When the suite started running

    elapsed_seconds : float
        The wall-clock time since the suite started running

    task_results : iterable of polaris.run.results.TaskResult
        The results of every task in the suite, in the order they run,
        including those that have not been run yet

    complete : bool
        Whether the suite has finished running
    """
    task_results = list(task_results)
    summary = {
        'total': len(task_results),
        'passed': 0,
        'failed': 0,
        'pending': 0,
    }
    status_counts = {'pass': 'passed', 'fail': 'failed', 'pending': 'pending'}
    for result in task_results:
        summary[status_counts[result.status]] += 1

    contents = {
        'schema_version': SCHEMA_VERSION,
        'suite': suite_name,
        'complete': complete,
        'start_time': start_time.isoformat(timespec='seconds'),
        'elapsed_seconds': elapsed_seconds,
        'summary': summary,
        'provenance': provenance,
        'tasks': [result.to_dict() for result in task_results],
    }

    tmp_filename = f'{filename}.tmp'
    with open(tmp_filename, 'w') as handle:
        json.dump(contents, handle, indent=2, allow_nan=False)
        handle.write('\n')
    os.replace(tmp_filename, filename)


def _pass_fail(passed: Optional[bool]) -> Optional[str]:
    """``pass`` or ``fail``, or ``None`` if there is no outcome"""
    if passed is None:
        return None
    return 'pass' if passed else 'fail'


def _json_safe(value: Any) -> Any:
    """
    Convert numpy scalars to Python numbers, which ``json`` can write, and
    non-finite floats to strings, which strict JSON requires
    """
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return 'NaN'
        return 'Infinity' if value > 0 else '-Infinity'
    return value
