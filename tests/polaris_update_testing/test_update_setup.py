import subprocess
from pathlib import Path

import polaris_update_setup
import pr_test_setup
import pytest
from update_fixtures import (
    git,
    load_env,
    make_tester,
    write_load_script,
)


@pytest.fixture
def tester(tmp_path, monkeypatch):
    return make_tester(tmp_path, monkeypatch)


def test_setup_both_models(tester, tmp_path):
    fixture, manifest, calls = tester
    load_script = write_load_script(
        tmp_path / 'load_main.sh', fixture.baseline_dir
    )

    states = _setup(fixture, manifest, baseline_load_script=load_script)

    run_dir = Path(fixture.config.work_base) / manifest.run_name / 'shared'
    (mpas, mpas_dir), (omega, omega_dir) = states
    assert Path(mpas_dir) == run_dir / 'chrysalis_gnu_mpas-ocean'
    assert Path(omega_dir) == run_dir / 'chrysalis_gnu_omega'
    assert (mpas.row, mpas.suite, mpas.model) == (
        'chrysalis/gnu/mpas-ocean',
        'mpaso_pr',
        'mpas-ocean',
    )
    assert mpas.ctest_dir is None
    assert omega.ctest_dir == str(Path(omega_dir) / 'ctest')
    assert mpas.environment['spack'] == 'shared'
    assert [job['name'] for job in mpas.jobs] == ['baseline suite', 'PR suite']
    assert [job['name'] for job in omega.jobs] == [
        'baseline suite',
        'PR suite',
        'CTests',
    ]

    mpas_baseline, mpas_pr, omega_baseline, omega_pr = calls['suite']
    # MPAS-Ocean builds from each checkout's E3SM-Project submodule
    assert mpas_baseline['branch'] is None
    assert mpas_baseline['polaris_dir'] == fixture.baseline_dir
    assert mpas_baseline['load_script'] == load_script
    assert '_e3sm-eeeeeee' in mpas_baseline['work_dir']
    assert mpas_pr['branch'] is None
    assert mpas_pr['polaris_dir'] == fixture.polaris_dir
    assert mpas_pr['baseline_work_dir'] == mpas_baseline['work_dir']
    # Omega builds from worktrees of the pinned commits
    assert omega_baseline['branch'].endswith(fixture.old_pin[:12])
    assert omega_pr['branch'].endswith(fixture.new_pin[:12])
    assert git(omega_pr['branch'], 'rev-parse', 'HEAD') == fixture.new_pin


def test_setup_needs_the_baseline_load_script(tester):
    fixture, manifest, _ = tester
    with pytest.raises(
        pr_test_setup.SetupError, match='--baseline-load-script'
    ):
        _setup(fixture, manifest)


def test_setup_without_baseline(tester):
    fixture, manifest, calls = tester

    states = _setup(
        fixture, manifest, no_baseline='main cannot run', submit=True
    )

    assert all(call['baseline_work_dir'] is None for call in calls['suite'])
    assert [state.no_baseline_reason for state, _ in states] == [
        'main cannot run',
        'main cannot run',
    ]
    # nothing waits on a baseline
    assert all(dependency is None for _, _, dependency in calls['submit'])


def test_setup_manifest_without_baseline(tmp_path, monkeypatch):
    fixture, manifest, calls = make_tester(
        tmp_path, monkeypatch, baseline=None
    )

    states = _setup(fixture, manifest)

    assert len(calls['suite']) == 2
    assert all(state.baseline_work_dir is None for state, _ in states)


def test_setup_baseline_with_former_compiler(tester, tmp_path, monkeypatch):
    fixture, manifest, calls = tester
    load_env(monkeypatch, fixture, 'aurora', 'intel', 'mpich')
    load_script = write_load_script(
        tmp_path / 'load_main_aurora.sh',
        fixture.baseline_dir,
        machine='aurora',
        compiler='oneapi-ifx',
        mpi='mpich',
    )

    ((state, _),) = _setup(fixture, manifest, baseline_load_script=load_script)

    assert state.row == 'aurora/intel/omega'
    assert '/aurora_oneapi-ifx_polaris-' in state.baseline_work_dir


def test_setup_checks_the_pins(tester, tmp_path):
    fixture, manifest, _ = tester
    git(
        fixture.polaris_dir,
        'update-index',
        '--cacheinfo',
        f'160000,{fixture.old_pin},e3sm_submodules/Omega',
    )
    git(fixture.polaris_dir, 'commit', '-q', '-m', 'Pin the old Omega')

    with pytest.raises(pr_test_setup.SetupError, match='pins'):
        _setup(fixture, manifest, no_baseline='main cannot run')


def test_setup_baseline_checkout_has_the_pr(tester, tmp_path):
    fixture, manifest, _ = tester
    load_script = write_load_script(
        tmp_path / 'load_pr.sh', fixture.polaris_dir
    )
    with pytest.raises(pr_test_setup.SetupError, match='contains the PR'):
        _setup(fixture, manifest, baseline_load_script=load_script)


def test_setup_wrong_environment(tester, monkeypatch):
    fixture, manifest, _ = tester
    load_env(monkeypatch, fixture, 'chrysalis', 'intel-classic', 'openmpi')
    with pytest.raises(pr_test_setup.SetupError, match='no row for'):
        _setup(fixture, manifest, no_baseline='main cannot run')

    load_env(monkeypatch, fixture, 'chrysalis', 'gnu', 'openmpi', view='')
    with pytest.raises(pr_test_setup.SetupError, match='no Spack'):
        _setup(fixture, manifest, no_baseline='main cannot run')


def test_mpas_ocean_builds_take_turns(tmp_path, monkeypatch):
    calls = []
    original = subprocess.run

    def run(args, *other, **kwargs):
        if args[0] != 'polaris':
            return original(args, *other, **kwargs)
        calls.append(args)

    monkeypatch.setattr(subprocess, 'run', run)
    tree = tmp_path / 'polaris' / 'e3sm_submodules' / 'E3SM-Project'
    tree.mkdir(parents=True)

    _mpas_ocean_suite(tmp_path)

    (args,) = calls
    assert '--branch' not in args
    assert args[:7] == [
        'polaris',
        'suite',
        '-c',
        'ocean',
        '-t',
        'mpaso_pr',
        '--model',
    ]

    # another setup building in the same tree
    Path(f'{tree}.lock').mkdir()
    monkeypatch.setattr(pr_test_setup, 'TREE_LOCK_TIMEOUT', 0)
    monkeypatch.setattr(pr_test_setup.time, 'sleep', lambda seconds: None)
    with pytest.raises(pr_test_setup.SetupError, match='using'):
        _mpas_ocean_suite(tmp_path)


def _mpas_ocean_suite(tmp_path):
    """Set up mpaso_pr from a checkout's E3SM-Project submodule"""
    pr_test_setup.polaris_suite(
        str(tmp_path / 'polaris'),
        suite='mpaso_pr',
        model='mpas-ocean',
        branch=None,
        build_dir=str(tmp_path / 'build'),
        work_dir=str(tmp_path / 'work'),
    )


def _setup(fixture, manifest, **kwargs):
    return polaris_update_setup.run_setup(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )
