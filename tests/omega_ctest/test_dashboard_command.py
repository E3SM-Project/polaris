import importlib.util
import subprocess
from pathlib import Path

UTILITY = (
    Path(__file__).resolve().parents[2]
    / 'utils'
    / 'omega'
    / 'ctest'
    / 'omega_ctest.py'
)


def test_build_stage_passes_submit(tmp_path):
    omega_ctest = _load_utility()
    for submit, flag in [(True, 'ON'), (False, 'OFF')]:
        command = omega_ctest.dashboard_ctest_command(
            stage='build',
            branch=str(tmp_path),
            build_dir=str(tmp_path / 'build'),
            dashboard=_dashboard(omega_ctest, submit),
            build_command='./omega_build_jobs.sh',
        )
        assert f'-DSUBMIT={flag}' in command
        assert '-DCTEST_BUILD_COMMAND=./omega_build_jobs.sh' in command


def test_submit_stage_has_no_submit_flag(tmp_path):
    omega_ctest = _load_utility()
    command = omega_ctest.dashboard_ctest_command(
        stage='submit',
        branch=str(tmp_path),
        build_dir=str(tmp_path / 'build'),
        dashboard=_dashboard(omega_ctest, True),
    )
    assert '-DSUBMIT' not in command


def test_run_script_runs_ctests_in_place(tmp_path, monkeypatch):
    omega_ctest = _load_utility()
    monkeypatch.chdir(tmp_path)
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    ctest_script = build_dir / 'omega_ctest.sh'
    ctest_script.write_text(
        '#!/bin/bash\necho "100% tests passed, 0 tests failed out of 1"\n',
        encoding='utf-8',
    )
    ctest_script.chmod(0o755)

    run_script = omega_ctest.write_omega_ctest_run_script(
        machine='pm-cpu',
        compiler='gnu',
        build_dir=str(build_dir),
        debug=False,
        ctest_command='./omega_ctest.sh',
    )

    assert Path(run_script) == (
        tmp_path / 'build_omega' / 'ctest_omega_pm-cpu_gnu.sh'
    )
    subprocess.run(['bash', run_script], check=True, capture_output=True)
    summary = (build_dir / 'ctest_output_for_pr.md').read_text('utf-8')
    assert '- Machine: `pm-cpu`' in summary
    assert '- Result: All tests passed' in summary


def _dashboard(omega_ctest, submit):
    return omega_ctest.DashboardOptions(
        site='pm-cpu',
        build_name='unitest-develop-gnu',
        model='Nightly',
        submit_url=omega_ctest.CDASH_SUBMIT_URL,
        submit=submit,
    )


def _load_utility():
    spec = importlib.util.spec_from_file_location('omega_ctest', UTILITY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
