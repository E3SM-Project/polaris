"""
The initiator's work: pin the commits to test in a branch with a manifest
"""

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import pr_test_git as git_tools
import pr_test_github as github
from pr_test_config import PrTestConfig
from pr_test_git import REF_PREFIX
from pr_test_manifest import (
    MANIFEST_FILENAME,
    POLARIS_SUBMODULE,
    TEMPLATE_ROWS,
    UPSTREAM,
    ExtraMerge,
    Manifest,
    Row,
)

#: the Polaris checkout this utility is part of
POLARIS_DIR = str(Path(__file__).resolve().parents[3])

#: where the default Polaris commit comes from, which needs no credentials
POLARIS_URL = 'https://github.com/E3SM-Project/polaris.git'

OMEGA_SUBMODULE = 'e3sm_submodules/Omega'


class InitError(Exception):
    """The commits to test could not be pinned"""


@dataclass
class InitResult:
    """
    What the initiator made

    Attributes
    ----------
    manifest : pr_test_manifest.Manifest
        The manifest

    manifest_commit : str
        The commit that adds the manifest on top of the test commit

    push_command : list of str
        The command that pushes both branches to the fork, run in the Omega
        clone

    pushed : bool
        Whether the branches were pushed

    prompt : str
        What to tell an agent testing on a machine itself, such as
        Frontier, which cannot be reached over ssh
    """

    manifest: Manifest
    manifest_commit: str
    push_command: List[str]
    pushed: bool
    prompt: str


def initiate(
    config: PrTestConfig,
    pull_request: int,
    polaris_ref: Optional[str] = None,
    baseline_polaris_ref: Optional[str] = None,
    baseline_ref: Optional[str] = None,
    reason: Optional[str] = None,
    merge_prs: Sequence[int] = (),
    baseline_merge_prs: Sequence[int] = (),
    rows: Optional[Sequence[Row]] = None,
    notes: Optional[str] = None,
    push: bool = False,
    force: bool = False,
    polaris_dir: str = POLARIS_DIR,
) -> InitResult:
    """
    Pin the commits to test in a branch with a manifest

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The settings

    pull_request : int
        The number of the Omega pull request to test

    polaris_ref : str, optional
        The Polaris branch the pull request is tested with, on the
        requester's Polaris fork, the current ``main`` of
        E3SM-Project/polaris by default

    baseline_polaris_ref : str, optional
        The Polaris branch the baseline runs with, on the same fork, whose
        Omega submodule is the baseline, ``polaris_ref`` by default

    baseline_ref : str, optional
        An Omega branch or commit to use as the baseline instead of the
        submodule

    reason : str, optional
        Why ``baseline_ref`` is used, required with it

    merge_prs : sequence of int, optional
        Other Omega pull requests to merge into the test commit

    baseline_merge_prs : sequence of int, optional
        Other Omega pull requests to merge into the baseline commit

    rows : sequence of pr_test_manifest.Row, optional
        The rows to test, the Omega PR template's by default

    notes : str, optional
        Notes for the requester, repeated in reports

    push : bool, optional
        Whether to push the branches to the requester's fork

    force : bool, optional
        Whether to overwrite branches of the same name on the fork

    polaris_dir : str, optional
        The Polaris checkout to read the submodule from

    Returns
    -------
    result : pr_test_init.InitResult
        What the initiator made
    """
    if baseline_ref is not None and not reason:
        raise InitError('A baseline other than the submodule needs --reason.')
    if push and config.fork is None:
        raise InitError('Pushing needs "fork" in the config file.')
    if baseline_polaris_ref is not None and polaris_ref is None:
        raise InitError('--baseline-polaris-ref needs --polaris-ref.')
    if polaris_ref is not None and config.polaris_fork is None:
        raise InitError(
            '--polaris-ref needs "polaris_fork" in the config file, so the '
            'testers know where to fetch it.'
        )

    pr = github.get_pull_request(pull_request)
    if pr['state'] != 'OPEN':
        raise InitError(
            f'{UPSTREAM}#{pull_request} is {pr["state"].lower()}, not open.'
        )
    requester = github.get_requester(config.fork)

    polaris_commit = _resolve_polaris(polaris_dir, polaris_ref)
    baseline_polaris_commit = polaris_commit
    if baseline_polaris_ref is not None:
        baseline_polaris_commit = git_tools.rev_parse(
            polaris_dir, baseline_polaris_ref
        )
    pin = git_tools.submodule_pin(
        polaris_dir, baseline_polaris_commit, OMEGA_SUBMODULE
    )

    repo = config.omega_repo
    base_branch = pr['baseRefName']
    all_prs = sorted({pull_request, *merge_prs, *baseline_merge_prs})
    heads = _fetch_omega(repo, base_branch, all_prs)
    pr_head = heads[pull_request]
    if pr_head != pr['headRefOid']:
        raise InitError(
            f'{UPSTREAM}#{pull_request} moved to {pr_head[:12]} while this '
            f'ran.  Run init again.'
        )
    base_head = git_tools.rev_parse(repo, f'{REF_PREFIX}/{base_branch}')

    if baseline_ref is None:
        baseline_start = _fetch_commit(repo, pin)
        baseline_source = POLARIS_SUBMODULE
    else:
        baseline_start = _resolve_omega(repo, baseline_ref, base_branch)
        baseline_source = baseline_ref

    work_dir = os.path.join(config.work_base, 'omega', f'init-{pull_request}')
    test_commit = _make_merges(
        repo,
        os.path.join(work_dir, 'test'),
        base_head,
        [(pull_request, pr_head, f'into {base_branch} ({base_head[:10]})')]
        + [(number, heads[number], 'for testing') for number in merge_prs],
    )
    baseline_commit = baseline_start
    if baseline_merge_prs:
        baseline_commit = _make_merges(
            repo,
            os.path.join(work_dir, 'baseline'),
            baseline_start,
            [
                (number, heads[number], 'for testing')
                for number in baseline_merge_prs
            ],
        )

    extra_merges = []
    for number in sorted({*merge_prs, *baseline_merge_prs}):
        sides = [
            side
            for side, numbers in [
                ('test', merge_prs),
                ('baseline', baseline_merge_prs),
            ]
            if number in numbers
        ]
        extra_merges.append(ExtraMerge(number, heads[number], sides))

    manifest = Manifest(
        requester=requester,
        pull_request=pull_request,
        pr_head=pr_head,
        base_branch=base_branch,
        base_head=base_head,
        test_commit=test_commit,
        baseline_commit=baseline_commit,
        baseline_source=baseline_source,
        baseline_reason=reason,
        polaris_commit=polaris_commit,
        baseline_polaris_commit=baseline_polaris_commit,
        extra_merges=extra_merges,
        rows=list(TEMPLATE_ROWS if rows is None else rows),
        notes=notes,
    )
    manifest_commit = _commit_manifest(
        repo, os.path.join(work_dir, 'test'), manifest
    )
    git_tools.git(
        ['update-ref', f'{REF_PREFIX}/{manifest.branch}', manifest_commit],
        repo,
    )
    git_tools.git(
        [
            'update-ref',
            f'{REF_PREFIX}/{manifest.baseline_branch}',
            baseline_commit,
        ],
        repo,
    )
    _remove_scratch(repo, work_dir)

    fork = config.fork or '<your fork>'
    push_command = ['git', 'push']
    if force:
        push_command.append('--force')
    push_command.extend(
        [
            fork,
            f'{manifest_commit}:refs/heads/{manifest.branch}',
            f'{baseline_commit}:refs/heads/{manifest.baseline_branch}',
        ]
    )
    if push:
        subprocess.run(push_command, cwd=repo, check=True)

    prompt = get_prompt(
        manifest, fork, config.polaris_fork, polaris_ref, baseline_polaris_ref
    )
    return InitResult(manifest, manifest_commit, push_command, push, prompt)


