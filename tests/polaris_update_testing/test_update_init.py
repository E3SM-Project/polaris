import polaris_update_init
import pytest
from polaris_update_manifest import (
    MANIFEST_FILENAME,
    Manifest,
    fetch_manifest,
)
from pr_test_rows import Row
from update_fixtures import E3SM_PIN, git, make_fixture


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    return make_fixture(tmp_path, monkeypatch)


def test_init_pins_head_baseline_and_rows(fixture):
    result = _initiate(fixture, baseline_ref='main', push=True)

    manifest = result.manifest
    assert result.pushed
    assert manifest.requester == 'tester'
    assert manifest.pr_head == fixture.pr_head
    assert manifest.test.polaris_version == '1.2.0-alpha.1'
    assert manifest.test.omega_commit == fixture.new_pin
    assert manifest.test.e3sm_commit == E3SM_PIN
    assert manifest.baseline is not None
    assert manifest.baseline.polaris_commit == fixture.main
    assert manifest.baseline.polaris_version == '1.1.0-alpha.7'
    assert manifest.baseline.omega_commit == fixture.old_pin
    # the rows come from the PR's table, without the entry with no compiler
    assert [row.name for row in manifest.rows] == [
        'aurora/intel/omega',
        'chrysalis/gnu/mpas-ocean',
        'chrysalis/intel/omega',
        'chrysalis/gnu/omega',
        'pm-cpu/gnu/omega',
        'pm-gpu/gnugpu/omega',
    ]
    assert manifest.branch == f'polaris-update-test/835-{fixture.pr_head[:7]}'

    # the branch on the fork is the PR head with the manifest on top
    tip = git(fixture.fork, 'rev-parse', manifest.branch)
    assert git(fixture.fork, 'rev-parse', f'{tip}^') == fixture.pr_head
    text = git(fixture.fork, 'show', f'{tip}:{MANIFEST_FILENAME}')
    assert Manifest.from_yaml(text) == manifest
    assert fetch_manifest(
        fixture.polaris_dir, fixture.fork, manifest.branch
    ) == (manifest)

    assert result.prompt == (
        f'Test Polaris PR 835 from branch {manifest.branch} on '
        f'{fixture.fork}, following utils/polaris_update_testing/AGENTS.md.  '
        f'The baseline runs from a second checkout of main on '
        f'E3SM-Project/polaris.'
    )


def test_init_baseline_other_than_main(fixture):
    on_main = _initiate(fixture, baseline_ref='main', push=True).manifest

    # a commit, even main's, is a baseline other than main, such as an older
    # main for the rows that today's main cannot run
    result = _initiate(
        fixture,
        baseline_ref=fixture.main,
        row_names=['aurora/intel/omega'],
        push=True,
    )

    manifest = result.manifest
    suffix = f'-{fixture.main[:7]}'
    assert not manifest.baseline_is_main
    assert manifest.branch == f'{on_main.branch}{suffix}'
    assert manifest.run_name == f'{on_main.run_name}{suffix}'
    # both branches are on the fork
    assert fetch_manifest(
        fixture.polaris_dir, fixture.fork, on_main.branch
    ) == (on_main)
    assert fetch_manifest(
        fixture.polaris_dir, fixture.fork, manifest.branch
    ) == (manifest)
    assert result.prompt.endswith(
        f'The baseline runs from a second checkout of E3SM-Project/polaris '
        f'at {fixture.main[:12]}, not main.'
    )


def test_manifest_from_before_baseline_is_main(fixture):
    manifest = _initiate(fixture, baseline_ref='main').manifest
    text = manifest.to_yaml().replace('baseline_is_main: true\n', '')

    assert 'baseline_is_main' not in text
    assert Manifest.from_yaml(text) == manifest


def test_init_without_baseline(fixture):
    result = _initiate(fixture)

    assert result.manifest.baseline is None
    assert not result.pushed
    assert 'git push' in polaris_update_init.format_result(
        result, fixture.polaris_dir
    )
    assert 'second checkout' not in result.prompt


def test_init_rows(fixture):
    result = _initiate(
        fixture, row_names=['chrysalis/gnu/omega', 'pm-gpu/gnugpu/omega']
    )
    assert result.manifest.rows == [
        Row('chrysalis', 'gnu', 'openmpi', model='omega'),
        Row('pm-gpu', 'gnugpu', 'mpich', model='omega'),
    ]

    with pytest.raises(polaris_update_init.InitError, match='anvil/gnu'):
        _initiate(fixture, row_names=['anvil/gnu/omega'])


def test_init_leaves_an_equivalent_branch(fixture):
    first = _initiate(fixture, baseline_ref='main', push=True)

    second = _initiate(fixture, baseline_ref='main', push=True)

    assert second.existing
    assert not second.pushed
    assert second.manifest == first.manifest


def test_init_merges_omega_prs(fixture):
    result = _initiate(
        fixture, baseline_ref='main', merge_omega_prs=[600], push=True
    )

    merge = result.manifest.omega_merge
    assert merge is not None
    assert merge.pull_requests == {600: fixture.fix_head}
    assert merge.branch == f'{result.manifest.branch}-omega'
    assert result.manifest.omega_build_commit == merge.commit
    # the merge is of the fix into the Omega the PR pins, on the E3SM fork
    assert git(fixture.e3sm_fork, 'rev-parse', merge.branch) == merge.commit
    parents = git(fixture.e3sm_fork, 'rev-parse', f'{merge.commit}^@')
    assert parents.split() == [fixture.new_pin, fixture.fix_head]
    # the PR's pin is still what the checkouts are checked against
    assert result.manifest.test.omega_commit == fixture.new_pin
    assert fetch_manifest(
        fixture.polaris_dir, fixture.fork, result.manifest.branch
    ) == (result.manifest)
    assert 'with E3SM-Project/Omega#600 merged in' in (
        polaris_update_init.format_result(result, fixture.polaris_dir)
    )

    # remaking the merge changes its hash, but not what testers build
    again = _initiate(
        fixture, baseline_ref='main', merge_omega_prs=[600], push=True
    )
    assert again.existing
    assert again.manifest == result.manifest


def test_init_refuses_an_omega_pr_already_pinned(fixture):
    with pytest.raises(polaris_update_init.InitError, match='already in'):
        _initiate(fixture, merge_omega_prs=[601])


def test_init_refuses_a_baseline_with_the_pr(fixture):
    with pytest.raises(polaris_update_init.InitError, match='contains'):
        _initiate(fixture, baseline_ref=fixture.pr_head)


def _initiate(fixture, **kwargs):
    return polaris_update_init.initiate(
        config=fixture.config,
        pull_request=835,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )
