"""
Git operations for the Omega PR testing utility
"""

import os
import subprocess
from typing import List, Optional

#: the URL fetches from E3SM-Project/Omega use, which needs no credentials
UPSTREAM_URL = 'https://github.com/E3SM-Project/Omega.git'

#: the namespace for refs the utility makes in the Omega clone, which keeps
#: them apart from the developer's own branches
REF_PREFIX = 'refs/omega-pr-test'


class GitError(Exception):
    """A git command failed"""


def git(args: List[str], cwd: str) -> str:
    """
    Run a git command and return its output

    Parameters
    ----------
    args : list of str
        The arguments to git

    cwd : str
        The repository to run in

    Returns
    -------
    output : str
        The command's standard output, without trailing whitespace
    """
    result = subprocess.run(
        ['git'] + args, cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GitError(
            f'"git {" ".join(args)}" failed in {cwd}:\n{result.stderr}'
        )
    return result.stdout.rstrip()


def fetch(repo: str, url: str, refspecs: List[str]) -> None:
    """
    Fetch refs into a repository, forcing the local refs to match

    Parameters
    ----------
    repo : str
        The repository to fetch into

    url : str
        The remote URL

    refspecs : list of str
        ``<remote ref>:<local ref>`` pairs
    """
    git(['fetch', '--quiet', url] + [f'+{spec}' for spec in refspecs], repo)


def has_remote_branch(repo: str, url: str, branch: str) -> bool:
    """Whether a remote has a branch"""
    output = git(['ls-remote', '--heads', url, f'refs/heads/{branch}'], repo)
    return bool(output)


def tree(repo: str, commit: str) -> str:
    """The hash of a commit's tree"""
    return git(['rev-parse', '--verify', f'{commit}^{{tree}}'], repo)


def rev_parse(repo: str, rev: str) -> str:
    """The full hash of a commit"""
    return git(['rev-parse', '--verify', f'{rev}^{{commit}}'], repo)


def is_ancestor(repo: str, ancestor: str, descendant: str) -> bool:
    """Whether one commit is an ancestor of, or the same as, another"""
    result = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', ancestor, descendant],
        cwd=repo,
        capture_output=True,
    )
    return result.returncode == 0


def has_commit(repo: str, sha: str) -> bool:
    """Whether a repository has a commit"""
    result = subprocess.run(
        ['git', 'cat-file', '-e', f'{sha}^{{commit}}'],
        cwd=repo,
        capture_output=True,
    )
    return result.returncode == 0


def submodule_pin(repo: str, commit: str, path: str) -> str:
    """
    The commit a repository pins a submodule to at one of its commits

    Parameters
    ----------
    repo : str
        The repository with the submodule

    commit : str
        The commit to look at

    path : str
        The path of the submodule

    Returns
    -------
    sha : str
        The pinned commit
    """
    output = git(['ls-tree', commit, path], repo)
    fields = output.split()
    if len(fields) < 3 or fields[1] != 'commit':
        raise GitError(f'{path} is not a submodule at {commit} in {repo}.')
    return fields[2]


def uncommitted_changes(repo: str) -> List[str]:
    """
    Tracked files with changes that are not committed, not counting
    submodules, whose checkouts the utility never builds from
    """
    output = git(
        [
            'status',
            '--porcelain',
            '--untracked-files=no',
            '--ignore-submodules=all',
        ],
        repo,
    )
    return [line[3:] for line in output.splitlines() if line.strip()]


def add_worktree(repo: str, sha: str, dest: str) -> None:
    """
    Make a detached worktree at a commit, reusing one that is already there

    Parameters
    ----------
    repo : str
        The repository to make the worktree from

    sha : str
        The commit to check out

    dest : str
        The path of the worktree
    """
    if os.path.exists(dest):
        existing = git(['rev-parse', 'HEAD'], dest)
        if existing != sha:
            raise GitError(
                f'{dest} exists but is at {existing[:12]}, not {sha[:12]}.'
            )
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    git(['worktree', 'add', '--quiet', '--detach', dest, sha], repo)


def remove_worktree(repo: str, dest: str) -> None:
    """Remove a worktree, discarding anything in it"""
    git(['worktree', 'remove', '--force', dest], repo)


def merge(worktree: str, sha: str, message: str) -> Optional[str]:
    """
    Merge a commit into a worktree's HEAD

    Parameters
    ----------
    worktree : str
        The worktree to merge in

    sha : str
        The commit to merge

    message : str
        The merge commit's message

    Returns
    -------
    conflicts : str, optional
        The conflicting paths if the merge failed, in which case it has been
        aborted, or ``None`` if it succeeded
    """
    result = subprocess.run(
        ['git', 'merge', '--no-ff', '--no-edit', '-m', message, sha],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    conflicts = git(['diff', '--name-only', '--diff-filter=U'], worktree)
    subprocess.run(
        ['git', 'merge', '--abort'], cwd=worktree, capture_output=True
    )
    return conflicts or result.stderr.strip()


def show_file(repo: str, commit: str, path: str) -> str:
    """The contents of a file at a commit"""
    return git(['show', f'{commit}:{path}'], repo)
