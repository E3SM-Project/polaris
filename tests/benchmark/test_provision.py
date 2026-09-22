import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / 'utils' / 'benchmark'

#: git config the fixture repositories need, as ``GIT_CONFIG_*`` variables
#:
#: ``protocol.file.allow`` is the one that matters: git has refused a
#: submodule whose URL is a local path since 2.38.1, and the miniature
#: repositories here are all local paths.  The rest keep the fixture from
#: depending on the developer's own git config.
GIT_CONFIG = {
    'protocol.file.allow': 'always',
    'user.name': 'Polaris Test',
    'user.email': 'test@example.com',
    'commit.gpgsign': 'false',
}


@pytest.fixture
def gitrepo(monkeypatch):
    """The benchmark driver's ``gitrepo`` module, with git set up for it."""
    monkeypatch.setenv('GIT_CONFIG_COUNT', str(len(GIT_CONFIG)))
    for index, (key, value) in enumerate(GIT_CONFIG.items()):
        monkeypatch.setenv(f'GIT_CONFIG_KEY_{index}', key)
        monkeypatch.setenv(f'GIT_CONFIG_VALUE_{index}', value)
    return _load_gitrepo()


def test_omega_override_gets_its_own_worktree(gitrepo, tmp_path):
    """
    Benchmarking an Omega branch with polaris pinned on both sides

    The two sides resolve to the same polaris commit and differ only in
    the Omega submodule, which used to give them one worktree and stop
    the benchmark before it began.
    """
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')

    baseline = _provision(gitrepo, repos, 'baseline', work_base)
    test = _provision(
        gitrepo,
        repos,
        'test',
        work_base,
        submodule_specs={'omega': ('', repos['omega_test'])},
    )

    assert baseline.path != test.path
    assert baseline.polaris_sha == test.polaris_sha
    assert gitrepo.check_single_variable(baseline, test) == ['omega']

    # each side has its own Omega checkout: a linked worktree keeps its
    # submodules in its own gitdir, so checking one out does not move the
    # other
    assert baseline.submodule_shas['omega'] == repos['omega_baseline']
    assert test.submodule_shas['omega'] == repos['omega_test']
    assert _omega_content(baseline.path) == 'baseline\n'
    assert _omega_content(test.path) == 'test\n'


def test_nested_submodules_are_left_uninitialized(gitrepo, tmp_path):
    """
    Provisioning checks out the submodule but not the ones inside it

    Polaris initializes the nested submodules it builds against as the
    first step of the build, and only those.  A bare recursive update
    here would clone the whole E3SM tree that Omega's repository carries.
    """
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')

    test = _provision(
        gitrepo,
        repos,
        'test',
        work_base,
        submodule_specs={'omega': ('', repos['omega_test'])},
    )

    nested = (
        Path(test.path) / 'e3sm_submodules' / 'Omega' / 'externals' / 'nested'
    )
    assert nested.is_dir()
    assert not (nested / 'file.txt').exists()


def test_worktree_name_records_the_override(gitrepo, tmp_path):
    """The worktree name says which Omega commit is checked out in it."""
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')

    test = _provision(
        gitrepo,
        repos,
        'test',
        work_base,
        submodule_specs={'omega': ('', repos['omega_test'])},
    )

    sha = repos['polaris_sha'][:7]
    name = Path(test.path).name
    assert name == f'main-{sha}-omega-{repos["omega_test"][:7]}'


def test_dry_run_provisions_the_two_sides(gitrepo, tmp_path):
    """
    A dry run provisions, so every hash it reports is the real one

    A submodule's commit is not known until it has been checked out, and
    a dry run whose hashes differed from the run it previews would not be
    worth much.
    """
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')

    baseline = _provision(gitrepo, repos, 'baseline', work_base, dry_run=True)
    test = _provision(
        gitrepo,
        repos,
        'test',
        work_base,
        submodule_specs={'omega': ('', repos['omega_test'])},
        dry_run=True,
    )

    assert baseline.path != test.path
    assert baseline.submodule_shas['omega'] == repos['omega_baseline']
    assert test.submodule_shas['omega'] == repos['omega_test']
    assert _omega_content(test.path) == 'test\n'
    assert gitrepo.check_single_variable(baseline, test) == ['omega']


def test_dry_run_reports_a_load_script_a_run_refuses(gitrepo, tmp_path):
    """
    Nothing is deployed into a worktree a dry run has just created

    So a dry run records the missing load script and carries on, where a
    run of the same config stops.
    """
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')
    kwargs = dict(
        name='baseline',
        primary_path=repos['polaris'],
        work_base=work_base,
        fork='',
        ref='main',
        model='omega',
        load_script_name='load_polaris_test.sh',
    )

    state = gitrepo.provision(dry_run=True, **kwargs)

    assert not state.load_script_ready
    with pytest.raises(ValueError, match='load script'):
        gitrepo.provision(dry_run=False, **kwargs)


