"""
Resolve, provision and adopt Polaris source trees for benchmarking.

Two modes are supported for each side of a benchmark:

``provision``
    Resolve a fork and ref to a commit, create a detached ``git worktree``
    under the benchmark work base, initialize submodules, and optionally
    check out a different fork/ref for one of the submodules.

``adopt``
    Use an existing Polaris worktree (typically the one the developer is
    already working in) exactly as it is found.  This module never runs
    fetch, checkout, submodule update, reset or clean against it.

    Note that this is not the same as the tree being untouched.  Polaris
    builds the component from ``--branch``, which for MPAS-Ocean is an
    in-source ``make`` in the branch directory, and both build templates
    run ``git submodule update --init --recursive`` there.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field

from shared import check_call, check_output

#: Mapping from a short submodule key to its path within Polaris
SUBMODULE_PATHS = {
    'e3sm': 'e3sm_submodules/E3SM-Project',
    'omega': 'e3sm_submodules/Omega',
}

#: Mapping from a Polaris ``--model`` value to the submodule it is built from
#:
#: Only the models Polaris can build automatically belong here; see
#: ``_build_model()`` in ``polaris/setup.py``.
MODEL_SUBMODULES = {
    'mpas-ocean': 'e3sm',
    'omega': 'omega',
}


@dataclass
class SourceState:
    """
    The fully resolved state of one side of a benchmark

    Attributes
    ----------
    name : str
        Either ``baseline`` or ``test``
    mode : str
        Either ``worktree`` (provisioned) or ``existing`` (adopted)
    path : str
        The absolute path to the Polaris worktree
    polaris_sha : str
        The full commit hash of Polaris at ``path``
    polaris_ref : str
        The branch name, tag or ref that was requested or is checked out
    polaris_fork : str
        The fork (owner or URL) the commit came from, when known
    submodule_shas : dict
        Commit hashes of the initialized submodules, keyed by short name
    pinned_shas : dict
        Commit hashes the Polaris commit pins for each submodule
    submodule_overrides : dict
        Submodules explicitly checked out to a different fork/ref
    dirty : bool
        Whether the worktree or any submodule has uncommitted or
        untracked changes
    load_script : str
        The absolute path to the load script used to activate the
        environment
    load_script_ready : bool
        Whether the load script exists yet.  It can be ``False`` only
        during a dry run of a worktree that has not been created
    model : str
        The Polaris ``--model`` value for this benchmark
    """

    name: str
    mode: str
    path: str
    polaris_sha: str = ''
    polaris_ref: str = ''
    polaris_fork: str = ''
    submodule_shas: dict = field(default_factory=dict)
    pinned_shas: dict = field(default_factory=dict)
    submodule_overrides: dict = field(default_factory=dict)
    dirty: bool = False
    load_script: str = ''
    load_script_ready: bool = True
    model: str = ''

    @property
    def component_branch_path(self):
        """
        str : the path passed to ``polaris setup --branch`` for this model
        """
        key = MODEL_SUBMODULES[self.model]
        return os.path.join(self.path, SUBMODULE_PATHS[key])

    @property
    def compare_shas(self):
        """
        dict : the commit hashes used by the one-variable guardrail
        """
        shas = {'polaris': self.polaris_sha}
        for key in SUBMODULE_PATHS:
            # a submodule that is not initialized is still pinned by the
            # polaris commit, and the pin is what it would be checked out
            # at, so report that rather than nothing
            actual = self.submodule_shas.get(key, '')
            shas[key] = actual or self.pinned_shas.get(key, '')
        return shas

    def provenance(self):
        """
        Get a dictionary describing this source state for the manifest

        Returns
        -------
        provenance : dict
            A JSON-serializable description of this source state
        """
        return {
            'name': self.name,
            'mode': self.mode,
            'path': self.path,
            'polaris_fork': self.polaris_fork,
            'polaris_ref': self.polaris_ref,
            'polaris_sha': self.polaris_sha,
            'submodule_shas': dict(self.submodule_shas),
            'pinned_shas': dict(self.pinned_shas),
            'submodule_overrides': dict(self.submodule_overrides),
            'dirty': self.dirty,
            'load_script': self.load_script,
            'load_script_ready': self.load_script_ready,
            'model': self.model,
        }


def provision(
    name,
    primary_path,
    work_base,
    fork,
    ref,
    model,
    load_script_name,
    submodule_specs=None,
    dry_run=False,
    logger=None,
):
    """
    Create (or reuse) a detached worktree at the requested fork and ref

    Parameters
    ----------
    name : str
        Either ``baseline`` or ``test``
    primary_path : str
        The Polaris clone to fetch from and create worktrees off of
    work_base : str
        The base directory for the benchmark; worktrees are created in a
        ``worktrees`` subdirectory
    fork : str
        A GitHub owner (e.g. ``E3SM-Project``) or a full remote URL
    ref : str
        A branch, tag or commit hash in ``fork``
    model : str
        The Polaris ``--model`` value
    load_script_name : str
        The name of the load script to source within the worktree
    submodule_specs : dict, optional
        A mapping from submodule key to a ``(fork, ref)`` tuple for
        submodules that should differ from the SHA pinned by Polaris
    dry_run : bool, optional
        Whether to only resolve commits and report planned commands
    logger : logging.Logger, optional
        A logger for command output

    Returns
    -------
    state : SourceState
        The resolved state of the provisioned worktree
    """
    if submodule_specs is None:
        submodule_specs = {}

    primary_path = os.path.abspath(primary_path)
    _check_is_polaris_repo(primary_path)

    sha = resolve(primary_path, fork, ref)
    slug = _slugify(ref)
    worktree = os.path.join(work_base, 'worktrees', f'{slug}-{sha[:7]}')

    state = SourceState(
        name=name,
        mode='worktree',
        path=worktree,
        polaris_sha=sha,
        polaris_ref=ref,
        polaris_fork=fork,
        model=model,
    )

    load_script = load_script_path(worktree, load_script_name)
    # a load script we can already resolve is checked before the worktree
    # and its submodules are created, so that a missing one fails fast
    predictable = os.path.isabs(load_script_name) or os.path.exists(worktree)
    if predictable:
        _require_load_script(worktree, load_script_name)

    if dry_run:
        state.pinned_shas = _pinned_submodule_shas(primary_path, sha)
        state.submodule_shas = dict(state.pinned_shas)
        for key, (sub_fork, sub_ref) in submodule_specs.items():
            state.submodule_overrides[key] = {
                'fork': sub_fork,
                'ref': sub_ref,
            }
            state.submodule_shas[key] = f'<{sub_fork}:{sub_ref}>'
        state.load_script = load_script
        state.load_script_ready = predictable
        return state

    add_worktree(primary_path, sha, worktree, logger=logger)
    _git('submodule update --init', cwd=worktree, logger=logger)

    state.pinned_shas = _pinned_submodule_shas(worktree, 'HEAD')

    for key, (sub_fork, sub_ref) in submodule_specs.items():
        sub_path = _submodule_path(worktree, key)
        sub_sha = resolve(sub_path, sub_fork, sub_ref)
        checkout_submodule(sub_path, sub_sha, logger=logger)
        state.submodule_overrides[key] = {
            'fork': sub_fork,
            'ref': sub_ref,
            'sha': sub_sha,
        }

    state.submodule_shas = _submodule_shas(worktree)
    state.load_script = _require_load_script(worktree, load_script_name)
    return state


def adopt(name, path, model, load_script_name, allow_dirty=False):
    """
    Validate and record the state of an existing Polaris worktree

    Only read-only ``git`` queries are run against the adopted worktree
    here.  Polaris' own build still writes into it; see the note in the
    module docstring.

    Parameters
    ----------
    name : str
        Either ``baseline`` or ``test``
    path : str
        The path to the existing Polaris worktree
    model : str
        The Polaris ``--model`` value
    load_script_name : str
        The name of the load script to source within the worktree
    allow_dirty : bool, optional
        Whether to permit uncommitted or untracked changes.  The run is
        then marked as not reproducible.

    Returns
    -------
    state : SourceState
        The recorded state of the adopted worktree

    Raises
    ------
    ValueError
        If the path is not a usable Polaris worktree, a required
        submodule is not initialized, or the tree is dirty and
        ``allow_dirty`` is not set
    """
    path = os.path.abspath(path)
    _check_is_polaris_repo(path)

    sha = check_output('git rev-parse HEAD', cwd=path)
    ref = check_output('git rev-parse --abbrev-ref HEAD', cwd=path)
    if ref == 'HEAD':
        ref = 'DETACHED'

    state = SourceState(
        name=name,
        mode='existing',
        path=path,
        polaris_sha=sha,
        polaris_ref=ref,
        polaris_fork=_fork_of_upstream(path),
        model=model,
    )

    key = MODEL_SUBMODULES[model]
    sub_path = _submodule_path(path, key)
    if not os.path.exists(os.path.join(sub_path, '.git')):
        raise ValueError(
            f'The submodule {SUBMODULE_PATHS[key]} in the adopted worktree\n'
            f'  {path}\n'
            f'is not initialized.  This workflow will not modify an '
            f'adopted worktree, so please run:\n'
            f'  git -C {path} submodule update --init '
            f'{SUBMODULE_PATHS[key]}'
        )

    state.pinned_shas = _pinned_submodule_shas(path, 'HEAD')
    state.submodule_shas = _submodule_shas(path)
    state.dirty = _is_dirty(path)

    if state.dirty and not allow_dirty:
        raise ValueError(
            f'The adopted worktree\n  {path}\nhas uncommitted or untracked '
            f'changes, so the benchmark would not be reproducible from the '
            f'recorded commit hashes.  Commit or stash the changes, or '
            f'rerun with --allow-dirty to record the run as '
            f'non-reproducible.'
        )

    state.load_script = _require_load_script(path, load_script_name)
    return state


def resolve(repo_path, fork, ref, fetch=True):
    """
    Resolve a fork and ref to a full commit hash without changing HEAD

    Parameters
    ----------
    repo_path : str
        The path to the repository to resolve the ref in
    fork : str
        A GitHub owner or a full remote URL.  If empty, the ref is
        resolved against the remotes already present.
    ref : str
        A branch, tag or commit hash
    fetch : bool, optional
        Whether to fetch from the fork before resolving

    Returns
    -------
    sha : str
        The full commit hash

    Raises
    ------
    ValueError
        If the ref cannot be resolved
    """
    remote = None
    if fork:
        remote = _ensure_remote(repo_path, fork)
        if fetch:
            _git(f'fetch --tags {remote}', cwd=repo_path)

    candidates = []
    if remote is not None:
        candidates.append(f'refs/remotes/{remote}/{ref}')
    candidates.extend([f'refs/tags/{ref}', ref])

    for candidate in candidates:
        try:
            return check_output(
                f'git rev-parse --verify --quiet {candidate}^{{commit}}',
                cwd=repo_path,
            )
        except subprocess.CalledProcessError:
            continue

    raise ValueError(
        f'Could not resolve ref "{ref}" in fork "{fork}" within {repo_path}'
    )


def add_worktree(repo_path, sha, dest, logger=None):
    """
    Create a detached worktree at a commit, reusing it if already correct

    Parameters
    ----------
    repo_path : str
        The Polaris clone to create the worktree from
    sha : str
        The commit hash to check out
    dest : str
        The path of the worktree to create
    logger : logging.Logger, optional
        A logger for command output

    Returns
    -------
    dest : str
        The path to the worktree

    Raises
    ------
    ValueError
        If ``dest`` exists but is not a worktree at ``sha``
    """
    if os.path.exists(dest):
        try:
            existing = check_output('git rev-parse HEAD', cwd=dest)
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                f'The worktree path {dest} exists but is not a git '
                f'worktree.  Remove it or choose another work base.'
            ) from exc
        if existing != sha:
            raise ValueError(
                f'The worktree path {dest} exists but is at {existing[:7]} '
                f'rather than the expected {sha[:7]}.'
            )
        return dest

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _git(f'worktree add --detach {dest} {sha}', cwd=repo_path, logger=logger)
    return dest


def checkout_submodule(sub_path, sha, logger=None):
    """
    Check out a commit in a submodule of a provisioned worktree

    Parameters
    ----------
    sub_path : str
        The path to the submodule
    sha : str
        The commit hash to check out
    logger : logging.Logger, optional
        A logger for command output

    Raises
    ------
    ValueError
        If the submodule has local modifications
    """
    if _is_dirty(sub_path):
        raise ValueError(
            f'The submodule at {sub_path} has local modifications and will '
            f'not be checked out.'
        )
    _git(f'checkout --detach {sha}', cwd=sub_path, logger=logger)
    _git('submodule update --init --recursive', cwd=sub_path, logger=logger)


def check_single_variable(baseline, test):
    """
    Get the repositories whose commits differ between the two sides

    Parameters
    ----------
    baseline : SourceState
        The baseline source state
    test : SourceState
        The test source state

    Returns
    -------
    differing : list of str
        The keys (``polaris``, ``e3sm``, ``omega``) that differ
    """
    baseline_shas = baseline.compare_shas
    test_shas = test.compare_shas
    differing = []
    for key, sha in baseline_shas.items():
        if sha != test_shas.get(key, ''):
            differing.append(key)
    return differing


def load_script_path(worktree, load_script_name):
    """
    Get the path to the load script for a worktree

    An absolute ``load_script_name`` is used as it is, which is how one
    deployment can serve several worktrees.  A bare name is taken to be
    relative to the worktree.

    Parameters
    ----------
    worktree : str
        The path to the Polaris worktree
    load_script_name : str
        The name of, or absolute path to, the load script

    Returns
    -------
    load_script : str
        The absolute path to the load script
    """
    return os.path.join(worktree, load_script_name)


def _check_is_polaris_repo(path):
    """Raise a ValueError if ``path`` is not a Polaris work tree."""
    if not os.path.isdir(path):
        raise ValueError(f'No such directory: {path}')
    try:
        check_output('git rev-parse --git-common-dir', cwd=path)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f'{path} is not a git work tree') from exc
    for expected in ['polaris/version.py', 'deploy.py']:
        if not os.path.exists(os.path.join(path, expected)):
            raise ValueError(
                f'{path} does not look like a Polaris repository '
                f'(missing {expected})'
            )


def _ensure_remote(repo_path, fork):
    """
    Add a remote for ``fork`` and return its name.

    An existing remote is used but never repointed, since ``repo_path``
    is the developer's own clone.
    """
    url = _fork_url(repo_path, fork)
    name = _remote_name(fork)
    remotes = check_output('git remote', cwd=repo_path).split()
    if name not in remotes:
        _git(f'remote add {name} {url}', cwd=repo_path)
        return name

    existing = check_output(f'git remote get-url {name}', cwd=repo_path)
    if existing != url:
        raise ValueError(
            f'The remote "{name}" in\n  {repo_path}\npoints at\n  '
            f'{existing}\nrather than the expected\n  {url}\nThe '
            f'benchmark will not repoint a remote in your clone.  Rename '
            f'the remote, or give the fork as a full URL.'
        )
    return name


def _fork_url(repo_path, fork):
    """Expand a GitHub owner into a URL matching the style of ``origin``."""
    if '://' in fork or fork.startswith('git@'):
        return fork
    repo = _repo_name(repo_path)
    origin = _origin_url(repo_path)
    if origin.startswith('git@') or origin.startswith('ssh://'):
        return f'git@github.com:{fork}/{repo}.git'
    return f'https://github.com/{fork}/{repo}.git'


def _origin_url(repo_path):
    """Get the URL of ``origin``, or an empty string if there is none."""
    try:
        return check_output('git remote get-url origin', cwd=repo_path)
    except subprocess.CalledProcessError:
        return ''


def _repo_name(repo_path):
    """Get the repository name from the URL of ``origin``."""
    origin = _origin_url(repo_path)
    if not origin:
        return os.path.basename(os.path.normpath(repo_path))
    name = origin.rstrip('/').split('/')[-1]
    if name.endswith('.git'):
        name = name[: -len('.git')]
    return name


def _fork_of_upstream(repo_path):
    """Get the owner of the ``origin`` remote, if it can be determined."""
    origin = _origin_url(repo_path)
    match = re.search(r'[:/]([^/:]+)/[^/]+?(\.git)?$', origin)
    if match is None:
        return ''
    return match.group(1)


def _remote_name(fork):
    """Get a safe remote name for a fork."""
    if '://' in fork or fork.startswith('git@'):
        match = re.search(r'[:/]([^/:]+)/[^/]+?(\.git)?$', fork)
        fork = match.group(1) if match is not None else 'benchmark'
    return re.sub(r'[^A-Za-z0-9_.-]', '_', fork)


def _slugify(ref):
    """Get a filesystem-safe version of a ref name."""
    return re.sub(r'[^A-Za-z0-9_.-]', '-', ref)


def _submodule_path(worktree, key):
    """Get the absolute path to a submodule within a worktree."""
    if key not in SUBMODULE_PATHS:
        raise ValueError(f'Unknown submodule "{key}"')
    return os.path.join(worktree, SUBMODULE_PATHS[key])


def _submodule_shas(worktree):
    """Get the commit hashes of the initialized submodules."""
    shas = {}
    for key, rel_path in SUBMODULE_PATHS.items():
        sub_path = os.path.join(worktree, rel_path)
        if not os.path.exists(os.path.join(sub_path, '.git')):
            continue
        shas[key] = check_output('git rev-parse HEAD', cwd=sub_path)
    return shas


def _pinned_submodule_shas(repo_path, ref):
    """Get the submodule commit hashes pinned by a Polaris commit."""
    shas = {}
    for key, rel_path in SUBMODULE_PATHS.items():
        try:
            output = check_output(
                f'git ls-tree {ref} {rel_path}', cwd=repo_path
            )
        except subprocess.CalledProcessError:
            continue
        parts = output.split()
        if len(parts) >= 3 and parts[1] == 'commit':
            shas[key] = parts[2]
    return shas


def _is_dirty(repo_path):
    """Whether a work tree has uncommitted or untracked changes."""
    status = check_output('git status --porcelain', cwd=repo_path)
    return status != ''


def _require_load_script(worktree, load_script_name):
    """Get the load script in a worktree, raising if it is missing."""
    load_script = load_script_path(worktree, load_script_name)
    if not os.path.exists(load_script):
        raise ValueError(
            f'Could not find the load script\n  {load_script}\n'
            f'Creating the Polaris environment is a developer action, so '
            f'it is never done for you.  Either run ./deploy.py in that '
            f'worktree, or set load_script to the absolute path of an '
            f'existing load script so that one deployment serves both '
            f'sides, and try again.'
        )
    return load_script


def _git(args, cwd, logger=None):
    """Run a git command in a directory."""
    check_call(f'git -C {cwd} {args}', logger=logger)
