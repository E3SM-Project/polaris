import json
from pathlib import Path

import pr_test_setup
import pytest
from pr_test_fixtures import commit, git, make_complete_baseline, make_tester
from pr_test_manifest import ManifestError


@pytest.fixture
def tester(tmp_path, monkeypatch):
    return make_tester(tmp_path, monkeypatch)


def test_setup_new_baseline(tester):
    fixture, manifest, calls = tester

    state = _setup(fixture, manifest)

    work_base = Path(fixture.config.work_base)
    baseline = (
        work_base
        / 'baselines'
        / f'chrysalis_intel_polaris-{manifest.polaris_commit[:7]}'
        f'_omega-{manifest.baseline_commit[:7]}' / 'omega_pr'
    )
    row_dir = work_base / manifest.run_name / 'chrysalis_intel'
    assert state.baseline_work_dir == str(baseline)
    assert not state.baseline_reused
    assert state.pr_work_dir == str(row_dir / 'omega_pr')
    assert state.baseline_build_log == str(
        baseline.parent / 'build' / 'build_omega.log'
    )

    # the baseline is set up before the PR suite, each from its own tree
    (baseline_call, pr_call) = calls['suite']
    assert baseline_call['branch'].endswith(manifest.baseline_commit[:12])
    assert pr_call['branch'].endswith(manifest.test_commit[:12])
    assert pr_call['baseline_work_dir'] == str(baseline)
    assert git(baseline_call['branch'], 'rev-parse', 'HEAD') == (
        manifest.baseline_commit
    )

    assert calls['submit'] == []
    assert [job['name'] for job in state.jobs] == [
        'baseline suite',
        'PR suite',
        'CTests',
    ]
    text = pr_test_setup.format_state(state, str(row_dir), 'chrysalis')
    assert 'Nothing was submitted' in text
    assert (
        f'cd {row_dir / "omega_pr"} && sbatch '
        "'--dependency=afterany:<baseline job id>' "
        '--kill-on-invalid-dep=yes job_script.omega_pr.sh'
    ) in text

    saved = json.loads((row_dir / 'setup.json').read_text())
    assert saved['baseline_work_dir'] == str(baseline)


def test_setup_submit(tester):
    fixture, manifest, calls = tester

    state = _setup(fixture, manifest, submit=True)

    baseline_submit, pr_submit, ctest_submit = calls['submit']
    assert baseline_submit[2] is None
    assert pr_submit[2] == '1001'
    assert ctest_submit[2] is None
    assert [job['job_id'] for job in state.jobs] == ['1001', '1002', '1003']
    assert (Path(state.pr_work_dir) / 'job_id').read_text() == '1002\n'


def test_setup_reuses_matching_baseline(tester, tmp_path):
    fixture, manifest, calls = tester
    polaris_hash = git(fixture.polaris_dir, 'rev-parse', 'HEAD')
    existing = make_complete_baseline(
        tmp_path / 'old_tests' / 'baseline', manifest, polaris_hash
    )
    fixture.config.baseline_search_roots = [str(tmp_path / 'old_tests')]

    state = _setup(fixture, manifest, submit=True)

    assert state.baseline_work_dir == str(existing)
    assert state.baseline_reused
    assert [call['branch'] for call in calls['suite']] == [
        str(
            Path(fixture.config.work_base)
            / 'omega'
            / manifest.test_commit[:12]
        )
    ]
    # the PR suite does not wait on anything
    assert calls['submit'][0][2] is None


def test_setup_waits_on_running_baseline(tester, monkeypatch):
    fixture, manifest, calls = tester
    _setup(fixture, manifest, submit=True)
    baseline_dir = Path(calls['submit'][0][0])
    monkeypatch.setattr(
        pr_test_setup, 'is_job_active', lambda job_id, system: True
    )
    # a second PR tested against the same baseline while it is running
    row_dir = Path(fixture.config.work_base) / manifest.run_name
    for path in sorted(row_dir.rglob('*'), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()

    state = _setup(fixture, manifest, submit=True)

    assert state.baseline_work_dir == str(baseline_dir)
    assert state.baseline_job == '1001'
    assert calls['submit'][3][2] == '1001'


def test_setup_frontier_avoids_debug_qos(tester, monkeypatch):
    fixture, manifest, calls = tester
    monkeypatch.setenv('POLARIS_MACHINE', 'frontier')
    monkeypatch.setenv('POLARIS_COMPILER', 'craygnu')
    monkeypatch.setenv('POLARIS_MPI', 'mpich')

    state = _setup(fixture, manifest)
    row_dir = Path(state.pr_work_dir).parent
    text = pr_test_setup.format_state(state, str(row_dir), 'frontier')
    assert text.count('--qos=normal') == 3

    _setup(fixture, manifest, submit=True)
    assert calls['extra_args'] == [['--qos=normal']] * 3


def test_setup_aurora_chains_jobs(tester, monkeypatch):
    fixture, manifest, calls = tester
    monkeypatch.setenv('POLARIS_MACHINE', 'aurora')
    monkeypatch.setenv('POLARIS_COMPILER', 'oneapi-ifx')
    monkeypatch.setenv('POLARIS_MPI', 'mpich')
    monkeypatch.setattr(pr_test_setup, '_get_system', lambda machine: 'pbs')

    state = _setup(fixture, manifest)
    row_dir = Path(state.pr_work_dir).parent
    text = pr_test_setup.format_state(state, str(row_dir), 'aurora')
    assert "-W 'depend=afterany:<baseline job id>'" in text
    assert "-W 'depend=afterany:<PR suite job id>'" in text

    _setup(fixture, manifest, submit=True)
    # each job waits for the one before, so only one is ever queued
    dependencies = [call[2] for call in calls['submit']]
    assert dependencies == [None, '1001', '1002']


def test_setup_pin_mismatch(tester):
    fixture, manifest, _ = tester
    git(
        fixture.polaris_dir,
        'update-index',
        '--cacheinfo',
        f'160000,{fixture.develop},e3sm_submodules/Omega',
    )
    git(fixture.polaris_dir, 'commit', '-q', '-m', 'Update Omega')

    with pytest.raises(pr_test_setup.SetupError, match='pins Omega'):
        _setup(fixture, manifest)


def test_setup_dirty_polaris(tester):
    fixture, manifest, _ = tester
    commit(fixture.polaris_dir, 'README.md', 'Polaris\n', 'Add a README')
    Path(fixture.polaris_dir, 'README.md').write_text('changed\n')

    with pytest.raises(pr_test_setup.SetupError, match='uncommitted'):
        _setup(fixture, manifest)


def test_setup_wrong_environment(tester, monkeypatch):
    fixture, manifest, _ = tester
    monkeypatch.setenv('POLARIS_COMPILER', 'gnu')
    with pytest.raises(ManifestError, match='no row for chrysalis/gnu'):
        _setup(fixture, manifest)

    monkeypatch.setenv('POLARIS_COMPILER', 'intel')
    monkeypatch.setenv('POLARIS_BRANCH', '/some/other/polaris')
    with pytest.raises(pr_test_setup.SetupError, match='belongs to'):
        _setup(fixture, manifest)


def test_setup_refuses_a_row_that_ran(tester):
    fixture, manifest, _ = tester
    state = _setup(fixture, manifest)
    Path(state.pr_work_dir, 'omega_pr_results.json').write_text('{}')

    with pytest.raises(pr_test_setup.SetupError, match='already run'):
        _setup(fixture, manifest)


def _setup(fixture, manifest, **kwargs):
    return pr_test_setup.run_setup(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )
