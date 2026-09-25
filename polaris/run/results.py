from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
