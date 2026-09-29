import pr_test_init
import pr_test_manifest
import pytest
from pr_test_fixtures import git, make_fixture, mock_github
from pr_test_manifest import (
    MANIFEST_FILENAME,
    POLARIS_SUBMODULE,
    TEMPLATE_ROWS,
    Manifest,
    get_row,
)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    return make_fixture(tmp_path, monkeypatch)


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
    mock_github(monkeypatch, 'f' * 40)

    with pytest.raises(pr_test_init.InitError, match='moved'):
        _initiate(fixture)


def test_init_closed_pr(fixture, monkeypatch):
    mock_github(monkeypatch, fixture.pr_head, state='MERGED')

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
