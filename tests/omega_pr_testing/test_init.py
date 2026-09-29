from dataclasses import dataclass

import pr_test_git
import pr_test_github
import pr_test_init
import pr_test_manifest
import pytest
from pr_test_config import PrTestConfig
from pr_test_fixtures import commit, git
from pr_test_manifest import (
    MANIFEST_FILENAME,
    POLARIS_SUBMODULE,
    TEMPLATE_ROWS,
    Manifest,
    get_row,
)


@dataclass
class Fixture:
    config: PrTestConfig
    polaris_dir: str
    fork: str
    pin: str
    develop: str
    pr_head: str
    extra_head: str
    conflict_head: str


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    """
    Local stand-ins for E3SM-Project/Omega, E3SM-Project/polaris, the
    requester's fork and the requester's Omega clone
    """
    omega = tmp_path / 'omega-work'
    omega.mkdir()
    git(omega, 'init', '-q')
    pin = commit(omega, 'a.txt', 'a\n', 'Initial commit')
    develop = commit(omega, 'b.txt', 'b\n', 'Merge pull request #3')
    git(omega, 'branch', '-q', 'develop')
    git(omega, 'checkout', '-q', '-b', 'feature', develop)
    pr_head = commit(omega, 'c.txt', 'c\n', 'Add c')
    git(omega, 'checkout', '-q', '-b', 'fix', develop)
    extra_head = commit(omega, 'd.txt', 'd\n', 'Fix the build')
    git(omega, 'checkout', '-q', '-b', 'conflict', pin)
    conflict_head = commit(omega, 'b.txt', 'not b\n', 'Change b')

    upstream = tmp_path / 'omega.git'
    git(tmp_path, 'init', '-q', '--bare', str(upstream))
    git(
        omega,
        'push',
        '-q',
        str(upstream),
        'develop:refs/heads/develop',
        f'{pr_head}:refs/pull/5/head',
        f'{extra_head}:refs/pull/7/head',
        f'{conflict_head}:refs/pull/9/head',
    )

    polaris = tmp_path / 'polaris'
    polaris.mkdir()
    git(polaris, 'init', '-q')
    git(
        polaris,
        'update-index',
        '--add',
        '--cacheinfo',
        f'160000,{pin},e3sm_submodules/Omega',
    )
    git(polaris, 'commit', '-q', '-m', 'Pin Omega')
    polaris_upstream = tmp_path / 'polaris.git'
    git(tmp_path, 'init', '-q', '--bare', str(polaris_upstream))
    git(polaris, 'push', '-q', str(polaris_upstream), 'HEAD:refs/heads/main')

    fork = tmp_path / 'fork.git'
    git(tmp_path, 'init', '-q', '--bare', str(fork))
    clone = tmp_path / 'clone'
    git(tmp_path, 'clone', '-q', str(upstream), str(clone))

    monkeypatch.setattr(pr_test_git, 'UPSTREAM_URL', str(upstream))
    monkeypatch.setattr(pr_test_init, 'POLARIS_URL', str(polaris_upstream))
    _mock_github(monkeypatch, pr_head)

    config = PrTestConfig(
        work_base=str(tmp_path / 'work'),
        omega_repo=str(clone),
        fork=str(fork),
    )
    return Fixture(
        config=config,
        polaris_dir=str(polaris),
        fork=str(fork),
        pin=pin,
        develop=develop,
        pr_head=pr_head,
        extra_head=extra_head,
        conflict_head=conflict_head,
    )


def test_init_pins_test_and_baseline(fixture):
    result = _initiate(fixture)
    manifest = result.manifest
    repo = fixture.config.omega_repo

    assert manifest.pr_head == fixture.pr_head
    assert manifest.base_head == fixture.develop
    assert manifest.baseline_commit == fixture.pin
    assert manifest.baseline_source == POLARIS_SUBMODULE
    assert manifest.requester == 'tester'
    assert manifest.rows == TEMPLATE_ROWS
    assert manifest.branch == f'omega-pr-test/5-{fixture.pr_head[:7]}'

    parents = git(repo, 'rev-parse', f'{manifest.test_commit}^@').split()
    assert parents == [fixture.develop, fixture.pr_head]
    assert git(repo, 'rev-parse', f'{result.manifest_commit}^') == (
        manifest.test_commit
    )
    committed = git(
        repo, 'show', f'{result.manifest_commit}:{MANIFEST_FILENAME}'
    )
    assert Manifest.from_yaml(committed) == manifest

    # nothing is pushed without --push, and the scratch worktrees are gone
    assert not result.pushed
    assert git(fixture.fork, 'branch', '--list') == ''
    assert git(repo, 'worktree', 'list').count('\n') == 0


