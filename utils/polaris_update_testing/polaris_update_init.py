"""
The initiator's work: pin the Polaris pull request's head, what it pins, an
optional baseline and the rows in a branch with a manifest
"""

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pr_test_git as git_tools
import pr_test_github as github
from polaris_update_manifest import (
    MANIFEST_FILENAME,
    UPSTREAM,
    Manifest,
    ManifestError,
    OmegaMerge,
    fetch_manifest,
    read_rows,
    read_side,
)
from pr_test_config import PrTestConfig
from pr_test_git import POLARIS_DIR, REF_PREFIX

#: the baseline that always means E3SM-Project/polaris's main, never the
#: requester's fork's, which is not kept up to date
POLARIS_MAIN = 'main'


class InitError(Exception):
    """The commits to test could not be pinned"""


@dataclass
class InitResult:
    """
    What the initiator made

    Attributes
    ----------
    manifest : polaris_update_manifest.Manifest
        The manifest

    manifest_commit : str
        The commit that adds the manifest on top of the PR's head

    push_commands : list of tuple
        The directory to run each push in and the command: the test branch
        to the Polaris fork, and any Omega merge to the E3SM fork

    pushed : bool
        Whether the branches were pushed

    prompt : str
        What to tell an agent testing on a machine itself, such as
        Frontier, which cannot be reached over ssh

    existing : bool
        Whether the fork already had the test branch with an equivalent
        manifest, which is then the one returned
    """

    manifest: Manifest
    manifest_commit: str
    push_commands: List[Tuple[str, List[str]]]
    pushed: bool
    prompt: str
    existing: bool = False


def initiate(
    config: PrTestConfig,
    pull_request: int,
    baseline_ref: Optional[str] = None,
    row_names: Optional[Sequence[str]] = None,
    merge_omega_prs: Sequence[int] = (),
    notes: Optional[str] = None,
    push: bool = False,
    force: bool = False,
    polaris_dir: str = POLARIS_DIR,
) -> InitResult:
    """
    Pin what to test in a branch with a manifest

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The settings

    pull_request : int
        The number of the Polaris pull request to test

    baseline_ref : str, optional
        The Polaris commit to compare against, ``main`` for the current main
        of E3SM-Project/polaris.  Without it, the rows run without a
        baseline.

    row_names : sequence of str, optional
        The rows to test, as ``<machine>/<compiler>/<model>``, every row the
        PR supports by default

    merge_omega_prs : sequence of int, optional
        Omega PRs to merge into the Omega the PR pins, such as a fix still
        in review.  The merge is pushed to the requester's E3SM fork, and
        the PR's Omega rows build it.

    notes : str, optional
        Notes for the requester, repeated in reports

    push : bool, optional
        Whether to push the branches to the requester's forks

    force : bool, optional
        Whether to overwrite a branch of the same name on the fork

    polaris_dir : str, optional
        The Polaris checkout to fetch into and make the branch in

    Returns
    -------
    result : polaris_update_init.InitResult
        What the initiator made
    """
    fork = config.polaris_fork
    if push and fork is None:
        raise InitError('Pushing needs "polaris_fork" in the config file.')
    if merge_omega_prs and config.fork is None:
        raise InitError(
            '--merge-omega-pr needs "fork" in the config file, the E3SM fork '
            'the merge is pushed to.'
        )

    pr = github.get_pull_request(UPSTREAM, pull_request)
    if pr['state'] != 'OPEN':
        raise InitError(
            f'{UPSTREAM}#{pull_request} is {pr["state"].lower()}, not open.'
        )
    requester = github.get_requester(fork)

    head_ref = f'{REF_PREFIX}/polaris-pr-{pull_request}'
    main_ref = f'{REF_PREFIX}/polaris-main'
    git_tools.fetch(
        polaris_dir,
        git_tools.POLARIS_URL,
        [
            f'refs/pull/{pull_request}/head:{head_ref}',
            f'refs/heads/main:{main_ref}',
        ],
    )
    pr_head = git_tools.rev_parse(polaris_dir, head_ref)
    if pr_head != pr['headRefOid']:
        raise InitError(
            f'{UPSTREAM}#{pull_request} moved to {pr_head[:12]} while this '
            f'ran.  Run init again.'
        )

    baseline = None
    if baseline_ref is not None:
        if baseline_ref == POLARIS_MAIN:
            baseline_commit = git_tools.rev_parse(polaris_dir, main_ref)
        else:
            baseline_commit = git_tools.rev_parse(polaris_dir, baseline_ref)
        if git_tools.is_ancestor(polaris_dir, pr_head, baseline_commit):
            raise InitError(
                f'The baseline {baseline_ref} ({baseline_commit[:12]}) '
                f'contains the PR head, so it would not show what the PR '
                f'changes.'
            )
        baseline = read_side(polaris_dir, baseline_commit)

    rows = read_rows(polaris_dir, pr_head)
    if row_names is not None:
        by_name = {row.name: row for row in rows}
        unknown = [name for name in row_names if name not in by_name]
        if unknown:
            raise InitError(
                f'The PR does not support {", ".join(unknown)}; its rows '
                f'are {", ".join(by_name)}.'
            )
        rows = [by_name[name] for name in row_names]

    manifest = Manifest(
        requester=requester,
        pull_request=pull_request,
        test=read_side(polaris_dir, pr_head),
        baseline=baseline,
        rows=rows,
        notes=notes,
        baseline_is_main=baseline_ref in (None, POLARIS_MAIN),
    )
    if merge_omega_prs:
        manifest.omega_merge = _merge_omega(
            config,
            manifest.test.omega_commit,
            merge_omega_prs,
            f'{manifest.branch}-omega',
            pull_request,
        )

    work_dir = os.path.join(
        config.work_base, 'polaris', f'init-{pull_request}'
    )
    manifest_commit = _commit_manifest(polaris_dir, work_dir, manifest)
    git_tools.git(
        ['update-ref', f'{REF_PREFIX}/{manifest.branch}', manifest_commit],
        polaris_dir,
    )

    shown_fork = fork or '<your Polaris fork>'
    # Testers may already be using the fork's test branch.  Replacing it with
    # an equivalent manifest only changes the commit hash under them.
    existing = _find_equivalent(polaris_dir, config.omega_repo, fork, manifest)
    if existing is not None:
        existing_manifest, existing_commit = existing
        return InitResult(
            existing_manifest,
            existing_commit,
            push_commands=[],
            pushed=False,
            prompt=get_prompt(existing_manifest, shown_fork),
            existing=True,
        )

    force_flag = ['--force'] if force else []
    push_commands = [
        (
            polaris_dir,
            ['git', 'push']
            + force_flag
            + [shown_fork, f'{manifest_commit}:refs/heads/{manifest.branch}'],
        )
    ]
    merge = manifest.omega_merge
    if merge is not None:
        push_commands.append(
            (
                config.omega_repo,
                ['git', 'push']
                + force_flag
                + [merge.fork, f'{merge.commit}:refs/heads/{merge.branch}'],
            )
        )
    if push:
        # the Omega merge goes first, so the manifest never names a branch
        # that is not there
        for cwd, command in reversed(push_commands):
            subprocess.run(command, cwd=cwd, check=True)
    return InitResult(
        manifest,
        manifest_commit,
        push_commands,
        push,
        get_prompt(manifest, shown_fork),
    )


