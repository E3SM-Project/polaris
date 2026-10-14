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