def get_prompt(
    manifest: Manifest,
    fork: str,
    polaris_fork: Optional[str] = None,
    polaris_ref: Optional[str] = None,
    baseline_polaris_ref: Optional[str] = None,
) -> str:
    """
    The prompt for an agent testing on a machine itself, which is the
    whole handoff and the same on every machine.  Each tester works out its
    own rows.  The utility's AGENTS.md
    shows the template; keep the two the same.

    Parameters
    ----------
    manifest : pr_test_manifest.Manifest
        The manifest

    fork : str
        The requester's fork with the test branch

    polaris_fork : str, optional
        The requester's Polaris fork, needed with ``polaris_ref``

    polaris_ref : str, optional
        The Polaris branch the pull request is tested with, if not ``main``

    baseline_polaris_ref : str, optional
        The Polaris branch the baseline runs with, if not ``polaris_ref``

    Returns
    -------
    prompt : str
        The prompt
    """
    prompt = (
        f'Test Omega PR {manifest.pull_request} from branch '
        f'{manifest.branch} on {fork}, following '
        f'utils/omega/pr_testing/AGENTS.md.'
    )
    if polaris_ref is None:
        return prompt
    if baseline_polaris_ref is None or (
        manifest.baseline_polaris_commit == manifest.polaris_commit
    ):
        return (
            f'{prompt}  The PR and baseline run from a Polaris checkout of '
            f'{polaris_ref} on {polaris_fork}.'
        )
    return (
        f'{prompt}  The PR runs from a Polaris checkout of {polaris_ref} on '
        f'{polaris_fork}, and the baseline from a second checkout of '
        f'{baseline_polaris_ref} on the same fork.'
    )


