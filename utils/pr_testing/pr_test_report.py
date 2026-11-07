"""
The pieces every Testing comment the PR testing utilities write has in
common: a hidden marker, a table with a line for each row and the files
Polaris and CTest wrote, the notes, the signature and posting
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pr_test_github as github
from pr_test_rows import MODEL_LABELS, Row

#: version 2 lists a machine's rows in one marker; version 1 had one row
MARKER_SCHEMA = 2

#: the signature that Polaris's AGENTS.md prescribes for posts made by an
#: agent on someone's behalf
SIGNATURE = (
    "*Posted by {agent} on @{user}'s behalf. The testing, analysis and "
    'wording above are AI-authored; please check them accordingly.*'
)

_CTEST_COUNTS = re.compile(
    r'(\d+)% tests passed, (\d+) tests failed out of (\d+)'
)


class ReportError(Exception):
    """A row's results are not ready to report"""


@dataclass
class RowResult:
    """
    A row's line in a Testing comment, and the files pasted below it

    Attributes
    ----------
    row : pr_test_rows.Row
        The row

    status : {'complete', 'not-run'}
        Whether the row was run

    result : {'pass', 'fail', 'none'}
        The row's overall result

    cells : list of str
        The row's cells in the table, after its label

    details : str, optional
        What goes in the row's collapsed block: the files Polaris and CTest
        wrote, pasted unchanged, and anything generated from them

    marker : dict
        Anything else to record about the row in the marker
    """

    row: Row
    status: str
    result: str
    cells: List[str]
    details: Optional[str] = None
    marker: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineComparison:
    """
    How a suite's tasks compare with the baseline.  A baseline comparison
    in Polaris passes only if the variables are bit-for-bit.

    Attributes
    ----------
    suite : str
        The suite

    bit_for_bit : list of str
        The tasks whose compared variables are bit-for-bit

    differ : dict of str to list of str
        The tasks that are not bit-for-bit, with the variables that differ

    did_not_run : list of str
        The tasks that failed to run or never ran, which have no
        bit-for-bit result either way

    not_compared : list of str
        The tasks that ran but compare no variables with the baseline

    failed_in_baseline : list of str
        The tasks that ran but could not be compared, because they failed
        in the baseline
    """

    suite: str
    bit_for_bit: List[str] = field(default_factory=list)
    differ: Dict[str, List[str]] = field(default_factory=dict)
    did_not_run: List[str] = field(default_factory=list)
    not_compared: List[str] = field(default_factory=list)
    failed_in_baseline: List[str] = field(default_factory=list)


