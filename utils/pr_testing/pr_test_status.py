"""
Which rows of a PR have Testing comments from a utility, whether they are
for the PR's current head, and which rows each machine tests
"""

from typing import Any, Dict, List, Optional

import pr_test_github as github
import pr_test_report as report
from pr_test_config import PrTestConfig
from pr_test_rows import Row, get_machine_rows, group_login_rows

from polaris.machines import discover_machine


def get_row_entries(
    repo: str, pull_request: int, prefix: str
) -> List[Dict[str, Any]]:
    """
    Each row the utility's Testing comments on a PR report on

    Parameters
    ----------
    repo : str
        The repository of the pull request, such as ``E3SM-Project/Omega``

    pull_request : int
        The pull request

    prefix : str
        The utility's marker prefix

    Returns
    -------
    entries : list of dict
        A dict for each row of each comment, oldest first, with its
        ``row``, ``status`` and ``result`` and its comment's ``pr_head``
    """
    entries = []
    for body in github.get_comment_bodies(repo, pull_request):
        marker = report.parse_marker(body, prefix)
        if marker is None or marker.get('pr') != pull_request:
            continue
        entries.extend(report.get_marker_rows(marker))
    return entries


def format_status(
    rows: List[str], entries: List[Dict[str, Any]], head: str
) -> str:
    """
    One line per row with its latest result

    Parameters
    ----------
    rows : list of str
        The rows to list, in order; rows that only appear in markers follow

    entries : list of dict
        The rows the PR's Testing comments report on, oldest first

    head : str
        The PR's current head

    Returns
    -------
    text : str
        The table
    """
    latest: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        latest[entry.get('row', '?')] = entry
    names = list(rows) + [row for row in latest if row not in rows]

    width = max(len(name) for name in names)
    lines = [f'{"row".ljust(width)}  result   PR head     test commit']
    for name in names:
        if name not in latest:
            lines.append(f'{name.ljust(width)}  -')
            continue
        entry = latest[name]
        if entry.get('status') == 'not-run':
            result = 'not run'
        else:
            result = str(entry.get('result', '?'))
        pr_head = str(entry.get('pr_head', ''))
        stale = '' if pr_head == head else '  (stale: the PR has moved)'
        warnings = entry.get('new_warnings')
        extra = f'  {warnings} new warnings' if warnings else ''
        lines.append(
            f'{name.ljust(width)}  {result.ljust(7)}  {pr_head[:10]}  '
            f'{str(entry.get("test", ""))[:10]}{extra}{stale}'
        )
    return '\n'.join(lines)


def format_machine_rows(
    rows: List[Row], config: Optional[PrTestConfig] = None
) -> str:
    """
    The line naming the rows a tester on this machine runs or, off the
    machines, the rows to test from each machine's login nodes, with how
    to reach each machine if the settings are given

    Parameters
    ----------
    rows : list of pr_test_rows.Row
        The rows to test

    config : pr_test_config.PrTestConfig, optional
        The settings, whose ``[machines]`` entries are named with each
        machine's rows off the machines

    Returns
    -------
    text : str
        The rows to test
    """
    machine = discover_machine(quiet=True)
    machine_rows = []
    if machine is not None:
        machine_rows = get_machine_rows(rows, machine)
    if machine_rows:
        names = ', '.join(row.name for row in machine_rows)
        return f'Rows to test on this machine ({machine}): {names}'
    lines = ["Rows to test from each machine's login nodes:"]
    for machines, login_rows in group_login_rows(rows):
        names = ', '.join(row.name for row in login_rows)
        line = f'  {" and ".join(machines)}: {names}'
        if config is not None:
            line = f'{line} {_format_remote(config, machines[0])}'
        lines.append(line)
    return '\n'.join(lines)


def _format_remote(config, machine):
    """How the settings say to reach a machine"""
    remote = config.find_machine(machine)
    if remote is None:
        return '(no [machines] line, so an agent on the machine tests it)'
    return f'(ssh {remote.host}, Polaris in {remote.polaris_dir})'
