"""
Cleaning up after Omega PR testing: ``work_base`` on a machine, and the
test branches on the requester's fork
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

import pr_test_cleanup
import pr_test_git as git_tools
from omega_pr_manifest import UPSTREAM
from pr_test_config import PrTestConfig
from pr_test_github import get_pull_request

#: the test branches ``init`` pushes to the requester's fork
BRANCH_PATTERN = 'omega-pr-test/*'

_BRANCH = re.compile(r'^omega-pr-test/(\d+)-[0-9a-f]{7}(-baseline)?$')


@dataclass
class TestBranch:
    """
    A test branch on the requester's fork

    Attributes
    ----------
    name : str
        The branch

    pull_request : int
        The Omega PR it tests

    state : str
        The PR's state: ``OPEN``, ``MERGED`` or ``CLOSED``
    """

    name: str
    pull_request: int
    state: str


def run_cleanup(
    config: PrTestConfig,
    cited_file: Optional[str],
    keep_days: float,
    delete: bool,
) -> str:
    """
    List, or remove, the old runs, baselines and worktrees in ``work_base``

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The settings

    cited_file : str, optional
        The paths open pull requests cite, from the cited command,
        ``cited_paths.txt`` in ``work_base`` by default

    keep_days : float
        How many days back a modification keeps an entry

    delete : bool
        Whether to remove what is not kept, rather than only list it

    Returns
    -------
    text : str
        What is kept and why, and what was (or would be) removed
    """
    if cited_file is None:
        cited_file = os.path.join(
            config.work_base, pr_test_cleanup.CITED_FILENAME
        )
    cited = pr_test_cleanup.read_citations(cited_file)
    entries = pr_test_cleanup.plan_cleanup(
        config.work_base,
        cited,
        keep_days,
        _polaris_hashes(config),
    )
    if delete:
        pr_test_cleanup.remove(entries)
    return pr_test_cleanup.format_plan(entries, config.work_base, delete)


def find_test_branches(repo: str, fork: str) -> List[TestBranch]:
    """
    The test branches on the requester's fork, with their PRs' states

    Parameters
    ----------
    repo : str
        The Omega clone to query the fork from

    fork : str
        The URL of the requester's fork

    Returns
    -------
    branches : list of omega_pr_cleanup.TestBranch
        The test branches, sorted
    """
    output = git_tools.git(
        ['ls-remote', '--heads', fork, f'refs/heads/{BRANCH_PATTERN}'], repo
    )
    states = {}
    branches = []
    for line in output.splitlines():
        name = line.split()[1].removeprefix('refs/heads/')
        match = _BRANCH.match(name)
        if match is None:
            continue
        number = int(match.group(1))
        if number not in states:
            states[number] = get_pull_request(UPSTREAM, number)['state']
        branches.append(TestBranch(name, number, states[number]))
    return sorted(branches, key=lambda branch: branch.name)


def delete_test_branches(
    repo: str, fork: str, branches: List[TestBranch]
) -> None:
    """
    Delete test branches from the requester's fork

    Parameters
    ----------
    repo : str
        The Omega clone to push from

    fork : str
        The URL of the requester's fork

    branches : list of omega_pr_cleanup.TestBranch
        The branches to delete
    """
    if branches:
        names = [branch.name for branch in branches]
        git_tools.git(['push', '--quiet', fork, '--delete'] + names, repo)


def format_branches(
    branches: List[TestBranch], fork: str, deleted: bool
) -> str:
    """
    List the test branches whose PRs are merged or closed, which are
    (or would be) deleted, and those kept for open PRs

    Parameters
    ----------
    branches : list of omega_pr_cleanup.TestBranch
        The test branches

    fork : str
        The URL of the requester's fork

    deleted : bool
        Whether the branches of merged and closed PRs have been deleted

    Returns
    -------
    text : str
        The list
    """
    verb = 'Deleted' if deleted else 'Would delete'
    old = [branch for branch in branches if branch.state != 'OPEN']
    kept = [branch for branch in branches if branch.state == 'OPEN']
    lines = [f'Test branches on {fork}:', f'{verb} ({len(old)}):']
    lines.extend(
        f'  {branch.name}  (#{branch.pull_request} {branch.state.lower()})'
        for branch in old
    )
    if not old:
        lines.append('  nothing')
    lines.append(f'Kept for open PRs ({len(kept)}):')
    lines.extend(f'  {branch.name}' for branch in kept)
    if not kept:
        lines.append('  nothing')
    return '\n'.join(lines)


def _polaris_hashes(config):
    """The Polaris commits whose baselines may still be reused: this
    checkout's and that of the deployed checkout of main"""
    hashes = [git_tools.rev_parse(git_tools.POLARIS_DIR, 'HEAD')]
    if config.polaris_main is not None and os.path.isdir(config.polaris_main):
        hashes.append(git_tools.rev_parse(config.polaris_main, 'HEAD'))
    return hashes