def get_prompt(manifest: Manifest, fork: str) -> str:
    """
    The prompt for an agent testing on a machine itself, which is the
    whole handoff and the same on every machine.  The utility's AGENTS.md
    shows the template; keep the two the same.

    Parameters
    ----------
    manifest : polaris_update_manifest.Manifest
        The manifest

    fork : str
        The requester's Polaris fork with the test branch

    Returns
    -------
    prompt : str
        The prompt
    """
    prompt = (
        f'Test Polaris PR {manifest.pull_request} from branch '
        f'{manifest.branch} on {fork}, following '
        f'utils/polaris_update_testing/AGENTS.md.'
    )
    if manifest.baseline is not None and manifest.baseline_is_main:
        prompt = (
            f'{prompt}  The baseline runs from a second checkout of main on '
            f'E3SM-Project/polaris.'
        )
    elif manifest.baseline is not None:
        prompt = (
            f'{prompt}  The baseline runs from a second checkout of '
            f'E3SM-Project/polaris at '
            f'{manifest.baseline.polaris_commit[:12]}, not main.'
        )
    return prompt


def format_result(result: InitResult, polaris_dir: str) -> str:
    """The summary init prints"""
    manifest = result.manifest
    test = manifest.test
    lines = [
        f'PR head:   {test.polaris_commit} (Polaris {test.polaris_version})',
        f'           Omega {test.omega_commit}, E3SM {test.e3sm_commit}',
    ]
    if manifest.baseline is None:
        lines.append('Baseline:  none')
    else:
        baseline = manifest.baseline
        lines += [
            f'Baseline:  {baseline.polaris_commit} '
            f'(Polaris {baseline.polaris_version})',
            f'           Omega {baseline.omega_commit}, E3SM '
            f'{baseline.e3sm_commit}',
        ]
    if manifest.omega_merge is not None:
        merged = ', '.join(
            f'E3SM-Project/Omega#{number}'
            for number in manifest.omega_merge.pull_requests
        )
        lines.append(
            f'Omega built: {manifest.omega_merge.commit}, with {merged} '
            f'merged in'
        )
    lines.append(f'Rows:      {", ".join(row.name for row in manifest.rows)}')
    lines += [f'Manifest commit: {result.manifest_commit}', '']
    if result.existing:
        lines.append(
            f'The fork already has {manifest.branch} with an equivalent '
            f'manifest.  Nothing needs pushing, and testers use it as it is.'
        )
    elif result.pushed:
        lines.append(f'Pushed {manifest.branch}.')
    else:
        lines.append(
            "Nothing was pushed.  With the requester's permission, run:"
        )
        lines.extend(
            f'  cd {cwd} && {shlex.join(command)}'
            for cwd, command in reversed(result.push_commands)
        )
    lines += [
        '',
        'Prompt for an agent testing on a machine itself, such as Frontier:',
        '',
        result.prompt,
    ]
    return '\n'.join(lines)


