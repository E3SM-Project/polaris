"""
Which rows of an Omega PR have Testing comments from the utility, and
whether they are for the PR's current head
"""

from typing import Any, Dict, List, Optional

import pr_test_github as github
import pr_test_report as report
from pr_test_manifest import TEMPLATE_ROWS, Manifest, get_machine_rows

from polaris.machines import discover_machine


def run_status(pull_request: int, manifest: Optional[Manifest] = None) -> str:
    """
    Summarize the Testing comments on an Omega PR

    Parameters
    ----------
    pull_request : int
        The number of the Omega PR

    manifest : pr_test_manifest.Manifest, optional
        The manifest whose rows to list, the Omega PR template's by default.
        With a manifest, the rows a tester on this machine runs are named
        as well.

    Returns
    -------
    text : str
        One line per row
    """
    head = github.get_pull_request(pull_request)['headRefOid']
    markers = [
        marker
        for marker in (
            report.parse_marker(body)
            for body in github.get_comment_bodies(pull_request)
        )
        if marker is not None and marker.get('pr') == pull_request
    ]
    # lint is only posted when it did not come from CI, so it is listed only
    # if it was
    rows = [row.name for row in (manifest.rows if manifest else TEMPLATE_ROWS)]
    text = format_status(rows, markers, head)
    if manifest is not None:
        text = f'{text}\n\n{format_machine_rows(manifest)}'
    return text


def format_machine_rows(manifest: Manifest) -> str:
    """The line naming the rows a tester on this machine runs"""
    machine = discover_machine(quiet=True)
    if machine is None:
        return 'This machine is not one Polaris recognizes.'
    rows = get_machine_rows(manifest.rows, machine)
    if not rows:
        return f'No rows to test on this machine ({machine}).'
    names = ', '.join(row.name for row in rows)
    return f'Rows to test on this machine ({machine}): {names}'


def format_status(
    rows: List[str], markers: List[Dict[str, Any]], head: str
) -> str:
    """
    One line per row with its latest result

    Parameters
    ----------
    rows : list of str
        The rows to list, in order; rows that only appear in markers follow

    markers : list of dict
        The markers of the PR's Testing comments, oldest first

    head : str
        The PR's current head

    Returns
    -------
    text : str
        The table
    """
    latest: Dict[str, Dict[str, Any]] = {}
    for marker in markers:
        latest[marker.get('row', '?')] = marker
    names = list(rows) + [row for row in latest if row not in rows]

    width = max(len(name) for name in names)
    lines = [f'{"row".ljust(width)}  result   PR head     test commit']
    for name in names:
        if name not in latest:
            lines.append(f'{name.ljust(width)}  -')
            continue
        marker = latest[name]
        if marker.get('status') == 'not-run':
            result = 'not run'
        else:
            result = str(marker.get('result', '?'))
        pr_head = str(marker.get('pr_head', ''))
        stale = '' if pr_head == head else '  (stale: the PR has moved)'
        warnings = marker.get('new_warnings')
        extra = f'  {warnings} new warnings' if warnings else ''
        lines.append(
            f'{name.ljust(width)}  {result.ljust(7)}  {pr_head[:10]}  '
            f'{str(marker.get("test", ""))[:10]}{extra}{stale}'
        )
    return '\n'.join(lines)