def format_result(result: InitResult, repo: str) -> str:
    """The summary init prints"""
    manifest = result.manifest
    lines = [
        f'Test commit:     {manifest.test_commit}',
        f'Baseline commit: {manifest.baseline_commit} '
        f'({manifest.baseline_source})',
        f'Polaris commit:  {manifest.polaris_commit}',
    ]
    if manifest.baseline_polaris_commit != manifest.polaris_commit:
        lines.append(f'Baseline Polaris: {manifest.baseline_polaris_commit}')
    lines += [
        f'Manifest commit: {result.manifest_commit}',
        '',
    ]
    command = shlex.join(result.push_command)
    if result.pushed:
        lines.append(
            f'Pushed {manifest.branch} and {manifest.baseline_branch}.'
        )
    else:
        lines.extend(
            [
                "Nothing was pushed.  With the requester's permission, run:",
                f'  cd {repo} && {command}',
            ]
        )
    lines.extend(
        [
            '',
            'Prompt for an agent testing on a machine itself, such as '
            'Frontier:',
            '',
        ]
    )
    lines.append(result.prompt)
    return '\n'.join(lines)


def _resolve_polaris(polaris_dir, polaris_ref):
    if polaris_ref is not None:
        return git_tools.rev_parse(polaris_dir, polaris_ref)
    local_ref = f'{REF_PREFIX}/polaris-main'
    git_tools.fetch(polaris_dir, POLARIS_URL, [f'refs/heads/main:{local_ref}'])
    return git_tools.rev_parse(polaris_dir, local_ref)


def _fetch_omega(repo, base_branch, pull_requests):
    """Fetch the base branch and the pull requests, returning their heads"""
    refspecs = [f'refs/heads/{base_branch}:{REF_PREFIX}/{base_branch}']
    refspecs.extend(
        f'refs/pull/{number}/head:{REF_PREFIX}/pr-{number}'
        for number in pull_requests
    )
    git_tools.fetch(repo, git_tools.UPSTREAM_URL, refspecs)
    return {
        number: git_tools.rev_parse(repo, f'{REF_PREFIX}/pr-{number}')
        for number in pull_requests
    }


def _fetch_commit(repo, sha):
    """Make sure the Omega clone has a commit, fetching it if needed"""
    if not git_tools.has_commit(repo, sha):
        git_tools.fetch(
            repo, git_tools.UPSTREAM_URL, [f'{sha}:{REF_PREFIX}/pin']
        )
    return git_tools.rev_parse(repo, sha)


def _resolve_omega(repo, ref, base_branch):
    """The commit of an Omega branch or commit given as the baseline"""
    if ref == base_branch:
        return git_tools.rev_parse(repo, f'{REF_PREFIX}/{base_branch}')
    try:
        git_tools.fetch(
            repo,
            git_tools.UPSTREAM_URL,
            [f'refs/heads/{ref}:{REF_PREFIX}/baseline-ref'],
        )
        return git_tools.rev_parse(repo, f'{REF_PREFIX}/baseline-ref')
    except git_tools.GitError:
        return _fetch_commit(repo, ref)


def _make_merges(repo, worktree, start, merges):
    """
    Merge pull request heads into a start commit in a scratch worktree,
    returning the result
    """
    if os.path.exists(worktree):
        git_tools.remove_worktree(repo, worktree)
    git_tools.add_worktree(repo, start, worktree)
    for number, sha, where in merges:
        message = f'Test merge of {UPSTREAM}#{number} ({sha[:10]}) {where}'
        conflicts = git_tools.merge(worktree, sha, message)
        if conflicts is not None:
            raise InitError(
                f'{UPSTREAM}#{number} does not merge cleanly:\n{conflicts}\n'
                f'Ask its author to update the branch.'
            )
    return git_tools.rev_parse(worktree, 'HEAD')


def _commit_manifest(repo, worktree, manifest):
    path = os.path.join(worktree, MANIFEST_FILENAME)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(manifest.to_yaml())
    git_tools.git(['add', MANIFEST_FILENAME], worktree)
    git_tools.git(
        [
            'commit',
            '--quiet',
            '--no-verify',
            '-m',
            f'Add the manifest for testing {UPSTREAM}#{manifest.pull_request}',
            '-m',
            'Temporary.  Testers build the parent of this commit.',
        ],
        worktree,
    )
    return git_tools.rev_parse(worktree, 'HEAD')


def _remove_scratch(repo, work_dir):
    for side in ['test', 'baseline']:
        worktree = os.path.join(work_dir, side)
        if os.path.exists(worktree):
            git_tools.remove_worktree(repo, worktree)
    if os.path.isdir(work_dir) and not os.listdir(work_dir):
        os.rmdir(work_dir)
