import json
import os
import subprocess
from pathlib import Path

import pr_test_init
import pr_test_setup
import pytest
from pr_test_fixtures import commit, git, make_complete_baseline, make_tester
from pr_test_manifest import ManifestError


@pytest.fixture
def tester(tmp_path, monkeypatch):
    return make_tester(tmp_path, monkeypatch)


@pytest.fixture
def separate(tester, tmp_path):
    """
    A manifest whose baseline runs from a second Polaris checkout, without
    the Polaris changes the PR needs
    """
    fixture, _, calls = tester
    baseline_polaris = tmp_path / 'baseline_polaris'
    git(tmp_path, 'clone', '-q', fixture.polaris_dir, str(baseline_polaris))
    baseline_hash = git(baseline_polaris, 'rev-parse', 'HEAD')
    commit(fixture.polaris_dir, 'stop.txt', 'StopType\n', 'Follow the PR')
    fixture.config.polaris_fork = 'polaris-fork'
    manifest = pr_test_init.initiate(
        config=fixture.config,
        pull_request=5,
        polaris_dir=fixture.polaris_dir,
        polaris_ref='HEAD',
        baseline_polaris_ref=baseline_hash,
        push=True,
        force=True,
    ).manifest
    load_script = _write_load_script(
        tmp_path / 'load_polaris_chrysalis_intel_openmpi.sh', baseline_polaris
    )
    return fixture, manifest, calls, baseline_polaris, load_script


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
    assert text.count('-q capacity') == 3

    _setup(fixture, manifest, submit=True)
    # each job waits for the one before, so only one is ever queued
    dependencies = [call[2] for call in calls['submit']]
    assert dependencies == [None, '1001', '1002']
    assert calls['extra_args'] == [['-q', 'capacity']] * 3


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


def test_setup_baseline_from_second_checkout(separate):
    fixture, manifest, calls, baseline_polaris, load_script = separate
    baseline_hash = manifest.baseline_polaris_commit

    state = _setup(fixture, manifest, baseline_load_script=load_script)

    baseline_call, pr_call = calls['suite']
    assert baseline_call['polaris_dir'] == str(baseline_polaris)
    assert baseline_call['load_script'] == load_script
    assert pr_call['polaris_dir'] == fixture.polaris_dir
    assert pr_call['load_script'] is None
    assert f'polaris-{baseline_hash[:7]}_omega' in state.baseline_work_dir
    assert state.polaris_hash == manifest.polaris_commit
    assert state.baseline_polaris_hash == baseline_hash
    row_dir = Path(state.pr_work_dir).parent
    text = pr_test_setup.format_state(state, str(row_dir), 'chrysalis')
    assert f'{baseline_hash} (baseline)' in text


def test_setup_reuses_baseline_from_second_checkout(separate, tmp_path):
    fixture, manifest, calls, _, load_script = separate
    existing = make_complete_baseline(
        tmp_path / 'old_tests' / 'baseline',
        manifest,
        manifest.baseline_polaris_commit,
    )
    fixture.config.baseline_search_roots = [str(tmp_path / 'old_tests')]

    state = _setup(fixture, manifest, baseline_load_script=load_script)

    assert state.baseline_work_dir == str(existing)
    assert len(calls['suite']) == 1


def test_setup_needs_baseline_load_script(separate):
    fixture, manifest, _, _, _ = separate
    with pytest.raises(
        pr_test_setup.SetupError, match='--baseline-load-script'
    ):
        _setup(fixture, manifest)


def test_setup_baseline_checkout_has_pr_polaris(separate, tmp_path):
    fixture, manifest, _, _, _ = separate
    load_script = _write_load_script(
        tmp_path / 'load_pr.sh', Path(fixture.polaris_dir)
    )
    with pytest.raises(pr_test_setup.SetupError, match='baseline Omega'):
        _setup(fixture, manifest, baseline_load_script=load_script)


def test_setup_baseline_load_script_wrong_row(separate, tmp_path):
    fixture, manifest, _, baseline_polaris, _ = separate
    load_script = _write_load_script(
        tmp_path / 'load_gnu.sh', baseline_polaris, compiler='gnu'
    )
    with pytest.raises(pr_test_setup.SetupError, match='POLARIS_COMPILER'):
        _setup(fixture, manifest, baseline_load_script=load_script)


def test_polaris_suite_in_clean_login_shell(tmp_path, monkeypatch):
    calls = []

    def run(args, cwd, env, check):
        calls.append((args, cwd, env))

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setenv('POLARIS_BRANCH', '/pr/polaris')
    build_dir = str(tmp_path / 'build')

    pr_test_setup._polaris_suite(
        '/baseline/polaris',
        branch='/omega/tree',
        build_dir=build_dir,
        work_dir='/work',
        load_script='/baseline/polaris/load.sh',
    )
    pr_test_setup._polaris_suite(
        '/pr/polaris', branch='/omega/tree', build_dir=build_dir, work_dir='/w'
    )

    (args, cwd, env), (pr_args, _, pr_env) = calls
    assert args[:3] == ['/bin/bash', '-l', '-c']
    assert args[3].startswith(
        'source /baseline/polaris/load.sh && cd /baseline/polaris && '
        'polaris suite -c ocean -t omega_pr --model omega --build'
    )
    assert cwd == '/baseline/polaris'
    # nothing of the loaded environment reaches the baseline's setup
    assert set(env) <= set(pr_test_setup.LOGIN_ENV_VARS)
    assert pr_args[0] == 'polaris'
    assert pr_env is None


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


def _write_load_script(path, polaris_dir, compiler='intel'):
    """The exports of a load script for a checkout"""
    path.write_text(
        f'export POLARIS_MACHINE="chrysalis"\n'
        f'export POLARIS_BRANCH="{polaris_dir}"\n'
        f'export POLARIS_COMPILER="{compiler}"\n'
        f'export POLARIS_MPI="openmpi"\n'
    )
    return os.path.abspath(path)
