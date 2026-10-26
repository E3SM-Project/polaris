"""
Cleaning up old test runs, baselines and Omega worktrees in ``work_base``,
keeping anything an open pull request cites
"""

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pr_test_git as git_tools
from pr_test_github import get_open_pull_request_texts
from pr_test_setup import STATE_FILENAME

#: the repositories whose open pull requests may cite test results
CITING_REPOS = ['E3SM-Project/Omega', 'E3SM-Project/polaris']

#: the file, in ``work_base``, that the paths open pull requests cite are
#: written to and read from by default
CITED_FILENAME = 'cited_paths.txt'

#: how old a list of cited paths may be, in hours, before cleanup refuses
#: it, since pull requests may have cited more paths since
MAX_CITED_AGE_HOURS = 24

#: anything modified more recently than this many days is kept by default,
#: since it may be in use
DEFAULT_KEEP_DAYS = 3

#: the first line of a list of cited paths, with the time it was written
_CITED_HEADER = '# paths cited by open pull requests of {repos} at {time}'

_CITED_TIME = re.compile(r' at (\S+)$')

#: an absolute path in a pull request's text, not part of a URL
_PATH = re.compile(r'(?<![\w.:/~-])(/[\w.+@=~-]+(?:/[\w.+@=~-]+)+)')

_RUN_DIR = re.compile(r'^pr\d+-[0-9a-f]{7}(\..+)?$')

_TREE_DIR = re.compile(r'^[0-9a-f]{12}$')

_BASELINE_OMEGA = re.compile(r'_omega-([0-9a-f]{7})$')

_SOURCE_DIR = re.compile(r'^OmegaOceanModel_SOURCE_DIR:\w+=(.+)$', re.M)


class CleanupError(Exception):
    """The cleanup cannot go ahead"""


@dataclass
class Entry:
    """
    Something in ``work_base`` that cleanup may remove

    Attributes
    ----------
    path : str
        Its path

    kind : str
        ``run``, ``baseline``, ``worktree`` or ``marker`` (a worktree's
        ``.ready`` file with no worktree)

    keep : str, optional
        Why it is kept, or ``None`` if it is to be removed
    """

    path: str
    kind: str
    keep: Optional[str] = None


def collect_citations(
    repos: Iterable[str] = tuple(CITING_REPOS),
) -> List[Tuple[str, str]]:
    """
    Find the absolute paths that open pull requests cite

    Parameters
    ----------
    repos : iterable of str, optional
        The repositories to look in

    Returns
    -------
    citations : list of tuple of str
        Each path and the pull request citing it, such as
        ``E3SM-Project/Omega#640``, sorted
    """
    citations = set()
    for repo in repos:
        for number, texts in get_open_pull_request_texts(repo).items():
            for text in texts:
                for path in find_paths(text):
                    citations.add((path, f'{repo}#{number}'))
    return sorted(citations)


def find_paths(text: str) -> List[str]:
    """
    Find the absolute paths in a text, leaving out URLs

    Parameters
    ----------
    text : str
        A pull request's description or a comment

    Returns
    -------
    paths : list of str
        The paths, normalized, without a final ``.`` or ``/``
    """
    return [
        os.path.normpath(match.rstrip('.')) for match in _PATH.findall(text)
    ]


def write_citations(
    filename: str,
    citations: List[Tuple[str, str]],
    repos: Iterable[str] = tuple(CITING_REPOS),
) -> None:
    """
    Write the cited paths, with the time, for cleanup to read

    Parameters
    ----------
    filename : str
        The file to write

    citations : list of tuple of str
        Each path and the pull request citing it

    repos : iterable of str, optional
        The repositories the citations come from
    """
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with open(filename, 'w') as f:
        f.write(_CITED_HEADER.format(repos=' and '.join(repos), time=now))
        f.write('\n')
        for path, source in citations:
            f.write(f'{path}\t{source}\n')