def _commit_manifest(polaris_dir, work_dir, manifest):
    """Commit the manifest on top of the PR's head in a scratch worktree"""
    worktree = os.path.join(work_dir, 'manifest')
    if os.path.exists(worktree):
        git_tools.remove_worktree(polaris_dir, worktree)
    git_tools.add_worktree(polaris_dir, manifest.pr_head, worktree)
    try:
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
                f'Add the manifest for testing '
                f'{UPSTREAM}#{manifest.pull_request}',
                '-m',
                'Temporary.  Testers test the parent of this commit.',
            ],
            worktree,
        )
        return git_tools.rev_parse(worktree, 'HEAD')
    finally:
        git_tools.remove_worktree(polaris_dir, worktree)
        if os.path.isdir(work_dir) and not os.listdir(work_dir):
            os.rmdir(work_dir)


def _merge_omega(
    config: PrTestConfig,
    pin: str,
    numbers: Sequence[int],
    branch: str,
    pull_request: int,
) -> OmegaMerge:
    """Merge Omega PRs into the Omega the Polaris PR pins"""
    repo = config.omega_repo
    assert config.fork is not None
    git_tools.fetch(
        repo,
        git_tools.OMEGA_URL,
        [
            f'refs/pull/{number}/head:{REF_PREFIX}/pr-{number}'
            for number in numbers
        ],
    )
    heads: Dict[int, str] = {
        number: git_tools.rev_parse(repo, f'{REF_PREFIX}/pr-{number}')
        for number in numbers
    }
    if not git_tools.has_commit(repo, pin):
        git_tools.fetch(repo, git_tools.OMEGA_URL, [f'{pin}:{REF_PREFIX}/pin'])
    for number, head in heads.items():
        if git_tools.is_ancestor(repo, head, pin):
            raise InitError(
                f'E3SM-Project/Omega#{number} is already in the Omega the PR '
                f'pins ({pin[:12]}).'
            )

    worktree = os.path.join(
        config.work_base, 'omega', f'init-polaris-{pull_request}'
    )
    if os.path.exists(worktree):
        git_tools.remove_worktree(repo, worktree)
    git_tools.add_worktree(repo, pin, worktree)
    try:
        for number, head in heads.items():
            conflicts = git_tools.merge(
                worktree,
                head,
                f'Test merge of E3SM-Project/Omega#{number} ({head[:10]}) '
                f'into {pin[:10]}',
            )
            if conflicts is not None:
                raise InitError(
                    f'E3SM-Project/Omega#{number} does not merge cleanly into '
                    f'the Omega the PR pins:\n{conflicts}'
                )
        commit = git_tools.rev_parse(worktree, 'HEAD')
    finally:
        git_tools.remove_worktree(repo, worktree)
    git_tools.git(['update-ref', f'{REF_PREFIX}/{branch}', commit], repo)
    return OmegaMerge(commit, heads, config.fork, branch)


def _find_equivalent(polaris_dir, omega_repo, fork, manifest):
    """
    The fork's manifest and manifest commit, if the fork already has the
    test branch with the same PR head, baseline, rows and Omega merges.
    Omega merges are compared by tree, since remaking a merge changes only
    its hash.
    """
    if fork is None:
        return None
    try:
        if not git_tools.has_remote_branch(polaris_dir, fork, manifest.branch):
            return None
        existing = fetch_manifest(polaris_dir, fork, manifest.branch)
    except (git_tools.GitError, ManifestError):
        return None
    same = all(
        getattr(existing, name) == getattr(manifest, name)
        for name in ['pull_request', 'test', 'baseline', 'rows']
    )
    if not same or not _same_omega_merge(
        omega_repo, existing.omega_merge, manifest.omega_merge
    ):
        return None
    existing_commit = git_tools.rev_parse(
        polaris_dir, f'{REF_PREFIX}/{manifest.branch}'
    )
    return existing, existing_commit


def _same_omega_merge(omega_repo, existing, new):
    """Whether two Omega merges merge the same PRs into the same tree"""
    if existing is None or new is None:
        return existing is None and new is None
    if existing.pull_requests != new.pull_requests:
        return False
    try:
        git_tools.fetch(
            omega_repo,
            existing.fork,
            [f'refs/heads/{existing.branch}:{REF_PREFIX}/existing-merge'],
        )
        return git_tools.tree(omega_repo, existing.commit) == git_tools.tree(
            omega_repo, new.commit
        )
    except git_tools.GitError:
        return False
