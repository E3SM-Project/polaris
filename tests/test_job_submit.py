import subprocess

import pytest

from polaris import job
from polaris.job import (
    get_submit_args,
    is_job_active,
    parse_job_id,
    submit_job,
)


def test_submit_args_slurm():
    assert get_submit_args('job.sh', 'slurm') == ['sbatch', 'job.sh']
    assert get_submit_args('job.sh', 'slurm', dependency='123') == [
        'sbatch',
        '--dependency=afterany:123',
        '--kill-on-invalid-dep=yes',
        'job.sh',
    ]


def test_submit_args_pbs():
    assert get_submit_args('job.sh', 'pbs') == ['qsub', 'job.sh']
    assert get_submit_args('job.sh', 'pbs', dependency='45.aurora') == [
        'qsub',
        '-W',
        'depend=afterany:45.aurora',
        'job.sh',
    ]


def test_submit_args_unsupported_system():
    with pytest.raises(ValueError, match='Unsupported parallel system'):
        get_submit_args('job.sh', 'single_node')


def test_parse_job_id():
    assert parse_job_id('Submitted batch job 1297234\n', 'slurm') == '1297234'
    output = 'some banner\n8012345.aurora-pbs-0001.hostmgmt.cm.aurora\n'
    assert parse_job_id(output, 'pbs') == (
        '8012345.aurora-pbs-0001.hostmgmt.cm.aurora'
    )
    with pytest.raises(ValueError, match='Could not determine'):
        parse_job_id('sbatch: error: invalid account\n', 'slurm')


def test_submit_job_runs_in_work_dir(tmp_path, monkeypatch):
    calls = []

    def check_output(args, cwd):
        calls.append((args, cwd))
        return b'Submitted batch job 42\n'

    monkeypatch.setattr(job.subprocess, 'check_output', check_output)

    job_id = submit_job('job.sh', str(tmp_path), 'slurm', dependency='41')

    assert job_id == '42'
    assert calls == [
        (
            [
                'sbatch',
                '--dependency=afterany:41',
                '--kill-on-invalid-dep=yes',
                'job.sh',
            ],
            str(tmp_path),
        )
    ]


@pytest.mark.parametrize(
    'returncode, stdout, active',
    [(0, 'RUNNING\n', True), (0, '', False), (1, '', False)],
)
def test_is_job_active(monkeypatch, returncode, stdout, active):
    def run(args, capture_output, text):
        return subprocess.CompletedProcess(args, returncode, stdout, '')

    monkeypatch.setattr(job.subprocess, 'run', run)

    assert is_job_active('42', 'slurm') is active
    assert is_job_active('42.aurora', 'pbs') is active