def test_init_push(fixture):
    result = _initiate(fixture, push=True)
    manifest = result.manifest

    assert git(fixture.fork, 'rev-parse', manifest.branch) == (
        result.manifest_commit
    )
    assert git(fixture.fork, 'rev-parse', manifest.baseline_branch) == (
        fixture.pin
    )


def test_init_extra_merge(fixture):
    result = _initiate(fixture, merge_prs=[7])
    manifest = result.manifest
    repo = fixture.config.omega_repo

    parents = git(repo, 'rev-parse', f'{manifest.test_commit}^@').split()
    assert parents[1] == fixture.extra_head
    assert [
        (merge.pull_request, merge.commit, merge.sides)
        for merge in manifest.extra_merges
    ] == [(7, fixture.extra_head, ['test'])]
    assert manifest.baseline_commit == fixture.pin


def test_init_baseline_merge(fixture):
    result = _initiate(fixture, baseline_merge_prs=[7])
    manifest = result.manifest
    repo = fixture.config.omega_repo

    parents = git(repo, 'rev-parse', f'{manifest.baseline_commit}^@').split()
    assert parents == [fixture.pin, fixture.extra_head]
    assert manifest.extra_merges[0].sides == ['baseline']


def test_init_conflict(fixture):
    with pytest.raises(pr_test_init.InitError, match='does not merge'):
        _initiate(fixture, merge_prs=[9])


def test_init_other_baseline_needs_reason(fixture):
    with pytest.raises(pr_test_init.InitError, match='--reason'):
        _initiate(fixture, baseline_ref='develop')

    result = _initiate(
        fixture, baseline_ref='develop', reason='The pin is too old'
    )

    assert result.manifest.baseline_commit == fixture.develop
    assert result.manifest.baseline_source == 'develop'
    assert result.manifest.baseline_reason == 'The pin is too old'


def test_init_pr_moved(fixture, monkeypatch):
    _mock_github(monkeypatch, 'f' * 40)

    with pytest.raises(pr_test_init.InitError, match='moved'):
        _initiate(fixture)


def test_init_closed_pr(fixture, monkeypatch):
    _mock_github(monkeypatch, fixture.pr_head, state='MERGED')

    with pytest.raises(pr_test_init.InitError, match='merged, not open'):
        _initiate(fixture)


def test_get_row():
    assert get_row('chrysalis/intel').template == (
        'chrysalis, oneapi-ifx, openmpi'
    )
    assert get_row('chrysalis/intel').label == (
        'chrysalis, oneapi-ifx, openmpi (Polaris `intel`)'
    )
    assert get_row('pm-cpu/gnu').label == 'pm-cpu, gnu, mpich'
    extra = get_row('chrysalis/gnu')
    assert (extra.mpi, extra.template) == ('openmpi', None)
    with pytest.raises(ValueError, match='does not support'):
        get_row('chrysalis/nvidia')
    with pytest.raises(ValueError, match='<machine>/<compiler>'):
        get_row('chrysalis')


def test_template_rows_are_supported():
    for row in TEMPLATE_ROWS:
        mpi = pr_test_manifest._get_polaris_mpi(row.machine, row.compiler)
        assert mpi == row.mpi


def _initiate(fixture, **kwargs):
    return pr_test_init.initiate(
        config=fixture.config,
        pull_request=5,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )


def _mock_github(monkeypatch, head, state='OPEN'):
    def get_pull_request(number):
        return {
            'state': state,
            'isDraft': False,
            'title': 'Add c',
            'url': f'https://github.com/E3SM-Project/Omega/pull/{number}',
            'headRefOid': head,
            'baseRefName': 'develop',
        }

    monkeypatch.setattr(pr_test_github, 'get_pull_request', get_pull_request)
    monkeypatch.setattr(pr_test_github, 'get_user', lambda: 'tester')
