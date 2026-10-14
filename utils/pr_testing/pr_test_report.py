"""
The pieces every Testing comment the PR testing utilities write has in
common: a hidden marker, a table with a line for each row and the files
Polaris and CTest wrote, the notes, the signature and posting
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pr_test_github as github
from pr_test_rows import Row

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


def deliver(
    text: str, path: str, repo: str, pull_request: int, post: bool
) -> Optional[str]:
    """
    Write a Testing comment to a file and post it if asked

    Parameters
    ----------
    text : str
        The comment

    path : str
        The file to write it to

    repo : str
        The repository of the pull request, such as ``E3SM-Project/Omega``

    pull_request : int
        The pull request to post it on

    post : bool
        Whether to post it

    Returns
    -------
    url : str, optional
        The URL of the posted comment, or ``None`` if it was not posted
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    if not post:
        return None
    return github.post_comment(repo, pull_request, path)


def post_file(repo: str, pull_request: int, path: str, prefix: str) -> str:
    """
    Post a Testing comment that a utility wrote, perhaps on another
    machine, from its file

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


def summarize_suite(work_dir: str, suite: str) -> Tuple[bool, str]:
    """
    Whether a suite passed, and its cell in the table

    Parameters
    ----------
    work_dir : str
        The suite's work directory

    suite : str
        The suite, such as ``omega_pr``

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
    summary = results['summary']
    total = summary['total']
    passed = summary['passed']
    diffs = [
        task['path']
        for task in results.get('tasks', [])
        if task.get('baseline') == 'fail'
    ]
    cell = f'{passed} of {total} passed'
    if diffs:
        cell = f'{cell}, {len(diffs)} with baseline differences'
    complete = results.get('complete', False)
    if not complete:
        cell = f'{cell} (the run did not finish)'
    return complete and passed == total, cell


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
