"""
Failures in runs on disk: Polaris suites, through their results files, and
CIME tests, through their ``TestStatus`` files
"""

import datetime
import json
import os
from dataclasses import dataclass
from typing import Iterator, List, Optional

from bug_hunt_keys import (
    cime_phase_to_key,
    first_error_line,
    is_cime_test,
    normalize_test,
)

#: how far below a root results files and test directories are looked for
SEARCH_DEPTH = 4


@dataclass
class LocalFailure:
    """
    A failure found in a run on disk

    Attributes
    ----------
    test : str
        The task path or CIME test name as reported

    phase : str
        The phase of the key

    message : str, optional
        The first error message, if one was found

    row : str
        ``<machine>/<compiler>``

    source : str
        ``polaris`` or ``cime``

    night : str
        The date of the run, ``yyyy-mm-dd``

    where : str
        The log or directory to look at

    excerpt : str, optional
        Lines from the log around the error
    """

    test: str
    phase: str
    message: Optional[str]
    row: str
    source: str
    night: str
    where: str
    excerpt: Optional[str] = None


def polaris_failures(roots: List[str]) -> List[LocalFailure]:
    """
    The failed tasks in Polaris suite runs under some directories

    Parameters
    ----------
    roots : list of str
        Directories to search for ``<suite>_results.json`` files

    Returns
    -------
    failures : list of bug_hunt_sources.LocalFailure
        A failure for each task that failed
    """
    failures = []
    for filename in _find_files(roots, '_results.json'):
        failures.extend(_read_suite_results(filename))
    return failures


def cime_failures(roots: List[str]) -> List[LocalFailure]:
    """
    The failed phases of CIME tests under some directories

    Parameters
    ----------
    roots : list of str
        Directories to search for ``TestStatus`` files

    Returns
    -------
    failures : list of bug_hunt_sources.LocalFailure
        A failure for the first failed phase of each test
    """
    failures = []
    for filename in _find_files(roots, 'TestStatus', exact=True):
        failure = _read_test_status(filename)
        if failure is not None:
            failures.append(failure)
    return failures


def _read_suite_results(filename: str) -> List[LocalFailure]:
    with open(filename) as handle:
        data = json.load(handle)
    provenance = data.get('provenance') or {}
    machine = provenance.get('machine') or 'unknown'
    compiler = provenance.get('compiler') or 'unknown'
    night = (data.get('start_time') or '')[:10] or _mtime_date(filename)
    base = os.path.dirname(filename)
    failures = []
    for task in data.get('tasks', []):
        if task.get('status') != 'fail':
            continue
        phase = 'run' if task.get('execution') == 'fail' else 'baseline'
        log = task.get('log')
        log_path = os.path.join(base, log) if log else base
        message = None
        excerpt = None
        if log and os.path.exists(log_path):
            with open(log_path, errors='replace') as handle:
                text = handle.read()
            message = first_error_line(text)
            excerpt = _excerpt(text, message)
        failures.append(
            LocalFailure(
                test=task['path'],
                phase=phase,
                message=message,
                row=f'{machine}/{compiler}',
                source='polaris',
                night=night,
                where=log_path,
                excerpt=excerpt,
            )
        )
    return failures


def _read_test_status(filename: str) -> Optional[LocalFailure]:
    with open(filename, errors='replace') as handle:
        lines = handle.read().splitlines()
    for line in lines:
        parts = line.split()
        if len(parts) < 3 or parts[0] != 'FAIL':
            continue
        test, cime_phase = parts[1], parts[2]
        phase = cime_phase_to_key(cime_phase)
        row = 'unknown/unknown'
        if is_cime_test(test):
            machine_compiler = test.split('.')[3]
            machine, _, compiler = machine_compiler.partition('_')
            row = f'{machine}/{compiler}'
        return LocalFailure(
            test=normalize_test(test),
            phase=phase,
            message=f'{cime_phase} failed',
            row=row,
            source='cime',
            night=_mtime_date(filename),
            where=os.path.dirname(filename),
        )
    return None


def _find_files(
    roots: List[str], suffix: str, exact: bool = False
) -> Iterator[str]:
    """Files ending in ``suffix``, or named ``suffix``, below some roots"""
    for root in roots:
        root = os.path.abspath(root)
        base_depth = root.rstrip(os.sep).count(os.sep)
        for directory, subdirs, filenames in os.walk(root):
            if directory.count(os.sep) - base_depth >= SEARCH_DEPTH:
                subdirs[:] = []
            for filename in filenames:
                if (exact and filename == suffix) or (
                    not exact and filename.endswith(suffix)
                ):
                    yield os.path.join(directory, filename)


def _excerpt(text: str, line: Optional[str]) -> Optional[str]:
    """Up to 20 lines of a log, from the first error line on"""
    if line is None:
        return None
    lines = text.splitlines()
    for index, candidate in enumerate(lines):
        if candidate.strip().startswith(line[:60]):
            return '\n'.join(lines[index : index + 20])
    return None


def _mtime_date(filename: str) -> str:
    stamp = os.path.getmtime(filename)
    return datetime.date.fromtimestamp(stamp).isoformat()