def read_citations(filename: str, now: Optional[float] = None) -> Set[str]:
    """
    Read the cited paths that :py:func:`write_citations` wrote, refusing
    a list that is too old

    Parameters
    ----------
    filename : str
        The file to read

    now : float, optional
        The current time, as from ``time.time()``

    Returns
    -------
    paths : set of str
        The cited paths
    """
    if not os.path.exists(filename):
        raise CleanupError(
            f'There is no list of cited paths at {filename}.  Write one with '
            f'the cited command, where gh is logged in, and copy it here.'
        )
    with open(filename) as f:
        lines = f.read().splitlines()
    match = _CITED_TIME.search(lines[0]) if lines else None
    if match is None:
        raise CleanupError(
            f'{filename} was not written by the cited command.  Write a new '
            f'one.'
        )
    written = (
        datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%SZ')
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    if now is None:
        now = time.time()
    if now - written > MAX_CITED_AGE_HOURS * 3600:
        raise CleanupError(
            f'{filename} was written at {match.group(1)}, more than '
            f'{MAX_CITED_AGE_HOURS} hours ago, and pull requests may cite '
            f'more since.  Write a new one with the cited command.'
        )
    return {line.split('\t')[0] for line in lines[1:] if line.strip()}


def plan_cleanup(
    work_base: str,
    cited: Set[str],
    keep_days: float,
    polaris_hashes: Iterable[str],
    now: Optional[float] = None,
) -> List[Entry]:
    """
    Decide what in ``work_base`` to keep and what to remove

    Kept are test runs, baselines and worktrees that an open pull request
    cites or that contain a cited path, anything modified in the last
    ``keep_days`` days, baselines for the given Polaris commits (those that
    may still be reused), the baselines of kept runs, and the worktrees
    that kept runs and baselines were built from.  Anything else in
    ``work_base``, such as notes or logs, is not the utility's and is left
    alone.

    Parameters
    ----------
    work_base : str
        The settings' ``work_base``

    cited : set of str
        The paths that open pull requests cite

    keep_days : float
        How many days back a modification keeps an entry

    polaris_hashes : iterable of str
        The Polaris commits whose baselines are kept

    now : float, optional
        The current time, as from ``time.time()``

    Returns
    -------
    entries : list of pr_test_cleanup.Entry
        Every run, baseline and worktree, with why it is kept, if it is
    """
    if now is None:
        now = time.time()
    since = now - keep_days * 86400
    cited = _with_real_paths(cited)
    runs = [Entry(path, 'run') for path in _subdirs(work_base, _RUN_DIR)]
    for entry in runs:
        entry.keep = _cited_or_recent(entry.path, cited, since)

    kept_baselines, kept_builds = _used_by_runs(runs)
    baselines = _plan_baselines(
        work_base, cited, since, polaris_hashes, kept_baselines
    )
    kept_builds.extend(
        os.path.join(entry.path, 'build')
        for entry in baselines
        if entry.keep is not None
    )
    trees = _plan_trees(
        work_base,
        cited,
        since,
        keep_days,
        baselines,
        _source_trees(kept_builds),
    )
    return runs + baselines + trees + _stale_markers(work_base)


def remove(entries: List[Entry]) -> List[str]:
    """
    Remove the entries that are not kept

    Worktrees are removed with ``git worktree remove`` from the clone they
    were made from, which also removes their submodule clones there.

    Parameters
    ----------
    entries : list of pr_test_cleanup.Entry
        What :py:func:`plan_cleanup` decided

    Returns
    -------
    removed : list of str
        The paths removed
    """
    removed = []
    clones = set()
    for entry in entries:
        if entry.keep is not None:
            continue
        if entry.kind == 'worktree':
            clone = _clone_of(entry.path)
            if clone is not None:
                clones.add(clone)
                try:
                    git_tools.remove_worktree(clone, entry.path)
                except git_tools.GitError:
                    pass
            if os.path.exists(entry.path):
                shutil.rmtree(entry.path)
            ready = f'{entry.path}.ready'
            if os.path.exists(ready):
                os.remove(ready)
        elif entry.kind == 'marker':
            os.remove(entry.path)
        else:
            shutil.rmtree(entry.path)
        removed.append(entry.path)
    for clone in sorted(clones):
        git_tools.git(['worktree', 'prune'], clone)
    return removed


def format_plan(entries: List[Entry], work_base: str, removed: bool) -> str:
    """
    List what is kept and why, and what is (or would be) removed

    Parameters
    ----------
    entries : list of pr_test_cleanup.Entry
        What :py:func:`plan_cleanup` decided

    work_base : str
        The settings' ``work_base``, which paths are shown relative to

    removed : bool
        Whether the entries that are not kept have been removed

    Returns
    -------
    text : str
        The list
    """
    verb = 'Removed' if removed else 'Would remove'
    groups: Dict[str, List[str]] = {verb: [], 'Kept': []}
    for entry in entries:
        path = os.path.relpath(entry.path, work_base)
        if entry.keep is None:
            groups[verb].append(f'  {path}')
        else:
            groups['Kept'].append(f'  {path}  ({entry.keep})')
    lines = [f'In {work_base}:']
    for title, items in groups.items():
        lines.append(f'{title} ({len(items)}):')
        lines.extend(items or ['  nothing'])
    return '\n'.join(lines)


def _used_by_runs(runs):
    """The baselines and builds of the runs that are kept"""
    baselines = set()
    builds = []
    for entry in runs:
        if entry.keep is None:
            continue
        for row_dir in _subdirs(entry.path):
            state = _read_state(row_dir)
            baseline = state.get('baseline_work_dir')
            if baseline:
                baselines.add(os.path.dirname(baseline))
            builds.append(
                state.get('pr_build_dir', os.path.join(row_dir, 'build'))
            )
    return baselines, builds


def _plan_baselines(work_base, cited, since, polaris_hashes, kept):
    """Decide which baselines to keep"""
    prefixes = {f'_polaris-{sha[:7]}_' for sha in polaris_hashes}
    baselines = [
        Entry(path, 'baseline')
        for path in _subdirs(os.path.join(work_base, 'baselines'))
    ]
    for entry in baselines:
        name = os.path.basename(entry.path)
        entry.keep = _cited_or_recent(entry.path, cited, since)
        if entry.keep is None and any(p in name for p in prefixes):
            entry.keep = 'for the current Polaris commit'
        if entry.keep is None and entry.path in kept:
            entry.keep = 'the baseline of a kept run'
    return baselines


def _plan_trees(work_base, cited, since, keep_days, baselines, used_trees):
    """Decide which Omega worktrees to keep"""
    commits = set()
    for entry in baselines:
        match = _BASELINE_OMEGA.search(os.path.basename(entry.path))
        if entry.keep is not None and match is not None:
            commits.add(match.group(1))

    tree_base = os.path.join(work_base, 'omega')
    trees = [
        Entry(path, 'worktree') for path in _subdirs(tree_base, _TREE_DIR)
    ]
    for entry in trees:
        name = os.path.basename(entry.path)
        entry.keep = _cited_or_recent(entry.path, cited, since)
        if entry.keep is None and _mtime(f'{entry.path}.ready') > since:
            entry.keep = f'made in the last {keep_days:g} days'
        if entry.keep is None and (
            entry.path in used_trees or name[:7] in commits
        ):
            entry.keep = 'used by a kept run or baseline'
    return trees


def _stale_markers(work_base):
    """The ``.ready`` files of worktrees that are gone"""
    tree_base = os.path.join(work_base, 'omega')
    if not os.path.isdir(tree_base):
        return []
    return [
        Entry(os.path.join(tree_base, name), 'marker')
        for name in sorted(os.listdir(tree_base))
        if name.endswith('.ready')
        and not os.path.isdir(os.path.join(tree_base, name[: -len('.ready')]))
    ]


def _with_real_paths(cited):
    """The cited paths, and the same paths with symlinks resolved, since
    a pull request may name a directory by another of its paths, such as
    through a link in the home directory"""
    paths = set(cited)
    for path in cited:
        existing = path
        rest: List[str] = []
        while not os.path.exists(existing) and existing != os.sep:
            rest.insert(0, os.path.basename(existing))
            existing = os.path.dirname(existing)
        paths.add(os.path.join(os.path.realpath(existing), *rest))
    return paths


def _cited_or_recent(path, cited, since):
    """Why an entry is kept for a citation or a recent change, if it is"""
    real = os.path.realpath(path)
    for candidate in sorted(cited):
        for prefix in (path, real):
            if candidate == prefix or candidate.startswith(prefix + os.sep):
                return f'cited: {candidate}'
    if _newest_mtime(path) > since:
        return 'modified recently'
    return None


def _newest_mtime(path, depth=2):
    """The newest modification time of a directory and its contents, a
    few levels down"""
    newest = _mtime(path)
    if depth == 0 or not os.path.isdir(path) or os.path.islink(path):
        return newest
    try:
        children = list(os.scandir(path))
    except OSError:
        return newest
    for child in children:
        newest = max(newest, _newest_mtime(child.path, depth - 1))
    return newest


def _mtime(path):
    try:
        return os.lstat(path).st_mtime
    except OSError:
        return 0.0


def _subdirs(directory, pattern=None):
    if not os.path.isdir(directory):
        return []
    return [
        os.path.join(directory, name)
        for name in sorted(os.listdir(directory))
        if os.path.isdir(os.path.join(directory, name))
        and not os.path.islink(os.path.join(directory, name))
        and (pattern is None or pattern.match(name))
    ]


def _read_state(row_dir):
    """A row's setup state as a dict, or an empty one"""
    path = os.path.join(row_dir, STATE_FILENAME)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _source_trees(build_dirs):
    """The Omega worktrees that builds were configured from"""
    trees = set()
    for build_dir in build_dirs:
        try:
            with open(os.path.join(build_dir, 'CMakeCache.txt')) as f:
                match = _SOURCE_DIR.search(f.read())
        except OSError:
            continue
        if match is not None:
            source = match.group(1).strip()
            # the source directory is components/omega in the worktree
            trees.add(os.path.dirname(os.path.dirname(source)))
    return trees


def _clone_of(tree):
    """The clone a worktree was made from, if its link to it is intact"""
    try:
        with open(os.path.join(tree, '.git')) as f:
            gitdir = f.read().strip()
    except OSError:
        return None
    gitdir = gitdir.removeprefix('gitdir:').strip()
    marker = f'{os.sep}.git{os.sep}worktrees{os.sep}'
    if marker not in gitdir:
        return None
    clone = gitdir.split(marker)[0]
    return clone if os.path.isdir(os.path.join(clone, '.git')) else None