def compare_with_baseline(
    work_dir: str, suite: str, baseline_work_dir: Optional[str] = None
) -> BaselineComparison:
    """
    Read how a suite's tasks compare with the baseline from its results

    Parameters
    ----------
    work_dir : str
        The suite's work directory

    suite : str
        The suite

    baseline_work_dir : str, optional
        The baseline's work directory, whose failed tasks have nothing to
        compare with

    Returns
    -------
    comparison : pr_test_report.BaselineComparison
        The comparison
    """
    path = os.path.join(work_dir, f'{suite}_results.json')
    with open(path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    failed_in_baseline = _failed_tasks(baseline_work_dir, suite)
    comparison = BaselineComparison(suite)
    for task in results.get('tasks', []):
        name = task['path']
        if task.get('execution') != 'pass':
            comparison.did_not_run.append(name)
        elif task.get('baseline') == 'fail':
            variables = _differing_variables(task)
            if variables or name not in failed_in_baseline:
                comparison.differ[name] = variables
            else:
                comparison.failed_in_baseline.append(name)
        elif task.get('baseline') == 'pass':
            comparison.bit_for_bit.append(name)
        else:
            comparison.not_compared.append(name)
    return comparison


def format_bit_for_bit(
    rows: Sequence[Tuple[Row, Optional[BaselineComparison], str]],
) -> str:
    """
    A section that says plainly which tasks differ from the baseline, and
    on which rows, keeping tasks that did not run and rows that were not
    compared apart

    Each task is named once, with the rows it differs on, and tasks that
    differ on the same rows share a line.  Which variables differ, and by
    how much, is in each row's collapsed block.

    Parameters
    ----------
    rows : list of tuple
        Each row, its comparison with the baseline, or ``None`` if it was
        not compared, and why not

    Returns
    -------
    text : str
        The section
    """
    compared = [(row, comparison) for row, comparison, _ in rows if comparison]
    compared_rows = [row for row, _ in compared]
    differ = _rows_by_task(compared, lambda c: list(c.differ))
    did_not_run = _rows_by_task(compared, lambda c: c.did_not_run)
    failed_in_baseline = _rows_by_task(
        compared, lambda c: c.failed_in_baseline
    )
    paragraphs = []
    if not compared:
        paragraphs.append('Nothing was compared with a baseline.')
    elif not differ:
        identical = len(
            {
                task
                for _, comparison in compared
                for task in comparison.bit_for_bit
            }
        )
        paragraphs.append(
            f'Every task compared is bit-for-bit with the baseline '
            f'({_count(identical, "task")}, on '
            f'{_count(len(compared), "row")}).'
        )
    else:
        verb = 'differs' if len(differ) == 1 else 'differ'
        paragraphs.append(
            f'**{_count(len(differ), "task")} {verb} from the baseline:**\n\n'
            + _list_tasks(differ, compared_rows, len(rows))
        )
    if did_not_run:
        they = 'it has' if len(did_not_run) == 1 else 'they have'
        paragraphs.append(
            f'{_count(len(did_not_run), "task")} did not run, so {they} '
            f'nothing to compare:\n\n'
            + _list_tasks(did_not_run, compared_rows, len(rows))
        )
    if failed_in_baseline:
        paragraphs.append(
            f'{_count(len(failed_in_baseline), "task")} failed in the '
            f'baseline, so there is nothing to compare with:\n\n'
            + _list_tasks(failed_in_baseline, compared_rows, len(rows))
        )
    by_reason: Dict[str, List[Row]] = {}
    for row, comparison, reason in rows:
        if comparison is None:
            by_reason.setdefault(reason, []).append(row)
    if by_reason:
        count = sum(len(reason_rows) for reason_rows in by_reason.values())
        verb = 'was' if count == 1 else 'were'
        paragraphs.append(
            f'{_count(count, "row")} {verb} not compared:\n\n'
            + '\n'.join(
                f'- {"; ".join(row.label for row in reason_rows)}, because '
                f'{reason}.'
                for reason, reason_rows in by_reason.items()
            )
        )
    return '### Differences from the baseline\n\n' + '\n\n'.join(paragraphs)


def make_marker(prefix: str, **contents: Any) -> str:
    """
    The hidden marker that starts a Testing comment

    Parameters
    ----------
    prefix : str
        The utility's marker prefix, such as ``omega-pr-test``

    **contents
        What to record, which should include ``pr`` and ``rows``, a list
        with a dict for each row with its ``row``, ``status`` and
        ``result``

    Returns
    -------
    marker : str
        An HTML comment holding the marker as JSON
    """
    contents = {'schema': MARKER_SCHEMA, **contents}
    return f'<!-- {prefix} {json.dumps(contents)} -->'


def parse_marker(body: str, prefix: str) -> Optional[Dict[str, Any]]:
    """The marker in a comment's body, or ``None`` if it has none"""
    pattern = re.compile(rf'<!--\s*{re.escape(prefix)}\s+(\{{.*?\}})\s*-->')
    match = pattern.search(body)
    if match is None:
        return None
    try:
        contents = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(contents, dict):
        return None
    return contents


def get_marker_rows(marker: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Each row a marker reports on, with the marker's other entries

    Parameters
    ----------
    marker : dict
        A marker, of either schema version

    Returns
    -------
    rows : list of dict
        A dict for each row, with its ``row``, ``status`` and ``result``
    """
    shared = {key: value for key, value in marker.items() if key != 'rows'}
    rows = marker.get('rows')
    if not isinstance(rows, list):
        # a schema 1 marker reports on one row itself
        return [shared]
    return [{**shared, **row} for row in rows if isinstance(row, dict)]


def get_marker_entries(results: List[RowResult]) -> List[Dict[str, Any]]:
    """The ``rows`` entry of a marker for a comment on these rows"""
    return [
        {
            'row': result.row.name,
            'status': result.status,
            'result': result.result,
            **result.marker,
        }
        for result in results
    ]


def get_overall_result(results: List[RowResult]) -> str:
    """``fail`` if any row failed, ``pass`` if any passed, else ``none``"""
    outcomes = {result.result for result in results}
    if 'fail' in outcomes:
        return 'fail'
    if 'pass' in outcomes:
        return 'pass'
    return 'none'


def not_run(row: Row, reason: str, columns: List[str]) -> RowResult:
    """
    The line for a row that was not run

    Parameters
    ----------
    row : pr_test_rows.Row
        The row

    reason : str
        Why it was not run

    columns : list of str
        The table's columns after the row's label

    Returns
    -------
    result : pr_test_report.RowResult
        The row's line
    """
    cells = [f'not run: {reason}'] + [''] * (len(columns) - 1)
    return RowResult(row=row, status='not-run', result='none', cells=cells)


def format_rows(columns: List[str], results: List[RowResult]) -> List[str]:
    """
    A table with a line for each row, then each row's collapsed block

    Parameters
    ----------
    columns : list of str
        The table's columns after the row's label

    results : list of pr_test_report.RowResult
        The rows, in order

    Returns
    -------
    sections : list of str
        The table, then a block for each row that has details
    """
    lines = [
        '| Row | ' + ' | '.join(columns) + ' |',
        '|' + '---|' * (len(columns) + 1),
    ]
    for result in results:
        cells = [result.row.label] + result.cells
        lines.append('| ' + ' | '.join(cells) + ' |')
    sections = ['\n'.join(lines)]
    for result in results:
        if result.details is None:
            continue
        sections.append(
            f'<details>\n<summary>{result.row.label}</summary>\n\n'
            f'{result.details.strip()}\n\n</details>'
        )
    return sections


def assemble(
    heading: str,
    marker: str,
    sections: List[str],
    requester: str,
    requester_notes: Optional[str] = None,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
) -> str:
    """
    Put a Testing comment together

    Parameters
    ----------
    heading : str
        The comment's heading, without the ``##``

    marker : str
        The hidden marker

    sections : list of str
        The generated sections, in order

    requester : str
        The GitHub user the comment is posted for

    requester_notes : str, optional
        The requester's notes from the manifest, which are repeated

    notes : str, optional
        The agent's or tester's notes

    agent : str, optional
        The agent posting the comment, which adds the signature

    Returns
    -------
    text : str
        The comment
    """
    parts = [f'## {heading}\n{marker}']
    parts.extend(section.strip('\n') for section in sections)
    note_lines = []
    if requester_notes:
        note_lines.append(f'From the requester: {requester_notes.strip()}')
    if notes:
        note_lines.append(notes.strip())
    if note_lines:
        parts.append('### Notes\n\n' + '\n\n'.join(note_lines))
    if agent:
        signature = SIGNATURE.format(agent=agent, user=requester)
        parts.append(f'---\n\n{signature}')
    return '\n\n'.join(parts) + '\n'


def write_comment(text: str, path: str) -> None:
    """
    Write a Testing comment to a file.  It is posted only with
    :py:func:`post_file`, once someone has read it.

    Parameters
    ----------
    text : str
        The comment

    path : str
        The file to write it to
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def post_file(repo: str, pull_request: int, path: str, prefix: str) -> str:
    """
    Post a Testing comment that a utility wrote, perhaps on another
    machine, from its file, once someone has read it

    The comment must have a marker for the pull request, so that only a
    comment the utility wrote is posted, and only on the PR it is for.

    Parameters
    ----------
    repo : str
        The repository of the pull request, such as ``E3SM-Project/Omega``

    pull_request : int
        The pull request to post it on

    path : str
        The comment's file

    prefix : str
        The utility's marker prefix

    Returns
    -------
    url : str
        The URL of the posted comment
    """
    with open(path, 'r', encoding='utf-8') as f:
        marker = parse_marker(f.read(), prefix)
    if marker is None:
        raise ValueError(
            f'{path} has no {prefix} marker, so it is not a comment that '
            f'the utility wrote.'
        )
    if marker.get('pr') != pull_request:
        raise ValueError(
            f'{path} is a comment for PR {marker.get("pr")}, not '
            f'{pull_request}.'
        )
    return github.post_comment(repo, pull_request, path)


def read_notes(filename: Optional[str]) -> Optional[str]:
    """The contents of a notes file, if one was given"""
    if filename is None:
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()


def read_required(path: str, what: str) -> str:
    """
    Read a file a job writes when it finishes

    Parameters
    ----------
    path : str
        The file

    what : str
        What its absence means, such as ``the PR suite has not finished``

    Returns
    -------
    text : str
        The file's contents
    """
    if not os.path.exists(path):
        raise ReportError(
            f'There is no {os.path.basename(path)} in '
            f'{os.path.dirname(path)}, so {what}'
        )
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def summarize_suite(
    work_dir: str, suite: str, baseline_work_dir: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Whether a suite passed, and its cell in the table

    A task that failed in the baseline has no baseline output to compare
    with, so a comparison that fails without a nonzero difference is not
    counted as a baseline difference or a failure of the task.

    Parameters
    ----------
    work_dir : str
        The suite's work directory

    suite : str
        The suite, such as ``omega_pr``

    baseline_work_dir : str, optional
        The baseline's work directory, if the suite was compared with one

    Returns
    -------
    passed : bool
        Whether every task passed

    cell : str
        Such as ``28 of 29 passed, 1 with baseline differences``
    """
    path = os.path.join(work_dir, f'{suite}_results.json')
    with open(path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    failed_in_baseline = _failed_tasks(baseline_work_dir, suite)
    tasks = results.get('tasks', [])
    passed = 0
    diffs = 0
    not_compared = 0
    for task in tasks:
        execution = task.get('execution')
        baseline = task.get('baseline')
        if baseline == 'fail' and task['path'] in failed_in_baseline:
            if not _differing_variables(task):
                baseline = None
                not_compared += 1
        if baseline == 'fail':
            diffs += 1
        if execution == 'pass' and baseline != 'fail':
            passed += 1
    cell = f'{passed} of {len(tasks)} passed'
    if diffs:
        cell = f'{cell}, {diffs} with baseline differences'
    if failed_in_baseline:
        cell = (
            f'{cell}, {_count(len(failed_in_baseline), "task")} failed in '
            f'the baseline'
        )
        if not_compared:
            cell = f'{cell} ({not_compared} not compared)'
    complete = results.get('complete', False)
    if not complete:
        cell = f'{cell} (the run did not finish)'
    return complete and passed == len(tasks), cell


def summarize_ctests(build_dir: str) -> Tuple[bool, str]:
    """
    Whether the CTests passed, and their cell in the table

    Parameters
    ----------
    build_dir : str
        The build the CTests ran in

    Returns
    -------
    passed : bool
        Whether every CTest passed

    cell : str
        Such as ``49 of 50 passed``
    """
    path = os.path.join(build_dir, 'ctests.log')
    counts: List[Tuple[str, str, str]] = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            counts = _CTEST_COUNTS.findall(f.read())
    if not counts:
        return False, 'no summary found'
    _, failed, total = counts[-1]
    passed = int(total) - int(failed)
    return int(failed) == 0, f'{passed} of {total} passed'


def _failed_tasks(work_dir: Optional[str], suite: str) -> List[str]:
    """The tasks that did not pass in a suite run, if it has results"""
    if work_dir is None:
        return []
    path = os.path.join(work_dir, f'{suite}_results.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except (OSError, ValueError):
        return []
    return [
        task['path']
        for task in results.get('tasks', [])
        if task.get('execution') != 'pass'
    ]


def _differing_variables(task: Dict[str, Any]) -> List[str]:
    """The variables with a nonzero difference from the baseline"""
    diffs = task.get('baseline_diffs') or {}
    return sorted(
        variable
        for variable, norms in diffs.items()
        if any(_is_nonzero(norm) for norm in norms.values())
    )


def _is_nonzero(norm):
    """Whether a difference norm, which may be NaN or infinite, is nonzero"""
    if isinstance(norm, str):
        return True
    return norm != 0


def _count(number, noun):
    """A count with its noun, such as ``1 task`` or ``3 tasks``"""
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def _list_tasks(by_task, compared_rows, row_count):
    """A line for each set of rows, with the tasks given for them"""
    lines = []
    for tasks, task_rows in _group_by_rows(by_task):
        names = ', '.join(f'`{task}`' for task in tasks)
        where = _name_rows(task_rows, compared_rows, row_count)
        lines.append(f'- {names}: on {where}')
    return '\n'.join(lines)


def _rows_by_task(compared, get_tasks):
    """
    Each task that ``get_tasks`` gives for a row's comparison, in the order
    first seen, with the rows it was given for
    """
    by_task: Dict[str, List[Row]] = {}
    for row, comparison in compared:
        for task in get_tasks(comparison):
            by_task.setdefault(task, []).append(row)
    return by_task


def _group_by_rows(by_task):
    """The tasks that share the same rows, in the order first seen"""
    groups: Dict[Tuple[str, ...], Tuple[List[str], List[Row]]] = {}
    for task, task_rows in by_task.items():
        key = tuple(row.name for row in task_rows)
        groups.setdefault(key, ([], task_rows))[0].append(task)
    return list(groups.values())


def _name_rows(task_rows, compared_rows, row_count):
    """
    The rows, as ``every row``, ``every Omega row`` or their labels, out
    of the rows that were compared, adding ``compared`` when there are
    rows that were not
    """
    suffix = '' if len(compared_rows) == row_count else ' compared'
    names = {row.name for row in task_rows}
    if len(compared_rows) > 1 and names == {row.name for row in compared_rows}:
        return f'every row{suffix}'
    models = {row.model for row in compared_rows}
    model = task_rows[0].model
    if len(models) > 1 and model is not None:
        of_model = {row.name for row in compared_rows if row.model == model}
        if len(of_model) > 1 and names == of_model:
            return f'every {MODEL_LABELS[model]} row{suffix}'
    return '; '.join(row.label for row in task_rows)
