import argparse

import common
import pytest


@pytest.mark.parametrize(
    'machine, qos, constraint',
    [('pm-cpu', 'debug', 'cpu'), ('pm-gpu', 'debug', 'gpu')],
)
def test_build_job_script(tmp_path, monkeypatch, machine, qos, constraint):
    submitted = []
    monkeypatch.setattr(
        common,
        'submit_and_wait',
        lambda job_script, config: submitted.append(job_script),
    )
    (tmp_path / 'omega_cdash_gnu.o123').write_text('last night\n')
    args = argparse.Namespace(
        build_in_job=True, machine=machine, account='e3sm'
    )
    command = ['/path/to/omega_ctest.py', '--cdash_build_name', 'a b']

    common.run_omega_ctest(command, str(tmp_path), args, 'omega_cdash_gnu')

    job_script = tmp_path / 'omega_cdash_gnu.sh'
    assert submitted == [str(job_script)]
    text = job_script.read_text()
    assert '#SBATCH --nodes=1\n' in text
    assert '#SBATCH --time=0:30:00\n' in text
    assert f'#SBATCH --qos={qos}\n' in text
    assert f'#SBATCH --constraint={constraint}\n' in text
    assert '#SBATCH --account=e3sm\n' in text
    assert '#SBATCH --output=omega_cdash_gnu.o%j\n' in text
    assert text.rstrip().endswith(
        "/path/to/omega_ctest.py --cdash_build_name 'a b'"
    )
    # an earlier night's output is not taken for this one's
    assert not (tmp_path / 'omega_cdash_gnu.o123').exists()


def test_build_here_without_build_in_job(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(
        common, 'run', lambda command, cwd=None: ran.append((command, cwd))
    )
    args = argparse.Namespace(build_in_job=False)

    common.run_omega_ctest(['omega_ctest.py'], str(tmp_path), args, 'job')

    assert ran == [(['omega_ctest.py'], str(tmp_path))]
    assert not (tmp_path / 'job.sh').exists()
