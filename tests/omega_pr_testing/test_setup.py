import json
import os
from pathlib import Path

import pr_test_init
import pr_test_setup
import pytest
from pr_test_fixtures import commit, git, make_fixture
from pr_test_manifest import ManifestError


@pytest.fixture
def tester(tmp_path, monkeypatch):
    """
    A pushed test branch, a loaded chrysalis/intel environment, and stand-ins
    for polaris suite, the CTest utility and the scheduler
    """
    fixture = make_fixture(tmp_path, monkeypatch)
    manifest = pr_test_init.initiate(
        config=fixture.config,
        pull_request=5,
        polaris_dir=fixture.polaris_dir,
        push=True,
    ).manifest
    monkeypatch.setenv('POLARIS_MACHINE', 'chrysalis')
    monkeypatch.setenv('POLARIS_COMPILER', 'intel')
    monkeypatch.setenv('POLARIS_MPI', 'openmpi')
    monkeypatch.setenv('POLARIS_BRANCH', fixture.polaris_dir)

    calls: dict[str, list] = {'suite': [], 'submit': []}
    monkeypatch.setattr(
        pr_test_setup, '_polaris_suite', _fake_polaris_suite(calls, fixture)
    )
    monkeypatch.setattr(pr_test_setup, '_set_up_ctests', _fake_ctests)
    monkeypatch.setattr(pr_test_setup, '_get_system', lambda machine: 'slurm')

    def submit_job(script, work_dir, system, dependency=None):
        calls['submit'].append((work_dir, script, dependency))
        return str(1000 + len(calls['submit']))

    monkeypatch.setattr(pr_test_setup, 'submit_job', submit_job)
    monkeypatch.setattr(
        pr_test_setup, 'is_job_active', lambda job_id, system: False
    )
    return fixture, manifest, calls


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
    existing = _make_complete_baseline(
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


def _fake_polaris_suite(calls, fixture):
    def polaris_suite(
        polaris_dir, branch, build_dir, work_dir, baseline_work_dir=None
    ):
        calls['suite'].append(
            {
                'branch': branch,
                'build_dir': build_dir,
                'work_dir': work_dir,
                'baseline_work_dir': baseline_work_dir,
            }
        )
        omega_hash = git(branch, 'rev-parse', 'HEAD')
        polaris_hash = git(polaris_dir, 'rev-parse', 'HEAD')
        _make_build(Path(build_dir), omega_hash)
        _make_run(Path(work_dir), Path(build_dir), omega_hash, polaris_hash)

    return polaris_suite


def _fake_ctests(polaris_dir, row, build_dir, ctest_dir):
    os.makedirs(ctest_dir, exist_ok=True)
    return pr_test_setup.Job(
        name='CTests',
        work_dir=ctest_dir,
        script='build_omega/job_build_and_ctest_omega_chrysalis_intel.sh',
    )


def _make_complete_baseline(work_dir, manifest, polaris_hash):
    build_dir = work_dir.parent / 'build'
    _make_build(build_dir, manifest.baseline_commit)
    _make_run(work_dir, build_dir, manifest.baseline_commit, polaris_hash)
    (work_dir / 'omega_pr_results.json').write_text(
        json.dumps({'complete': True, 'summary': {'failed': 0, 'pending': 0}})
    )
    return work_dir


def _make_build(build_dir, omega_hash):
    (build_dir / 'src').mkdir(parents=True, exist_ok=True)
    (build_dir / 'src' / 'omega.exe').write_bytes(b'')
    (build_dir / 'build_omega.log').write_text('')
    (build_dir / 'CMakeCache.txt').write_text(
        'OMEGA_BUILD_TYPE:UNINITIALIZED=Release\n'
        'OMEGA_CIME_COMPILER:UNINITIALIZED=intel\n'
        'OMEGA_CIME_MACHINE:UNINITIALIZED=chrysalis\n'
    )
    (build_dir / 'omega_source.txt').write_text(
        f'hash: {omega_hash}\ndescribe: omega\nclean_build: true\nlog:\n'
    )


def _make_run(work_dir, build_dir, omega_hash, polaris_hash):
    work_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        'polaris git version: polaris',
        f'polaris git hash: {polaris_hash}',
        'component git version: omega',
        f'component git hash: {omega_hash}',
        f'command: polaris suite -c ocean -t omega_pr -w {work_dir}',
        'machine: chrysalis',
        'compiler: intel',
        f'build directory: {build_dir}',
        'build type: Release',
        'tasks:',
    ]
    (work_dir / 'provenance').write_text('\n\n'.join(lines) + '\n')
    (work_dir / 'omega_pr.pickle').write_bytes(b'')
    (work_dir / 'job_script.omega_pr.sh').write_text('#!/bin/bash\n')