def test_same_ref_in_two_forks_gets_two_worktrees(gitrepo, tmp_path):
    """Two sides may ask for one branch name in two different forks."""
    repos = _make_repos(tmp_path)
    work_base = str(tmp_path / 'work_base')

    sides = []
    for owner, text in [('E3SM-Project', 'theirs\n'), ('cbegeman', 'mine\n')]:
        fork = _make_fork(tmp_path, owner, repos['omega'], text)
        sides.append(
            _provision(
                gitrepo,
                repos,
                'test',
                work_base,
                submodule_specs={'omega': (fork, 'my-omega-feature')},
            )
        )

    assert sides[0].path != sides[1].path
    assert _omega_content(sides[0].path) == 'theirs\n'
    assert _omega_content(sides[1].path) == 'mine\n'


def _load_gitrepo():
    """Import ``gitrepo`` from ``utils/benchmark``, which is not a package."""
    if str(BENCHMARK_DIR) not in sys.path:
        # gitrepo imports its own helpers as `shared`, so the directory has
        # to be importable before it is loaded
        sys.path.insert(0, str(BENCHMARK_DIR))
    spec = importlib.util.spec_from_file_location(
        'benchmark_gitrepo', BENCHMARK_DIR / 'gitrepo.py'
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _provision(
    gitrepo, repos, name, work_base, submodule_specs=None, dry_run=False
):
    """Provision one side of a benchmark from the fixture repositories."""
    return gitrepo.provision(
        name=name,
        primary_path=repos['polaris'],
        work_base=work_base,
        fork='',
        ref='main',
        model='omega',
        load_script_name=repos['load_script'],
        submodule_specs=submodule_specs,
        dry_run=dry_run,
    )


def _make_repos(tmp_path):
    """
    Make a miniature polaris repository with a miniature Omega submodule

    Returns
    -------
    repos : dict
        The path to the polaris clone, an absolute load script for it to
        find, its commit, and the two Omega commits
    """
    # Omega carries nested submodules of its own -- in the real one, the
    # whole E3SM tree -- which provisioning must leave alone
    nested = tmp_path / 'nested'
    _init(nested)
    _commit(nested, 'nested\n')

    omega = tmp_path / 'Omega'
    _init(omega)
    _git(['submodule', 'add', str(nested), 'externals/nested'], omega)
    _git(['commit', '-m', 'add a nested submodule'], omega)
    omega_baseline = _commit(omega, 'baseline\n')
    omega_test = _commit(omega, 'test\n')

    polaris = tmp_path / 'polaris'
    _init(polaris)
    (polaris / 'polaris').mkdir()
    (polaris / 'polaris' / 'version.py').write_text("__version__ = '0.0.0'\n")
    (polaris / 'deploy.py').write_text('')
    _git(['add', 'polaris/version.py', 'deploy.py'], polaris)
    _git(
        ['submodule', 'add', str(omega), 'e3sm_submodules/Omega'],
        polaris,
    )
    _git(['-C', 'e3sm_submodules/Omega', 'checkout', omega_baseline], polaris)
    _git(['add', 'e3sm_submodules/Omega'], polaris)
    _git(['commit', '-m', 'add a submodule'], polaris)

    # an absolute load script is how one deployment serves both sides,
    # which is what a provisioned worktree needs: nothing deploys into it
    load_script = tmp_path / 'load_polaris_test.sh'
    load_script.write_text('')

    return {
        'omega': str(omega),
        'polaris': str(polaris),
        'polaris_sha': _head(polaris),
        'load_script': str(load_script),
        'omega_baseline': omega_baseline,
        'omega_test': omega_test,
    }


def _make_fork(tmp_path, owner, source, text):
    """Make a fork of the Omega fixture with a branch of its own."""
    path = tmp_path / 'forks' / owner / 'Omega'
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(['clone', '-q', str(source), str(path)], tmp_path)
    _git(['checkout', '-q', '-b', 'my-omega-feature'], path)
    _commit(path, text)
    # a fork is given as a URL rather than a path so that the driver takes
    # it as one; a bare path would be read as a GitHub owner
    return f'file://{path}'


def _init(path):
    """Make an empty git repository on a ``main`` branch."""
    path.mkdir()
    _git(['init', '-q', '-b', 'main'], path)


def _commit(path, text):
    """Commit ``text`` to ``file.txt`` and return the commit hash."""
    (path / 'file.txt').write_text(text)
    _git(['add', 'file.txt'], path)
    _git(['commit', '-m', text.strip()], path)
    return _head(path)


def _head(path):
    """Get the full commit hash of ``HEAD``."""
    return subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git(args, cwd):
    """Run a git command in the fixture."""
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


def _omega_content(worktree):
    """Read the one file in a worktree's Omega submodule."""
    path = Path(worktree) / 'e3sm_submodules' / 'Omega' / 'file.txt'
    return path.read_text()
